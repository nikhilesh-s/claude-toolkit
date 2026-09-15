"""Orchestration: classify -> adapter -> depth -> extract -> (save -> export -> cleanup)."""
from __future__ import annotations

import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from . import cleanup, config, depth, destinations, extract, store
from .adapters import direct_file, google_workspace, media_unlocker as mu, video, web_page
from .records import clip, new_record, normalize_destination
from .router import canonicalize, classify


class DuplicateError(RuntimeError):
    pass


def ingest(url: str, destination: str, instruction: str, *, save: bool = False, force: bool = False,
           refresh: bool = False) -> dict:
    dest = normalize_destination(destination)
    canonical = canonicalize(url)
    cls, platform = classify(canonical)
    rec = new_record(original_url=url.strip(), canonical_url=canonical, source_class=cls, platform=platform,
                     destination=dest, instruction=instruction.strip())
    rec["duplicate_of"] = [e["id"] for e in store.find_by_url(canonical)]
    exact = store.find_exact(rec["dedupe_key"])
    rec["exact_duplicate"] = exact["id"] if exact else ""

    flags = depth.infer(cls, dest, instruction)
    rec["processing"]["depth"] = flags
    images: list[Path] = []
    documents: list[Path] = []
    try:
        _run_adapter(rec, flags, images, documents, refresh)
    except Exception as exc:  # adapter failure = record still saved, marked failed
        rec["errors"].append(f"adapter: {type(exc).__name__}: {str(exc)[:400]}")
        rec["status"] = "failed"

    if rec["status"] != "failed" and flags["llm"]:
        try:
            out, backend = extract.run(rec, flags, images, documents)
            rec["processing"]["llm_backend"] = backend
            if backend == "claude":
                rec["processing"]["claude_profile"] = __import__("os").path.expanduser(config.load()["llm"].get("claude_config_dir") or "~/.claude-nebula")
            rec["source"]["title"] = rec["source"]["title"] or out["title"]
            rec["source"]["creator"] = rec["source"]["creator"] or out["creator"]
            rec["context"]["short_source_summary"] = out["short_source_summary"]
            rec["context"]["visual_notes"] = out["visual_notes"]
            rec["extraction"] = {"takeaways": out["takeaways"], "focused_result": out["focused_result"],
                                 "uncertainty": out["uncertainty"], "structured_data": out["structured_data"],
                                 "confidence": out["confidence"]}
            rec["status"] = "needs_review" if (out["needs_review"] or out["confidence"] < 0.6) else "ready"
            if out["review_reason"]:
                rec["errors"].append(f"review: {out['review_reason']}")
        except Exception as exc:
            rec["errors"].append(f"llm: {type(exc).__name__}: {str(exc)[:400]}")
            rec["processing"]["llm_backend"] = "none"
            _heuristic_fill(rec)
    elif rec["status"] != "failed":
        rec["processing"]["llm_backend"] = "skipped"
        _heuristic_fill(rec)

    store.write_pending(rec)
    return save_record(rec["id"], force=force) if save else rec


def _heuristic_fill(rec: dict) -> None:
    c = rec["context"]
    if not c["short_source_summary"]:
        c["short_source_summary"] = clip(c.get("caption_or_text") or c.get("transcript") or rec["source"].get("title", ""), 400)
    rec["status"] = "needs_review"


def _run_adapter(rec: dict, flags: dict, images: list[Path], documents: list[Path], refresh: bool) -> None:
    cls, url = rec["source"]["source_class"], rec["source"]["original_url"]
    rec["processing"]["adapter"] = cls
    if cls == "social_media":
        _via_media_unlocker(rec, url, flags["visual"], images, refresh)
    elif cls == "video":
        meta = video.metadata(url)
        _apply_meta(rec, meta.get("title"), meta.get("uploader"), meta.get("upload_date"), meta.get("description"))
        if meta.get("chapters"):
            rec["context"]["caption_or_text"] += "\n\nChapters: " + " / ".join(meta["chapters"])
        if flags["transcript"]:
            try:
                rec["context"]["transcript"] = video.transcript(url)
            except Exception as exc:
                rec["errors"].append(f"transcript: {str(exc)[:200]}")
        if flags["visual"]:
            try:
                _via_media_unlocker(rec, url, True, images, refresh)
            except Exception as exc:
                rec["errors"].append(f"visual: {str(exc)[:200]}")
    elif cls == "web_page":
        ctype, body, final = web_page.fetch(url)
        if ctype == "application/pdf":
            rec["source"]["source_class"] = "direct_file"
            _pdf(rec, url, documents)
        elif ctype.startswith(("image/", "video/")):
            rec["source"]["source_class"] = "direct_file"
            _via_media_unlocker(rec, url, True, images, refresh)
        else:
            page = web_page.parse_html(body)
            _apply_meta(rec, page["title"], page["author"], page["published"], (page["description"] + "\n\n" + page["text"]).strip())
    elif cls == "google_workspace":
        doc = google_workspace.read(url)
        _apply_meta(rec, doc["title"], doc["creator"], doc["published"], doc["text"])
    elif cls == "direct_file":
        info = direct_file.head(url)
        ct = info["content_type"] or ""
        if ct == "application/pdf" or url.lower().endswith(".pdf"):
            _pdf(rec, url, documents)
        elif ct.startswith(("image/", "video/")) or url.lower().rsplit(".", 1)[-1] in {"jpg", "jpeg", "png", "webp", "gif", "mp4", "mov", "webm"}:
            _via_media_unlocker(rec, url, True, images, refresh)
        else:
            _apply_meta(rec, url.rsplit("/", 1)[-1], "", "", f"[{ct or 'file'}, {info['size']} bytes]")
    else:
        raise ValueError("unknown source class")


def _apply_meta(rec: dict, title, creator, published, text) -> None:
    s = rec["source"]
    s["title"] = s["title"] or (title or "")
    s["creator"] = s["creator"] or (creator or "")
    if published and not s["published_at"]:
        p = str(published)
        s["published_at"] = f"{p[:4]}-{p[4:6]}-{p[6:8]}" if len(p) == 8 and p.isdigit() else p
    if text:
        rec["context"]["caption_or_text"] = (rec["context"]["caption_or_text"] + "\n\n" + text).strip()


def _pdf(rec: dict, url: str, documents: list[Path]) -> None:
    p = direct_file.download_pdf(url, rec["id"])
    rec["artifacts"]["tmp_pdf"] = str(p)
    documents.append(p)
    _apply_meta(rec, url.rsplit("/", 1)[-1], "", "", "")


def _via_media_unlocker(rec: dict, url: str, need_visual: bool, images: list[Path], refresh: bool) -> None:
    pre = mu.job_preexisting(url)
    manifest = mu.unlock(url, refresh=refresh)
    jid = manifest["job_id"]
    rec["artifacts"]["media_unlocker_job_id"] = jid
    rec["artifacts"]["job_preexisting"] = pre
    rec["processing"]["resolver"] = manifest.get("resolver", "")
    info = mu.read_info(jid)
    meta = manifest.get("metadata", {})
    _apply_meta(rec, info.get("title") or meta.get("title"), info.get("uploader") or info.get("channel") or meta.get("uploader") or meta.get("username"),
                info.get("upload_date") or meta.get("date"), info.get("description") or info.get("caption") or meta.get("description") or meta.get("caption"))
    if info.get("duration"):
        rec["context"]["caption_or_text"] += f"\n\n[duration: {info['duration']}s]"
    if need_visual:
        sheet = mu.contact_sheet(jid)
        store.PREVIEWS.mkdir(parents=True, exist_ok=True)
        raw = config.STATE_DIR / "tmp" / f"{rec['id']}-sheet.jpg"
        raw.parent.mkdir(parents=True, exist_ok=True)
        raw.write_bytes(sheet)
        preview = store.PREVIEWS / f"{rec['id']}.jpg"
        if shutil.which("ffmpeg"):
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(raw), "-vf", "scale='min(1280,iw)':-2", "-q:v", "6", str(preview)], check=False)
        if not preview.exists():
            preview.write_bytes(sheet)
        rec["artifacts"]["contact_sheet"] = str(preview)
        rec["artifacts"]["tmp_sheet"] = str(raw)
        frames = sorted((mu.job_dir(jid) / "preview").glob("frame-*.jpg"))
        if _image_width(raw) < 1000 and len(frames) > 1:
            # Older cached jobs have a one-frame "sheet"; hand the model the frames themselves.
            images.extend(frames[:12])
            rec["processing"]["visual_input"] = f"{min(len(frames), 12)} frames"
            rec["artifacts"]["frames"] = _frame_times(jid, frames[:12], info.get("duration"))
        else:
            images.append(raw)
            rec["processing"]["visual_input"] = "contact sheet"


def _frame_times(jid: str, frames: list[Path], info_duration) -> list[dict]:
    """Approximate timestamp per sampled frame. Media Unlocker samples frames evenly between a small margin;
    we mirror that formula using the media duration (ffprobe while the file is still cached, else resolver
    metadata). Unknown duration -> frames listed in order with no time."""
    duration = 0.0
    media = [p for p in (mu.job_dir(jid) / "media").glob("**/*") if p.is_file() and p.suffix.lower() in {".mp4", ".mov", ".mkv", ".webm"}]
    if media:
        proc = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(media[0])],
                              capture_output=True, text=True, check=False)
        try:
            duration = float(proc.stdout.strip())
        except ValueError:
            duration = 0.0
    if duration <= 0 and info_duration:
        try:
            duration = float(info_duration)
        except (TypeError, ValueError):
            duration = 0.0
    n = len(frames)
    if duration <= 0.5 or n < 2:
        return [{"file": f.name, "t": ""} for f in frames]
    margin = min(0.4, duration * 0.05)
    usable = max(0.1, duration - 2 * margin)
    out = []
    for i, f in enumerate(frames):
        t = margin + usable * i / (n - 1)
        out.append({"file": f.name, "t": f"{int(t // 60)}:{int(t % 60):02d}", "seconds": round(t, 1)})
    return out


def _image_width(path: Path) -> int:
    proc = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width",
                           "-of", "csv=p=0", str(path)], capture_output=True, text=True, check=False)
    try:
        return int(proc.stdout.strip() or 0)
    except ValueError:
        return 0


def save_record(record_id: str, force: bool = False) -> dict:
    rec = store.load(record_id)
    if rec.get("saved_at") and not force:
        raise DuplicateError(f"{record_id} is already saved. Use --force to export it again.")
    if rec.get("exact_duplicate") and not force:
        raise DuplicateError(f"Already saved as {rec['exact_duplicate']} (same URL + destination + instruction). Use --force to save anyway.")
    rec["export"] = destinations.export(rec)
    rec["saved_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    store.save(rec)  # record file + index line
    rec["cleanup"] = cleanup.cleanup_record(rec)
    store.write(rec)  # refresh the file only
    return rec


def mark_exported(record_id: str, master_url: str = "", destination_url: str = "", note: str = "") -> dict:
    """Called after Claude (or a person) exported the record through the Drive connector."""
    rec = store.load(record_id)
    rec["export"] = {"status": "exported", "via": "claude", "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                     "master": {"ok": True, "url": master_url}, "destination": {"ok": True, "url": destination_url}, "note": note}
    store.write(rec)
    return rec


def export_rest(record_id: str) -> dict:
    """Optional fallback: push one saved record through the stdlib Google REST client."""
    rec = store.load(record_id)
    cfg = config.load()
    cfg["google"]["export_mode"] = "rest"
    config.save(cfg)
    rec["export"] = destinations.export(rec)
    store.write(rec)
    return rec


def reprocess(record_id: str, instruction: str | None = None, destination: str | None = None, refresh: bool = False) -> dict:
    old = store.load(record_id)
    new = ingest(old["source"]["original_url"], destination or old["intent"]["destination"],
                 instruction if instruction is not None else old["intent"]["user_instruction"], refresh=refresh)
    (store.PENDING / f"{record_id}.json").unlink(missing_ok=True)
    return new
