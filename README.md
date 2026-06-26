# cdfi-benchmark 📊

**CDFI and MDI peer benchmarking tool using FDIC call report data.**

Pull call report financials for any FDIC-insured CDFI or MDI, compute key performance
metrics, build a peer group of similar institutions, and generate a benchmarking report
— using the free FDIC BankFind Suite API, no API key required.

---

## Why cdfi-benchmark?

CDFI banks and MDIs benchmark their performance against peers manually — pulling
call report data from FFIEC, computing ratios in Excel, and building comparison
tables by hand. cdfi-benchmark automates the entire workflow in Python.

---

## Installation

    pip install cdfi-benchmark

---

## Quickstart

    from cdfibenchmark import (
        get_financials, build_peer_group,
        generate_report, summary_table,
    )

    # Pull call report data for Broadway Federal Bank (CERT 57542)
    institution = get_financials(cert=57542)

    # Build peer group — similar asset size, no API key needed
    peers = build_peer_group(institution, same_state=True)

    # Generate benchmarking report
    report = generate_report(institution, peers)
    print(report)

    # Get results as DataFrame
    df = summary_table(institution, peers)

---

## Sample Data (No API Required)

    from cdfibenchmark import build_sample_peer_group
    from cdfibenchmark.data.schema import InstitutionProfile

    institution = InstitutionProfile(
        cert=57542,
        name="Broadway Federal Bank",
        city="Los Angeles",
        state="CA",
        report_date="20241231",
        total_assets=655_000,
        total_deposits=520_000,
        net_loans=380_000,
        net_income=1_950,
        interest_income=28_000,
        interest_expense=8_000,
        non_interest_income=3_500,
        non_interest_expense=22_000,
        total_equity=48_000,
        tier1_ratio=12.2,
    )

    peers = build_sample_peer_group(institution)
    report = generate_report(institution, peers)
    print(report)

---

## Metrics Computed

| Metric | Description | Benchmark (Strong) |
|--------|-------------|-------------------|
| NIM | Net Interest Margin | >= 3.5% |
| Efficiency Ratio | Non-interest expense / Revenue | <= 60% |
| ROAA | Return on Average Assets | >= 1.0% |
| ROAE | Return on Average Equity | >= 10% |
| Tier 1 Capital Ratio | Regulatory capital ratio | >= 12% |
| Loans-to-Deposits | Loan utilization | <= 80% |
| NPL Ratio | Non-performing loans / Gross loans | <= 1.0% |
| Reserve Coverage | Loan loss reserve / NPLs | >= 100% |

---

## Asset Size Buckets

- micro — Under $50MM
- small — $50MM to $250MM
- medium — $250MM to $1B
- large — $1B to $5B
- mega — Over $5B

---

## Data Source

FDIC BankFind Suite API — free public API, no authentication required.
Data covers all FDIC-insured institutions with quarterly call report data
since 1934.

    https://banks.data.fdic.gov/api

---

## Error handling

The data layer **fails loud**. In an early-warning / anomaly-detection pipeline a
silently-empty or fabricated result reads as "nothing anomalous" and masks the real
problem, so the FDIC fetchers raise typed errors instead of swallowing failures:

- **`FDICAPIError`** — a *transport* problem: the request never produced a usable
  response body. Network/timeout errors, non-2xx HTTP status, and JSON decode
  failures all raise this.
- **`FDICResponseError`** — the response *decoded* but its structure is wrong, either
  at the envelope level (the top-level `data` key absent, `null`, or not a list) or at
  the *field* level inside a record: a record missing its `CERT` identity, a `CERT`
  that isn't int-coercible, or any core/optional financial field that is **present but
  not numeric**. A bad record is never coerced into a phantom `cert=0` bank or a
  fabricated `0.0`.
- **Legitimately empty is not an error.** A successful request that returns zero rows
  (`{"data": []}`) returns the empty value for that fetcher — `None`,
  an empty `DataFrame`, or `[]` — and does **not** raise.

Missing-but-not-garbage fields inside an otherwise valid record are kept, not dropped:
an absent **core** financial (e.g. `ASSET`) becomes `NaN` (unknown — it propagates to
any metric computed from it rather than fabricating `0.0`), and an absent **optional**
ratio (e.g. `RBCT1J`) becomes `None`. A real present `0.0` is preserved as `0.0`.

Both error types subclass `CDFIBenchmarkError`, so callers can catch the contract
broadly or distinguish "the API is unreachable" (`FDICAPIError`) from "the API changed
its shape" (`FDICResponseError`):

    from cdfibenchmark import FDICAPIError, FDICResponseError

    try:
        institution = get_financials(cert=57542)
    except FDICAPIError:
        ...   # transport/HTTP/decode failure — retry or alert
    except FDICResponseError:
        ...   # wrong-shape or present-but-garbage field — contract problem

---

## Running Tests

    PYTHONPATH=. pytest tests/ -v

79 tests across all modules.

---

## Who This Is For

- CDFI banks and credit unions benchmarking against peers
- MDI management teams preparing board reports
- CDFI Fund analysts reviewing institution performance
- Impact investors evaluating CDFI bank investments
- Researchers studying community banking performance trends

---

## License

MIT 2026 Jaypatel1511
