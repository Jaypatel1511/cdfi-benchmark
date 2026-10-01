"""0.3.4: per-metric peer n, and the floor below which peer statistics are withheld.

Methodology v2.1 (2026-09-30), section 2.1, gates G-P1 to G-P11. Every page
here is rendered offline from synthetic profiles. The CERT-16583-shaped group
(G-P11) reproduces the SHAPE the audit measured live at 20260630 -- group 19;
reserve_coverage n = 1, npl_ratio n = 4 with median 0.00, loans_to_deposits
n = 7, every other metric n = 19 -- not its values.
"""
import re

import pandas as pd
import pytest

import cdfibenchmark
from cdfibenchmark import (
    InstitutionProfile, benchmark_institution, build_sample_peer_group,
    generate_report, summary_table,
)
from cdfibenchmark.data import schema
from cdfibenchmark.data.schema import BENCHMARKS, PEER_STAT_MIN_N
from cdfibenchmark.peers import selector
from cdfibenchmark.peers.selector import HOUSE_MIN_PEERS, PeerGroup
from cdfibenchmark.report import generator
from cdfibenchmark.report.generator import METRIC_LABELS, _metric_label

from . import _gp7
from . import _layout as layout


# ── fixtures ─────────────────────────────────────────────────────────────────
def _bank(cert, i=0, **over):
    return _gp7._profile(InstitutionProfile, cert, "20260630", i, **over)


def _group(peers, subject, **over):
    kw = dict(min_peers=HOUSE_MIN_PEERS, target_report_date="20260630",
              subject_assets=subject.total_assets, universe_size=621,
              asset_tolerance=0.5, max_peers=50)
    kw.update(over)
    return PeerGroup(peers, **kw)


def _cert16583():
    subject, peers = _gp7.cert16583_shaped(InstitutionProfile)
    return subject, _group(peers, subject)


def _uniform(k, **group_kw):
    """k peers, every metric defined on every peer."""
    subject = _bank(1, 7)
    return subject, _group([_bank(9000 + i, i) for i in range(k)], subject,
                           **group_kw)


def _reserve_n(n, size=20, **group_kw):
    """A `size`-peer group in which exactly `n` peers have reserve coverage
    (the rest report zero non-current loans: a zero denominator)."""
    subject = _bank(1, 7)
    peers = [_bank(9000 + i, i, **({} if i < n else {"non_current_loans": 0.0}))
             for i in range(size)]
    return subject, _group(peers, subject, **group_kw)


def _sample():
    subject = _bank(99001, 7)
    return subject, build_sample_peer_group(subject)


def _pages():
    """Every page shape the gates run on: (name, subject, peers)."""
    return [("cert16583-shape", *_cert16583()), ("3-peer", *_uniform(3)),
            ("7-peer", *_uniform(7)), ("sample", *_sample()),
            ("reserve-n0", *_reserve_n(0))]


PAGES = _pages()
PAGE_IDS = [name for name, _, _ in PAGES]


def _summary_cells(report):
    """{label: {header: cell}} for the Performance Summary table."""
    lines = report.splitlines()
    header = next(ln for ln in lines if ln.startswith("| Metric |"))
    labels = [c.strip() for c in header.strip().strip("|").split("|")]
    out = {}
    for ln in lines[lines.index(header) + 2:]:
        if not ln.startswith("|"):
            break
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        out[cells[0]] = dict(zip(labels, cells))
    return out


def _block(report, label):
    start = report.index(f"### {label}\n")
    nxt = report.find("\n### ", start + 1)
    end = nxt if nxt != -1 else report.index("\n## Peer Group Summary", start)
    return report[start:end]


# ── G-P1 / G-P11: n is shown wherever a peer statistic is ────────────────────
@pytest.mark.parametrize("name,subject,peers", PAGES, ids=PAGE_IDS)
def test_every_peer_statistic_carries_its_n(name, subject, peers):
    report = generate_report(subject, peers)
    table = _summary_cells(report)
    assert "Peers (n)" in next(iter(table.values())), "no Peers (n) column"
    checked = 0
    for r in benchmark_institution(subject, peers):
        label = _metric_label(r.metric, r.basis)
        n = r.peer_count
        assert table[label]["Peers (n)"] == str(n), (label, table[label])
        block = _block(report, label)
        if n >= PEER_STAT_MIN_N:
            pm = [ln for ln in block.splitlines()
                  if ln.startswith("**Peer Median:**")]
            assert len(pm) == 1 and pm[0].endswith(
                f"(n = {n} peers with a value for this metric)"), block
            for vs in (ln for ln in block.splitlines()
                       if ln.startswith("**vs Peer Median:**")):
                assert vs.endswith(f" (vs a median of {n} peers with a value)"), vs
        elif n > 0:
            assert (f"**Peer statistics:** withheld — only {n} of the "
                    f"{len(peers)} peers in this group have a value for this "
                    f"metric") in block, block
        checked += 1
    assert checked == len(BENCHMARKS)


def test_the_cert16583_fixture_has_the_measured_shape():
    """G-P11: the fixture is what it claims to be, or every gate on it is moot."""
    subject, peers = _cert16583()
    assert len(peers) == 19
    got = {r.metric: r for r in benchmark_institution(subject, peers)}
    assert got["reserve_coverage"].peer_count == 1
    assert round(got["reserve_coverage"].peer_median, 2) == 60.24
    assert got["npl_ratio"].peer_count == 4
    assert got["npl_ratio"].peer_median == 0.0
    assert got["loans_to_deposits"].peer_count == 7
    for m in ("nim", "efficiency_ratio", "roaa", "roae", "tier1_ratio"):
        assert got[m].peer_count == 19, m
    assert peers.caveats == [] or not any(
        "below the requested minimum" in c for c in peers.caveats)


def test_the_cert16583_page_withholds_the_one_and_four_peer_cells():
    subject, peers = _cert16583()
    report = generate_report(subject, peers)
    table = _summary_cells(report)
    for label, n in (("Loan Loss Reserve Coverage", 1),
                     ("Non-Performing Loan Ratio", 4)):
        row = table[label]
        assert [row["Peer Median"], row["25th Pctile"], row["75th Pctile"]] \
            == ["withheld"] * 3, row
        assert row["Peers (n)"] == str(n)
        block = _block(report, label)
        assert "**Peer Median:**" not in block and "**vs Peer Median:**" not in block
    assert "60.24%" not in report, "the one-peer reserve-coverage median reached the page"
    ltd = _block(report, "Loans-to-Deposits")
    assert "(n = 7 peers with a value for this metric)" in ltd
    assert "**Thin peer cell:** 7 of 19 peers have a value" in ltd


# ── G-P1b: the vocabulary ────────────────────────────────────────────────────
@pytest.mark.parametrize("name,subject,peers", PAGES, ids=PAGE_IDS)
def test_no_page_says_a_peer_reported_or_did_not_report_a_metric(name, subject, peers):
    report = generate_report(subject, peers)
    for banned in ("reported this metric", "peers reporting"):
        assert banned not in report, banned
    df = summary_table(subject, peers)
    for v in df["report_withholds_peer_stats"]:
        if v is not None:
            assert "reported this metric" not in v and "peers reporting" not in v


# ── G-P2: the floor and the thin band ────────────────────────────────────────
def _reserve_block(n, size=20, **group_kw):
    subject, peers = _reserve_n(n, size, **group_kw)
    report = generate_report(subject, peers)
    return report, _block(report, "Loan Loss Reserve Coverage"), \
        _summary_cells(report)["Loan Loss Reserve Coverage"]


@pytest.mark.parametrize("n", [1, 4])
def test_below_the_floor_every_peer_statistic_is_withheld(n):
    _, block, row = _reserve_block(n)
    assert [row["Peer Median"], row["25th Pctile"], row["75th Pctile"]] \
        == ["withheld"] * 3, row
    assert row["Peers (n)"] == str(n)
    assert (f"**Peer statistics:** withheld — only {n} of the 20 peers in this "
            f"group have a value for this metric, below this tool's house "
            f"minimum of {PEER_STAT_MIN_N} for showing a median or "
            f"percentiles. A peer has no value when the metric is undefined "
            f"for it (a zero denominator, e.g. reserve coverage at a bank with "
            f"no noncurrent loans), when a field was not reported, or when "
            f"this tool refused the published value.") in block, block
    assert "**Peer Median:**" not in block
    assert "**vs Peer Median:**" not in block
    assert "**Thin peer cell:**" not in block


def test_at_the_floor_statistics_are_shown_with_the_thin_cell_line():
    _, block, row = _reserve_block(PEER_STAT_MIN_N)
    assert "withheld" not in row.values()
    assert f"(n = {PEER_STAT_MIN_N} peers with a value for this metric)" in block
    assert "**vs Peer Median:**" in block
    assert (f"**Thin peer cell:** {PEER_STAT_MIN_N} of 20 peers have a value "
            f"for this metric (this tool's house minimum for a peer group is "
            f"{HOUSE_MIN_PEERS}); read the median and percentiles as "
            f"indicative.") in block, block
    assert "**Peer statistics:**" not in block


def test_at_the_house_minimum_there_is_no_thin_cell_line():
    _, block, _ = _reserve_block(HOUSE_MIN_PEERS)
    assert f"(n = {HOUSE_MIN_PEERS} peers with a value" in block
    assert "**Thin peer cell:**" not in block


def test_the_thin_band_ignores_a_larger_caller_minimum():
    """min_peers=20, metric n = 15: above the HOUSE minimum, so no thin line,
    whatever the caller asked for."""
    _, block, _ = _reserve_block(15, size=20, min_peers=20)
    assert "(n = 15 peers with a value" in block
    assert "**Thin peer cell:**" not in block


def test_the_thin_band_ignores_a_smaller_caller_minimum():
    """min_peers=0, metric n = 6: below the HOUSE minimum, so the thin line."""
    _, block, _ = _reserve_block(6, size=20, min_peers=0)
    assert "**Thin peer cell:** 6 of 20 peers have a value" in block


# ── G-P3: the group count is never offered as a statistic's n ────────────────
@pytest.mark.parametrize("name,subject,peers", PAGES[:4], ids=PAGE_IDS[:4])
def test_the_group_count_is_qualified_everywhere_it_is_printed(name, subject, peers):
    report = generate_report(subject, peers)
    assert report.count("Peer Count:") == 0
    assert report.count("reported this metric") == 0
    clause = ("— each metric's peer statistics use only the peers with a value "
              "for that metric; see Peers (n)")
    n = len(peers)
    assert f"**Peer Group Size:** {n} institutions selected {clause}" in report
    assert f"**Institutions Selected:** {n} {clause}" in report
    assert f"\n**Distinct Institutions:** {len({p.cert for p in peers})}\n" in report


@layout.needs("README.md")
def test_the_readme_has_no_vs_median_example_without_its_n():
    """E12: README renders on PyPI; a 0.3.3-shaped example is a stale claim."""
    text = layout.SURFACES["README.md"].read_text()
    lines = [ln for ln in text.splitlines() if "**vs Peer Median:**" in ln]
    assert lines, "the README lost its vs-median example"
    for ln in lines:
        assert re.search(r"\(vs a median of \d+ peers? with a value\)\s*$", ln), ln


# ── G-P4: n = 0 ──────────────────────────────────────────────────────────────
def test_zero_peers_with_a_value_never_reads_only_zero():
    subject, peers = _reserve_n(0)
    report = generate_report(subject, peers)
    assert "only 0" not in report
    block = _block(report, "Loan Loss Reserve Coverage")
    assert ("**Peer statistics:** none — no peer in this group has a value for "
            "this metric.") in block, block
    row = _summary_cells(report)["Loan Loss Reserve Coverage"]
    assert row["Peers (n)"] == "0"
    assert row["Peer Median"] == "N/A"
    df = summary_table(subject, peers)
    assert df.loc[df["metric"] == "Loan Loss Reserve Coverage",
                  "report_withholds_peer_stats"].iloc[0] is None


def test_an_empty_group_never_reads_only_zero():
    subject = _bank(1, 7)
    report = generate_report(subject, _group([], subject))
    assert "only 0" not in report
    assert report.count("no peer in this group has a value") == len(BENCHMARKS)


# ── G-P5: the two constants are read, not retyped ────────────────────────────
def test_the_render_layer_reads_the_constants_it_prints():
    assert generator.PEER_STAT_MIN_N is schema.PEER_STAT_MIN_N
    assert selector.PEER_STAT_MIN_N is schema.PEER_STAT_MIN_N
    assert generator.HOUSE_MIN_PEERS is selector.HOUSE_MIN_PEERS


def test_moving_the_floor_moves_every_surface(monkeypatch):
    """If any surface typed 5 or 10, moving the constant would leave it behind."""
    monkeypatch.setattr(generator, "PEER_STAT_MIN_N", 7)
    monkeypatch.setattr(schema, "PEER_STAT_MIN_N", 7)
    monkeypatch.setattr(selector, "PEER_STAT_MIN_N", 7)
    monkeypatch.setattr(generator, "HOUSE_MIN_PEERS", 12)
    report, block, row = _reserve_block(6)
    assert row["Peer Median"] == "withheld"
    assert "house minimum of 7 for showing a median" in block
    subject, peers = _reserve_n(6)
    df = summary_table(subject, peers)
    reason = df.loc[df["metric"] == "Loan Loss Reserve Coverage",
                    "report_withholds_peer_stats"].iloc[0]
    assert "house minimum of 7." in reason
    _, block, _ = _reserve_block(11)
    assert "this tool's house minimum for a peer group is 12" in block
    subject, peers = _uniform(6, min_peers=10)
    assert "house minimum for showing them is 7" in " ".join(peers.caveats)


@layout.needs("README.md")
def test_the_readme_states_the_floor_the_code_uses():
    """Census row 16 types the number; it must be the constant's value (E11)."""
    text = " ".join(layout.SURFACES["README.md"].read_text().split())
    m = re.search(r"the whole comparison is withheld when fewer than (\d+) "
                  r"peers have a value", text)
    assert m, "README lost the withheld-comparison sentence"
    assert int(m.group(1)) == PEER_STAT_MIN_N


def test_the_floor_is_not_exported():
    assert "PEER_STAT_MIN_N" not in cdfibenchmark.__all__


# ── G-P6: None stays None ────────────────────────────────────────────────────
def test_none_stays_none_in_both_object_columns():
    """Under whatever pandas this leg resolved; the version is in the id
    below and in the assertion message."""
    subject, peers = _cert16583()
    df = summary_table(subject, peers)
    for col in ("not_graded_reason", "report_withholds_peer_stats"):
        assert df[col].dtype == object, (pd.__version__, col, df[col].dtype)
    withheld = df[df["metric"] == "Loan Loss Reserve Coverage"].iloc[0]
    normal = df[df["metric"] == "Efficiency Ratio"].iloc[0]
    assert isinstance(withheld["report_withholds_peer_stats"], str)
    assert normal["report_withholds_peer_stats"] is None, pd.__version__
    assert normal["not_graded_reason"] is None, pd.__version__
    assert withheld["not_graded_reason"] is None, pd.__version__


def test_pandas_version_under_test_is_recorded(record_property):
    record_property("pandas", pd.__version__)
    assert pd.__version__


def test_the_dataframe_and_the_page_state_the_same_n_of_n():
    subject, peers = _cert16583()
    report = generate_report(subject, peers)
    df = summary_table(subject, peers)
    for label, n in (("Loan Loss Reserve Coverage", 1),
                     ("Non-Performing Loan Ratio", 4)):
        reason = df.loc[df["metric"] == label,
                        "report_withholds_peer_stats"].iloc[0]
        assert reason == (
            f"The rendered report withholds this row's peer median, "
            f"percentiles and vs-median: only {n} of the 19 peers have a value "
            f"for this metric, below this tool's house minimum of "
            f"{PEER_STAT_MIN_N}. The values in this row are computed over "
            f"those {n} peer{'s' if n != 1 else ''}.")
        assert f"only {n} of the 19 peers in this group have a value" \
            in _block(report, label)
    for label in ("Loans-to-Deposits", "Efficiency Ratio"):
        assert df.loc[df["metric"] == label,
                      "report_withholds_peer_stats"].iloc[0] is None


def test_a_result_built_without_the_group_size_omits_it():
    r = schema.BenchmarkResult(metric="npl_ratio", institution_value=1.0,
                               peer_median=0.0, peer_25th=0.0, peer_75th=0.0,
                               peer_count=1)
    assert "only 1 peer has a value" in r.report_withholds_peer_stats
    assert " of the " not in r.report_withholds_peer_stats


# ── G-P7: no grade or value moves (regression tripwire, not a proof) ─────────
def test_no_value_or_grade_differs_from_the_published_033_wheel():
    """Compares against `tests/_gp7_v033.py`, which `tests/_gp7.py` printed
    under a venv holding only the published 0.3.3 wheel. No network, no
    second interpreter."""
    from . import _gp7_v033 as recorded
    assert recorded.VERSION == "0.3.3"
    now = _gp7.snapshot()
    assert sorted(now) == sorted(recorded.SNAPSHOT)
    for case, rows in recorded.SNAPSHOT.items():
        assert now[case] == rows, case


def test_the_group_size_field_is_the_number_of_peers_passed():
    for _cid, subject, peers in _gp7.cases(InstitutionProfile):
        for r in benchmark_institution(subject, peers):
            assert r.peer_group_size == len(peers)


# ── G-P8: the column contract ────────────────────────────────────────────────
def test_summary_table_has_twelve_columns_and_all_has_twenty_one():
    subject, peers = _cert16583()
    assert list(summary_table(subject, peers).columns) == [
        *_gp7.TABLE_COLUMNS, "report_withholds_peer_stats"]
    assert len(cdfibenchmark.__all__) == 21


# ── P8 / G-P10: the group caveat describes this document ─────────────────────
@pytest.mark.parametrize("k", [1, 2, 3, 4])
def test_a_group_below_the_floor_says_every_statistic_is_withheld(k):
    subject, peers = _uniform(k)
    report = generate_report(subject, peers)
    word = "institution" if k == 1 else "institutions"
    assert (f"Peer group has {k} {word}, below the requested minimum of "
            f"{HOUSE_MIN_PEERS}; every peer median and percentile in this "
            f"report is withheld (this tool's house minimum for showing them "
            f"is {PEER_STAT_MIN_N}).") in report
    assert "Percentiles over so few peers" not in report
    assert "**Peer Median:**" not in report
    for row in _summary_cells(report).values():
        assert row["Peer Median"] == "withheld", row


def test_the_cert16583_group_has_no_below_minimum_caveat():
    subject, peers = _cert16583()
    report = generate_report(subject, peers)
    assert "below the requested minimum" not in report


# ── N11 ──────────────────────────────────────────────────────────────────────
def test_the_sample_selection_basis_has_one_article():
    _, peers = _sample()
    basis = peers.selection_basis
    assert "in an unrecorded asset window" in basis
    assert "a an" not in basis
    _, peers = _uniform(20)
    assert "in a +/-50% asset window" in peers.selection_basis
