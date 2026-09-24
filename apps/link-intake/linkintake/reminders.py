"""Weekly Apple Reminders intake sweep.

DISCOVER with the read-only AppleScript in bulk.py -> the SAME candidate inference as `bulk` -> the SAME pipeline
as Raycast Intake Link (bulk.process_candidate: ingest -> extraction check -> save_record -> entities -> Google) ->
report. Every URL-bearing reminder ends accounted for as one of OUTCOMES; ambiguous links are never guessed.

A sweep never modifies a reminder. The only mutating AppleScript is COMPLETE_SCRIPT, used by clear_confirm(): it
marks reminders complete (never deletes), only reminders whose every link was ingested or already known, only
after a preview whose token the user echoes back, and never from the scheduled LaunchAgent.

State in ~/.link-intake/reminder-sweeps/: ledger.json (one entry per URL + list + meaningful wording),
state.json (runs, last successful sweep), <run_id>/report.json + report.md, clear-log.jsonl."""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import secrets
import subprocess
import time
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone

from . import bulk, config, store
from .records import DESTINATIONS, normalize_destination, normalize_instruction

SWEEP_DIR = config.STATE_DIR / "reminder-sweeps"
LEDGER, STATE, LOCK, CLEAR_LOG = (SWEEP_DIR / n for n in ("ledger.json", "state.json", ".lock", "clear-log.jsonl"))

AUTO_INGESTED, REVIEW, ALREADY_INGESTED = "AUTO_INGESTED", "REVIEW", "ALREADY_INGESTED"
DEFERRED, FAILED, SKIPPED_UNSUPPORTED, QUEUED = "DEFERRED", "FAILED", "SKIPPED_UNSUPPORTED", "QUEUED"
OUTCOMES = (AUTO_INGESTED, REVIEW, ALREADY_INGESTED, DEFERRED, FAILED, SKIPPED_UNSUPPORTED)
CLEARABLE = {AUTO_INGESTED, ALREADY_INGESTED}  # unsupported/tooling links stay: the reminder may still be a live task
_WORST = (FAILED, DEFERRED, QUEUED, REVIEW, SKIPPED_UNSUPPORTED, AUTO_INGESTED, ALREADY_INGESTED)
_CATEGORY = {AUTO_INGESTED: "ingested", ALREADY_INGESTED: "already_known", REVIEW: "needs_review", DEFERRED: "deferred",
             QUEUED: "deferred", FAILED: "failed", SKIPPED_UNSUPPORTED: "unsupported"}
_FROM_CANDIDATE = {"invalid": SKIPPED_UNSUPPORTED, "skip": SKIPPED_UNSUPPORTED, "existing": ALREADY_INGESTED, "review": REVIEW, "ready": QUEUED}
_FROM_PROCESS = {"ingested": AUTO_INGESTED, "already_ingested": ALREADY_INGESTED, "review": REVIEW, "deferred": DEFERRED, "failed": FAILED}
_REMINDER_ID = re.compile(r"^x-apple-reminder://[A-Za-z0-9-]+$")

# READ ONLY: look reminders up by id to confirm they are unchanged before a clear is offered or applied.
READ_BY_ID_SCRIPT = '''on run argv
tell application "Reminders"
set out to ""
repeat with rid in argv
  try
    set r to reminder id (rid as string)
    set b to body of r
    if b is missing value then set b to ""
    set out to out & rid & "%SEP%" & (name of r) & "%SEP%" & b & "%SEP%" & ((completed of r) as string) & "%RS%"
  on error
    set out to out & rid & "%SEP%%SEP%%SEP%missing%RS%"
  end try
end repeat
return out
end tell
end run'''.replace("%SEP%", bulk.SEP).replace("%RS%", bulk.RS)

# THE ONLY MUTATING SCRIPT: mark complete (never delete). Reached only through clear_confirm().
COMPLETE_SCRIPT = '''on run argv
tell application "Reminders"
set out to ""
repeat with rid in argv
  try
    set r to reminder id (rid as string)
    set completed of r to true
    set out to out & rid & "%SEP%" & ((completed of r) as string) & "%RS%"
  on error errMsg
    set out to out & rid & "%SEP%error: " & errMsg & "%RS%"
  end try
end repeat
return out
end tell
end run'''.replace("%SEP%", bulk.SEP).replace("%RS%", bulk.RS)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _read(path, default):
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def _write(path, obj) -> None:
    """Atomic: a crash mid-write never leaves a half ledger or report."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(obj, indent=2, ensure_ascii=False))
    os.replace(tmp, path)


def load_ledger() -> dict:
    return _read(LEDGER, {})


def save_ledger(ledger: dict) -> None:
    _write(LEDGER, ledger)


@contextmanager
def lock():
    """One mutating sweep at a time (launchd vs Raycast vs Claude)."""
    SWEEP_DIR.mkdir(parents=True, exist_ok=True)
    with open(LOCK, "w") as fh:
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("a Reminder sweep is already running") from None
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def link_hash(canonical_url: str, container: str, context: str) -> str:
    """Identity of one link as written: case, punctuation and spacing changes are not a new intent; different
    wording or a move to another list is, and gets reconsidered."""
    norm = lambda s: " ".join(normalize_instruction(s).split())  # noqa: E731
    return hashlib.sha1(f"{canonical_url}|{norm(container)}|{norm(context)}".encode()).hexdigest()[:16]


# ---------- discovery + planning (no writes)
def plan(items: list[dict], ledger: dict) -> tuple[list[dict], list[tuple[str, dict]]]:
    """-> (new ledger entries, every discovered (hash, provenance) link). Seen links produce no new entry."""
    new: dict[str, dict] = {}
    links: list[tuple[str, dict]] = []
    for c in bulk.build_candidates(items):
        for p in c["provenance"]:
            h = link_hash(c["canonical_url"], p["container"], p["context"])
            links.append((h, p))
            if h in ledger:
                continue
            if h in new:
                if p.get("source_id") and p["source_id"] not in new[h]["reminder_ids"]:
                    new[h]["reminder_ids"].append(p["source_id"])
                continue
            new[h] = {"id": "r" + h[:8], "hash": h, "url": c["original_url"], "canonical_url": c["canonical_url"],
                      "reminder_ids": [p["source_id"]] if p.get("source_id") else [], "list": p["container"], "title": p["title"],
                      "text": p.get("text", ""), "context": p["context"], "destination": c["inferred_destination"],
                      "destination_confidence": c["destination_confidence"], "instruction": c["inferred_instruction"],
                      "intent_confidence": c["intent_confidence"], "instruction_origin": "inferred", "reason": c["reason"],
                      "outcome": _FROM_CANDIDATE.get(c["status"], REVIEW), "record_id": c.get("existing_intake_match", "") if c["status"] == "existing" else "",
                      "resolution": "", "export_status": "", "attempts": 0, "last_error": "", "first_seen_run": "", "last_run": "", "updated_at": _now()}
    return list(new.values()), links


def _settings(lists, include_completed, limit) -> tuple[list[str] | None, bool, int]:
    rc = config.load().get("reminders", {})
    lists = lists if lists is not None else (rc.get("lists") or None)
    include_completed = include_completed if include_completed is not None else bool(rc.get("include_completed"))
    limit = limit if limit is not None else int(rc.get("max_items_per_run", 25))
    return lists, include_completed, limit


def preview(lists=None, include_completed=None, limit=None) -> dict:
    """Dry run: discovery + inference + what a real run would do. Writes nothing anywhere."""
    lists, include_completed, limit = _settings(lists, include_completed, limit)
    items = bulk.discover_reminders(include_completed=include_completed, lists=lists)
    ledger = load_ledger()
    new, links = plan(items, ledger)
    retry = [e for e in ledger.values() if e["outcome"] in (QUEUED, DEFERRED)]
    queued = [e for e in new if e["outcome"] == QUEUED]
    return {"dry_run": True, "urls_discovered": len({h for h, _ in links}), "reminders_with_urls": len({_rem_key(p) for _, p in links}),
            "previously_accounted": len({h for h, _ in links if h in ledger}), "new_candidates": len(new),
            "would_process": [_view(e) for e in (queued + retry)[:limit or None]],
            "over_cap": max(0, len(queued) + len(retry) - limit) if limit else 0,
            "new_by_outcome": dict(Counter("WOULD_INGEST" if e["outcome"] == QUEUED else e["outcome"] for e in new)),
            "new": [_view(e) for e in new]}


# ---------- processing
def _batch(e: dict, run_id: str) -> dict:
    return {"run_id": f"reminders-{run_id}", "candidate_id": e["id"], "source_origin": "reminders", "source_container": e["list"],
            "source_context": e["context"], "instruction_origin": e.get("instruction_origin", "inferred"),
            "reminder_ids": e["reminder_ids"], "reminder_title": e["title"]}


def _set(e: dict, outcome: str, reason: str = "", **kw) -> None:
    e.update(outcome=outcome, updated_at=_now(), **kw)
    if reason:
        e["reason" if outcome in (REVIEW, SKIPPED_UNSUPPORTED) else "last_error"] = reason
    if outcome in (AUTO_INGESTED, ALREADY_INGESTED):
        e["last_error"] = ""


def process(todo: list[dict], ledger: dict, run_id: str, limit: int) -> list[dict]:
    """Sequential; ledger saved after every item so an interrupted sweep resumes. One failure never stops it."""
    claude_down, attempts, touched = "", 0, []
    for e in todo:
        touched.append(e)
        if claude_down:
            _set(e, DEFERRED, f"not attempted: Claude unavailable earlier in this run ({claude_down[:160]})")
        elif limit and attempts >= limit:
            _set(e, DEFERRED, f"per-run cap of {limit} reached; picked up by the next sweep or `linkintake reminders retry-deferred`")
        else:
            attempts += 1
            e["attempts"] = e.get("attempts", 0) + 1
            e["last_run"] = run_id
            try:
                r = bulk.process_candidate({"original_url": e["url"], "canonical_url": e["canonical_url"], "inferred_destination": e["destination"],
                                            "inferred_instruction": e["instruction"]}, _batch(e, run_id))
            except Exception as exc:  # never stop the sweep
                r = {"outcome": "failed", "reason": f"{type(exc).__name__}: {exc}"[:400]}
            _set(e, _FROM_PROCESS[r["outcome"]], r.get("reason", ""), record_id=r.get("record_id", "") or e.get("record_id", ""),
                 resolution=r.get("resolution", ""), export_status=r.get("export_status", ""))
            if r.get("claude_down"):
                claude_down = r["reason"]
        save_ledger(ledger)
        print(f"[reminders] {e['id']} {e['outcome']} {e.get('record_id', '')} {e.get('last_error', '')[:100]}", flush=True)
    return touched


def _refresh(ledger: dict) -> None:
    """A possible duplicate the user resolved with `linkintake resolve` is no longer a review item."""
    for e in ledger.values():
        if e["outcome"] == REVIEW and e.get("record_id") and e.get("resolution") == "possible_duplicate":
            try:
                res = (store.load(e["record_id"]).get("destination_resolution") or {}).get("action", "")
            except FileNotFoundError:
                continue
            if res and res != "possible_duplicate":
                _set(e, AUTO_INGESTED, resolution=res)


def sweep(*, scheduled: bool = False, lists=None, include_completed=None, limit=None, notify: bool = True) -> dict:
    """The real run: discover (read only) -> new entries -> process queued + deferred -> report -> one notification."""
    lists, include_completed, limit = _settings(lists, include_completed, limit)
    with lock():
        run_id = time.strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(2)
        started = _now()
        state = _read(STATE, {"runs": []})
        for r in state["runs"]:
            if r.get("status") == "running":
                r["status"] = "interrupted"
        state["runs"].append({"run_id": run_id, "started": started, "status": "running", "scheduled": scheduled})
        _write(STATE, state)
        ledger = load_ledger()
        try:
            items = bulk.discover_reminders(include_completed=include_completed, lists=lists)
        except Exception as exc:
            rep = _finish(run_id, started, scheduled, ledger, [], [], [], error=f"Reminders discovery failed: {exc}"[:400])
            if notify:
                send_notification("Link Intake Weekly", f"Reminder sweep failed: {str(exc)[:120]}")
            return rep
        _refresh(ledger)
        new, links = plan(items, ledger)
        for e in new:
            e["first_seen_run"] = e["last_run"] = run_id
            ledger[e["hash"]] = e
        save_ledger(ledger)
        todo = [e for e in ledger.values() if e["outcome"] == QUEUED] + [e for e in ledger.values() if e["outcome"] == DEFERRED]
        touched = process(todo, ledger, run_id, limit)
        rep = _finish(run_id, started, scheduled, ledger, new, touched, links)
    if notify:
        send_notification("Link Intake Weekly", rep["notification"])
    return rep


def retry_deferred(include_failed: bool = False, limit=None) -> dict:
    """Retry DEFERRED (and interrupted QUEUED) items; FAILED too with include_failed. Idempotent: an item that
    succeeded is AUTO_INGESTED/ALREADY_INGESTED and is never picked again."""
    _, _, limit = _settings(None, None, limit)
    with lock():
        ledger = load_ledger()
        _refresh(ledger)
        want = {QUEUED, DEFERRED} | ({FAILED} if include_failed else set())
        todo = [e for e in ledger.values() if e["outcome"] in want]
        touched = process(todo, ledger, "retry-" + time.strftime("%Y%m%d-%H%M%S"), limit)
    c = Counter(e["outcome"] for e in touched)
    return {"retried": len(touched), "ingested": c[AUTO_INGESTED], "already_ingested": c[ALREADY_INGESTED], "review": c[REVIEW],
            "still_deferred": c[DEFERRED], "failed": c[FAILED], "items": [_view(e) for e in touched]}


# ---------- review
def _find(ledger: dict, eid: str) -> dict:
    e = next((x for x in ledger.values() if eid and eid in (x["id"], x["hash"])), None)
    if not e:
        raise KeyError(f"no reminder intake item {eid}")
    return e


def review_items() -> list[dict]:
    ledger = load_ledger()
    _refresh(ledger)
    return [_view(e) for e in ledger.values() if e["outcome"] == REVIEW]


def review_update(ledger: dict, eid: str, *, approve=False, dest="", instruction="", skip=False) -> dict:
    e = _find(ledger, eid)
    if e.get("resolution") == "possible_duplicate" and (approve or dest or instruction):
        raise ValueError(f"{eid} is saved as {e['record_id']} but may duplicate an existing entry: run `linkintake resolve {e['record_id']} --merge|--new`")
    if dest:
        e["destination"], e["destination_confidence"] = normalize_destination(dest), 1.0
    if instruction:
        e["instruction"], e["intent_confidence"], e["instruction_origin"] = instruction, 1.0, "user"
    if skip:
        _set(e, SKIPPED_UNSUPPORTED, "skipped by you in review")
    elif (approve or dest or instruction) and e["outcome"] in (REVIEW, SKIPPED_UNSUPPORTED, FAILED):
        _set(e, QUEUED)
    return e


def process_queued(limit=None) -> list[dict]:
    """After review approvals: process only what you just approved (QUEUED), now."""
    _, _, limit = _settings(None, None, limit)
    with lock():
        ledger = load_ledger()
        return [_view(e) for e in process([e for e in ledger.values() if e["outcome"] == QUEUED], ledger, "review-" + time.strftime("%Y%m%d-%H%M%S"), limit)]


# ---------- reporting + reconciliation
def _rem_key(p: dict) -> str:
    return p.get("source_id") or f"{p['container']}|{p['title']}"


def _next_action(e: dict) -> str:
    o = e["outcome"]
    if o == REVIEW and e.get("resolution") == "possible_duplicate":
        return f"linkintake resolve {e['record_id']} --merge  (or --new)"
    if o == REVIEW:
        return f"linkintake reminders review --approve {e['id']} [--dest <destination>] [--instruction \"…\"] --execute   or   --skip {e['id']}"
    if o in (DEFERRED, QUEUED):
        login = " (first: CLAUDE_CONFIG_DIR=~/.claude-nebula claude login)" if re.search(r"not logged in|/login|authenticat", e.get("last_error", ""), re.I) else ""
        return "retried automatically by the next sweep, or now: linkintake reminders retry-deferred" + login
    if o == FAILED:
        return "fix the cause, then: linkintake reminders retry-deferred --include-failed"
    return ""


def _view(e: dict) -> dict:
    return {"id": e["id"], "outcome": e["outcome"], "list": e["list"], "title": e["title"], "text": e.get("text", "")[:300],
            "url": e["url"], "destination": e["destination"], "destination_title": DESTINATIONS.get(e["destination"], e["destination"]),
            "destination_confidence": e.get("destination_confidence", 0), "instruction": e["instruction"],
            "reason": e.get("last_error") if e["outcome"] in (DEFERRED, FAILED) and e.get("last_error") else e.get("reason", ""),
            "next_action": _next_action(e), "record_id": e.get("record_id", ""), "resolution": e.get("resolution", ""),
            "export_status": e.get("export_status", ""), "reminder_ids": e.get("reminder_ids", []), "attempts": e.get("attempts", 0)}


def reconcile(links: list, ledger: dict) -> dict:
    """Per reminder: every link it holds and its outcome. Eligible to clear only if every link is ingested or known."""
    by: dict[str, dict] = {}
    for h, p in links:
        r = by.setdefault(_rem_key(p), {"reminder_id": p.get("source_id", ""), "list": p["container"], "title": p["title"],
                                         "text": p.get("text", "")[:300], "content_hash": p.get("content_hash", ""), "links": []})
        if all(l["hash"] != h for l in r["links"]):
            e = ledger.get(h, {})
            r["links"].append({"hash": h, "entry_id": e.get("id", ""), "url": e.get("url", ""), "outcome": e.get("outcome", QUEUED),
                               "record_id": e.get("record_id", "")})
    rems = list(by.values())
    for r in rems:
        outs = [l["outcome"] for l in r["links"]]
        r["status"] = next(o for o in _WORST if o in outs)
        r["category"] = _CATEGORY[r["status"]]
        blockers = sorted({_CATEGORY[o] for o in outs if o not in CLEARABLE})
        r["eligible_to_clear"] = bool(r["reminder_id"]) and not blockers
        r["why_not"] = ("has links that " + ", ".join(blockers).replace("_", " ")) if blockers else ("" if r["reminder_id"] else "no stable reminder id")
    s = Counter(r["category"] for r in rems)
    elig = sum(r["eligible_to_clear"] for r in rems)
    summary = {"reminders_found": len(rems), **{k: s[k] for k in ("ingested", "already_known", "needs_review", "deferred", "failed", "unsupported")},
               "eligible_to_clear": elig, "remain_untouched": len(rems) - elig}
    return {"summary": summary, "reminders": rems, "confirmation": confirmation(summary)}


def confirmation(s: dict) -> str:
    words = [("ingested", "ingested successfully"), ("already_known", "already known"), ("needs_review", "needs review"),
             ("deferred", "deferred (Claude/quota — will retry)"), ("failed", "failed"), ("unsupported", "unsupported (left alone)")]
    lines = [f"{s['reminders_found']} URL reminders found."] + [f"{s[k]} {w}." for k, w in words if s[k]]
    return "\n".join(lines) + (f"\n\n{s['eligible_to_clear']} reminders are fully handled and eligible to clear.\n"
                               f"{s['remain_untouched']} will remain untouched.")


def _finish(run_id, started, scheduled, ledger, new, touched, links, error: str = "") -> dict:
    this = {e["hash"]: e for e in new + touched}
    c = Counter(e["outcome"] for e in this.values())
    ing = [e for e in this.values() if e["outcome"] == AUTO_INGESTED]
    by_dest = lambda d, merged: sum(1 for e in ing if e["destination"] == d and (e.get("resolution") == "merged") == merged)  # noqa: E731
    rep = {"run_id": run_id, "started": started, "finished": _now(), "scheduled": scheduled, "status": "failed" if error else "ok", "error": error,
           "counts": {"urls_discovered": len({h for h, _ in links}), "reminders_with_urls": len({_rem_key(p) for _, p in links}),
                      "previously_accounted": len({h for h, _ in links} - {e["hash"] for e in new}), "new_candidates": len(new),
                      "auto_ingested": c[AUTO_INGESTED], "wishlist_created": by_dest("wishlist", False), "wishlist_merged": by_dest("wishlist", True),
                      "scholarships_created": by_dest("scholarships", False), "scholarships_merged": by_dest("scholarships", True),
                      "other_destinations": dict(Counter(e["destination"] for e in ing if e["destination"] not in ("wishlist", "scholarships"))),
                      "already_ingested": c[ALREADY_INGESTED], "needs_review": c[REVIEW], "deferred": c[DEFERRED] + c[QUEUED], "failed": c[FAILED],
                      "google_pending": sum(1 for e in ing if e.get("export_status") in ("export_pending", "partial", "not_configured", "blocked")),
                      "skipped_unsupported": c[SKIPPED_UNSUPPORTED]},
           "items": [_view(e) for e in this.values()],
           "links": [[h, {k: p.get(k, "") for k in ("source_id", "container", "title", "text", "context", "content_hash")}] for h, p in links],
           "clear_decision": {"action": "pending"}}
    _overlay(rep, ledger)
    k = rep["counts"]
    rep["notification"] = (f"Reminder sweep failed: {error[:100]}" if error else
                           f"{k['new_candidates']} links found · {k['auto_ingested']} saved · {k['already_ingested']} already known · "
                           f"{k['needs_review']} review · {k['deferred']} deferred" + (f" · {k['failed']} failed" if k["failed"] else "")
                           + (f" · {rep['reconciliation']['summary']['eligible_to_clear']} ready to clear" if rep["reconciliation"]["summary"]["eligible_to_clear"] else ""))
    write_report(rep)
    state = _read(STATE, {"runs": []})
    for r in state["runs"]:
        if r["run_id"] == run_id:
            r.update(status=rep["status"], finished=rep["finished"], report=str(SWEEP_DIR / run_id / "report.json"))
    state["runs"] = state["runs"][-50:]
    state["last_run_id"] = run_id
    if not error:
        state["last_successful_sweep"] = rep["finished"]
    _write(STATE, state)
    return rep


def _overlay(rep: dict, ledger: dict) -> dict:
    """Recompute what is still outstanding from the CURRENT ledger (reviews approved, retries done since the run)."""
    links = [(h, p) for h, p in rep.get("links", [])]
    hashes = {h for h, _ in links} | {i["id"] for i in rep.get("items", [])}
    rep["reconciliation"] = reconcile(links, ledger)
    rep["attention"] = [_view(e) for e in ledger.values() if e["outcome"] in (REVIEW, DEFERRED, QUEUED, FAILED) and (e["hash"] in hashes or e["id"] in hashes)]
    return rep


def write_report(rep: dict) -> None:
    d = SWEEP_DIR / rep["run_id"]
    _write(d / "report.json", rep)
    (d / "report.md").write_text(markdown(rep))


def latest_run_id() -> str:
    for r in reversed(_read(STATE, {"runs": []})["runs"]):
        if (SWEEP_DIR / r["run_id"] / "report.json").exists():
            return r["run_id"]
    return ""


def load_report(run_id: str = "", refresh: bool = True) -> dict:
    run_id = run_id or latest_run_id()
    if not run_id:
        raise FileNotFoundError("no Reminder sweep yet: run `linkintake reminders run --execute`")
    rep = _read(SWEEP_DIR / run_id / "report.json", None)
    if rep is None:
        raise FileNotFoundError(f"no report for run {run_id}")
    if refresh:
        ledger = load_ledger()
        _refresh(ledger)
        _overlay(rep, ledger)
    state = _read(STATE, {})
    rep["last_successful_sweep"] = state.get("last_successful_sweep", "")
    rep["markdown"] = markdown(rep)  # Raycast shows this as-is; no report logic in TypeScript
    return rep


def markdown(rep: dict) -> str:
    k, rc = rep["counts"], rep["reconciliation"]
    other = ", ".join(f"{DESTINATIONS.get(d, d)} {n}" for d, n in k["other_destinations"].items()) or "0"
    L = [f"# Link Intake — Reminder sweep {rep['run_id']}", "",
         f"Run time: {rep['started']} → {rep['finished']} ({'scheduled' if rep['scheduled'] else 'manual'})" + (f"  \n**FAILED:** {rep['error']}" if rep["error"] else ""),
         "", "```", rc["confirmation"], "```", "",
         "| | |", "|---|---|",
         *[f"| {a} | {b} |" for a, b in [
             ("URLs discovered", k["urls_discovered"]), ("New candidates", k["new_candidates"]), ("Previously accounted", k["previously_accounted"]),
             ("Auto-ingested", k["auto_ingested"]), ("Wishlist created", k["wishlist_created"]), ("Wishlist merged", k["wishlist_merged"]),
             ("Scholarships created / merged", f"{k['scholarships_created']} / {k['scholarships_merged']}"), ("Other destinations", other),
             ("Already ingested", k["already_ingested"]), ("Needs review", k["needs_review"]), ("Deferred due to Claude/quota", k["deferred"]),
             ("Failed", k["failed"]), ("Google pending", k["google_pending"]), ("Skipped unsupported", k["skipped_unsupported"])]], ""]
    if rep["attention"]:
        L += ["## Needs attention", ""]
        for i in rep["attention"]:
            L += [f"### {i['outcome']} · {i['list']} · {i['title'] or '(no title)'}  (`{i['id']}`)",
                  f"- Wording: {(i['title'] + ' — ' + i['text']).strip(' —')[:300]}", f"- URL: {i['url']}",
                  f"- Destination guess: {i['destination_title']} ({i['destination_confidence']:.2f})", f"- Reason: {i['reason']}",
                  f"- Next action: `{i['next_action']}`", ""]
    elig = [r for r in rc["reminders"] if r["eligible_to_clear"]]
    keep = [r for r in rc["reminders"] if not r["eligible_to_clear"]]
    L += ["## Eligible to clear (mark complete — never deleted; nothing has been changed)", ""]
    L += [f"- [{r['list']}] {r['title'] or '(no title)'} — {len(r['links'])} link(s): {', '.join(sorted({_CATEGORY[l['outcome']] for l in r['links']}))}" for r in elig] or ["- none"]
    L += ["", "## Will remain untouched", ""]
    L += [f"- [{r['list']}] {r['title'] or '(no title)'} — {r['why_not']}" for r in keep] or ["- none"]
    d = rep.get("clear_decision", {})
    L += ["", f"Clear decision: **{d.get('action', 'pending')}**" + (f" ({d.get('count', 0)} completed {d.get('at', '')})" if d.get("action") == "cleared" else ""),
          "Clearing always needs your approval: `linkintake reminders clear` (preview) then `linkintake reminders clear --confirm <token>`."]
    return "\n".join(L) + "\n"


# ---------- clearing (the only Reminders mutation; explicit, previewed, confirmed)
def _read_by_id(ids: list[str]) -> dict:
    ids = [i for i in ids if _REMINDER_ID.match(i)]
    if not ids:
        return {}
    out = {}
    for rec in bulk._osa(READ_BY_ID_SCRIPT, args=tuple(ids)).split(bulk.RS):
        parts = rec.strip("\n").split(bulk.SEP)
        if len(parts) >= 4 and parts[0]:
            out[parts[0]] = {"title": parts[1], "body": parts[2], "completed": parts[3].strip() == "true", "missing": parts[3].strip() == "missing"}
    return out


def _records_ok(r: dict) -> bool:
    for l in r["links"]:
        try:
            rec = store.load(l["record_id"]) if l["record_id"] else None
        except FileNotFoundError:
            rec = None
        if not rec or not rec.get("saved_at") or rec.get("status") == "failed":
            return False
    return True


def clear_preview(run_id: str = "") -> dict:
    """What `clear --confirm` would complete, re-verified live (read only). Nothing is changed here."""
    rep = load_report(run_id)
    rc = rep["reconciliation"]
    elig = [r for r in rc["reminders"] if r["eligible_to_clear"]]
    live = _read_by_id([r["reminder_id"] for r in elig])
    ok, untouched = [], [{**r, "why": r["why_not"]} for r in rc["reminders"] if not r["eligible_to_clear"]]
    for r in elig:
        lv = live.get(r["reminder_id"])
        why = ("not found in Reminders" if not lv or lv["missing"] else "already completed" if lv["completed"] else
               "text changed since the sweep read it" if bulk.content_hash(lv["title"], lv["body"]) != r["content_hash"] else
               "an intake record is missing or failed" if not _records_ok(r) else "")
        (untouched.append({**r, "why": why}) if why else ok.append(r))
    token = hashlib.sha1("|".join(sorted(f"{r['reminder_id']}:{r['content_hash']}" for r in ok)).encode()).hexdigest()[:12] if ok else ""
    return {"run_id": rep["run_id"], "action": "mark complete (never delete)", "will_complete": ok, "untouched": untouched, "token": token,
            "confirm_command": f"linkintake reminders clear --confirm {token}" if token else "", "clear_decision": rep.get("clear_decision", {})}


def _decide(run_id: str, decision: dict) -> None:
    rep = load_report(run_id, refresh=False)
    for k in ("markdown", "last_successful_sweep"):  # derived on load, not stored
        rep.pop(k, None)
    rep["clear_decision"] = decision
    ledger = load_ledger()
    _overlay(rep, ledger)
    write_report(rep)


def clear_keep(run_id: str = "") -> dict:
    run_id = run_id or latest_run_id()
    _decide(run_id, {"action": "kept", "at": _now()})
    return {"run_id": run_id, "action": "kept", "changed": 0}


def clear_confirm(token: str, run_id: str = "") -> dict:
    """Mark the previewed reminders complete. Refuses under the scheduler, on a stale/foreign token, or on any change."""
    if os.environ.get("LINKINTAKE_SCHEDULED"):
        raise PermissionError("refusing: clearing Reminders needs your explicit approval and never runs from the schedule")
    with lock():
        pv = clear_preview(run_id)
        if not token or token != pv["token"]:
            raise PermissionError("confirmation token does not match the current preview (a reminder changed, or this is another run). "
                                  "Run `linkintake reminders clear` again and confirm what it shows.")
        ids = [r["reminder_id"] for r in pv["will_complete"] if _REMINDER_ID.match(r["reminder_id"])]
        raw = bulk._osa(COMPLETE_SCRIPT, args=tuple(ids))
        after = _read_by_id(ids)
        done, failed = [], []
        for r in pv["will_complete"]:
            ok = bool(after.get(r["reminder_id"], {}).get("completed"))
            (done if ok else failed).append({"reminder_id": r["reminder_id"], "list": r["list"], "title": r["title"]})
            with CLEAR_LOG.open("a") as fh:
                fh.write(json.dumps({"at": _now(), "run_id": pv["run_id"], "reminder_id": r["reminder_id"], "list": r["list"], "title": r["title"],
                                     "links": [(l["url"], l["outcome"], l["record_id"]) for l in r["links"]], "completed": ok}, ensure_ascii=False) + "\n")
        _decide(pv["run_id"], {"action": "cleared", "at": _now(), "count": len(done), "ids": [d["reminder_id"] for d in done]})
    return {"run_id": pv["run_id"], "completed": done, "failed": failed, "untouched": len(pv["untouched"]), "raw": raw[:500] if failed else ""}


# ---------- notification
def send_notification(title: str, message: str) -> None:
    """One macOS notification per sweep. Text goes in as argv data, never script text."""
    try:
        subprocess.run(["osascript", "-e", "on run argv", "-e", "display notification (item 2 of argv) with title (item 1 of argv)",
                        "-e", "end run", title, message], capture_output=True, timeout=15, check=False)
    except Exception:
        pass
