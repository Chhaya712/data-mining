"""
Section A(a) -- turning a notice into something comparable.

Two decisions live in this file:

  D1  granularity  : how finely the text is decomposed (word n-gram width)
  D2  signal/noise : what happens to money, dates, reference numbers and
                     portal boilerplate

Both are configurable so that experiments/exp_a_representation.py can run the
competing variants against each other on the same corpus.
"""
from __future__ import annotations

import collections
import re

# --------------------------------------------------------------------------
# D2 part 1 -- volatile literals
#
# The scraping notes say the *same* estimated cost is written five different
# ways (`Rs. 4,50,00,000/-`, `Rs. 450.00 lakh`, `INR 4.500 Cr`, `45000000`,
# `RUPEES 4,50,00,000 ONLY`), the same date seven ways, and that every portal
# invents its own reference number with no cross-walk. A literal that is
# rewritten by the act of re-publication cannot carry evidence of identity; it
# only manufactures disagreement. We replace each class with a single sentinel
# so that the *sentence shape* survives and the volatile filling does not.
# --------------------------------------------------------------------------

RE_REF = re.compile(
    r"\b(?:[a-z]{2,6}[-/][0-9a-z/\-]{4,}[0-9]"      # NPAS-2024-0081304, SPC/2024-25/004512
    r"|ref[-/][0-9\-/]{4,}"                          # ref-2024-00912
    r"|[0-9]{6,})\b",                                # bare 00048213
    re.I,
)
RE_MONEY = re.compile(
    r"(?:rs\.?|inr|rupees)\s*[0-9][0-9,\.]*\s*(?:lakh|crore|cr|only)?"
    r"(?:\s*/\s*-)?|[0-9][0-9,]*\s*(?:lakh|crore|cr)\b",
    re.I,
)
RE_DATE = re.compile(
    r"\b(?:[0-9]{1,2}[-/.][0-9]{1,2}[-/.][0-9]{2,4}"
    r"|[0-9]{4}-[0-9]{2}-[0-9]{2}"
    r"|[0-9]{1,2}[- ][a-z]{3,9}[-, ] ?[0-9]{2,4}"
    r"|[a-z]{3,9} [0-9]{1,2},? [0-9]{4})\b",
    re.I,
)
RE_NUM = re.compile(r"\b[0-9][0-9,\.]*\b")
RE_PUNCT = re.compile(r"[^a-z0-9<>_\s]+")
RE_WS = re.compile(r"\s+")


def mask_volatile(text: str) -> str:
    """Order matters: dates and money before the generic number rule."""
    text = RE_REF.sub(" <ref> ", text)
    text = RE_MONEY.sub(" <money> ", text)
    text = RE_DATE.sub(" <date> ", text)
    text = RE_NUM.sub(" <num> ", text)
    return text


# --------------------------------------------------------------------------
# D2 part 2 -- boilerplate
#
# We do NOT hard-code the two preamble blocks named in portal_profiles.md.
# Hard-coding them would break the first time a seventh aggregator appears.
# Instead boilerplate is defined operationally: a line of text that occurs in
# at least `df_threshold` of all notices carries no evidence about *which*
# opportunity a notice describes, because almost every opportunity has it.
# The threshold itself is chosen from the corpus in exp_a (see REPORT.md A.2).
# --------------------------------------------------------------------------

RE_LINE_NORM = re.compile(r"[^a-z ]+")


def _line_key(line: str) -> str:
    return RE_WS.sub(" ", RE_LINE_NORM.sub(" ", line.lower())).strip()


def learn_boilerplate(bodies, df_threshold: float = 0.02) -> set:
    """Return the set of line-keys whose document frequency >= df_threshold."""
    counter = collections.Counter()
    for body in bodies:
        counter.update({_line_key(l) for l in body.split("\n") if _line_key(l)})
    n = len(bodies)
    return {k for k, c in counter.items() if c / n >= df_threshold}


def strip_boilerplate(body: str, boiler: set) -> str:
    keep = []
    for line in body.split("\n"):
        key = _line_key(line)
        if not key or key in boiler:
            continue
        keep.append(line)
    return "\n".join(keep)


# --------------------------------------------------------------------------
# normalise + D1 shingling
# --------------------------------------------------------------------------

def normalise(title: str, body: str, boiler: set | None, mask: bool) -> str:
    text = f"{title}\n{body}".lower()
    if boiler is not None:
        text = strip_boilerplate(text, boiler)
    if mask:
        text = mask_volatile(text)
    text = RE_PUNCT.sub(" ", text)
    return RE_WS.sub(" ", text).strip()


def shingles(norm_text: str, width: int = 5) -> set:
    """D1: word n-grams of `width` tokens, as a set (order kept inside a gram,
    dropped between grams). Returns the set of gram strings."""
    toks = norm_text.split()
    if len(toks) < width:
        return {" ".join(toks)} if toks else set()
    return {" ".join(toks[i : i + width]) for i in range(len(toks) - width + 1)}


def jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    inter = len(a & b)
    return inter / (len(a) + len(b) - inter)
