# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

> History prior to 0.2.0 predates this changelog and is not documented here.

## [0.2.1] - 2026-07-09

Field-semantics corrections. Every fix below changes a value the package
displayed or graded; the disclosures state plainly where earlier releases were
wrong so downstream users can re-check any conclusions drawn from them.

### Fixed
- **Tier 1 ratio graded a dollar amount, not a ratio (D1).** The `tier1_ratio`
  slot was mapped from `RBCT1J` — "Tier One (Core) Capital (YTD, $)", a dollar
  field in thousands — while being labelled and graded as a percentage. It now
  sources `RBC1AAJ`, the FDIC "Leverage (Core Capital) Ratio, %". The metric key
  `tier1_ratio` is kept for back-compat but every display label is renamed from
  "Tier 1 Capital Ratio" to **"Tier 1 Leverage Ratio"** — the old label was never
  true of any value the package showed. Thresholds are reset for a leverage
  ratio: STRONG `>= 8` (CBLR qualifying, 12 CFR 324.12, lowered from 9%
  effective 2026-07-01), ADEQUATE `>= 5` (well-capitalized leverage minimum
  under PCA, 12 CFR 324.403), WEAK `< 5` (previously an uncalibrated
  `good=12 / warning=8`). An absent `RBC1AAJ` is
  `None` → status N/A; the parser never falls back to the dollar field.
- **Parse-layer plausibility bound on ratio-class fields (D1-guard).** A
  ratio-class field (the leverage ratio) whose value falls outside `[-100, 150]`
  now raises `FDICResponseError` naming the field and value — a dollar magnitude
  in a ratio slot is a wrong-field-class / API-drift signal and fails loud
  instead of grading. Dollar-class fields are intentionally not bounded. This is
  defense-in-depth: a future regression that remaps a dollar field into the
  ratio slot is caught by the bound even if the field map itself is wrong.
- **Name search never matched (D2).** `search_institutions(name=...)` used
  `filters=INSTNAME:"<name>"` — an exact-phrase filter against a field
  (`INSTNAME`) that is not present on the `/institutions` endpoint — so real name
  queries surfaced nothing. It now uses the `search=NAME:<name>` parameter, the
  substring/relevance match the FDIC API provides. `ACTIVE:1` filtering is
  retained; a well-formed query returning zero matches is still a legitimate
  empty result, not an error.
- **Name field read from the wrong key everywhere (D3).** All endpoints
  requested and read `INSTNAME`; the FDIC API returns the name under `NAME`, so
  every institution's name silently rendered as "Unknown". All requests and reads
  (`get_institution`, `get_financials`, `get_peer_financials`,
  `search_institutions`) now use `NAME`. The "Unknown" default is retained only
  for a genuinely absent name; stored names are not normalised (an internal
  double space, e.g. "First Eagle  Bank", is preserved).
- **Efficiency-ratio denominator understated the ratio (D5).** The denominator
  used gross interest income (`interest_income + non_interest_income`). It now
  uses **net** interest income plus non-interest income
  (`(interest_income − interest_expense) + non_interest_income`), matching the
  FDIC `EEFFR` definition ("noninterest expense as a percent of net interest
  income plus noninterest income"). A denominator `<= 0` yields `None` (the
  existing zero-denominator convention), never `inf` or a negative grade.

### Disclosures (earlier releases were wrong)
- **Efficiency ratios in 0.1.0–0.2.0 were understated at every period.** The
  gross-interest-income denominator is strictly larger than the correct net
  denominator, so every efficiency ratio the package reported was lower (looked
  better) than the true FDIC-consistent value. Any efficiency figure produced by
  0.1.0–0.2.0 should be recomputed.
- **Tier 1 "Capital Ratio" in 0.1.0–0.2.0 graded a dollar amount.** The value
  shown was Tier One Capital in thousands of dollars, not a percentage; the
  "STRONG" label attached to that row carried no information about capital
  adequacy and should be disregarded for any institution benchmarked with those
  releases.

### Known issues
- **Legacy FDIC host reached via 301 redirect.** `FDIC_API_BASE` points at
  `https://banks.data.fdic.gov/api`, which the FDIC now serves via a 301
  redirect to the current host. Requests still succeed because `requests`
  follows the redirect, but the package relies on that redirect rather than
  targeting the canonical host directly. Tracked for a future release; no code
  change in 0.2.1.
- **Annualization / period basis (D4) is deferred to 0.3.0.** NIM, ROAA, and
  ROAE are computed from as-reported YTD flows without annualizing interim
  periods, so non-Q4 figures are not annualized. The decision (adopt the FDIC
  precomputed `NIMY` / `ROA` / `ROE` fields) is made and lands in 0.3.0; it is
  intentionally out of scope for this field-semantics release.

## [0.2.0] - 2026-06-23

### Added
- Typed exception hierarchy in `cdfibenchmark/exceptions.py`, exported from the
  package root: `CDFIBenchmarkError` (base), `FDICAPIError`
  (transport/HTTP/JSON-decode failures), and `FDICResponseError` (valid JSON
  whose structure is unexpected).

### Changed
- **FDIC data layer now fails loud (breaking).** The four fetchers
  (`get_institution`, `search_institutions`, `get_financials`,
  `get_peer_financials`) previously caught every exception, printed it, and
  returned an empty value. In an early-warning / anomaly-detection pipeline a
  fetch failure that returns empty reads as "nothing anomalous" — masking the
  outage. They now raise:
  - a transport, HTTP, or JSON-decode failure raises `FDICAPIError`;
  - a successfully decoded response whose shape is unexpected raises
    `FDICResponseError`.

  A successful request that legitimately returns zero rows is **not** an error
  and still returns the empty value (`None` / empty `DataFrame` / `[]`).
- `__version__` is now derived from installed package metadata via
  `importlib.metadata` instead of a hardcoded string, so it can no longer drift
  from `pyproject.toml`.

### Removed
- All `print()`-based error reporting in the FDIC data layer (replaced by raised
  exceptions).
