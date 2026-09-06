"""A lightweight, dependency-free help assistant.

This is deliberately NOT a machine learning model and NOT an LLM. It is a
plain-text search over two sources:

1. A curated FAQ knowledge base (below) covering how the tool works, what
   its statuses mean, and how to use its features.
2. The engineer's OWN currently-calculated results — the exact audit
   messages and limitations already produced by the calc engine for
   whatever they've run this session.

It uses only Python's standard library (difflib) — no API key, no external
service, no ongoing cost, works fully offline.

Hard scope boundary: this module answers questions about HOW THE TOOL
WORKS. It never generates a new engineering opinion, never judges whether
a design is adequate beyond what the calc engine already decided, and
every answer that touches a real design check is a direct quote of text
the calc engine already produced — never a new sentence invented about
the engineering itself.
"""
from __future__ import annotations

import difflib
from typing import Dict, List, Optional, Tuple

FAQ: List[Dict[str, str]] = [
    {
        "id": "status-meaning",
        "keywords": "pass fail warning not checked status mean meaning green red audit label explain thing deal understand",
        "question": "What do PASS, FAIL, WARNING and NOT CHECKED mean?",
        "answer": (
            "PASS: this specific check was performed and the member is adequate for it. "
            "FAIL: this specific check was performed and the member is NOT adequate — a suggestion "
            "for what to change is usually shown. WARNING: worth a closer look, but not necessarily "
            "a failure. NOT CHECKED: this version of the tool does not perform this particular check "
            "yet — it is not a pass and not a fail, it's an honest gap that still needs independent "
            "verification before construction."
        ),
    },
    {
        "id": "not-checked-vs-pass",
        "keywords": "not checked same as pass safe ignore trust okay fine",
        "question": "Is NOT CHECKED the same as PASS? Can I ignore it?",
        "answer": (
            "No. NOT CHECKED means that specific check has not been implemented in this tool yet — "
            "it says nothing about whether the member is actually adequate for it. Never treat it as "
            "a pass. Check the 'Limitations' section under the relevant result for exactly what still "
            "needs independent verification."
        ),
    },
    {
        "id": "ec2-shear-deflection-gap",
        "keywords": "eurocode ec2 shear deflection not checked why missing",
        "question": "Why does Eurocode 2 show some checks as NOT CHECKED that BS8110 doesn't?",
        "answer": (
            "The two codes aren't implemented to identical depth everywhere. For example, EC2's second-order "
            "(slenderness) column moment and its span/depth deflection screening are not implemented yet, "
            "while the BS8110 equivalents are. Rather than approximate an EC2 check with a BS8110-style formula "
            "and risk it being wrong for that code, the tool marks it NOT CHECKED and says so plainly."
        ),
    },
    {
        "id": "linking-checkboxes",
        "keywords": "pull beam column footing link checkbox reaction automatically load path",
        "question": "What do the 🔗 'pull from result' checkboxes do?",
        "answer": (
            "They carry a load automatically from one calculated element to the next — Beam Design's reaction "
            "into Column Design's Gk/Qk fields, and Column Design's axial load into Pad Footing Design — so "
            "you don't have to retype numbers you've already calculated. Uncheck the box at any time to enter "
            "loads manually instead."
        ),
    },
    {
        "id": "retry-button",
        "keywords": "retry button fail suggestion fix increase depth",
        "question": "What does the 'Retry with...' button do after a FAIL?",
        "answer": (
            "It reruns the same calculation with the suggested change already applied (for example, beam depth "
            "+50mm, column size +25mm each way, footing plan +200mm each way) so you don't have to reopen the "
            "form and retype every input. You can still adjust further manually afterwards."
        ),
    },
    {
        "id": "settings-drift",
        "keywords": "settings drift warning stale fcu fy code changed recalculate",
        "question": "Why am I seeing a warning that my results are 'stale'?",
        "answer": (
            "Every calculated element remembers which concrete grade, steel grade, and code it was calculated "
            "with. If you change those settings in the sidebar afterwards, the tool warns you that the element "
            "on screen no longer matches your current settings, so you don't accidentally trust an out-of-date "
            "result. Recalculate that element to clear the warning."
        ),
    },
    {
        "id": "importer-not-detected",
        "keywords": "cad pdf importer not detected drawing upload dxf span missing wrong",
        "question": "The drawing importer says 'Not detected' — why didn't it read my drawing?",
        "answer": (
            "The importer never guesses a value it isn't confident about — if it can't clearly read a span, "
            "footing size, or slab thickness off your file, it says 'Not detected' rather than silently filling "
            "in a plausible-looking but possibly wrong number. Enter the correct value yourself in the "
            "confirmation form; it works alongside whatever the importer did find."
        ),
    },
    {
        "id": "dxf-wont-open",
        "keywords": "dxf drawing wont open cad autocad file corrupt",
        "question": "The downloaded DXF file won't open in my CAD software.",
        "answer": (
            "Try opening it in a different DXF-capable viewer first (LibreCAD is free) to check whether it's the "
            "file or your particular software's DXF import settings. If it fails in more than one viewer, that's "
            "worth reporting directly as a bug, including which viewer and version you tried."
        ),
    },
    {
        "id": "save-load-project",
        "keywords": "save load project json resume later download",
        "question": "How do I save my work and come back to it later?",
        "answer": (
            "Use the '💾 Save / load project' section in the sidebar. 'Save project' downloads everything you've "
            "calculated as one .json file. 'Load project' lets you re-upload that file later, even on a different "
            "day or computer, to continue exactly where you left off. Uploaded drawing images are not included in "
            "the save file to keep it small."
        ),
    },
    {
        "id": "moment-interaction-simplified",
        "keywords": "column moment interaction simplified linear approximation biaxial chart",
        "question": "Why does the column moment check say it's a 'simplified' or 'conservative' approximation?",
        "answer": (
            "The biaxial moment-axial interaction check uses a straight-line approximation between the pure-axial "
            "capacity and an estimated pure-moment capacity — not a full strain-compatibility interaction diagram. "
            "It's deliberately conservative (it can flag a column as FAIL that a full design chart would actually "
            "pass), so treat a FAIL or a utilization close to 1.0 as 'verify this with a full column chart', not "
            "as a final verdict."
        ),
    },
    {
        "id": "what-is-this-tool",
        "keywords": "what is this tool for purpose preliminary construction ready",
        "question": "What is this tool actually for, and what isn't it for?",
        "answer": (
            "It's a preliminary reinforced-concrete sizing aid for BS 8110 and Eurocode 2 — beams, columns, "
            "footings, slabs, and stairs — meant to cut the time spent on early-stage sizing. It is explicitly "
            "not a construction-ready design tool: every calc sheet and drawing states this, and independent "
            "review by a qualified engineer is required before anything is used on site."
        ),
    },
    {
        "id": "license-screen",
        "keywords": "license pin login screen key access dev mode",
        "question": "Why didn't I see a login or license screen?",
        "answer": (
            "This build has development mode enabled, which skips the license/PIN screen entirely for testing. "
            "A production deployment would normally require a license key."
        ),
    },
    {
        "id": "app-error-crash",
        "keywords": "error crash broken app wont work doesnt work stuck freeze frozen",
        "question": "The app shows an error, crashed, or seems stuck — what do I do?",
        "answer": (
            "Try refreshing the page first — Streamlit apps sometimes need a reload after a long idle period or a "
            "deployment update. If a specific button or calculation is stuck, try re-entering that module from the "
            "sidebar rather than the browser back button. If it still fails, note exactly what you clicked and what "
            "inputs you used, and report it directly — that's the most useful kind of bug report."
        ),
    },
    {
        "id": "result-looks-wrong",
        "keywords": "result looks wrong confused dont understand number seems off strange unexpected",
        "question": "A result looks wrong or confusing, but I'm not sure why.",
        "answer": (
            "That's genuinely useful feedback even without a clear cause — please report it with the exact inputs "
            "you used and what you expected instead. In the meantime, check the 'Design verification' audit table "
            "under the result and the 'Limitations' note — the explanation is often there, stating exactly what was "
            "and wasn't checked for that calculation."
        ),
    },
]


def _score(query: str, entry: Dict[str, str]) -> float:
    """Simple, dependency-free relevance score: fuzzy match against the
    question text plus a keyword-overlap bonus. No ML, just string matching.

    The keyword-overlap term uses RECALL (overlap / number of keywords), not
    overlap / query length — a long, casually-phrased query that still
    contains the key terms ("what's the deal with this NOT CHECKED thing")
    would otherwise get diluted by its own filler words and score lower than
    a short, precisely-phrased one. Recall avoids penalising a query just
    for being wordy."""
    query_l = query.lower().strip()
    if not query_l:
        return 0.0
    question_score = difflib.SequenceMatcher(None, query_l, entry["question"].lower()).ratio()
    keywords = set(entry["keywords"].split())
    query_words = set(query_l.replace("?", "").replace(",", "").replace("'", "").split())
    overlap = len(keywords & query_words)
    overlap_score = overlap / max(1, len(keywords))
    return 0.5 * question_score + 0.5 * overlap_score


def _dynamic_entries_from_results(design_results: Dict) -> List[Dict[str, str]]:
    """Builds searchable entries out of the engineer's OWN current session
    results — audit check messages and limitations — so a question about
    a specific result surfaces the exact text the calc engine produced,
    never a newly invented sentence."""
    entries: List[Dict[str, str]] = []
    for element_key, raw in (design_results or {}).items():
        if raw is None:
            continue
        data = raw
        if isinstance(raw, dict) and "result" in raw and "audit" not in raw:
            data = raw["result"]
        audit = data.get("audit", {}) if isinstance(data, dict) else {}
        for check in audit.get("checks", []):
            if check.get("message"):
                entries.append({
                    "id": f"{element_key}-{check['name']}",
                    "keywords": f"{element_key} {check['name']} {check['status']}".lower(),
                    "question": f"{element_key.title()} — {check['name']} ({check['status']})",
                    "answer": check["message"],
                })
        for i, lim in enumerate(data.get("limitations", []) if isinstance(data, dict) else []):
            entries.append({
                "id": f"{element_key}-limitation-{i}",
                "keywords": f"{element_key} limitation".lower(),
                "question": f"{element_key.title()} — limitation",
                "answer": lim,
            })
    return entries


def search(query: str, design_results: Optional[Dict] = None, top_k: int = 3, min_score: float = 0.35) -> List[Tuple[float, Dict[str, str]]]:
    """Returns up to top_k (score, entry) pairs ranked by relevance,
    searching both the static FAQ and the engineer's current session
    results, filtered to a minimum relevance threshold so irrelevant
    queries return nothing rather than a confident-looking wrong guess."""
    pool = list(FAQ) + _dynamic_entries_from_results(design_results or {})
    scored = [(_score(query, e), e) for e in pool]
    scored = [(s, e) for s, e in scored if s >= min_score]
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[:top_k]
