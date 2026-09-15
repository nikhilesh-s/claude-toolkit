"""Heavy media is cache. After a successful save we drop the media files and per-frame JPEGs of jobs
*this* intake created, keeping manifest.json, resolver metadata (*.json) and contact-sheet.jpg so the
source can be re-downloaded later. Jobs that existed before intake (e.g. the 10-Reel regression set) are never touched."""
from __future__ import annotations

from pathlib import Path

from . import config
from .adapters import media_unlocker as mu


def cleanup_job(job_id: str) -> dict:
    d = mu.job_dir(job_id)
    removed, freed = [], 0
    if not d.exists():
        return {"removed": 0, "bytes": 0}
    for p in (d / "media").glob("**/*"):
        if p.is_file() and p.suffix.lower() != ".json":
            freed += p.stat().st_size
            p.unlink()
            removed.append(p.name)
    for p in (d / "preview").glob("frame-*.jpg"):
        freed += p.stat().st_size
        p.unlink()
        removed.append(p.name)
    return {"removed": len(removed), "bytes": freed}


def cleanup_record(rec: dict) -> dict:
    out: dict = {"skipped": True}
    if not config.load()["cleanup"]["enabled"]:
        return out
    art = rec.get("artifacts", {})
    if art.get("media_unlocker_job_id") and art.get("job_preexisting") is False:
        out = cleanup_job(art["media_unlocker_job_id"])
    for key in ("tmp_pdf", "tmp_sheet"):
        if art.get(key):
            Path(art[key]).unlink(missing_ok=True)
    return out
