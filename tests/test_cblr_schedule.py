"""0.3.3: the CBLR period schedule refuses what it cannot attest.

Methodology v4.2 (`claude/methodology-cblr-period-schedule-v4.2-2026-09-24.md`),
sections 3-8. Every row of the section 8.4 matrix is an assertion here, and each
date is its own parametrized id.

THE REASONS BELOW ARE TYPED, NOT READ FROM THE PACKAGE. A gate that compared
`_cblr_at`'s output to a template `_cblr_at` also reads would certify
consistency, not wording: swap the MISSING reason for the BELOW one and both
sides would move together. So each expected reason is spelled out here, from the
methodology, and the package has to produce it.
"""
import ast
import datetime
import inspect
import io
import pathlib
import re
import tokenize

import pytest

from cdfibenchmark.data import schema
from cdfibenchmark.data.schema import (
    BenchmarkResult, InstitutionProfile, BENCHMARKS, CBLR_LEVELS,
    CBLR_FRAMEWORK_EFFECTIVE, CBLR_RELIEF_REFUSED, LEVELS_VERIFIED_THROUGH,
    DISPLAY_PCT_DP, BASIS_FDIC, BASIS_FDIC_LEVERAGE, BASIS_UNRULED,
    BASIS_COMPUTED_YTD, GRADEABLE_BASES,
    _PCA_CITED_FROM, _check_cblr_schedule, _cblr_at, _iso, benchmark_for,
    fmt_pct_digits,
)
from cdfibenchmark.exceptions import CBLRScheduleError, CDFIBenchmarkError
from cdfibenchmark.metrics.calculator import rank_institution
from cdfibenchmark.report import generator
from cdfibenchmark.report.generator import generate_report, summary_table

from . import _layout as layout

L = LEVELS_VERIFIED_THROUGH
#: PINNED LITERALLY, not derived from L (methodology v4.2 section 5): this
#: build verified on 2026-09-24 with LVT 2026-09-22, which is case (a) -- L <
#: 20260930, so no report date is graded at the 8% row. Deriving the case from
#: L would let a moved LVT silently re-shape the matrix instead of failing it.
CASE_B = False


# ── the reasons, typed from methodology v4.2 section 3.1 ─────────────────────
MISSING = (
    "This report carries no report date (REPDTE), so the period its Tier 1 "
    "leverage ratio describes is unknown. The CBLR qualifying level (12 CFR "
    "324.12) depends on the period, so none is applied and this value is not "
    "graded."
)


def MALFORMED(d):
    return (
        f"The report date {d!r} is not a calendar date in YYYYMMDD form, so the "
        f"period this value describes cannot be established. No CBLR qualifying "
        f"level is applied and this value is not graded."
    )


def NONQ(d):
    return (
        f"The report date {_iso(d)} is not a Call Report quarter-end (March 31, "
        f"June 30, September 30 or December 31). This tool applies a CBLR "
        f"qualifying level only at quarter-end report dates, so none is applied "
        f"and this value is not graded."
    )


def BELOW(d):
    return (
        f"The community bank leverage ratio framework (12 CFR 324.12) took "
        f"effect on January 1, 2020 (84 FR 61776, Nov. 13, 2019). This report "
        f"date, {_iso(d)}, is earlier, so no CBLR qualifying level was in force "
        f"and none is applied. The PCA leverage leg is withheld too: the "
        f"paragraph this tool cites for it, 12 CFR 324.403(b)(1)(i)(D), did not "
        f"carry that number before 2020. This value is not graded."
    )


def RELIEF(d):
    return (
        f"For report dates from 2020-06-30 through 2021-12-31 the CBLR "
        f"qualifying level was set by a temporary section, 12 CFR 324.303, "
        f"which this version of cdfi-benchmark does not encode. No CBLR "
        f"qualifying level is applied at {_iso(d)} and this value is not "
        f"graded. The PCA leverage leg is withheld too, so that a partial grade "
        f"is not read as a full one. See CHANGELOG.md, section [0.3.3]."
    )


def BEYOND(d):
    return (
        f"This version's CBLR schedule was verified against the CFR as in force "
        f"on {_iso(L)}. This report date, {_iso(d)}, is later, so no CBLR "
        f"qualifying level is applied and this value is not graded. A later "
        f"release of cdfi-benchmark may cover it."
    )


def EQUAL(shown, level):
    return (
        f"This value rounds to {shown}% at the {DISPLAY_PCT_DP} decimal places "
        f"this tool's report displays, which is the CBLR qualifying level for "
        f"this report date itself ({level:g}%). At that precision this tool "
        f"cannot state on the face of its report whether the value exceeds the "
        f"level, so it does not grade it."
    )


# ── the section 8.4 matrix ──────────────────────────────────────────────────
REFUSED = (
    [(d, MISSING) for d in (None, "", "None", "  ")]
    + [(d, MALFORMED(d)) for d in ("2026063", "2026-06-30", "20261331", "nan")]
    + [(d, NONQ(d)) for d in ("20191113", "20200101", "20200515", "20260701",
                              "20260515")]
    + [(d, BELOW(d)) for d in ("19960930", "19901231", "20190331", "20191231")]
    + [(d, RELIEF(d)) for d in ("20200630", "20200930", "20201231", "20210331",
                                "20210630", "20210930", "20211231")]
    + ([] if CASE_B else [("20260930", BEYOND("20260930"))])
    + [(d, BEYOND(d)) for d in ("20261231", "20270331")]
)
GRADED = (
    [("20200331", 9), ("20220331", 9), ("20250630", 9), ("20260630", 9)]
    + ([("20260930", 8)] if CASE_B else [])
)
#: Every string report date the matrix covers (the int case is separate).
ALL_DATES = [d for d, _ in REFUSED] + [d for d, _ in GRADED]


def _rid(d):
    return repr(d)


def _bank(cert, repdte, tier1):
    return InstitutionProfile(
        cert=cert, name=f"Bank {cert}", city="Oakland", state="CA",
        report_date=repdte,
        total_assets=655_000, total_deposits=520_000, net_loans=380_000,
        net_income=1_950, interest_income=28_000, interest_expense=8_000,
        non_interest_income=3_500, non_interest_expense=22_000,
        total_equity=48_000, tier1_ratio=tier1,
        gross_loans=390_000, non_current_loans=5_850,
        loan_loss_allowance=7_800,
    )


def _peers():
    return [_bank(9000 + i, "20250630", 11.0) for i in range(20)]


def _tier1_block(report):
    block = report[report.index("### Tier 1 Leverage Ratio"):]
    return block[:block.index("\n###")] if "\n###" in block else block


def _render(repdte, tier1):
    subject = _bank(1, repdte, tier1)
    peers = _peers()
    report = generate_report(subject, peers)
    df = summary_table(subject, peers)
    row = df[df["metric"] == "Tier 1 Leverage Ratio"].iloc[0]
    return report, _tier1_block(report), row


def _result(value, repdte, basis=BASIS_FDIC_LEVERAGE, metric="tier1_ratio"):
    return BenchmarkResult(
        metric=metric, institution_value=value, peer_median=None,
        peer_25th=None, peer_75th=None, peer_count=0,
        basis=basis, report_date=repdte,
    )


@pytest.mark.parametrize("d,reason", REFUSED, ids=[_rid(d) for d, _ in REFUSED])
def test_a_refused_date_is_not_graded_anywhere(d, reason):
    level, text = _cblr_at(d)
    assert level is None and text == reason, (d, text)
    cfg = benchmark_for("tier1_ratio", d)
    assert cfg["good"] is None and cfg["warning"] is None, cfg
    assert cfg["refusal"] == reason
    assert cfg["source"].startswith("none applied at this report date: "), cfg
    # 3.0 and 6.0 prove the PCA leg is withheld too, not just the CBLR leg.
    for value in (3.0, 6.0, 8.2, 14.99):
        r = _result(value, d)
        assert r.status == "N/A", (d, value, r.status)
        assert r.not_graded_reason == reason
    report, block, row = _render(d, 8.2)
    assert "**Institution Value:** 8.20%" in block, block
    bench = [ln for ln in block.splitlines() if ln.startswith("**Benchmark:**")]
    assert len(bench) == 1 and "none applied at this report date" in bench[0] \
        and "12 CFR" in bench[0], block
    assert f"**Not graded:** {reason}" in block, block
    assert block.count("**Not graded:**") == 1, block
    assert "Strong >" not in block and "Strong >=" not in block, block
    assert row["not_graded_reason"] == reason
    assert row["status"] == "N/A"


@pytest.mark.parametrize("d", [None, "", "None", "  "], ids=_rid)
def test_the_missing_reason_claims_nothing_about_the_law_or_the_schedule(d):
    _, reason = _cblr_at(d)
    assert "took effect on January 1, 2020" not in reason
    assert "verified against the CFR" not in reason


@pytest.mark.parametrize("d,level", GRADED, ids=[d for d, _ in GRADED])
def test_an_attested_date_is_graded_at_its_level(d, level):
    got, text = _cblr_at(d)
    assert got == level, (d, got, text)
    cfg = benchmark_for("tier1_ratio", d)
    assert cfg["good"] == level and cfg["warning"] == 5
    assert cfg["good_exclusive"] is True
    assert "refusal" not in cfg
    assert _result(14.99, d).status == "STRONG"
    assert _result(6.0, d).status == "ADEQUATE"
    assert _result(3.0, d).status == "WEAK"
    _, block, row = _render(d, 13.2)
    assert "**Not graded:**" not in block, block
    assert row["not_graded_reason"] is None
    assert row["status"] == "STRONG"


def test_an_int_report_date_is_normalised_through_the_resolver_only():
    """`str()` normalisation. The int never reaches the render path: an
    `InstitutionProfile` with an int report_date already fails in
    `fiscal_quarter` (pre-existing, out of scope), and `fdic.py` always passes
    a str. So the int is tested on `benchmark_for` / `_cblr_at` only."""
    level, text = _cblr_at(20250630)
    assert level == 9 and text == _cblr_at("20250630")[1]
    assert benchmark_for("tier1_ratio", 20250630)["good"] == 9


# ── boundary pairs, each asserted in one function ────────────────────────────
def _graded_at(d):
    return _cblr_at(d)[0] is not None


def test_boundary_framework_effective():
    assert not _graded_at("20191231") and _graded_at("20200331")


def test_boundary_relief_start():
    assert _graded_at("20200331") and not _graded_at("20200630")


def test_boundary_relief_end():
    assert not _graded_at("20211231") and _graded_at("20220331")


def test_boundary_verified_through():
    assert _graded_at("20260630")
    assert _graded_at("20260930") is CASE_B, (
        f"LEVELS_VERIFIED_THROUGH is {L}; 20260930 must be "
        f"{'graded' if CASE_B else 'refused'}")


# ── the equality matrix (section 6) ──────────────────────────────────────────
EQUALITY = (
    [(v, "EQUAL") for v in (9.0, 9.003, 8.996, 9.0049999)]
    + [(v, "STRONG") for v in (9.005, 9.01, 14.9876825620271)]
    + [(v, "ADEQUATE") for v in (8.995, 8.994, 8.5, 8.0)]
    + [(5.0, "ADEQUATE"), (4.99, "WEAK"),
       # CARRIED, NOT FIXED (0.4.0): 4.996 displays as 5.00% and grades WEAK.
       # "5.0 percent or greater" makes the grade legally right, but it cannot
       # be checked against the figure on the page. Pinned so it cannot change
       # silently.
       (4.996, "WEAK")]
)
#: Level-9 dates. In case (b) the matrix must ALSO run at 20260930 with level
#: 8; this build is case (a) (LVT 2026-09-22), so that date is refused and the
#: level-8 matrix has no attested date to run at. The sweep below runs at every
#: GRADED date in either case.
EQ_DATES = ["20250630", "20200331"]


@pytest.mark.parametrize("d", EQ_DATES)
@pytest.mark.parametrize("value,expected", EQUALITY,
                         ids=[f"{v!r}-{e}" for v, e in EQUALITY])
def test_the_equality_matrix(d, value, expected):
    level = _cblr_at(d)[0]
    assert level == 9
    r = _result(value, d)
    if expected == "EQUAL":
        assert r.status == "N/A", (value, r.status)
        assert r.not_graded_reason == EQUAL(fmt_pct_digits(value), level)
        _, block, row = _render(d, value)
        assert "**Institution Value:** 9.00%" in block, block
        assert f"**Not graded:** {EQUAL('9.00', 9)}" in block, block
        assert row["not_graded_reason"] == EQUAL("9.00", 9)
    else:
        assert r.status == expected, (value, r.status)
        assert r.not_graded_reason is None


@pytest.mark.parametrize("d,level", GRADED, ids=[d for d, _ in GRADED])
def test_the_display_equality_sweep(d, level):
    """N/A exactly when the value displays as the level; otherwise the
    displayed figure is on the same side of the level as the grade."""
    target = fmt_pct_digits(level)
    lo, hi = level - 0.02, level + 0.02
    n = int(round((hi - lo) / 0.0001))
    seen = {"N/A": 0, "STRONG": 0, "ADEQUATE": 0}
    for i in range(n + 1):
        v = lo + i * 0.0001
        status = _result(v, d).status
        seen[status] += 1
        shown = fmt_pct_digits(v)
        assert (status == "N/A") == (shown == target), (v, shown, status)
        if status == "STRONG":
            assert float(shown) > level, (v, shown)
        if status == "ADEQUATE":
            assert float(shown) < level, (v, shown)
    assert all(seen.values()), seen


# ── T-G: import-time data invariants ─────────────────────────────────────────
_GOOD = dict(levels=CBLR_LEVELS, relief=CBLR_RELIEF_REFUSED, lvt=L,
             pca_from=_PCA_CITED_FROM,
             framework_effective=CBLR_FRAMEWORK_EFFECTIVE)
_BAD = {
    "floor-00000000": dict(levels=(("00000000",) + CBLR_LEVELS[0][1:],)
                           + CBLR_LEVELS[1:]),
    "floor-not-framework": dict(levels=(("20191113",) + CBLR_LEVELS[0][1:],)
                                + CBLR_LEVELS[1:]),
    "unordered": dict(levels=(CBLR_LEVELS[0], ("20190101", 8, "x"))),
    "lvt-before-last-row": dict(lvt="20260630"),
    "lvt-unparseable": dict(lvt="2026093"),
    "relief-not-quarter-end": dict(relief=("20200515", "20211231")),
    "relief-crosses-row": dict(relief=("20200630", "20261231")),
    "pca-after-framework": dict(pca_from="20200102"),
}


def test_the_live_schedule_passes_its_invariants():
    _check_cblr_schedule(**_GOOD)


@pytest.mark.parametrize("case", sorted(_BAD))
def test_a_broken_schedule_raises_cblr_schedule_error(case):
    with pytest.raises(CBLRScheduleError):
        _check_cblr_schedule(**{**_GOOD, **_BAD[case]})


def test_the_schedule_error_is_a_runtime_error_not_an_import_error():
    assert issubclass(CBLRScheduleError, RuntimeError)
    assert issubclass(CBLRScheduleError, CDFIBenchmarkError)
    assert not issubclass(CBLRScheduleError, ImportError)


# ── T-R1: forbidden phrases ──────────────────────────────────────────────────
FORBIDDEN = ("for report dates before it", "Strong >= 9", "Strong >= 8",
             "the level in force at this report date", ">= 9% before",
             ">= 8% from")
ROOT = layout.ROOT


def _unwrap(text):
    text = re.sub(r"\n(?:[ \t]*>)+[ \t]?", "\n", text)
    text = re.sub(r"(?<!\n)\n(?!\n)", " ", text)
    return re.sub(r"[ \t]+", " ", text)


def _package_string_tokens():
    pkg = pathlib.Path(schema.__file__).resolve().parents[1]
    out = []
    for path in sorted(pkg.rglob("*.py")):
        toks = tokenize.generate_tokens(io.StringIO(path.read_text()).readline)
        out += [(path.name, t.string) for t in toks if t.type == tokenize.STRING]
    return out


def test_no_forbidden_phrase_in_package_strings_or_rendered_pages():
    tokens = _package_string_tokens()
    assert len(tokens) > 0
    pages = [_render(d, 8.2)[0] for d in ALL_DATES]
    assert len(pages) > 0
    hits = []
    for name, s in tokens:
        for p in FORBIDDEN:
            hits += [(name, p) for _ in re.finditer(re.escape(p), s)]
    for d, page in zip(ALL_DATES, pages):
        text = _unwrap(page)
        for p in FORBIDDEN:
            hits += [(d, p) for _ in re.finditer(re.escape(p), text)]
    assert not hits, hits


@layout.needs("README.md")
def test_no_forbidden_phrase_in_the_readme_and_it_names_the_verified_date():
    """T-R3 (and T-R1's README half)."""
    text = _unwrap(layout.SURFACES["README.md"].read_text())
    assert len(text) > 0
    hits = [p for p in FORBIDDEN for _ in re.finditer(re.escape(p), text)]
    assert not hits, hits
    assert _iso(L) in text, f"README does not state the verified date {_iso(L)}"


# ── T-R2 ─────────────────────────────────────────────────────────────────────
def test_the_attested_page_carries_the_relabelled_line_and_the_verified_date():
    report, block, _ = _render("20250630", 13.2)
    for needle in ("elected the CBLR framework", "greater than 9% at this report date",
                   "84 FR 61776, 61802", "Nov. 13, 2019"):
        assert needle in block, (needle, block)
    assert f"**CBLR schedule verified through:** {_iso(L)}" in report
    assert "2026-07-01" not in block and "91 FR 22973" not in block, block


# ── T-R5 ─────────────────────────────────────────────────────────────────────
def test_the_report_and_the_equality_check_share_one_formatter():
    assert generator._PCT_DP is schema.DISPLAY_PCT_DP
    assert generator._fmt_pct(9.003) == schema.fmt_pct_digits(9.003) + "%"


# ── T-R6, T-R9, T-R10 ────────────────────────────────────────────────────────
def test_levels_verified_through_is_the_date_the_build_recorded():
    """Recorded by the 0.3.3 build on 2026-09-24 (America/Chicago).

    1. LII 12 CFR 324.12 (https://www.law.cornell.edu/cfr/text/12/324.12, via
       WebFetch): (a)(1) ends "... if it has a leverage ratio greater than 8
       percent."; note "[84 FR 61802, Nov. 13, 2019, as amended at 85 FR 77363,
       Dec. 2, 2020; 91 FR 22989, Apr. 29, 2026]"; no as-of date on the page.
       eCFR versioner: title 12 up_to_date_as_of 2026-09-22; the 324.12 version
       list ends at 2026-07-01.
    2. federalregister.gov documents API, CFR 12 part 324: "community bank
       leverage ratio" published >= 2026-04-29 -> only 2026-08298 itself;
       any term published >= 2026-04-30 -> 0 results.
    LVT = min(2026-09-24, 2026-09-22).
    """
    assert LEVELS_VERIFIED_THROUGH == "20260922"


def test_levels_verified_through_is_not_in_the_future():
    """The clock check, as a test, never at import (methodology v4.2 B1).
    `lvt <= today` only gets truer as time passes, so it cannot go red later."""
    lvt = datetime.datetime.strptime(LEVELS_VERIFIED_THROUGH, "%Y%m%d").date()
    assert lvt <= datetime.date.today()


def test_the_framework_effective_date_is_pinned():
    """84 FR 61776, DATES: "The final rule is effective on January 1, 2020."
    G1 checks this constant only for internal consistency; this pins it."""
    assert CBLR_FRAMEWORK_EFFECTIVE == "20200101"


# ── T-R7 ─────────────────────────────────────────────────────────────────────
def test_the_fdic_parser_feeds_missing_dates_to_the_missing_refusal():
    from cdfibenchmark.data.fdic import _parse_institution
    base = {"CERT": 1, "ASSET": 100, "DEP": 80, "LNLSNET": 60, "NETINC": 1,
            "INTINC": 5, "EINTEXP": 2, "NONII": 1, "NONIX": 3, "EQ": 10,
            "RBC1AAJ": 8.2}
    absent = _parse_institution(dict(base))
    assert absent.report_date == ""
    assert benchmark_for("tier1_ratio", absent.report_date)["refusal"] == MISSING
    none = _parse_institution({**base, "REPDTE": None})
    assert none.report_date == "None"
    assert benchmark_for("tier1_ratio", none.report_date)["refusal"] == MISSING


# ── T-R8 (a regression pin, not a gate) ──────────────────────────────────────
def test_a_refused_date_does_not_change_the_peer_rank():
    """REGRESSION PIN, NOT A GATE: no mutation in methodology section 8.7
    targets it. `rank_institution` reads only `floor`, which tier1 lacks, so a
    refused threshold must not move a peer rank."""
    peers_a = [_bank(9000 + i, "20200930", 7.0 + i * 0.5) for i in range(20)]
    peers_b = [_bank(9000 + i, "20250630", 7.0 + i * 0.5) for i in range(20)]
    a = rank_institution(_bank(1, "20200930", 11.2), peers_a, "tier1_ratio")
    b = rank_institution(_bank(1, "20250630", 11.2), peers_b, "tier1_ratio")
    assert a["rank"] is not None
    assert (a["rank"], a["percentile"]) == (b["rank"], b["percentile"])


# ── T-R11: an attested line names no date except inside its own citation ────
_DATE_RES = (
    re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),
    re.compile(r"\b(?:19|20)\d{6}\b"),
    re.compile(r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)"
               r"[a-z]*\.? \d{1,2}, \d{4}\b"),
)


def _dates_in(text):
    return [m.group(0) for rx in _DATE_RES for m in rx.finditer(text)]


def _rule_for(d):
    chosen = [row for row in CBLR_LEVELS if row[0] <= str(d)][-1]
    return chosen[2]


def _assert_no_date_outside_citation(text, rule, where):
    assert _dates_in(text), f"{where}: no date extracted at all: {text!r}"
    assert text.count(rule) == 1, (
        f"{where}: the citation {rule!r} appears {text.count(rule)} times: "
        f"{text!r}")
    rest = text.replace(rule, "", 1)
    assert not _dates_in(rest), (
        f"{where}: names a date outside its citation: {_dates_in(rest)} in "
        f"{text!r}")


@pytest.mark.parametrize("d", [d for d, _ in GRADED])
def test_an_attested_line_names_no_date_outside_its_citation(d):
    rule = _rule_for(d)
    _, block, row = _render(d, 13.2)
    bench = [ln for ln in block.splitlines() if ln.startswith("**Benchmark:**")]
    assert len(bench) == 1, block
    for where, text in (("source", benchmark_for("tier1_ratio", d)["source"]),
                        ("Benchmark line", bench[0]),
                        ("threshold_source", row["threshold_source"])):
        _assert_no_date_outside_citation(text, rule, f"{d} {where}")


def test_an_int_attested_date_names_no_date_outside_its_citation():
    _assert_no_date_outside_citation(
        benchmark_for("tier1_ratio", 20250630)["source"], _rule_for(20250630),
        "int 20250630 source")


def test_a_schedule_with_more_rows_still_names_no_other_row(monkeypatch):
    """A synthetic middle row gives every later attested date an EARLIER row
    and a LATER row, so a restored backward or forward clause shows up even
    while the real 8% row attests nothing (case (a))."""
    levels = (CBLR_LEVELS[0], ("20230101", 8.5, "99 FR 100, 105, Jan. 5, 2023"),
              CBLR_LEVELS[1])
    monkeypatch.setattr(schema, "CBLR_LEVELS", levels)
    for d in ("20200331", "20250630"):
        level, text = schema._cblr_at(d)
        assert level is not None
        assert "for report dates before" not in text, text
        rule = [row for row in levels if row[0] <= d][-1][2]
        _assert_no_date_outside_citation(text, rule, f"synthetic {d}")


# ── T-R12: one EQUAL wording, true on three surfaces ─────────────────────────
@layout.needs("README.md")
def test_the_equal_reason_is_one_wording_on_page_dataframe_and_readme():
    _, block, row = _render("20250630", 9.003)
    page = [ln for ln in block.splitlines() if ln.startswith("**Not graded:**")]
    assert len(page) == 1, block
    page = page[0][len("**Not graded:** "):]
    frame = row["not_graded_reason"]
    readme = _unwrap(layout.SURFACES["README.md"].read_text())
    m = re.search(r"- (a value that rounds, at the .*?so it does not grade it\.)",
                  readme)
    assert m, "README carries no equality bullet"
    bullet = m.group(1)
    assert page == frame
    for text in (page, frame, bullet):
        assert (f"at the {DISPLAY_PCT_DP} decimal places this tool's report "
                f"displays") in text, text
        assert ("cannot state on the face of its report whether the value "
                "exceeds the level") in text, text
        for banned in ("requires", "shown as", "on this page",
                       "decimal places this tool displays"):
            assert banned not in text, (banned, text)
    band = [ln for ln in block.splitlines() if ln.startswith("**Benchmark:**")][0]
    assert f"rounds to {fmt_pct_digits(9)}%" in band, band


# ── T-R13: no clock at import ────────────────────────────────────────────────
_CLOCK = ("date.today", "datetime.now", "datetime.today", "time.time")


def _dotted(node):
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def _import_time_nodes(body):
    """Statements that execute at import: module statements and class bodies,
    but not function bodies."""
    for stmt in body:
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if isinstance(stmt, ast.ClassDef):
            yield from _import_time_nodes(stmt.body)
            continue
        yield stmt


def test_nothing_schema_runs_at_import_reads_a_clock():
    tree = ast.parse(pathlib.Path(schema.__file__).read_text())
    funcs = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
    called, clock_calls = set(), []
    stack = list(_import_time_nodes(tree.body))
    seen = set()
    while stack:
        node = stack.pop()
        for sub in ast.walk(node):
            if isinstance(sub, ast.Call):
                name = _dotted(sub.func)
                if any(name == c or name.endswith("." + c) for c in _CLOCK):
                    clock_calls.append(name)
                if name in funcs and name not in seen:
                    seen.add(name)
                    called.add(name)
                    stack.extend(funcs[name].body)
    assert "_check_cblr_schedule" in called, (
        "the scan did not find the import-time schedule check, so it proves "
        "nothing")
    assert not clock_calls, clock_calls
    assert "today" not in inspect.signature(_check_cblr_schedule).parameters


# ── T-R14: at most one Not graded line ───────────────────────────────────────
def test_both_reasons_share_one_not_graded_line():
    r = _result(8.2, "20200930", basis=BASIS_UNRULED)
    lines = generator._not_graded_lines(r)
    assert len(lines) == 1, lines
    assert lines[0].startswith("**Not graded:** " + RELIEF("20200930")), lines
    assert f"Separately, this value is {BASIS_UNRULED}" in lines[0], lines


def test_the_not_graded_helper_in_its_single_reason_cases():
    assert generator._not_graded_lines(
        _result(3.9, "20250630", basis=BASIS_FDIC, metric="nim")) == []
    only_reason = generator._not_graded_lines(_result(8.2, "20200930"))
    assert only_reason == ["**Not graded:** " + RELIEF("20200930")]
    ytd = BASIS_COMPUTED_YTD.format(q=1)
    assert ytd not in GRADEABLE_BASES
    only_basis = generator._not_graded_lines(
        _result(0.9, "20260331", basis=ytd, metric="roaa"))
    assert len(only_basis) == 1
    assert only_basis[0].startswith(f"**Not graded:** this value is {ytd}.")
    assert "Separately" not in only_basis[0]


# ── fix round 1 (hostile audit 2026-09-24) ───────────────────────────────────
def test_not_graded_reason_is_none_on_graded_rows_of_a_mixed_frame():
    """B1. The CHANGELOG documents `None` on graded rows and on every HOUSE
    row. Under pandas 3 a column mixing None and str is inferred as a string
    dtype and every None becomes NaN -- in exactly the frames where Tier 1 was
    refused. A frame with one refused tier1 row and seven graded HOUSE rows
    must still hold `None` on the HOUSE rows."""
    import pandas as pd
    subject = _bank(1, "20200930", 8.2)          # RELIEF: tier1 refused
    df = summary_table(subject, _peers())
    tier1 = df[df["metric"] == "Tier 1 Leverage Ratio"]
    assert len(tier1) == 1 and tier1["not_graded_reason"].iloc[0] == RELIEF(
        "20200930")
    house = df[df["metric"] != "Tier 1 Leverage Ratio"]
    assert len(house) == 7
    values = list(house["not_graded_reason"])
    assert all(v is None for v in values), (pd.__version__, values)
    # The numeric columns keep their dtypes; only this column is object.
    assert df["not_graded_reason"].dtype == object
    assert df["institution"].dtype.kind == "f", df["institution"].dtype


def test_the_tier1_band_pins_both_operators():
    """N4 / X4: `Adequate >= 5%` is what the grade does (5.0 is ADEQUATE; the
    rule reads "5.0 percent or greater"). A `>` there would be a false
    operator on the report face."""
    _, block, _ = _render("20250630", 13.2)
    band = [ln for ln in block.splitlines() if ln.startswith("**Benchmark:**")][0]
    assert band.startswith(
        "**Benchmark:** Strong > 9% (a value that rounds to 9.00% is not "
        "graded) | Adequate >= 5% — "), band
    assert _result(5.0, "20250630").status == "ADEQUATE"


def test_a_verified_through_date_on_a_quarter_end_is_itself_graded(monkeypatch):
    """X7: BEYOND is `d > LEVELS_VERIFIED_THROUGH`, so LVT itself is graded.
    Today's LVT (20260922) is not a quarter-end, so NONQ fires first and a
    `>=` would be invisible; with LVT on a quarter-end it is not."""
    monkeypatch.setattr(schema, "LEVELS_VERIFIED_THROUGH", "20260630")
    level, text = schema._cblr_at("20260630")
    assert level == 9, text
    level, text = schema._cblr_at("20260930")
    assert level is None and text.startswith(
        "This version's CBLR schedule was verified against the CFR as in force "
        "on 2026-06-30."), text


@pytest.mark.parametrize("d", [" 20250630 ", "20250630\n", "\t20250630"],
                         ids=repr)
def test_a_whitespace_padded_valid_date_is_graded(d):
    """N5: `str(report_date).strip()` normalises padding; the date is the
    same quarter-end and is graded at its level."""
    assert _cblr_at(d)[0] == 9
    assert _result(13.2, d).status == "STRONG"


def _period_basis_rows():
    text = layout.SURFACES["README.md"].read_text()
    header = "| Metric | Computed fallback | Graded? |"
    assert text.count(header) == 1, "the README period-basis table moved"
    rows = []
    for line in text[text.index(header):].splitlines()[2:]:
        if not line.startswith("|"):
            break
        rows.append([c.strip() for c in line.strip("|").split("|")])
    assert rows, "the README period-basis table has no rows"
    return rows


@layout.needs("README.md")
def test_the_readme_period_basis_table_does_not_say_tier1_is_always_graded():
    """B2. 0.3.3 refuses Tier 1 for some report dates and for values that
    display as the level, so the "Graded?" cell for Tier 1 cannot say
    "Always" -- the census regex cannot see this row (no CBLR/324/% token)."""
    tier1 = [r for r in _period_basis_rows() if "Tier 1" in r[0]]
    assert len(tier1) == 1, tier1
    graded = tier1[0][2]
    assert "Always" not in graded, graded
    assert "Not graded" in graded and "Tier 1 section" in graded, graded
