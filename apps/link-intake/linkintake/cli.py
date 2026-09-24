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
    if rec.get("saved_at"):
        from .sync import summary_line
        lines.append(f"Sync:        {summary_line(ex, rec)}")
        res = rec.get("destination_resolution") or {}
        if res.get("action") not in (None, "", "n/a"):
            lines.append(f"Entity:      {res['action']} {res.get('entity_key') or res.get('matched_entity', '')}  ({', '.join(res.get('match_reasons', []))})")
        for k in ("master_sync", "destination_sync"):
            v = ex.get(k) or {}
            if v.get("status") == "synced":
                lines.append(f"  {k.split('_')[0]:12s} synced {v.get('remote_ref', '')}")
            elif v.get("last_error"):
                lines.append(f"  {k.split('_')[0]:12s} FAILED {v['last_error'][:160]}")
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


def cmd_sync(a) -> int:
    from . import sync
    if a.id:
        rec = store.load(a.id)
        sync.sync_record(rec)
        _out(rec if a.json else {"id": rec["id"], **rec["export"]}, a.json)
        return 0 if rec["export"]["status"] == "synced" else 1
    done = sync.sync_pending(limit=a.limit, budget_s=a.budget)
    _out(done if a.json else {"synced": [d for d in done if d["status"] == "synced"], "still_pending": [d for d in done if d["status"] != "synced"],
                              "remaining": len(sync.pending_records())}, a.json)
    return 0


def cmd_sync_status(a) -> int:
    from . import sync
    if a.id:
        rec = store.load(a.id)
        _out(rec["export"], a.json)
        return 0
    pend = sync.pending_records()
    rows = [{"id": r["id"], "destination": r["intent"]["destination"], "status": r["export"].get("status"),
             "last_error": r["export"].get("last_error", ""), "last_attempt": r["export"].get("last_attempt", "")} for r in pend]
    _out({"google": sync.google_state(), "pending": rows}, a.json)
    return 0


def cmd_sync_skip(a) -> int:
    """Mark records as never-to-sync (test artifacts, junk). Reversible with `linkintake sync <id>`."""
    from . import sync
    ids = a.ids or ([r["id"] for r in sync.pending_records()] if a.all_pending else [])
    for rid in ids:
        rec = store.load(rid)
        rec.setdefault("export", {})["status"] = "skipped"
        rec["export"]["last_error"] = ""
        store.write(rec)
    _out({"skipped": ids}, a.json)
    return 0


def cmd_resolve(a) -> int:
    """Decide a possible duplicate: merge into the matched entity or create a separate one; then sync."""
    from . import entities, sync
    res = entities.decide(a.id, "merge" if a.merge else "new", a.entity or "")
    rec = store.load(a.id)
    sync.sync_record(rec)
    _out(rec if a.json else {"resolution": res, "sync": rec["export"]["status"]}, a.json)
    return 0


def cmd_entities(a) -> int:
    from . import entities, sync
    kind = "wishlist" if a.kind == "wishlist" else "scholarship"
    if a.detach:
        key, rid = a.detach
        local = entities.detach(kind, key, rid)
        remote = {}
        if local.get("detached"):
            ent = entities.get(kind, key)
            if ent and ent["record_ids"]:
                remote = sync.absorb_remote(kind, key, [rid])  # rewrite the entity's row without the detached id; drop nothing else
            sync.sync_record(store.load(rid))  # the detached record gets its own row
        _out({"local": local, "remote": remote}, a.json)
        return 0
    if a.absorb:
        if not a.into:
            raise SystemExit("--into <canonical entity key> required")
        stray = entities.get(kind, a.absorb)
        stray_ids = list(stray["record_ids"]) if stray else []
        local = entities.absorb(kind, a.absorb, a.into)
        remote = sync.absorb_remote(kind, a.into, stray_ids)
        for rid in stray_ids:  # re-sync moved records so their export state reflects the canonical row
            sync.sync_record(store.load(rid))
        _out({"local": local, "remote": remote}, a.json)
        return 0
    rows = [{"key": e["key"], "label": entities._label(e), "records": e["record_ids"], "sources": len(e["source_urls"]),
             "variant_key": e["identity"].get("variant_key", ""), "model_numbers": e["identity"].get("model_numbers", [])} for e in entities.load(kind)]
    _out(rows, a.json)
    return 0


def _cand_line(c: dict) -> str:
    return (f"{c['id']}  [{c['status']:8s}] {DESTINATIONS.get(c['inferred_destination'], c['inferred_destination']):30s} "
            f"d={c['destination_confidence']:.2f} i={c['intent_confidence']:.2f}  {c['source_origin']}:{c['source_container'][:22]}\n"
            f"       {c['canonical_url']}\n       instruction: {c['inferred_instruction'][:110]}\n       why: {c['reason'][:140]}")


def cmd_bulk(a) -> int:
    from . import bulk
    if a.action == "scan":
        sources = [x.strip() for x in a.sources.split(",") if x.strip()]
        items = []
        for src in sources:
            if src == "reminders":
                items += bulk.discover_reminders(include_completed=a.include_completed, lists=[x.strip() for x in a.lists.split(",")] if a.lists else None)
            elif src == "notes":
                items += bulk.discover_notes(limit=a.notes_limit)
            elif src == "manifest":
                items += bulk.discover_manifest()
            elif src.startswith("file:"):
                items += bulk.discover_file(src[5:])
            else:
                raise SystemExit(f"unknown source {src} (reminders|notes|manifest|file:<path>)")
        cands = bulk.build_candidates(items)
        if a.limit:
            cands = cands[: a.limit]
        run_id = bulk.new_run(cands, sources)
        summ = bulk.summary(cands)
        if a.json:
            print(json.dumps({"run_id": run_id, "summary": summ, "candidates": cands}, ensure_ascii=False))
        else:
            print(f"bulk run {run_id}: {summ['found']} links found · {summ['existing']} already ingested · {summ['ready']} high-confidence ready · "
                  f"{summ['review']} need review · {summ['invalid']} invalid/unsupported\n(no extraction, no Google writes yet)\n")
            for c in cands:
                print(_cand_line(c))
        return 0
    run = bulk.load_run(a.run)
    if a.action == "status":
        _out({"run_id": run["run_id"], **bulk.summary(run["candidates"])}, a.json)
        return 0
    if a.action == "review":
        changed = []
        for cid in a.approve or []:
            changed.append(bulk.review_update(run, cid, approve=True))
        if a.approve_all:
            for c in run["candidates"]:
                if c["status"] in ("review", "ready") and (not a.origin or c["source_origin"] == a.origin):
                    changed.append(bulk.review_update(run, c["id"], approve=True))
        for cid, dest in a.dest or []:
            changed.append(bulk.review_update(run, cid, dest=dest))
        for cid, ins in a.instruction or []:
            changed.append(bulk.review_update(run, cid, instruction=ins))
        for cid in a.skip or []:
            changed.append(bulk.review_update(run, cid, skip=True))
        if changed:
            bulk.save_run(run)
        rows = [c for c in run["candidates"] if c["status"] == "review"] if not changed else changed
        if a.json:
            print(json.dumps(rows, ensure_ascii=False))
        else:
            print(f"run {run['run_id']} · {bulk.summary(run['candidates'])}")
            for c in rows:
                print(_cand_line(c))
        return 0
    if a.action == "run":
        report = bulk.run_batch(run, dry_run=not a.execute, limit=a.limit, delay=a.delay)
        _out(report, a.json)
        return 0 if report["failed"] == 0 else 1
    return 2


def cmd_google_setup(a) -> int:
    from . import google_setup
    google_setup.run()
    return 0


def cmd_google_audit(a) -> int:
    """Read-only: signed-in identity and the owner of every configured target. Writes nothing."""
    from . import ownership
    rep = ownership.audit()
    print(json.dumps(rep, ensure_ascii=False) if a.json else ownership.text_report(rep))
    return 0 if rep["all_personal"] else 1


def cmd_list(a) -> int:
    rows = store.history(a.limit, include_pending=not a.saved_only)
    if a.json:
        print(json.dumps(rows, ensure_ascii=False))
    else:
        for r in rows:
            flag = "SAVED " if r["saved"] else "unsaved"
            print(f"{r['id']}  {flag}  {r['destination_title']:32s} {r['sync_line']:40s} {r['title'][:40]}  {r['url']}")
        if not rows:
            print("(no records)")
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
    from . import sync
    from .google_api import Google, GoogleError
    state = sync.google_state(cfg)
    if state == "ready":
        from . import ownership
        try:
            rep = ownership.audit(Google(), cfg, legacy=False, scan_foreign=False)
        except GoogleError as exc:
            rep = None
            row("google", False, str(exc))
        if rep:
            print(f"\n     Google authenticated identity: {rep['authenticated_account'] or '(unknown)'}")
            print(f"     Required identity:             {rep['required_account'] or '(not configured)'}")
            row("Identity OK", rep["identity_ok"], "yes" if rep["identity_ok"] else "NO — ALL GOOGLE WRITES BLOCKED; re-run `linkintake google-auth` with the personal account")
            for r in rep["targets"] + [rep["wishlist_tab"]]:
                if r["status"] == ownership.PERSONAL:
                    row(r["label"], True, "personal-owned ✓")
                elif r["status"] == ownership.FOREIGN:
                    row(r["label"], False, f"!!! OWNED BY {', '.join(r['owners']).upper()} — WRITES BLOCKED ✗ (linkintake google-audit)")
                else:
                    row(r["label"], False, f"{r['status']} ✗ {r['note']}" + (" -> run `linkintake google-setup`" if r["status"] == ownership.MISSING else ""))
            print()
    elif state == "off":
        print("ok   google: export off (config google.export_mode)")
    else:
        row("google", False, "not authorized -> run `linkintake google-auth` with your PERSONAL account")
    print(f"     records pending google sync: {len(sync.pending_records())}")
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
    s = sub.add_parser("sync", help="retry pending/partial Google exports (oldest first, bounded); or one record with an id")
    s.add_argument("id", nargs="?"); s.add_argument("--limit", type=int, default=10); s.add_argument("--budget", type=float, default=60)
    s.set_defaults(fn=cmd_sync)
    s = sub.add_parser("sync-status", help="Google auth state + records still pending, with last errors")
    s.add_argument("id", nargs="?"); s.set_defaults(fn=cmd_sync_status)
    s = sub.add_parser("resolve", help="decide a possible duplicate: --merge (into the matched entity) or --new")
    s.add_argument("id"); g = s.add_mutually_exclusive_group(required=True); g.add_argument("--merge", action="store_true"); g.add_argument("--new", action="store_true")
    s.add_argument("--entity", help="entity key to merge into (default: the matched candidate)"); s.set_defaults(fn=cmd_resolve)
    s = sub.add_parser("entities", help="list destination entities (wishlist products / scholarship cycles)")
    s.add_argument("kind", choices=["wishlist", "scholarships"]); s.add_argument("--absorb", metavar="STRAY_KEY", help="fold this stray entity into --into")
    s.add_argument("--into", metavar="CANONICAL_KEY"); s.add_argument("--detach", nargs=2, metavar=("ENTITY_KEY", "RECORD_ID"), help="undo a wrong merge")
    s.set_defaults(fn=cmd_entities)
    s = sub.add_parser("sync-skip", help="exclude records from Google sync (test junk); `sync <id>` re-includes")
    s.add_argument("ids", nargs="*"); s.add_argument("--all-pending", action="store_true"); s.set_defaults(fn=cmd_sync_skip)
    s = sub.add_parser("bulk", help="bulk ingest from Reminders/Notes/manifest/file: scan -> review -> run (dry-run by default)")
    s.add_argument("action", choices=["scan", "review", "run", "status"])
    s.add_argument("--sources", default="reminders,notes,manifest", help="comma list: reminders,notes,manifest,file:<path>")
    s.add_argument("--lists", default="", help="scan: only these Reminders lists (comma separated)")
    s.add_argument("--include-completed", action="store_true"); s.add_argument("--notes-limit", type=int, default=400)
    s.add_argument("--limit", type=int, default=0, help="scan: keep first N candidates; run: process at most N")
    s.add_argument("--run", default="", help="run id (default: latest)")
    s.add_argument("--approve", nargs="*", metavar="ID"); s.add_argument("--approve-all", action="store_true"); s.add_argument("--origin", default="")
    s.add_argument("--dest", nargs=2, action="append", metavar=("ID", "DESTINATION")); s.add_argument("--instruction", nargs=2, action="append", metavar=("ID", "TEXT"))
    s.add_argument("--skip", nargs="*", metavar="ID")
    s.add_argument("--execute", action="store_true", help="run: actually process (default is dry-run preview)")
    s.add_argument("--delay", type=float, default=2.0, help="run: seconds between items")
    s.set_defaults(fn=cmd_bulk)
    sub.add_parser("google-setup", help="one-time: pick/create the destination docs, folders and sheet; persists IDs").set_defaults(fn=cmd_google_setup)
    sub.add_parser("google-audit", help="read-only: signed-in Google identity + owner of every configured target").set_defaults(fn=cmd_google_audit)
    s = sub.add_parser("list", help="history: saved records and unsaved reviews, newest first")
    s.add_argument("--limit", type=int, default=50); s.add_argument("--saved-only", action="store_true"); s.set_defaults(fn=cmd_list)

    s = sub.add_parser("batch", help="ingest many: file lines `URL | destination | instruction`")
    s.add_argument("file")
    s.add_argument("--save", action="store_true")
    s.add_argument("--force", action="store_true")
    s.set_defaults(fn=cmd_batch)

    sub.add_parser("doctor").set_defaults(fn=cmd_doctor)
    s = sub.add_parser("config"); s.add_argument("--set", action="append", metavar="dotted.key=value"); s.set_defaults(fn=cmd_config)
    sub.add_parser("google-auth", help="one-time: sign in with your PERSONAL Google account (Desktop OAuth client)").set_defaults(fn=cmd_google_auth)
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
