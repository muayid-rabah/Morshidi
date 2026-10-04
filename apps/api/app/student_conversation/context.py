"""Bounded, non-authoritative context from explicitly stated planning preferences."""

import re
from typing import Mapping


def extract_explicit_preferences(message: str) -> dict[str, str]:
    """Conservative extraction only; never derive academic facts or sensitive traits."""
    normalized = message.casefold().translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789"))
    if not re.search(r"\b(i want|i prefer|i changed my mind|i'll take|اريد|أريد|بدي|أفضل)\b", normalized):
        return {}
    found: dict[str, str] = {}
    for regular in re.finditer(r"\b(\d{1,2})\s*(?:credits?|hours?|ساعة|ساعات)\b", normalized):
        prefix = normalized[max(0, regular.start() - 30):regular.start()]
        # A summer-only statement must not silently replace the regular load.
        if re.search(r"(?:summer|صيفي|الصيفي)\s*$", prefix):
            continue
        if 3 <= int(regular.group(1)) <= 30:
            found["regular_load"] = regular.group(1)
    summer = re.search(r"(?:summer|صيفي|الصيفي).{0,30}?(\d{1,2})(?:\s*(?:credits?|hours?|ساعة|ساعات))?", normalized)
    if summer and 3 <= int(summer.group(1)) <= 9:
        found["summer_enabled"] = "true"
        found["summer_load"] = summer.group(1)
    elif re.search(r"(?:no summer|without summer|بدون صيفي)", normalized):
        found["summer_enabled"] = "false"
    # Explicit pace statements only; no inference from grades or student traits.
    pace_patterns = {"FASTEST": r"fastest|أسرع|اسرع", "BALANCED": r"balanced|متوازن",
                     "LOWER_LOAD": r"lower load|lighter load|حمل أخف|حمل اخف"}
    matches = [(match.start(), pace) for pace, pattern in pace_patterns.items()
               for match in re.finditer(pattern, normalized)]
    if matches:
        found["graduation_pace"] = max(matches)[1]
    return found


def bounded_conversation_context(preferences: Mapping[str, str], recent: list[str],
                                 summary: str | None = None) -> str:
    """No transcript dump, authoritative facts, hidden reasoning or raw logs."""
    safe = {key: value for key, value in preferences.items()
            if key in {"regular_load", "summer_enabled", "summer_load", "graduation_pace"}}
    preference_summary = "; ".join(f"{key}={safe[key]}" for key in sorted(safe))
    snippets = [item.replace("\n", " ")[:180] for item in recent[-4:]]
    safe_summary = (summary or "").replace("\n", " ")[:800]
    return (f"USER_STATED planning preferences: {preference_summary or 'none'}\n"
            f"CHAT_DERIVED bounded summary (not academic facts): {safe_summary or 'none'}\n"
            f"CHAT_DERIVED recent topics (not academic facts): {' | '.join(snippets)}")[:1600]
