"""Bulk ingest: DISCOVER -> NORMALIZE -> DEDUPE -> INFER -> (review) -> PROCESS through the normal pipeline.

Sources are READ ONLY. The AppleScript below only uses `get`/`every ... whose`; nothing is set, completed,
deleted or moved. Candidates live in ~/.link-intake/bulk/<run_id>/candidates.json; `bulk run` walks them
sequentially with a delay, resumes if interrupted, and never lets one failure stop the batch."""
from __future__ import annotations

import json
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from . import config, store
from .records import DESTINATIONS, dedupe_key, normalize_instruction
from .router import canonicalize, classify

BULK_DIR = config.STATE_DIR / "bulk"
URL_RE = re.compile(r"https?://[^\s<>\"'\)\]]+")
AUTO_THRESHOLD = 0.80
MANIFEST = Path(__file__).resolve().parents[2] / "media-unlocker" / "test_wishlist_reels.sh"

# ---------- destination signals (strongest first: container, then wording near the URL)
CONTAINER_HINTS = [
    ("wishlist", r"wish\s?list|dorm|shopping|to buy|buy list|gear"),
    ("scholarships", r"scholarship"),
    ("supplement_ideas", r"college app|supplement|essay|personal statement|common app"),
    ("design_inspo", r"design|inspo|ui|ux|brand|typograph|portfolio"),
    ("personal_ig", r"instagram|reel|content|film|video|photo|edit"),
]
TEXT_HINTS = [
    ("wishlist", r"\b(want|buy|cop|need|order|price|wishlist|wish list|desk setup|charger|setup|for my (dorm|room|desk)|link to buy|purchase|get this)\b"),
    ("scholarships", r"\b(scholarship|deadline|apply|application|award|grant)\b"),
    ("supplement_ideas", r"\b(essay|supplement|supplemental|metaphor|framing of (the|this) (idea|story|essay)|opening line|why major|personal statement|prompt|thesis|argument|writing)\b"),
    ("personal_ig", r"\b(shot|shots|framing|angle|edit|editing|transition|transitions|hook|film|filmed|lighting|cinematic|b-?roll|pacing|color grade|how (this|the) (reel|video) (is|was) (shot|made|edited)|reel idea|post idea|content idea)\b"),
    ("design_inspo", r"\b(design|layout|font|typography|ui|ux|color palette|palette|logo|poster|animation|website|landing page)\b"),
]
# words that name the destination outright; enough on their own for a confident destination
STRONG_WORDS = {
    "wishlist": r"\b(wishlist|wish list|for my dorm|dorm room|buy this|want this|cop this)\b",
    "scholarships": r"\b(scholarships?|scholars)\b",
    "supplement_ideas": r"\b(supplement(al)?|essay|personal statement|common app)\b",
    "design_inspo": r"\b(design inspo|ui inspo|inspo|typography)\b",
    "personal_ig": r"\b(reel idea|content idea|post idea|video inspo|filmmaking|cinematic|b-?roll|transitions?)\b",
}
WORK_LINK = re.compile(r"(github\.com|gitlab\.com|supabase\.co|tally\.so|notion\.so|figma\.com/file|docs\.google\.com|drive\.google\.com|localhost|vercel\.app|\.edu/)", re.I)

GENERIC_INSTRUCTION = {
    "wishlist": "Identify the product shown so I can add it to my wishlist.",
    "scholarships": "Extract the scholarship, deadline, amount, eligibility and required materials.",
    "supplement_ideas": "Capture the idea or framing here that could inspire a college supplement essay.",
    "design_inspo": "Capture the design concept that stands out here.",
    "personal_ig": "Capture the filming, framing, editing or hook techniques worth reusing.",
    "inbox": "Save for later classification.",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _osa(script: str, timeout: int = 600) -> str:
    proc = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=timeout, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"osascript failed: {proc.stderr.strip()[:300]}")
    return proc.stdout


SEP, RS = "␟", "␞"  # unit / record separators, never in real text

# READ ONLY: only `get`-style property reads. No set/delete/make/complete anywhere.
REMINDERS_SCRIPT = '''tell application "Reminders"
set out to ""
repeat with L in lists
  set ln to name of L
  set ns to name of every reminder of L
  set bs to body of every reminder of L
  set cs to completed of every reminder of L
  set ds to creation date of every reminder of L
  repeat with i from 1 to (count of ns)
    set b to item i of bs
    if b is missing value then set b to ""
    set out to out & ln & "%SEP%" & (item i of ns) & "%SEP%" & b & "%SEP%" & (item i of cs) & "%SEP%" & ((item i of ds) as string) & "%RS%"
  end repeat
end repeat
return out
end tell'''.replace("%SEP%", SEP).replace("%RS%", RS)

NOTES_SCRIPT = '''tell application "Notes"
set ns to (every note whose body contains "http")
set out to ""
repeat with i from 1 to (count of ns)
  if i > %LIMIT% then exit repeat
  set n to item i of ns
  set f to ""
  try
    set f to name of container of n
  end try
  set out to out & (name of n) & "%SEP%" & f & "%SEP%" & (id of n) & "%SEP%" & ((modification date of n) as string) & "%SEP%" & (plaintext of n) & "%RS%"
end repeat
return out
end tell'''.replace("%SEP%", SEP).replace("%RS%", RS)


# ---------- discovery
def discover_reminders(include_completed: bool = False, lists: list[str] | None = None) -> list[dict]:
    raw = _osa(REMINDERS_SCRIPT)
    items = []
    for rec in raw.split(RS):
        if not rec.strip():
            continue
        parts = rec.split(SEP)
        if len(parts) < 5:
            continue
        ln, name, body, completed, created = parts[:5]
        if lists and ln not in lists:
            continue
        if completed.strip() == "true" and not include_completed:
            continue
        items.append({"origin": "reminders", "container": ln, "title": name.strip(), "text": body.strip(),
                      "completed": completed.strip() == "true", "created": created.strip()})
    return items


def discover_notes(limit: int = 400) -> list[dict]:
    raw = _osa(NOTES_SCRIPT.replace("%LIMIT%", str(limit)))
    items = []
    for rec in raw.split(RS):
        if not rec.strip():
            continue
        parts = rec.split(SEP)
        if len(parts) < 5:
            continue
        name, folder, nid, mod, text = parts[0], parts[1], parts[2], parts[3], SEP.join(parts[4:])
        items.append({"origin": "notes", "container": folder.strip() or "Notes", "title": name.strip(), "text": text, "note_id": nid.strip(), "modified": mod.strip()})
    return items


def discover_manifest() -> list[dict]:
    if not MANIFEST.exists():
        return []
    urls = re.findall(r"https://www\.instagram\.com/reel/[^'\"\s]+", MANIFEST.read_text())
    return [{"origin": "manifest", "container": "wishlist regression manifest", "title": "", "text": u} for u in urls]


def discover_file(path: str) -> list[dict]:
    items = []
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        items.append({"origin": "file", "container": Path(path).name, "title": "", "text": line})
    return items


# ---------- normalization: one candidate per (url, nearby context)
def _context_for(url: str, text: str, title: str) -> str:
    """The line holding the URL plus the nearest non-empty line above it, minus the URL itself."""
    lines = [l.strip() for l in text.splitlines()]
    ctx = []
    for i, l in enumerate(lines):
        if url in l:
            own = l.replace(url, "").strip(" -–—:|•")
            prev = next((lines[j] for j in range(i - 1, -1, -1) if lines[j] and not URL_RE.search(lines[j])), "")
            ctx = [x for x in (own, prev) if x]
            break
    if not ctx and title:
        ctx = [title]
    out = " — ".join(ctx)
    return re.sub(r"\s+", " ", out)[:240]


def _valid(url: str) -> str:
    try:
        cls, _ = classify(url)
    except Exception:
        return "unparseable"
    host = re.sub(r"^https?://", "", url).split("/")[0].split(":")[0].lower()
    if host in {"localhost", "127.0.0.1", "0.0.0.0"} or host.endswith(".local") or re.fullmatch(r"(10|192\.168|172\.(1[6-9]|2\d|3[01]))\..*", host):
        return "private host"
    if cls == "unknown":
        return "unknown source class"
    return ""


def infer(container: str, context: str, url: str) -> tuple[str, float, str, float, str]:
    """-> (destination, destination_confidence, instruction, intent_confidence, reason)."""
    ctx = context or ""
    c_hit = next((d for d, rx in CONTAINER_HINTS if re.search(rx, container or "", re.I)), "")
    strong = [d for d, rx in STRONG_WORDS.items() if re.search(rx, ctx, re.I)]
    hits = {d: len(set(m.lower() for m in re.findall(rx, ctx, re.I) for m in ([m] if isinstance(m, str) else [x for x in m if x])))
            for d, rx in TEXT_HINTS if re.search(rx, ctx, re.I)}
    for d in strong:  # an explicit destination word counts as a hint even if the generic list misses it ("video inspo")
        hits[d] = hits.get(d, 0) + 1
    t_hits = sorted(hits, key=lambda d: (-(d in strong), -hits[d]))
    reasons = []
    if c_hit:
        reasons.append(f"list/folder '{container}' -> {DESTINATIONS[c_hit]}")
    if t_hits:
        reasons.append("wording near URL -> " + ", ".join(DESTINATIONS[d] for d in t_hits))
    if c_hit and (not t_hits or t_hits[0] == c_hit):
        dest, dconf = c_hit, 0.9 if t_hits else 0.85
    elif c_hit and t_hits and t_hits[0] != c_hit:
        dest, dconf = t_hits[0], 0.6  # the words beat the folder, but flag it
        reasons.append("container and wording disagree")
    elif len(t_hits) == 1:
        d = t_hits[0]
        dest, dconf = d, 0.85 if (d in strong or hits[d] >= 2) else 0.75  # one weak keyword is not enough to auto-run
        if dconf < 0.8:
            reasons.append("single weak keyword")
    elif len(t_hits) > 1 and (t_hits[0] in strong and t_hits[1] not in strong):
        dest, dconf = t_hits[0], 0.8
        reasons.append("explicit word wins over weaker hints")
    elif len(t_hits) > 1:
        dest, dconf = t_hits[0], 0.55
        reasons.append("wording matches several destinations")
    else:
        dest, dconf = ("inbox", 0.5)
        reasons.append("no explicit context")
    if WORK_LINK.search(url) and dest != "scholarships":
        dconf = min(dconf, 0.6)
        reasons.append("looks like a work/tooling link")
    words = [w for w in re.sub(URL_RE, "", context or "").split() if w.strip("-–—:|•")]
    if len(words) >= 3:
        instruction, iconf = context.strip(), 0.85
    elif words:
        instruction, iconf = context.strip(), 0.7  # verbatim, so exact-intake checks still match; short -> review
        reasons.append("very short context")
    else:
        instruction, iconf = GENERIC_INSTRUCTION[dest], 0.6 if dest != "inbox" else 0.5
        reasons.append("no wording near URL; generic instruction")
    return dest, dconf, instruction, iconf, "; ".join(reasons)


def build_candidates(items: list[dict]) -> list[dict]:
    """Discovered items -> normalized, deduped candidates with inferred intent and existing-intake checks."""
    cands: dict[str, dict] = {}
    for it in items:
        text = (it.get("title", "") + "\n" + it.get("text", "")).strip()
        for url in dict.fromkeys(URL_RE.findall(text)):
            url = url.rstrip(".,;)")
            ctx = _context_for(url, text, it.get("title", ""))
            err = _valid(url)
            try:
                canon = canonicalize(url)
            except Exception:
                canon, err = url, err or "unparseable"
            dest, dconf, instr, iconf, reason = infer(it.get("container", ""), ctx, url)
            key = f"{canon}|{dest}|{normalize_instruction(instr)}" if not err else f"{canon}|invalid"
            prov = {"origin": it["origin"], "container": it.get("container", ""), "title": it.get("title", ""), "context": ctx}
            if key in cands:  # same URL, same meaning: one candidate, several provenances
                cands[key]["provenance"].append(prov)
                continue
            c = {"id": "", "original_url": url, "canonical_url": canon, "source_origin": it["origin"], "source_container": it.get("container", ""),
                 "source_context": ctx, "inferred_destination": dest, "destination_confidence": round(dconf, 2),
                 "inferred_instruction": instr, "intent_confidence": round(iconf, 2), "reason": reason,
                 "existing_intake_match": "", "status": "ready", "provenance": [prov]}
            if err:
                c["status"], c["reason"] = "invalid", err
            cands[key] = c
    out = []
    for n, c in enumerate(cands.values(), 1):
        c["id"] = f"c{n:03d}"
        if c["status"] == "invalid":
            out.append(c)
            continue
        exact = store.find_exact(dedupe_key(c["canonical_url"], c["inferred_destination"], c["inferred_instruction"]))
        same_url = store.find_by_url(c["canonical_url"])
        if exact:
            c["status"], c["existing_intake_match"] = "existing", exact["id"]
            c["reason"] = f"already ingested as {exact['id']} (same URL, destination, instruction)"
        elif same_url:
            same_dest = [e["id"] for e in same_url if e["destination"] == c["inferred_destination"]]
            c["existing_intake_match"] = ", ".join(e["id"] for e in same_url)
            if same_dest:
                c["status"] = "review"
                c["reason"] += f"; same URL already saved to this destination ({', '.join(same_dest)}) with a different instruction"
            else:
                c["reason"] += f"; same URL saved before with a different intent ({', '.join(e['id'] for e in same_url)}) — OK"
        if c["status"] == "ready" and (c["destination_confidence"] < AUTO_THRESHOLD or c["intent_confidence"] < AUTO_THRESHOLD):
            c["status"] = "review"
        out.append(c)
    return out


# ---------- queue persistence
def _run_dir(run_id: str) -> Path:
    return BULK_DIR / run_id


def new_run(candidates: list[dict], sources: list[str]) -> str:
    run_id = time.strftime("%Y%m%d-%H%M%S")
    d = _run_dir(run_id)
    d.mkdir(parents=True, exist_ok=True)
    (d / "candidates.json").write_text(json.dumps({"run_id": run_id, "created_at": _now(), "sources": sources, "candidates": candidates}, indent=2, ensure_ascii=False))
    BULK_DIR.mkdir(parents=True, exist_ok=True)
    (BULK_DIR / "current").write_text(run_id)
    return run_id


def current_run_id() -> str:
    p = BULK_DIR / "current"
    return p.read_text().strip() if p.exists() else ""


def load_run(run_id: str = "") -> dict:
    run_id = run_id or current_run_id()
    if not run_id:
        raise FileNotFoundError("no bulk run yet: run `linkintake bulk scan`")
    return json.loads((_run_dir(run_id) / "candidates.json").read_text())


def save_run(run: dict) -> None:
    (_run_dir(run["run_id"]) / "candidates.json").write_text(json.dumps(run, indent=2, ensure_ascii=False))


def summary(cands: list[dict]) -> dict:
    s = {"found": len(cands)}
    for st in ("ready", "approved", "review", "existing", "invalid", "skip", "done", "failed"):
        s[st] = sum(1 for c in cands if c["status"] == st)
    return s


# ---------- review actions
def review_update(run: dict, cid: str, *, approve: bool = False, dest: str = "", instruction: str = "", skip: bool = False) -> dict:
    c = next((x for x in run["candidates"] if x["id"] == cid), None)
    if not c:
        raise KeyError(cid)
    if dest:
        from .records import normalize_destination
        c["inferred_destination"] = normalize_destination(dest)
        c["destination_confidence"] = 1.0
    if instruction:
        c["inferred_instruction"] = instruction
        c["intent_confidence"] = 1.0
    if skip:
        c["status"] = "skip"
    elif approve or dest or instruction:
        if c["status"] in ("review", "ready", "existing"):
            c["status"] = "approved"
    return c


# ---------- run
def run_batch(run: dict, *, dry_run: bool = True, limit: int = 0, delay: float = 2.0, statuses=("ready", "approved")) -> dict:
    """Sequential, resumable. Each candidate goes through pipeline.ingest(save=True) exactly like Raycast."""
    from . import pipeline
    todo = [c for c in run["candidates"] if c["status"] in statuses]
    if limit:
        todo = todo[:limit]
    report = {"run_id": run["run_id"], "dry_run": dry_run, "processed": 0, "saved": 0, "merged": 0, "possible_duplicates": 0,
              "already_ingested": summary(run["candidates"])["existing"], "failed": 0, "google_pending": 0, "skipped": summary(run["candidates"])["skip"], "items": []}
    if dry_run:
        report["would_process"] = [{"id": c["id"], "url": c["canonical_url"], "destination": c["inferred_destination"], "instruction": c["inferred_instruction"]} for c in todo]
        return report
    for c in todo:
        try:
            rec = pipeline.ingest(c["original_url"], c["inferred_destination"], c["inferred_instruction"], save=True,
                                  batch={"run_id": run["run_id"], "candidate_id": c["id"], "source_origin": c["source_origin"],
                                         "source_container": c["source_container"], "source_context": c["source_context"]})
            res = rec.get("destination_resolution") or {}
            ex = rec.get("export") or {}
            c.update({"status": "failed" if rec["status"] == "failed" else "done", "record_id": rec["id"], "record_status": rec["status"],
                      "resolution": res.get("action", ""), "export_status": ex.get("status", "")})
            report["processed"] += 1
            if rec["status"] == "failed":
                report["failed"] += 1
            else:
                report["saved"] += 1
                if res.get("action") == "merged":
                    report["merged"] += 1
                if res.get("action") == "possible_duplicate":
                    report["possible_duplicates"] += 1
                if ex.get("status") in ("export_pending", "partial", "not_configured"):
                    report["google_pending"] += 1
        except pipeline.DuplicateError as exc:
            c.update({"status": "existing", "reason": str(exc)})
            report["already_ingested"] += 1
        except Exception as exc:  # never stop the batch
            c.update({"status": "failed", "error": f"{type(exc).__name__}: {exc}"[:300]})
            report["processed"] += 1
            report["failed"] += 1
        report["items"].append({k: c.get(k) for k in ("id", "canonical_url", "inferred_destination", "status", "record_id", "resolution", "export_status", "error")})
        save_run(run)  # resumable after every item
        time.sleep(delay)
    return report
