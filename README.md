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

    # Pull call report data for City First Bank, N.A. (CERT 34352) — a real
    # CDFI/MDI in Washington, DC. Look a CERT up with search_institutions()
    # rather than copying one; a cert and a name are bound by the FDIC, not
    # by this README.
    institution = get_financials(cert=34352)

    # Build peer group — similar asset size, no API key needed. Peers are
    # pinned to the institution's own report_date unless you pass another.
    peers = build_peer_group(institution, same_state=True)

    # Anything that makes the peer group less than ideal is on the group and
    # is rendered on the report — a dropped same-state constraint, a group
    # below min_peers, a mixed reporting period.
    for caveat in peers.caveats:
        print("CAVEAT:", caveat)

    # Generate benchmarking report
    report = generate_report(institution, peers)
    print(report)

    # Get results as DataFrame — includes `basis` and `threshold_source`
    df = summary_table(institution, peers)

---

## Sample Data (No API Required)

**Everything in this block is invented.** The institution does not exist, its
CERT is outside the FDIC's issued range, and `build_sample_peer_group` generates
its peers by scaling these figures pseudo-randomly. No report built from it
describes any real bank. Use it to see the output shape, never as data.

    from cdfibenchmark import build_sample_peer_group
    from cdfibenchmark.data.schema import InstitutionProfile

    institution = InstitutionProfile(
        cert=99001,                                   # not an issued FDIC cert
        name="Riverstone Community Bank (SYNTHETIC)",
        city="Los Angeles",
        state="CA",
        report_date="20241231",                       # Q4 — a full-year period
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

Because this profile carries no FDIC-published ratios, NIM/ROAA/ROAE fall back to
the computed proxy — so the report shows their values with a **Basis:** line and
grades NIM `N/A`. That is the intended behaviour, not a bug; see
**Period basis** below.

---

## Metrics Computed

| Metric | Source field | Benchmark (Strong) | Threshold provenance |
|--------|--------------|--------------------|----------------------|
| NIM | FDIC `NIMY` | >= 3.5% | **HOUSE** |
| Efficiency Ratio | FDIC `EEFFR` | <= 60% | **HOUSE** |
| ROAA | FDIC `ROA` | >= 1.0% | **HOUSE** |
| ROAE | FDIC `ROE` | >= 10% | **HOUSE** |
| Tier 1 Leverage Ratio | FDIC `RBC1AAJ` | >= 8% | 12 CFR 324.12 / 324.403 |
| Loans-to-Deposits | `LNLSNET` / `DEP` | 50%–80% (band) | **HOUSE** |
| NPL Ratio | `NCLNLS` / `LNLSGR` | <= 1.0% | **HOUSE** |
| Reserve Coverage | `LNATRES` / `NCLNLS` | >= 100% | **HOUSE** |

### Threshold provenance

`tier1_ratio` is the **only** metric whose thresholds come from a published
regulatory standard. Bank capital has one; earnings, efficiency, funding and
reserve-coverage ratios do not — the FDIC publishes these series and reports them
against a peer group in the UBPR, but publishes no required or "well
capitalized"-equivalent cut point for any of them.

Every other threshold in this package is therefore a **HOUSE** rule of thumb: this
tool's own, marked `"source": "HOUSE"` in `BENCHMARKS`, defined by `HOUSE_`-prefixed
constants, and rendered on every report as *"this tool's own threshold (HOUSE), not
a regulatory or supervisory standard"*. Treat them as a starting point to be
argued with, not as a standard to be met.

**Loans-to-deposits is graded as a band, not a ladder.** Above the band is funding
strain; below it is under-deployment, which for a CDFI bank is its own failure. All
three boundaries are house numbers. Calibration note, measured against the 50 real
peers of CERT 34352 at `20260630`: this band grades 22 of 50 WEAK, with a peer
median of 91.12% sitting inside the WEAK zone. The boundaries are deliberately
conservative; they have not been fitted to any population.

---

## Period basis — read this before comparing a quarter

FDIC call-report income items (`INTINC`, `EINTEXP`, `NETINC`) are **year-to-date**.
At a Q1 `REPDTE` they cover three months. Dividing them by a point-in-time balance
and grading the result against an annual-basis threshold reads roughly **4x low** —
a healthy bank grades WEAK. Measured for CERT 34352 at `20260331`, computed versus
FDIC's own published series: NIM 4.30x, ROAA 4.12x, ROAE 4.01x.

This package does **not** annualize an estimate. It prefers FDIC's own published
ratios — `NIMY`, `ROA`, `ROE`, `EEFFR` — which are already annualized and computed
over the correct *average* denominators, which is the basis the thresholds are
calibrated to. That is a measurement, not a projection.

When a published ratio is absent (a hand-built `InstitutionProfile`, or a field the
API omitted) the computed proxy is used, its **basis is rendered on the report**,
and it is **not graded**:

| Metric | Computed fallback | Graded? |
|--------|-------------------|---------|
| NIM | net interest income / **total** assets, YTD | **Never** — the 3.5% threshold is calibrated to `NIMY`, which is over average **earning** assets. A larger denominator biases it low at every period, including Q4. |
| ROAA / ROAE | YTD net income / **period-end** balances | Only at a Q4 `REPDTE`, where the flow covers the full year. |
| Efficiency Ratio | `(NONIX - EAMINTAN) / ((INTINC - EINTEXP) + NONII)` | **Always** — numerator and denominator are YTD flows over the same period, so the period cancels exactly. Annualizing it would *introduce* an error. |
| Tier 1, L/D, NPL, Reserve Coverage | period-end balances only | **Always** — no flow item, no period error. |

Labels follow the basis. "Return on **Average** Assets (ROAA)" is used only when
the value is FDIC's published `ROA`; the computed fallback renders as "Return on
Assets, period-end (ROAA)", because that is what was actually divided by what.

A value that is reported but not graded shows its measurement and an explicit
**Not graded:** line. The number is never hidden — only the grade is withheld.

---

The **Tier 1 Leverage Ratio** thresholds follow bank-capital regulation, not an
arbitrary target: Strong `>= 8%` is the Community Bank Leverage Ratio (CBLR)
qualifying level (12 CFR 324.12, lowered from 9% effective 2026-07-01) and
Adequate `>= 5%` is the leverage-ratio minimum for "well capitalized" under
Prompt Corrective Action (12 CFR 324.403).

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

    https://api.fdic.gov/banks

The historical host `banks.data.fdic.gov/api` now answers HTTP 301 and redirects
here. Requests still succeed through the redirect, which is why the move went
unnoticed; the package now calls the canonical host directly.

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
        institution = get_financials(cert=34352)
    except FDICAPIError:
        ...   # transport/HTTP/decode failure — retry or alert
    except FDICResponseError:
        ...   # wrong-shape or present-but-garbage field — contract problem

---

## Running Tests

    PYTHONPATH=. pytest tests/ -v

Every gate in this suite was run RED before the fix it covers was written.

---

## Who This Is For

- CDFI banks and MDIs benchmarking against peers (**FDIC-insured banks only** —
  credit unions are NCUA-regulated and are not covered by this API or this tool)
- MDI management teams preparing board reports
- CDFI Fund analysts reviewing institution performance
- Impact investors evaluating CDFI bank investments
- Researchers studying community banking performance trends

---

## License

MIT 2026 Jaypatel1511
