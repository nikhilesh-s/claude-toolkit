"""Offline checks: canonicalization, classification, dedupe identity, depth inference. Run: uv run python tests/test_router.py"""
from linkintake.depth import infer
from linkintake.records import dedupe_key, normalize_destination
from linkintake.router import canonicalize, classify

REEL = "https://www.instagram.com/reel/DalkeLOBAmg/?igsi=NTc4MTIwNjQ2YQ=="


def main() -> None:
    assert canonicalize(REEL) == "https://www.instagram.com/reel/DalkeLOBAmg/"
    assert canonicalize("instagram.com/reel/DalkeLOBAmg?igshid=abc") == "https://www.instagram.com/reel/DalkeLOBAmg/"
    assert canonicalize("https://youtu.be/jNQXAC9IVRw?si=xyz") == "https://www.youtube.com/watch?v=jNQXAC9IVRw"
    assert canonicalize("https://m.youtube.com/watch?v=jNQXAC9IVRw&feature=share&t=42") == "https://www.youtube.com/watch?v=jNQXAC9IVRw&t=42"
    assert canonicalize("https://www.youtube.com/shorts/abc123") == "https://www.youtube.com/watch?v=abc123"
    assert canonicalize("https://example.com/article/?utm_source=x&id=5") == "https://example.com/article?id=5"
    assert canonicalize("https://docs.google.com/document/d/ABC/edit?tab=t.0") == "https://docs.google.com/document/d/ABC/edit?tab=t.0"

    assert classify(REEL) == ("social_media", "instagram")
    assert classify("https://www.tiktok.com/@u/video/1") == ("social_media", "tiktok")
    assert classify("https://x.com/a/status/1") == ("social_media", "x")
    assert classify("https://www.youtube.com/watch?v=1") == ("video", "youtube")
    assert classify("https://vimeo.com/1") == ("video", "vimeo")
    assert classify("https://docs.google.com/spreadsheets/d/1/edit") == ("google_workspace", "google_sheets")
    assert classify("https://drive.google.com/file/d/1/view") == ("google_workspace", "google_drive")
    assert classify("https://site.org/paper.pdf") == ("direct_file", "site.org")
    assert classify("https://www.nytimes.com/2026/01/01/x.html") == ("web_page", "nytimes.com")

    # same source, different intent = different record; same everything = duplicate (case/punct-insensitive)
    a = dedupe_key(canonicalize(REEL), "design_inspo", "love camera movement at 0:12")
    b = dedupe_key(canonicalize(REEL), "supplement_ideas", "love metaphor from opening line")
    c = dedupe_key(canonicalize(REEL), "design_inspo", "Love camera movement at 0:12!")
    assert a != b and a == c

    assert normalize_destination("Personal Instagram Inspiration") == "personal_ig"
    assert normalize_destination("Inbox / Unsorted") == "inbox"
    assert normalize_destination("supplement ideas") == "supplement_ideas"

    assert infer("social_media", "personal_ig", "I like the cinematic wide shots and pacing")["visual"]
    assert not infer("social_media", "supplement_ideas", "I like this metaphor")["visual"]
    assert infer("social_media", "supplement_ideas", "I like this metaphor")["transcript"]
    assert infer("social_media", "wishlist", "identify this product")["research"]
    assert not infer("web_page", "inbox", "")["llm"]
    print("test_router: ok")


if __name__ == "__main__":
    main()
