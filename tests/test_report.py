import pytest
import pandas as pd
from cdfibenchmark.report.generator import generate_report, summary_table


def test_generate_report_returns_string(sample_institution, sample_peers):
    report = generate_report(sample_institution, sample_peers)
    assert isinstance(report, str)
    assert len(report) > 100


def test_report_contains_institution_name(sample_institution, sample_peers):
    report = generate_report(sample_institution, sample_peers)
    assert sample_institution.name in report


def test_report_contains_sections(sample_institution, sample_peers):
    report = generate_report(sample_institution, sample_peers)
    assert "Performance Summary" in report
    assert "Metric Detail" in report
    assert "Peer Group Summary" in report


def test_summary_table_returns_dataframe(sample_institution, sample_peers):
    df = summary_table(sample_institution, sample_peers)
    assert isinstance(df, pd.DataFrame)
    assert len(df) > 0
    assert "metric" in df.columns
    assert "status" in df.columns


def test_report_contains_nim(sample_institution, sample_peers):
    report = generate_report(sample_institution, sample_peers)
    assert "Net Interest Margin" in report


# ── fail-loud rendering: absence (NaN) must read as N/A, never "nan" ──────────

def _summary_rows(report):
    """The data rows of the Performance Summary markdown table."""
    return [
        ln for ln in report.splitlines()
        if ln.startswith("|") and "Metric" not in ln and "---" not in ln
    ]


def test_nan_cored_report_has_no_nan_substring(nan_cored_institution, sample_peers):
    """A NaN-cored institution must never leak 'nan'/'$nanMM' into the report."""
    report = generate_report(nan_cored_institution, sample_peers)
    assert "nan" not in report.lower()


def test_nan_cored_value_cell_renders_na_consistent_with_status(
    nan_cored_institution, sample_peers
):
    """The NaN value cell renders 'N/A' and agrees with its Status cell —
    no 'nan%' beside a graded status, no value erased while still graded."""
    report = generate_report(nan_cored_institution, sample_peers)
    roaa_rows = [r for r in _summary_rows(report) if "ROAA" in r]
    assert roaa_rows, "ROAA row missing from summary table"
    row = roaa_rows[0]
    cells = [c.strip() for c in row.strip("|").split("|")]
    # cells: label | institution | median | p25 | p75 | status
    inst_cell, status_cell = cells[1], cells[5]
    assert inst_cell == "N/A", f"expected N/A institution cell, got {inst_cell!r}"
    # value N/A must be consistent with an N/A status (—), not graded
    assert status_cell == "—", f"value N/A but status graded: {status_cell!r}"


def test_present_zero_renders_as_zero_not_na_and_is_graded(
    present_zero_cored_institution, sample_peers
):
    """A real reported 0.0 (roaa) must render '0.00%', NOT 'N/A', and be graded."""
    report = generate_report(present_zero_cored_institution, sample_peers)
    roaa_rows = [r for r in _summary_rows(report) if "ROAA" in r]
    assert roaa_rows, "ROAA row missing from summary table"
    cells = [c.strip() for c in roaa_rows[0].strip("|").split("|")]
    inst_cell, status_cell = cells[1], cells[5]
    assert inst_cell == "0.00%", f"present zero erased: got {inst_cell!r}"
    # roaa 0.0 < warning 0.5 → graded WEAK; value and status must agree (graded)
    assert status_cell != "—", "present zero rendered a value but was not graded"
    assert "WEAK" in status_cell


def test_present_zero_detail_section_renders_zero(
    present_zero_cored_institution, sample_peers
):
    """The Metric Detail section shows the present zero as '0.00%', not omitted."""
    report = generate_report(present_zero_cored_institution, sample_peers)
    assert "**Institution Value:** 0.00%" in report


def test_nan_assets_render_na_not_dollar_nan(nan_cored_institution, sample_peers):
    """NaN total assets render 'N/A', never '$nanMM'."""
    report = generate_report(nan_cored_institution, sample_peers)
    assert "$nanMM" not in report
    assert "**Total Assets:** N/A" in report


def test_zero_assets_render_zero_mm():
    """Real 0.0 total assets render '$0.0MM', not 'N/A'."""
    from cdfibenchmark.data.schema import InstitutionProfile
    from cdfibenchmark.peers.selector import build_sample_peer_group

    inst = InstitutionProfile(
        cert=57544, name="Zero Asset Bank", city="LA", state="CA",
        report_date="20241231",
        total_assets=0, total_deposits=0, net_loans=0, net_income=0,
        interest_income=0, interest_expense=0, non_interest_income=0,
        non_interest_expense=0, total_equity=0,
    )
    # peers built from a non-degenerate institution so rendering has real data
    peers = build_sample_peer_group(
        InstitutionProfile(
            cert=1, name="P", city="LA", state="CA", report_date="20241231",
            total_assets=655_000, total_deposits=520_000, net_loans=380_000,
            net_income=1_950, interest_income=28_000, interest_expense=8_000,
            non_interest_income=3_500, non_interest_expense=22_000,
            total_equity=48_000,
        )
    )
    report = generate_report(inst, peers)
    assert "**Total Assets:** $0.0MM" in report
    assert "$nanMM" not in report
