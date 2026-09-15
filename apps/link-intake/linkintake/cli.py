"""linkintake CLI. Every command supports --json so Raycast / Claude / Codex can drive it."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import sys
from pathlib import Path

from . import config, pipeline, store
from .records import DESTINATIONS


def _out(obj, as_json: bool) -> None:
    if as_json:
        print(json.dumps(obj, ensure_ascii=False))
    else:
        print(_summary(obj) if isinstance(obj, dict) and "source" in obj else json.dumps(obj, indent=2, ensure_ascii=False))


def _summary(rec: dict) -> str:
    s, i, e, c = rec["source"], rec["intent"], rec["extraction"], rec["context"]
    lines = [
        f"[{rec['status'].upper()}] {rec['id']}  conf={e.get('confidence', 0):.2f}  backend={rec['processing'].get('llm_backend', '')}",
        f"Source:      {s['platform']} / {s['source_class']}  {s['original_url']}",
        f"Title:       {s.get('title', '')}  by {s.get('creator', '')}",
        f"Destination: {DESTINATIONS[i['destination']]}",
        f"Instruction: {i['user_instruction']}",
        f"Summary:     {c.get('short_source_summary', '')}",
    ]
    for t in e.get("takeaways") or []:
        lines.append(f"  • {t}")
    lines.append(f"Details:     {e.get('focused_result', '')}")
    if e.get("uncertainty"):
        lines.append(f"Uncertain:   {e['uncertainty']}")
    if rec.get("artifacts", {}).get("frames"):
        lines.append("Frames:      " + "  ".join(f"{f['t'] or '?'}" for f in rec["artifacts"]["frames"]))
    if e.get("structured_data"):
        lines.append("Fields:      " + "; ".join(f"{k}={v}" for k, v in e["structured_data"].items() if v))
    if rec.get("artifacts", {}).get("contact_sheet"):
        lines.append(f"Preview:     {rec['artifacts']['contact_sheet']}")
    if rec.get("exact_duplicate"):
        lines.append(f"DUPLICATE of {rec['exact_duplicate']} (same URL+destination+instruction)")
    elif rec.get("duplicate_of"):
        lines.append(f"Same source already saved as: {', '.join(rec['duplicate_of'])} (different intent; OK)")
    ex = rec.get("export", {})
    if ex.get("status") == "export_pending":
        lines.append("Export:      pending (saved locally; run `linkintake exports` and let Claude export via its Drive connector)")
    for k in ("master", "destination"):
        if ex.get(k):
            v = ex[k]
            lines.append(f"Export {k}: {'OK ' + v.get('url', '') if v.get('ok') else 'FAILED ' + v.get('error', '')}")
    for err in rec.get("errors", []):
        lines.append(f"! {err}")
    return "\n".join(lines)


def cmd_ingest(a) -> int:
    try:
        rec = pipeline.ingest(a.url, a.dest, a.instruction, save=a.save, force=a.force, refresh=a.refresh)
    except pipeline.DuplicateError as exc:
        _out({"error": str(exc), "duplicate": True}, a.json)
        return 3
    _out(rec, a.json)
    return 0 if rec["status"] != "failed" else 1


def cmd_save(a) -> int:
    try:
        rec = pipeline.save_record(a.id, force=a.force)
    except pipeline.DuplicateError as exc:
        _out({"error": str(exc), "duplicate": True}, a.json)
        return 3
    _out(rec, a.json)
    return 0


def cmd_reprocess(a) -> int:
    rec = pipeline.reprocess(a.id, instruction=a.instruction, destination=a.dest, refresh=a.refresh)
    _out(rec, a.json)
    return 0


def cmd_show(a) -> int:
    _out(store.load(a.id), a.json)
    return 0


def cmd_exports(a) -> int:
    """Records saved locally but not yet in Google. Claude reads this and exports via its Drive connector."""
    from .destinations import export_payload
    rows = [export_payload(r) for r in store.pending_exports()]
    if a.json:
        print(json.dumps(rows, ensure_ascii=False))
    elif not rows:
        print("(nothing pending export)")
    else:
        for r in rows:
            print(f"{r['record_id']}  -> {r['destination']}  [{r['destination_target']}]\n{r['entry_block']}")
    return 0


def cmd_mark_exported(a) -> int:
    _out(pipeline.mark_exported(a.id, a.master_url or "", a.destination_url or "", a.note or ""), a.json)
    return 0


def cmd_export(a) -> int:
    _out(pipeline.export_rest(a.id), a.json)
    return 0


def cmd_list(a) -> int:
    rows = store.recent(a.limit)
    _out(rows, a.json) if a.json else print("\n".join(store.describe(r) for r in rows) or "(no saved records)")
    return 0


def cmd_batch(a) -> int:
    """File lines: URL | destination | instruction   (# comments allowed)."""
    rc = 0
    for line in open(a.file):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 3:
            print(f"skip (need url | destination | instruction): {line}", file=sys.stderr)
            continue
        url, dest, instr = parts[0], parts[1], " | ".join(parts[2:])
        try:
            rec = pipeline.ingest(url, dest, instr, save=a.save, force=a.force)
            print(_summary(rec) + "\n")
            rc |= rec["status"] == "failed"
        except Exception as exc:
            print(f"FAILED {url}: {exc}\n")
            rc = 1
    return rc


def cmd_doctor(a) -> int:
    cfg = config.load()
    ok = True

    def row(label, good, detail=""):
        nonlocal ok
        ok &= bool(good)
        print(f"{'ok  ' if good else 'MISS'} {label}: {detail}")

    for b in ("uv", "ffmpeg", "yt-dlp"):
        row(b, shutil.which(b), shutil.which(b) or "not on PATH")
    try:
        host, port = cfg["media_unlocker"]["mcp_url"].split("//")[1].split("/")[0].split(":")
        with socket.create_connection((host, int(port)), timeout=2):
            row("media-unlocker", True, cfg["media_unlocker"]["mcp_url"])
    except Exception:
        row("media-unlocker", False, "not reachable; run `mediaunlock start`")
    from . import __version__
    from .extract import choose_backend, resolve_claude, claude_env
    import linkintake
    print(f"     linkintake {__version__} source: {Path(linkintake.__file__).resolve().parent}")
    print(f"     claude binary: {resolve_claude(cfg)} -> {Path(resolve_claude(cfg)).resolve() if Path(resolve_claude(cfg)).exists() else '?'}")
    print(f"     claude profile: {claude_env(cfg)['CLAUDE_CONFIG_DIR']}")
    print(f"     last claude call log: {config.STATE_DIR / 'debug' / 'claude-last.json'}")
    backend = choose_backend(cfg)
    if backend == "claude":
        import subprocess
        env = claude_env(cfg)
        try:
            proc = subprocess.run([resolve_claude(cfg), "-p", "OK", "--output-format", "json", "--model", "sonnet"],
                                  input="", text=True, capture_output=True, timeout=60, env=env, check=False)
            d = json.loads(proc.stdout.strip().split("\n")[-1] or "{}")
            ok = not d.get("is_error")
            detail = f"claude @ {env['CLAUDE_CONFIG_DIR']}" + ("" if ok else f" — {d.get('result', 'auth failed')}; run `CLAUDE_CONFIG_DIR={env['CLAUDE_CONFIG_DIR']} claude login`")
            row("llm backend", ok, detail)
        except Exception as exc:
            row("llm backend", False, f"claude probe failed: {exc}")
    else:
        row("llm backend", backend != "none", f"{backend} (model {cfg['llm']['model']})"
            + (" — set ANTHROPIC_API_KEY or `claude login`" if backend == "none" else ""))
    mode = cfg["google"].get("export_mode", "off")
    if mode == "rest":
        from .google_api import Google, GoogleError
        try:
            g = Google()
            me = g.request("GET", "https://www.googleapis.com/oauth2/v3/userinfo").get("email", "")
            row("google rest exporter", True, f"{me} via {g.path}")
        except GoogleError as exc:
            row("google rest exporter", False, str(exc))
    else:
        print("ok   google export: off — records save locally as export_pending; Claude exports via its Drive connector (`linkintake exports`)")
    pend = len(store.pending_exports())
    print(f"     records pending export: {pend}")
    print(f"     state dir: {config.STATE_DIR}")
    return 0 if ok else 1


def cmd_config(a) -> int:
    cfg = config.load()
    for kv in a.set or []:
        k, _, v = kv.partition("=")
        if v.lower() in {"true", "false"}:
            v = v.lower() == "true"
        config.set_path(cfg, k, v)
    if a.set:
        config.save(cfg)
    print(json.dumps(cfg, indent=2))
    return 0


def cmd_google_auth(a) -> int:
    from . import google_auth
    google_auth.run()
    return 0


def cmd_cleanup(a) -> int:
    from . import cleanup
    _out(cleanup.cleanup_record(store.load(a.id)), a.json)
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="linkintake", description="Universal link intake")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("ingest", help="process a URL (does not save unless --save)")
    s.add_argument("url")
    s.add_argument("--dest", "-d", required=True, help="|".join(DESTINATIONS))
    s.add_argument("--instruction", "-i", required=True, help="what you want extracted (10-15 words is ideal)")
    s.add_argument("--save", action="store_true")
    s.add_argument("--force", action="store_true", help="save even if an exact duplicate exists")
    s.add_argument("--refresh", action="store_true", help="re-download media instead of using the cache")
    s.set_defaults(fn=cmd_ingest)

    s = sub.add_parser("save", help="save a pending record: local store + Google export + cleanup")
    s.add_argument("id")
    s.add_argument("--force", action="store_true")
    s.set_defaults(fn=cmd_save)

    s = sub.add_parser("reprocess", help="re-run a record with a new instruction and/or destination")
    s.add_argument("id")
    s.add_argument("--instruction", "-i")
    s.add_argument("--dest", "-d")
    s.add_argument("--refresh", action="store_true")
    s.set_defaults(fn=cmd_reprocess)

    s = sub.add_parser("show"); s.add_argument("id"); s.set_defaults(fn=cmd_show)
    sub.add_parser("exports", help="records saved locally and awaiting Google export (payloads for Claude)").set_defaults(fn=cmd_exports)
    s = sub.add_parser("mark-exported", help="record that Claude/you exported a record to Google")
    s.add_argument("id"); s.add_argument("--master-url"); s.add_argument("--destination-url"); s.add_argument("--note")
    s.set_defaults(fn=cmd_mark_exported)
    s = sub.add_parser("export", help="optional fallback: export one record via the REST client (google.export_mode=rest)")
    s.add_argument("id"); s.set_defaults(fn=cmd_export)
    s = sub.add_parser("list"); s.add_argument("--limit", type=int, default=20); s.set_defaults(fn=cmd_list)

    s = sub.add_parser("batch", help="ingest many: file lines `URL | destination | instruction`")
    s.add_argument("file")
    s.add_argument("--save", action="store_true")
    s.add_argument("--force", action="store_true")
    s.set_defaults(fn=cmd_batch)

    sub.add_parser("doctor").set_defaults(fn=cmd_doctor)
    s = sub.add_parser("config"); s.add_argument("--set", action="append", metavar="dotted.key=value"); s.set_defaults(fn=cmd_config)
    sub.add_parser("google-auth", help="(optional, REST fallback only) authorize a Google account").set_defaults(fn=cmd_google_auth)
    s = sub.add_parser("cleanup"); s.add_argument("id"); s.set_defaults(fn=cmd_cleanup)

    a = p.parse_args(argv)
    try:
        return a.fn(a)
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        if a.json:
            print(json.dumps({"error": f"{type(exc).__name__}: {exc}"}))
        else:
            print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
