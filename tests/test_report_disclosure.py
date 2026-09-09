"""What the rendered report must say about its own warrant.

`generate_report` printed the institution's Report Date and the peer group
SIZE and nothing else about the peer group — no peer period, no note when the
same-state constraint had been dropped, no note when the group was below the
requested floor. It also printed a "Benchmark: Strong >= N%" line for every
metric with no indication that seven of the eight thresholds are this tool's
own rules of thumb and one is a CFR citation.

A grade is only as good as its warrant. If the warrant cannot be seen on the
rendered surface, the reader cannot tell a measured, cited, single-period
comparison from an estimated, house-thresholded, mixed-period one.
"""
import pytest
from unittest.mock import patch

from cdfibenchmark.data.schema import BENCHMARKS, InstitutionProfile
from cdfibenchmark.peers.selector import build_peer_group, build_sample_peer_group
from cdfibenchmark.report.generator import generate_report, summary_table


def _peer(cert, repdte="20260331", state="CA"):
    return InstitutionProfile(
        cert=cert, name=f"Peer {cert}", city="LA", state=state,
        report_date=repdte, total_assets=655_000, total_deposits=520_000,
        net_loans=380_000, net_income=1_950, interest_income=28_000,
        interest_expense=8_000, non_interest_income=3_500,
        non_interest_expense=22_000, total_equity=48_000, tier1_ratio=12.0,
        gross_loans=390_000, non_current_loans=5_850, loan_loss_allowance=7_800,
    )


@pytest.fixture
def q1_institution():
    return _peer(57543, repdte="20260331")


# ── peer period must be on the face ──────────────────────────────────────────
def test_report_renders_the_peer_period(q1_institution):
    rows = [_peer(c) for c in range(1, 21)]
    with patch("cdfibenchmark.peers.selector.get_peer_financials",
               return_value=rows):
        peers = build_peer_group(q1_institution)
    report = generate_report(q1_institution, peers)
    assert "Peer Report Date" in report or "Peer Period" in report, (
        "the report shows the institution's period and the peer COUNT, but "
        "never the peers' own period"
    )
    assert "20260331" in report


def test_report_discloses_a_dropped_state_constraint(q1_institution):
    state_rows = [_peer(c, state="CA") for c in range(1, 4)]
    national_rows = [_peer(c, state="TX") for c in range(50, 70)]

    def fake(**kw):
        return state_rows if kw.get("state") else national_rows

    with patch("cdfibenchmark.peers.selector.get_peer_financials",
               side_effect=fake):
        peers = build_peer_group(q1_institution, same_state=True, min_peers=10)
    report = generate_report(q1_institution, peers)
    assert "NATIONAL" in report.upper(), (
        "same-state was requested, a national group was returned, and the "
        "report said nothing"
    )


def test_report_discloses_an_undersized_peer_group(q1_institution):
    rows = [_peer(c) for c in range(1, 4)]
    with patch("cdfibenchmark.peers.selector.get_peer_financials",
               return_value=rows):
        peers = build_peer_group(q1_institution, min_peers=10)
    report = generate_report(q1_institution, peers)
    assert "below the requested minimum" in report


def test_report_discloses_a_mixed_period_peer_group(q1_institution):
    rows = [_peer(c, repdte="20260331") for c in range(1, 11)]
    rows += [_peer(c, repdte="20251231") for c in range(50, 60)]
    with patch("cdfibenchmark.peers.selector.get_peer_financials",
               return_value=rows):
        peers = build_peer_group(q1_institution)
    report = generate_report(q1_institution, peers)
    assert "NOT all at one reporting period" in report


def test_clean_peer_group_renders_no_caveats(q1_institution):
    rows = [_peer(c) for c in range(1, 21)]
    with patch("cdfibenchmark.peers.selector.get_peer_financials",
               return_value=rows):
        peers = build_peer_group(q1_institution)
    report = generate_report(q1_institution, peers)
    assert "below the requested minimum" not in report
    assert "NOT all at one reporting period" not in report


# ── the basis must be on the face ────────────────────────────────────────────
def test_ungraded_flow_metric_states_why_it_is_not_graded(q1_institution):
    peers = build_sample_peer_group(q1_institution)
    report = generate_report(q1_institution, peers)
    assert "NOT annualized" in report, (
        "a Q1 YTD proxy is rendered ungraded with no stated reason"
    )


def test_report_states_the_basis_of_each_metric(q1_institution):
    peers = build_sample_peer_group(q1_institution)
    report = generate_report(q1_institution, peers)
    assert "**Basis:**" in report


def test_nim_computed_over_total_assets_says_so(q1_institution):
    peers = build_sample_peer_group(q1_institution)
    report = generate_report(q1_institution, peers)
    assert "not FDIC NIMY" in report


# ── house thresholds must not read as standards ──────────────────────────────
#: The exact attribution `_threshold_line` appends to a HOUSE benchmark. Pinned
#: as a literal, and asserted ON the Benchmark line, because the substring test
#: it replaces was satisfied from anywhere in the document.
_HOUSE_THRESHOLD_MARK = "**this tool's own threshold (HOUSE)**"


def _benchmark_lines(report):
    return [ln.strip() for ln in report.splitlines()
            if ln.strip().startswith("**Benchmark:**")]


def test_house_thresholds_are_marked_house_on_the_report(q1_institution):
    """THIS GATE COULD NOT BE MADE TO FAIL, AND THAT IS WHAT IT NOW FIXES.

    It read `"this tool's own" in report.lower() or "house" in report.lower()`
    -- a substring anywhere in the whole rendered document, standing in for "the
    threshold lines carry their attribution". The report says "this tool's own"
    in several unrelated places, so the assertion was satisfied without the
    threshold attribution existing at all. Measured, python3.10, deleting only
    the thing the gate names -- the HOUSE branch of `_threshold_line` at
    `cdfibenchmark/report/generator.py:116`, reduced to
    `" - not a regulatory or supervisory standard"`:

        PYTHONPATH=. pytest tests -q   ->  330 passed, 3 skipped
                                           (byte-identical to control)

    What kept it green was `cdfibenchmark/peers/selector.py:159`, a sentence
    about PEER-GROUP SELECTION -- "...nearest-neighbour selection are this
    tool's own choices (HOUSE)..." -- which appears on every report and has
    nothing to do with thresholds. That is the same class as the credit-union
    assertion this release deleted: a limb true of the artifact for an unrelated
    reason. For contrast the SIZE-BAND attribution was already gated properly,
    on its own line, by
    `test_report_face_claims.py::test_the_asset_bucket_carries_its_boundaries_and_its_attribution`.

    So the question is now asked where it means something. The scan is scoped to
    the `**Benchmark:**` lines; the marker is the literal attribution rather
    than a word that also appears in the size band and the selection basis; and
    how many lines must carry it is DERIVED from BENCHMARKS rather than typed
    here, so citing or adding a threshold cannot leave a stale count behind.

    NO `cdfibenchmark/` CHANGE WAS NEEDED, which is why this release is still a
    PATCH. The rendered page already distinguishes in words the three HOUSE
    attributions it carries -- threshold, size band, selection basis. Only the
    test was asking the cheap question.

    Red-proof of the replacement, same mutation, python3.10:

        PYTHONPATH=. pytest tests -q   ->  1 failed, 329 passed, 3 skipped
    """
    peers = build_sample_peer_group(q1_institution)
    report = generate_report(q1_institution, peers)
    lines = _benchmark_lines(report)

    house_metrics = sorted(
        m for m, cfg in BENCHMARKS.items()
        if cfg.get("source") == "HOUSE"
        and cfg.get("good") is not None and cfg.get("warning") is not None
    )
    assert house_metrics, (
        "BENCHMARKS declares no HOUSE-sourced graded threshold at all, so this "
        "gate would have nothing to look for and would pass having certified "
        "nothing. Either the table changed or this gate is now vacuous."
    )
    assert len(lines) == len(BENCHMARKS), (
        f"the report renders {len(lines)} `**Benchmark:**` lines for "
        f"{len(BENCHMARKS)} entries in BENCHMARKS. A threshold whose line never "
        f"renders cannot be checked for its attribution, and its absence is "
        f"invisible to a scan of the lines that DID render."
    )

    marked = [ln for ln in lines if _HOUSE_THRESHOLD_MARK in ln]
    assert len(marked) == len(house_metrics), (
        f"{len(house_metrics)} of the {len(BENCHMARKS)} thresholds are HOUSE "
        f"rules of thumb ({', '.join(house_metrics)}), but {len(marked)} of the "
        f"{len(lines)} rendered `**Benchmark:**` lines carry "
        f"{_HOUSE_THRESHOLD_MARK!r}. A house threshold rendered in the same "
        f"column as a CFR citation without that marker reads as a standard."
        + "\nLines:\n  " + "\n  ".join(lines)
    )

    for line in lines:
        if _HOUSE_THRESHOLD_MARK in line:
            continue
        assert any(tok in line for tok in ("CFR", "USC", "FFIEC", "FDIC")), (
            f"this `**Benchmark:**` line is neither marked HOUSE nor carries a "
            f"citation naming an instrument, so it renders as a standard with "
            f"no warrant: {line!r}"
        )


def test_cited_threshold_shows_its_citation(q1_institution):
    peers = build_sample_peer_group(q1_institution)
    report = generate_report(q1_institution, peers)
    assert "12 CFR 324.12" in report


# ── summary_table must expose the same facts ─────────────────────────────────
def test_summary_table_carries_basis_and_source(q1_institution):
    peers = build_sample_peer_group(q1_institution)
    df = summary_table(q1_institution, peers)
    assert "basis" in df.columns
    assert "threshold_source" in df.columns


# ── F3 (0.3.2): the document carries no context about ITSELF ─────────────────
#
# 115 lines destined for a credit memo, and nothing said which tool version
# produced them or when the FDIC data was pulled. `Report Date: 20260630` is the
# CALL-REPORT PERIOD, not a retrieval date, and a reader has no way to know that
# from the line.
#
# Every metric line carries `Basis:` because this package cares that a figure
# carries what it was computed from. The document did not extend that rule to
# itself. Sharpened by `LTD_CALIBRATION` pinning `retrieved: 2026-09-05` -- the
# package already knows retrieval date matters enough to pin it in a test.
import re as _re
import pathlib as _pathlib

import cdfibenchmark
from cdfibenchmark.report import generator as _generator


def _provenance(report):
    assert "## Provenance" in report, (
        f"the report renders no provenance block at all:\n{report[-600:]}"
    )
    return report[report.index("## Provenance"):]


def test_the_report_states_the_version_of_the_tool_that_produced_it():
    rows = [_peer(c) for c in range(1, 21)]
    report = generate_report(_peer(57543, repdte="20260630"), rows)
    block = _provenance(report)
    assert cdfibenchmark.__version__ in block, (
        f"the provenance block does not state {cdfibenchmark.__version__!r}, "
        f"which is what `cdfibenchmark.__version__` is at render time:\n{block}"
    )


def test_an_undeterminable_version_is_rendered_honestly_not_suppressed():
    """Running from a clone is exactly when a reader most needs to know.

    `__version__` falls back to "0.0.0+unknown" when no installed distribution
    metadata exists. That must reach the page, with the reason, rather than
    being hidden or replaced by a number read out of pyproject.toml -- which
    would make the artifact claim a version the running code may not be.
    """
    with patch.object(cdfibenchmark, "__version__", "0.0.0+unknown"):
        rows = [_peer(c) for c in range(1, 21)]
        report = generate_report(_peer(57543, repdte="20260630"), rows)
    block = _provenance(report)
    assert "0.0.0+unknown" in block, (
        f"an undeterminable version was suppressed rather than stated:\n{block}"
    )
    assert "no installed distribution metadata" in block, (
        f"the page states 0.0.0+unknown without saying what it means:\n{block}"
    )


def test_the_version_is_read_at_render_time_not_frozen_at_import():
    """A module-level snapshot would be right today and wrong after an upgrade."""
    rows = [_peer(c) for c in range(1, 21)]
    with patch.object(cdfibenchmark, "__version__", "9.9.9-probe"):
        report = generate_report(_peer(57543, repdte="20260630"), rows)
    assert "9.9.9-probe" in _provenance(report), (
        "the rendered version did not follow cdfibenchmark.__version__"
    )


def _code_strings(module):
    """Every string constant in `module` that is not a docstring.

    A regex over the file text cannot draw this distinction, and the
    distinction is the whole gate: the docstring below deliberately QUOTES
    `version="0.2.1"` in order to record the defect this gate exists to
    prevent, and a scan that cannot tell a quotation from an assertion forces
    the documentation out. The same ruling `_CODE_SPAN` reached for the cert
    scan in test_package_claims.py, made structurally here rather than by
    pattern.
    """
    import ast

    tree = ast.parse(_pathlib.Path(module.__file__).read_text())
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)):
            body = getattr(node, "body", None)
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                docstrings.add(id(body[0].value))
    return [n.value for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
            and id(n) not in docstrings]


def test_no_version_string_is_hand_typed_in_the_renderer():
    """One declared version. A second site that no gate reads goes stale.

    This is the defect `setup.py` was emptied for in 0.3.1: it carried
    `version="0.2.1"` while two further releases shipped to PyPI, and no gate
    read it. The sentinel for an undeterminable version is likewise named once,
    as `cdfibenchmark.UNKNOWN_VERSION`, rather than re-typed here.
    """
    literals = [v for v in _code_strings(_generator)
                if _re.search(r"\d+\.\d+\.\d+", v)]
    assert not literals, (
        f"the renderer hand-types version-shaped literals {literals}; the "
        f"version must come from cdfibenchmark.__version__ alone"
    )
    # Also structural, and for the same reason: the docstring above explains
    # WHY the renderer must not read pyproject.toml, and a raw-text scan for
    # the word cannot tell that explanation from the act.
    reads_toml = [v for v in _code_strings(_generator) if "pyproject" in v]
    assert not reads_toml, (
        f"the renderer names pyproject.toml in code ({reads_toml}) — that is "
        f"the DECLARED version, not the version of the code actually running"
    )
    import ast as _ast

    imported = set()
    for node in _ast.walk(_ast.parse(
            _pathlib.Path(_generator.__file__).read_text())):
        if isinstance(node, _ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, _ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert not {"tomllib", "tomli"} & imported, (
        f"the renderer imports a TOML parser ({sorted(imported)}); the only "
        f"version it may state is the one the running code reports"
    )


def test_the_report_states_when_it_was_generated():
    rows = [_peer(c) for c in range(1, 21)]
    block = _provenance(generate_report(_peer(57543, repdte="20260630"), rows))
    assert _re.search(r"\*\*Report Generated:\*\* \d{4}-\d{2}-\d{2} "
                      r"\d{2}:\d{2}:\d{2} UTC", block), (
        f"no generation timestamp on the page:\n{block}"
    )


def test_the_report_separates_the_call_report_period_from_the_retrieval_date():
    """`Report Date: 20260630` is a period. It is not when the data was pulled."""
    rows = [_peer(c) for c in range(1, 21)]
    block = _provenance(generate_report(_peer(57543, repdte="20260630"), rows))
    assert "20260630" in block, "the provenance block does not name the period"
    assert "not the date" in block or "not when" in block, (
        f"the block does not tell the reader the period is not a retrieval "
        f"date:\n{block}"
    )


def test_a_hand_built_profile_says_the_retrieval_date_is_unknown():
    """Nothing was retrieved, so nothing may be claimed about when."""
    rows = [_peer(c) for c in range(1, 21)]
    block = _provenance(generate_report(_peer(57543, repdte="20260630"), rows))
    assert _re.search(r"\*\*FDIC Data Retrieved:\*\* .*(unknown|not recorded)",
                      block), (
        f"a profile that was never retrieved claims a retrieval date:\n{block}"
    )


def test_a_parsed_profile_carries_the_moment_it_was_retrieved():
    """The parse layer is the only place that knows when the wire was read."""
    from cdfibenchmark.data.fdic import _parse_institution
    row = {
        "CERT": 34352, "NAME": "CITY FIRST BANK NA", "CITY": "Washington",
        "STALP": "DC", "REPDTE": "20260630",
        "ASSET": 1562007, "DEP": 1182800, "LNLSNET": 1126539,
        "NETINC": 2345, "INTINC": 34011, "EINTEXP": 15521,
        "NONII": 1541, "NONIX": 15143, "EQ": 120000,
    }
    profile = _parse_institution(row)
    assert profile.retrieved_at, "a parsed profile records no retrieval moment"
    assert _re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} UTC",
                         profile.retrieved_at), (
        f"retrieved_at is not a UTC timestamp: {profile.retrieved_at!r}"
    )
    report = generate_report(profile, [_peer(c) for c in range(1, 21)])
    assert profile.retrieved_at in _provenance(report), (
        "the recorded retrieval moment does not reach the page"
    )
