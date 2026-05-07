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
