"""Canonical intake record. One shape, every adapter fills what it can."""
from __future__ import annotations

import hashlib
import re
import secrets
import time
from datetime import datetime, timezone

DESTINATIONS = {
    "wishlist": "Wishlist",
    "supplement_ideas": "Supplement Ideas",
    "design_inspo": "Design Inspo",
    "scholarships": "Scholarships",
    "personal_ig": "Personal Instagram Inspiration",
    "inbox": "Inbox / Unsorted",
}
STRUCTURED_DESTINATIONS = {"wishlist", "scholarships"}
STATUSES = ("ready", "needs_review", "failed")


def normalize_destination(value: str) -> str:
    v = (value or "").strip().lower()
    if v in DESTINATIONS:
        return v
    for key, title in DESTINATIONS.items():
        if v == title.lower() or v.replace(" ", "_") == key:
            return key
    aliases = {"ig": "personal_ig", "instagram": "personal_ig", "personal instagram": "personal_ig",
               "supplements": "supplement_ideas", "supplement": "supplement_ideas",
               "design": "design_inspo", "scholarship": "scholarships", "unsorted": "inbox"}
    if v in aliases:
        return aliases[v]
    raise ValueError(f"Unknown destination {value!r}. Options: {', '.join(DESTINATIONS)}")


def normalize_instruction(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", "", (text or "").lower()).strip()


def dedupe_key(canonical_url: str, destination: str, instruction: str) -> str:
    raw = f"{canonical_url}|{destination}|{normalize_instruction(instruction)}"
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


def new_id() -> str:
    return time.strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(3)


def new_record(*, original_url: str, canonical_url: str, source_class: str, platform: str,
               destination: str, instruction: str) -> dict:
    return {
        "id": new_id(),
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": {
            "original_url": original_url,
            "canonical_url": canonical_url,
            "source_class": source_class,
            "platform": platform,
            "title": "",
            "creator": "",
            "published_at": "",
        },
        "intent": {"destination": destination, "user_instruction": instruction},  # verbatim
        "context": {
            "short_source_summary": "",
            "caption_or_text": "",
            "transcript": "",
            "visual_notes": "",
        },
        # confidence = how confident we are that focused_result answers the instruction from the available evidence (0-1)
        "extraction": {"takeaways": [], "focused_result": "", "uncertainty": "", "structured_data": {}, "confidence": 0.0},
        "artifacts": {"contact_sheet": "", "media_unlocker_job_id": "", "job_preexisting": None, "frames": []},
        "processing": {"depth": {}, "llm_backend": "", "adapter": ""},
        "export": {},
        "errors": [],
        "status": "needs_review",
        "duplicate_of": [],
        "dedupe_key": dedupe_key(canonical_url, destination, instruction),
    }


def clip(text: str, n: int) -> str:
    text = (text or "").strip()
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"
