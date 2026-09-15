"""Infer how much work an instruction needs. Not exposed in the UI."""
from __future__ import annotations

import re

_VISUAL = re.compile(r"\b(look|shot|frame|framing|colou?r|visual|design|outfit|fit|product|identify|what is th|which|brand|font|layout|"
                     r"transition|edit|pacing|aesthetic|slide|scene|angle|camera|lighting|wide|close.?up|b.?roll|composition|"
                     r"style|texture|logo|packaging|wear|shoes|bag|thumbnail|grade|grading|cinematic|motion|movement)\b", re.I)
_TEXT = re.compile(r"\b(say|says|said|quote|metaphor|line|words|phrase|hook|opening|script|caption|story|advice|tip|explain|"
                   r"argument|point|idea|analogy|joke|structure|essay|prompt|question|message|lesson|takeaway|framing)\b", re.I)
_RESEARCH = re.compile(r"\b(identify|what product|which product|brand|model|price|where to buy|find (the|this)|link to|exact|spec)\b", re.I)


def infer(source_class: str, destination: str, instruction: str) -> dict:
    ins = instruction or ""
    if destination == "inbox":
        return {"visual": False, "transcript": False, "research": False, "llm": False}
    visual = destination in {"wishlist", "design_inspo", "personal_ig"} or bool(_VISUAL.search(ins))
    transcript = destination in {"supplement_ideas", "scholarships"} or bool(_TEXT.search(ins)) or not _VISUAL.search(ins)
    research = destination == "wishlist" or bool(_RESEARCH.search(ins))
    if source_class in {"web_page", "google_workspace"}:
        visual = False
    return {"visual": visual, "transcript": transcript, "research": research, "llm": True}
