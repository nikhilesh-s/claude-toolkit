"""LLM extraction. Backends: Anthropic SDK (ANTHROPIC_API_KEY / ANTHROPIC_AUTH_TOKEN), the `claude` CLI
(uses your Claude login), or none (record is saved as needs_review with raw context)."""
from __future__ import annotations

import base64
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from . import config
from .records import DESTINATIONS, clip

SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string", "description": "Best title for the source, or empty"},
        "creator": {"type": "string", "description": "Author/creator/handle, or empty"},
        "short_source_summary": {"type": "string", "description": "2-4 sentences: what the whole source is about"},
        "takeaways": {"type": "array", "items": {"type": "string"},
                      "description": "4-6 strongest actionable takeaways answering Nik's instruction, one sentence each, grounded in evidence"},
        "focused_result": {"type": "string", "description": "The full answer to Nik's instruction, grounded in the source. Detailed, reusable; bullets welcome"},
        "uncertainty": {"type": "string", "description": "One or two sentences on what the evidence could NOT establish (missing transcript, stills only, timing unknown); empty if none"},
        "tags": {"type": "array", "items": {"type": "string"}, "description": "1-4 short tags. Supplement Ideas: use the given vocabulary. Others: loose, lowercase categories"},
        "visual_notes": {"type": "string", "description": "What the frames/images show that matters for the instruction; empty if no visuals"},
        "structured_data": {
            "type": "array",
            "items": {"type": "object", "properties": {"field": {"type": "string"}, "value": {"type": "string"}},
                      "required": ["field", "value"], "additionalProperties": False},
        },
        "confidence": {"type": "number", "description": "0-1, how well the source supports the focused_result"},
        "needs_review": {"type": "boolean"},
        "review_reason": {"type": "string"},
    },
    "required": ["title", "creator", "short_source_summary", "takeaways", "focused_result", "uncertainty", "tags", "visual_notes",
                 "structured_data", "confidence", "needs_review", "review_reason"],
    "additionalProperties": False,
}

SYSTEM = """You are the extraction step of Nik's personal link-intake system.
Nik pastes a URL, picks a destination, and writes a short instruction saying what they care about.
You get the whole source context (caption, transcript, page text, and/or a contact sheet of video frames in
time order, left-to-right then top-to-bottom). Understand the whole source, but the saved result must focus on
Nik's instruction. Never invent details the source does not support; say what is uncertain instead.
Write for future-Nik: enough context to remember why this was saved, no filler. Output must match the JSON schema.

Output hierarchy: short_source_summary (1-3 sentences) -> takeaways (4-6 strongest, one sentence each; these are the
first screen) -> focused_result (the full detail) -> visual_notes (frame-by-frame, cite frame times when given).
Confidence means: how confident are we that the focused extraction accurately answers Nik's instruction from the
evidence available. 0.85+ only when the requested detail was directly observed; 0.6-0.8 when mostly observed with
gaps; below 0.6 when key parts are inferred or unobservable. Do not inflate when only still frames exist, when the
transcript is missing, or when the requested detail (cut timing, camera motion, audio) cannot be seen in stills.
Make pacing, cut-length, or camera-motion claims only when frame times or sequence support them; otherwise say so
in uncertainty."""

GUIDANCE = {
    "wishlist": """Destination: Wishlist (structured). Fill structured_data with these fields when supported by evidence:
product_item, brand, model, variant (the purchase choice: color/size/wattage, e.g. "Navy" or "65W"), color_style,
size_spec, price, identifier (ASIN/SKU/model number if visible or found), product_url (official or retailer page if
found), notes. Use "exact model TBD" when the product is recognizable but the exact model is not supported. Only
give a price if it is visible in the source or confirmed by targeted research. Never guess model, variant, or price.""",
    "scholarships": """Destination: Scholarships (structured). Fill structured_data with: scholarship (program name without the
year), organization, cycle_year (application cycle, e.g. 2027, from the deadline or page), deadline, amount,
eligibility, required_materials, link, notes. Leave a field empty rather than guessing. Dates as ISO if possible.""",
    "supplement_ideas": """Destination: Supplement Ideas (college supplemental essays / content bank). Prioritize the specific idea Nik
pointed at (metaphor, framing, line, structure). Quote or closely paraphrase it, then say in 1-3 sentences why it works
and how it could be reused. structured_data may be empty. tags: pick from Personal Statement, Why Major, Intellectual
Curiosity, Community, Identity / Background, Challenge / Growth, Roommate / Personality, Activity / Impact,
School-specific, Writing Style / Structure, Other (several allowed).""",
    "design_inspo": """Destination: Design Inspo. Focus on the visual/design concept Nik named: layout, type, color, motion, spacing,
composition. Describe it concretely enough to recreate. structured_data fields when supported: what_stood_out,
reusable_ideas, visual_notes. tags: loose categories (e.g. typography, layout, motion, color, ui, packaging).""",
    "personal_ig": """Destination: Personal Instagram Inspiration (Nik's own content: lifestyle, filmmaking, photography, editing,
framing, transitions, aesthetics). Do not summarize the whole post; answer the instruction with concrete, reusable
technique notes (shot types, pacing, cuts, timing, light, movement). structured_data fields, only those supported:
format, key_shots, composition, lighting_color, transitions_sequence, pacing_editing, hooks_text,
techniques_to_recreate, unknowns. tags: loose (e.g. filming, editing, hooks, captions, lifestyle).""",
    "inbox": "Destination: Inbox. Minimal: summarize and preserve context.",
}


def _user_text(rec: dict, flags: dict, attachments: list[str]) -> str:
    s, c, i = rec["source"], rec["context"], rec["intent"]
    parts = [
        f"SOURCE: {s['original_url']}\nsource_class: {s['source_class']} | platform: {s['platform']}",
        f"title: {s.get('title') or '(unknown)'} | creator: {s.get('creator') or '(unknown)'} | published: {s.get('published_at') or '(unknown)'}",
        f"DESTINATION: {DESTINATIONS[i['destination']]}",
        f"NIK'S INSTRUCTION (verbatim): {i['user_instruction']}",
        GUIDANCE[i["destination"]],
    ]
    if c.get("caption_or_text"):
        parts.append("CAPTION / PAGE TEXT:\n" + clip(c["caption_or_text"], 24000))
    if c.get("transcript"):
        parts.append("TRANSCRIPT:\n" + clip(c["transcript"], 16000))
    frames = rec.get("artifacts", {}).get("frames") or []
    if frames:
        timing = ", ".join(f"{f['file']}≈{f['t']}" if f.get("t") else f["file"] for f in frames)
        parts.append("FRAME TIMING (approximate; sampled evenly across the video" + ("" if frames[0].get("t") else ", duration unknown") + "): " + timing)
    if attachments:
        parts.append("ATTACHED FILES (read/view every one; frame-NN.jpg files are video frames in time order, a "
                     "contact-sheet is a grid of frames left-to-right, top-to-bottom): " + ", ".join(attachments))
    if flags.get("research"):
        parts.append("You may do a few targeted web searches only to resolve identification from visible clues "
                     "(brand, model text, logos). Prefer official/retailer pages. Do not research beyond the instruction.")
    if not c.get("caption_or_text") and not c.get("transcript") and not attachments:
        parts.append("NOTE: little source context was available; be explicit about uncertainty and set needs_review=true.")
    return "\n\n".join(parts)


def choose_backend(cfg: dict) -> str:
    b = cfg["llm"]["backend"]
    if b != "auto":
        return b
    if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        return "anthropic"
    if shutil.which("claude") or Path(cfg["llm"]["claude_cli"]).exists():
        return "claude"
    return "none"


def run(rec: dict, flags: dict, images: list[Path], documents: list[Path]) -> tuple[dict, str]:
    """Return (extraction dict matching SCHEMA, backend name). Raises on hard failure."""
    cfg = config.load()
    backend = choose_backend(cfg)
    if backend == "none":
        raise RuntimeError("No LLM backend: set ANTHROPIC_API_KEY or install/login the claude CLI")
    text = _user_text(rec, flags, [str(p) for p in images + documents] if backend == "claude" else [])
    out = _anthropic(cfg, text, flags, images, documents) if backend == "anthropic" else _claude_cli(cfg, text, flags)
    return _normalize(out), backend


def _normalize(out: dict) -> dict:
    sd = out.get("structured_data")
    if isinstance(sd, list):
        out["structured_data"] = {d.get("field", "").strip(): d.get("value", "").strip() for d in sd if isinstance(d, dict) and d.get("field")}
    elif not isinstance(sd, dict):
        out["structured_data"] = {}
    try:
        out["confidence"] = max(0.0, min(1.0, float(out.get("confidence", 0))))
    except (TypeError, ValueError):
        out["confidence"] = 0.0
    for k in ("title", "creator", "short_source_summary", "focused_result", "visual_notes", "review_reason", "uncertainty"):
        out[k] = str(out.get(k) or "")
    tg = out.get("tags")
    out["tags"] = [str(t).strip() for t in tg if str(t).strip()][:6] if isinstance(tg, list) else []
    tk = out.get("takeaways")
    out["takeaways"] = [str(t).strip() for t in tk if str(t).strip()][:6] if isinstance(tk, list) else []
    out["needs_review"] = bool(out.get("needs_review"))
    return out


def _anthropic(cfg: dict, text: str, flags: dict, images: list[Path], documents: list[Path]) -> dict:
    import anthropic

    client = anthropic.Anthropic()
    content: list[dict] = []
    for p in images:
        content.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                                     "data": base64.standard_b64encode(p.read_bytes()).decode()}})
    for p in documents:
        content.append({"type": "document", "source": {"type": "base64", "media_type": "application/pdf",
                                                        "data": base64.standard_b64encode(p.read_bytes()).decode()}})
    content.append({"type": "text", "text": text})
    kwargs: dict = dict(model=cfg["llm"]["model"], max_tokens=8000, system=SYSTEM,
                        messages=[{"role": "user", "content": content}],
                        output_config={"format": {"type": "json_schema", "schema": SCHEMA}})
    if flags.get("research"):
        kwargs["tools"] = [{"type": "web_search_20260209", "name": "web_search", "max_uses": 4}]
    try:
        # Server-side refusal fallback (opt-in per Anthropic guidance for Opus 5-class models).
        resp = client.beta.messages.create(betas=["server-side-fallback-2026-07-01"], fallbacks="default", **kwargs)
    except TypeError:
        resp = client.messages.create(**kwargs)
    if resp.stop_reason == "refusal":
        raise RuntimeError("model refused the extraction request")
    texts = [b.text for b in resp.content if getattr(b, "type", "") == "text"]
    if not texts:
        raise RuntimeError("no text block in model response")
    return _parse_json(texts[-1])


def resolve_claude(cfg: dict) -> str:
    """Absolute path to the claude binary, independent of the caller's PATH (Raycast's is bare)."""
    configured = cfg["llm"].get("claude_cli") or ""
    for cand in (configured, shutil.which("claude"), "/opt/homebrew/bin/claude", "/usr/local/bin/claude",
                 os.path.expanduser("~/.local/bin/claude")):
        if cand and Path(cand).exists():
            return cand
    return "claude"


def claude_env(cfg: dict) -> dict:
    """A clean environment that always points claude at the configured Claude profile, whatever launched us.
    Strips every CLAUDE_CODE*/CLAUDECODE var (so a parent Claude session can't leak its own session/profile)
    and guarantees the Homebrew bin dir is on PATH."""
    env = {k: v for k, v in os.environ.items()
           if k != "CLAUDECODE" and not k.startswith("CLAUDE_CODE") and k != "CLAUDE_CONFIG_DIR"}
    profile = os.path.expanduser(cfg["llm"].get("claude_config_dir") or "~/.claude-nebula")
    env["CLAUDE_CONFIG_DIR"] = profile
    # Raycast's extension runtime strips USER/LOGNAME. claude keys its Keychain credential item by the
    # USER name; without it the lookup targets account "unknown" and reports "Not logged in".
    import pwd
    user = pwd.getpwuid(os.getuid()).pw_name
    env.setdefault("USER", user)
    env.setdefault("LOGNAME", user)
    env.setdefault("HOME", os.path.expanduser("~"))
    env.setdefault("SHELL", "/bin/zsh")
    parts = env.get("PATH", "").split(os.pathsep)
    for extra in (os.path.expanduser("~/.local/bin"), "/usr/local/bin", "/opt/homebrew/bin"):
        if extra not in parts:
            parts.insert(0, extra)
    env["PATH"] = os.pathsep.join(p for p in parts if p)
    return env


def _claude_cli(cfg: dict, text: str, flags: dict) -> dict:
    exe = resolve_claude(cfg)
    tools = ["Read"] + (["WebSearch"] if flags.get("research") else [])
    cmd = [exe, "-p", "--output-format", "json", "--json-schema", json.dumps(SCHEMA), "--model", cfg["llm"]["model"],
           "--allowedTools", *tools, "--max-turns", "8", "--strict-mcp-config", "--append-system-prompt", SYSTEM]
    env = claude_env(cfg)
    proc = subprocess.run(cmd, input=text, text=True, capture_output=True, timeout=600, env=env, check=False)
    _debug_dump(exe, cmd, env, proc)
    raw = proc.stdout.strip() or proc.stderr.strip()
    try:
        d = json.loads(raw)
    except json.JSONDecodeError:
        raise RuntimeError(f"claude CLI returned non-JSON: {raw[:200]}") from None
    if d.get("is_error"):
        raise RuntimeError(f"claude CLI [{env.get('CLAUDE_CONFIG_DIR')}]: {d.get('result', d)}"[:300])
    if isinstance(d.get("structured_output"), dict):
        return d["structured_output"]
    return _parse_json(str(d.get("result", "")))


def _debug_dump(exe: str, cmd: list[str], env: dict, proc) -> None:
    """Write what the last claude invocation actually saw to ~/.link-intake/debug/claude-last.json.
    Lets us prove which binary/profile/env a Raycast-spawned run used. Secrets are masked."""
    try:
        import getpass
        import platform
        from . import __version__
        d = config.STATE_DIR / "debug"
        d.mkdir(parents=True, exist_ok=True)
        masked = {k: ("<masked>" if any(t in k.upper() for t in ("KEY", "TOKEN", "SECRET", "PASS")) else v) for k, v in env.items()}
        (d / "claude-last.json").write_text(json.dumps({
            "linkintake_version": __version__, "linkintake_source": str(Path(__file__).resolve().parent),
            "python": platform.python_version(), "ppid": os.getppid(), "pid": os.getpid(),
            "cwd": os.getcwd(), "user": getpass.getuser(), "uid": os.getuid(),
            "exe": exe, "exe_real": str(Path(exe).resolve()) if Path(exe).exists() else "",
            "claude_config_dir": env.get("CLAUDE_CONFIG_DIR"), "argv": cmd[:6] + ["…"],
            "env": masked, "returncode": proc.returncode,
            "stdout_head": proc.stdout[:1200], "stderr": proc.stderr[-4000:],
        }, indent=2, ensure_ascii=False))
    except Exception:
        pass


def _parse_json(s: str) -> dict:
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", s, re.S)
        if not m:
            raise RuntimeError("model output was not JSON") from None
        return json.loads(m.group(0))
