"""No prose in this tree may state a numeric bound that the constant contradicts.

The class, seen six times in this portfolio before this gate existed: a comment
justifying a number is copied, quoted, or simply left behind when the number
changes, and the stale prose then reads as a live claim. It has already escaped
into a RENDERED label once (`_disclosure.py:56`), which is the reason the rule
exists at all — a comment that justifies becomes a claim that renders.

The `_RATIO_MIN` / `_RATIO_MAX` bound is where it recurred. When the bound moved
from [-100, 150] the change reached the constant and ONE of the sentences about
it; the audit that found it named one site by hand and missed three, and the
hand-typed list in the brief that ordered this fix named six and missed two more.
So this gate does not work from a list. It SCANS.

What it scans, and why that shape:

* Every ``.py`` file, but only its COMMENT and STRING tokens. Tokenizing rather
  than grepping is what keeps ``_peers_with_roaa([0.1, 0.2])`` — a Python list
  literal, not a claim — from being read as a bound.
* Every ``.md`` file, all of which is prose.

What is allowed:

* A pair equal to the live constants. That is the claim being true.
* A pair inside a sentence marked as HISTORY. A changelog that cannot say what
  it changed is not a changelog, and `fdic.py` explaining why the old bound was
  wrong is the comment doing its job. The marker has to be in the text.
* Any entry under a RELEASED version header in CHANGELOG.md. An entry under
  ``## [0.2.1]`` is a statement about 0.2.1 by construction — at tag v0.2.1 the
  bound really was [-100.0, 150.0] and really did raise, so rewriting that entry
  would replace a true statement with a false one. This is the one ruling in the
  brief that ordering this fix got backwards, and it is recorded here rather
  than argued in a commit message.
"""
import io
import re
import tokenize
from pathlib import Path

import pytest

from cdfibenchmark.data import fdic

ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = {".git", "build", "dist", ".pytest_cache", "__pycache__",
             "cdfi_benchmark.egg-info", ".venv", "venv"}

#: A bracketed numeric pair, the shape every statement of this bound takes.
_PAIR = re.compile(r"\[\s*(-?\d[\d.,_]*)\s*,\s*(-?\d[\d.,_]*)\s*\]")

#: Words that mark a sentence as describing a PAST state of the code. Kept
#: short and explicit: a loose marker list is a hole, not a gate.
_HISTORY_MARKERS = (
    "was ", "were ", "used to ", "previously", "no longer", "retired",
    "through 0.2", "through 0.3.0", "before this", "old comment", "old bound",
    "it replaces", "moved from",
)


def _current_version() -> str:
    text = (ROOT / "pyproject.toml").read_text()
    m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.M)
    assert m, "pyproject.toml has no [project] version"
    return m.group(1)


def _shipped_files():
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file() or path.suffix not in (".py", ".md"):
            continue
        if any(part in SKIP_DIRS for part in path.relative_to(ROOT).parts):
            continue
        yield path


def _prose_segments(path: Path):
    """(line_number, text) for every stretch of PROSE in ``path``.

    Markdown is prose throughout. Python is prose only inside comments and
    string literals; everything else is code, where a bracketed pair is a list.
    """
    text = path.read_text()
    if path.suffix == ".md":
        for i, line in enumerate(text.splitlines(), 1):
            yield i, line
        return
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(text).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError):  # pragma: no cover
        pytest.fail(f"{path} could not be tokenized")
    for tok in tokens:
        if tok.type in (tokenize.COMMENT, tokenize.STRING):
            yield tok.start[0], tok.string


def _claim_window(file_lines, lineno: int) -> str:
    """The sentence a pair sits in: its own line plus the line above it.

    Read from the FILE, not from the segment, so the window is the same width in
    a Markdown file and inside a Python docstring. Two earlier drafts got this
    wrong in opposite directions and both were caught by red-proving:

    * Searching the whole segment exempted too much — a Python docstring is one
      STRING token, so a fourteen-line docstring containing "was" anywhere
      exempted every bound claim inside it. Restoring "150" to `_coerce_float`'s
      docstring PASSED because a sentence four paragraphs away said "it was
      avoiding".
    * Searching the segment with look-back exempted too little in Markdown,
      where each line is its own segment and there was no previous line to look
      back at. It failed this file's own retraction entry, which is precisely
      the sentence a changelog has to be allowed to write.

    One line of context, because that is how far these sentences actually wrap.
    """
    return "\n".join(file_lines[max(0, lineno - 2):lineno])


def _changelog_section_versions(text: str):
    """Line number -> the version header that line sits under, for CHANGELOG.md."""
    current, out = None, {}
    for i, line in enumerate(text.splitlines(), 1):
        m = re.match(r"^##\s*\[([^\]]+)\]", line)
        if m:
            current = m.group(1)
        out[i] = current
    return out


def _hits():
    """Every bracketed numeric pair stated in prose anywhere in the tree."""
    version = _current_version()
    for path in _shipped_files():
        rel = path.relative_to(ROOT)
        text = path.read_text()
        file_lines = text.splitlines()
        sections = None
        if path.name == "CHANGELOG.md":
            sections = _changelog_section_versions(text)
        for lineno, segment in _prose_segments(path):
            for m in _PAIR.finditer(segment):
                offset = segment[:m.start()].count("\n")
                yield {
                    "path": rel,
                    "line": lineno + offset,
                    "pair": (m.group(1), m.group(2)),
                    "text": _claim_window(file_lines, lineno + offset),
                    "section": (sections or {}).get(lineno + offset),
                    "released_section": bool(
                        sections
                        and (sections.get(lineno + offset) not in (None, version))
                    ),
                }


def _numeric(token: str) -> float:
    return float(token.replace(",", "").replace("_", ""))


def _is_bound_shaped(hit) -> bool:
    """A pair that could be read as a statement of the ratio-class bound.

    A pair is bound-shaped when it is negative-then-positive, which is the form
    every statement of this bound takes and which a coordinate, a range of dates
    or a list of positive figures is not.
    """
    try:
        low, high = (_numeric(t) for t in hit["pair"])
    except ValueError:  # pragma: no cover - the regex only matches numbers
        return False
    return low < 0 < high


def _is_history(hit) -> bool:
    if hit["released_section"]:
        return True
    # Whitespace-normalised: these sentences wrap, and a marker split across a
    # line break ("moved\nfrom") is still the marker.
    lowered = " ".join(hit["text"].lower().split())
    return any(marker in lowered for marker in _HISTORY_MARKERS)


# ── the gate ─────────────────────────────────────────────────────────────────
def test_the_scan_finds_the_sites_it_is_supposed_to_guard():
    """A scan that finds nothing certifies nothing.

    This gate's failure mode is a regex that silently stops matching, after
    which every stale bound in the tree passes. Pin that the scan still sees
    the class it was written for, in both file types.

    `fdic.py` is deliberately NOT expected here: its remaining statement of the
    bound is symbolic (`[_RATIO_MIN, _RATIO_MAX]`), which is the end state this
    whole gate is trying to reach — a sentence that cannot go stale because it
    names the constant instead of copying it.
    """
    hits = [h for h in _hits() if _is_bound_shaped(h)]
    assert hits, (
        "the bound-claim scan found NO bound-shaped pair anywhere in the tree. "
        "The bound is stated in prose in several places; a scan returning zero "
        "is broken, not clean."
    )
    suffixes = {h["path"].suffix for h in hits}
    assert suffixes == {".py", ".md"}, (
        f"the scan reaches only {suffixes}; the class spans code comments AND "
        f"shipped markdown, and has escaped into both"
    )


def test_the_scan_reads_python_prose_and_not_python_code():
    """Tokenizing, not grepping, is what makes this gate usable.

    `tests/test_ranking.py` contains `_peers_with_roaa([0.1, 0.2])` — a list
    literal, not a claim about anything. A grep-based gate has to either flag it
    or carry an exclusion list, and an exclusion list is the hand-typed list this
    gate exists to replace.
    """
    sample = ROOT / "tests" / "test_ranking.py"
    assert sample.exists()
    segments = list(_prose_segments(sample))
    assert segments, "no prose found in a file that has a module docstring"
    joined = "\n".join(text for _, text in segments)
    assert "_peers_with_roaa([0.1, 0.2])" not in joined, (
        "a Python list literal was read as prose; the scan is grepping, not "
        "tokenizing"
    )
    assert any("#" in text or text.startswith(('"', "'")) for _, text in segments)


@pytest.mark.parametrize(
    "hit",
    [pytest.param(h, id=f"{h['path']}:{h['line']}")
     for h in _hits() if _is_bound_shaped(h)],
)
def test_no_live_prose_states_a_bound_the_constant_contradicts(hit):
    """Every bound-shaped pair states the live constants, or is marked history.

    Red-proving this is one edit: put "150" back as the upper number of any
    corrected site — `fdic.py`'s `_coerce_float` docstring, or the `test_fdic.py`
    header comment — and this fails naming that file and line.
    """
    if _is_history(hit):
        return
    low, high = (_numeric(t) for t in hit["pair"])
    assert (low, high) == (fdic._RATIO_MIN, fdic._RATIO_MAX), (
        f"{hit['path']}:{hit['line']} states the ratio-class bound as "
        f"[{hit['pair'][0]}, {hit['pair'][1]}], but the constants are "
        f"[{fdic._RATIO_MIN:g}, {fdic._RATIO_MAX:g}]. Either correct the "
        f"sentence or mark it as history (one of: "
        f"{', '.join(repr(m.strip()) for m in _HISTORY_MARKERS)}).\n"
        f"  text: {hit['text'].strip()[:200]}"
    )


def test_the_guard_no_longer_claims_it_separates_the_field_classes():
    """The specific false justification this round was ordered to correct.

    "1000 admits every observed leverage ratio with room" was refuted by the
    package's own sweep: the observed maximum over 1984Q1-2026Q2 is 466,500.
    A false justification for a WIDENED safety bound is the strongest form of
    the comment-that-becomes-a-claim defect, so the sentence must not come back.
    """
    text = (ROOT / "cdfibenchmark" / "data" / "fdic.py").read_text()
    assert "admits every observed leverage ratio" not in text, (
        "fdic.py still claims the bound admits every OBSERVED leverage ratio. "
        "The observed maximum is 466,500 (CERT 27213, 19880331); the claim is "
        "true only of the modern population and must say so."
    )
    assert "466,500" in text, (
        "fdic.py does not state the whole-history maximum it was corrected with"
    )
    assert "951.11" in text, (
        "fdic.py does not state the MODERN maximum the bound is calibrated "
        "against — which is 5.1% below the bound, not the 3.6x the retracted "
        "comment implied"
    )


def test_the_floor_is_derived_from_the_ceiling_not_hand_set():
    """`_RATIO_MIN` was -100.0, never derived and never exercised.

    Whatever it is, it must stop being a bare number with no relationship to
    anything. It is now the mirror of `_RATIO_MAX`, because what the guard
    detects is magnitude.
    """
    assert fdic._RATIO_MIN == -fdic._RATIO_MAX
