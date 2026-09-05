# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

> History prior to 0.2.0 predates this changelog and is not documented here.

## [0.3.0] - 2026-09-05

Grading-direction, period-basis and peer-composition corrections. Every fix
below changes a value or a grade the package displayed. Where an earlier
release was wrong, this says so plainly so downstream users can re-check
conclusions drawn from it.

**Anyone who ran 0.2.x should re-run.** Grades change for `loans_to_deposits`
(direction), `efficiency_ratio` (numerator), `nim`/`roaa`/`roae` (basis), and
every peer median and percentile changes because the peer group itself was
wrong — twice over: the group was pinned to one period AND reselected by
proximity rather than by size.

### Fixed (second pass, after a hostile audit and before any release)

- **The peer group was the 50 LARGEST banks in the asset window, at every size
  (B1).** `get_peer_financials` sent `sort_by=ASSET, sort_order=DESC,
  limit=max_peers+5` and `build_peer_group` kept `[:50]`. The sort predates this
  release; what this release did was PIN the REPDTE, which made all 55 rows
  distinct institutions at one date — so the group became exactly the 50 largest
  in the window. Executed against the live API at REPDTE 20260630:

      CERT 34352, assets $1562.0MM, window $781.0MM-$2343.0MM
        banks actually in the window:  764
        peer group n=50   asset range  $2119.3MM-$2341.3MM
        -> the subject sat at percentile 0 of its own peer group
        -> PeerGroup.caveats was EMPTY

      swept at 20260630 over subjects $75MM / $150MM / $400MM / $1,000MM /
      $1,562MM / $5,000MM: EVERY peer larger than the subject at every size,
      smallest peer 1.15x-1.45x the subject's own assets.

  Pinning the period converted a LOUD defect (55 rows, 8 certs, 23 years) into a
  quiet one, and the README then presented the result as "the 50 real peers of
  CERT 34352". `PeerGroup.caveats` disclosed a dropped state constraint, a short
  group and a mixed period, and said nothing about the one basis that skewed
  every number on the page.

  **Route taken, and why not the two-bounded-query design the brief
  recommended.** Probed first: `sort_order=ASC` IS accepted; `limit` caps at
  10,000 (`limit=20000` -> HTTP 400 `validate:too_big`); `offset` works. And the
  widest +/-50% window anywhere in the CDFI size range holds **1,439** banks
  (measured at 20260630 across subjects from $25MM to $25,000MM), so the whole
  window fits in ONE query — the brief's premise that paging the window is "more
  expensive" than two bounded queries is false here. `build_peer_group` now
  fetches the complete window in a single call (764 rows, 341 KiB, 0.88s for the
  subject) and keeps the `max_peers` banks NEAREST the subject by
  `|assets - subject|`, ties broken on CERT. One round trip instead of two,
  exact instead of nearly exact, and it yields the window's true population.

  After the fix, same sweep: subject asset percentile **40-70** at every size
  (was 0), peer range brackets the subject everywhere.

  **What this selection gets wrong.** A nearest-neighbour group is not a random
  sample of the window and is not a supervisory peer group. Where the window is
  dense near the subject the group is NARROWER than "peers" suggests — for CERT
  34352 the 50 nearest span $1,499.9MM-$1,621.7MM, about +/-4%, drawn from a
  window of +/-50%. That is a tighter comparison than the asset tolerance
  advertises, and it trades the old size bias for a size *concentration*. The
  report now states the window, the group size, the selection rule and the
  subject's position, so the reader can see this rather than infer it.

- **The peer-selection parameters were unnamed house numbers.** The +/-50%
  window, the 50-bank cap and the 10-peer floor decide WHICH BANKS the report
  compares against and were bare literals in a signature. They are now
  `HOUSE_ASSET_TOLERANCE` / `HOUSE_MAX_PEERS` / `HOUSE_MIN_PEERS` and are
  rendered on the report as `PeerGroup.selection_basis`, which states that they
  are this tool's own and that the FDIC's UBPR peer groups are a different
  construct.

- **The report showed a peer asset range and never said where the institution
  fell inside it.** `**Peer Asset Range:** $2119.3MM - $2341.3MM` printed two
  lines under `**Total Assets:** $1562.0MM` with no relationship stated is what
  let a size-skewed group read as a peer group. The report now renders the
  subject's percentile within its own peer group, and a group in which the
  subject sits at an extreme is caveated.

- **A calibration note in the README stated a falsehood about the tool's own
  output (B2).** `README.md` claimed "this band grades 22 of 50 WEAK, with a
  peer median of 91.12% sitting inside the WEAK zone". The counts were exact;
  the zone claim was **false** — the band is WEAK below 50 or above 95, and
  91.12 satisfies `80 < v <= 95` -> **ADEQUATE**. The same sentence had been
  copied into this changelog, so it shipped in two places.

  Re-measured over the corrected peer group (the numbers described a cohort
  ~1.4x the subject's size and did not survive B1): **13 of 50 WEAK, 11 of them
  for exceeding 95%, peer median 85.19% -> ADEQUATE**. The corrected sentence
  does the disclosure work better than the false one: the WEAK tail is almost
  entirely the funding-strain edge, which is what the band was added to catch.

- **FDIC's zero-fill was graded as a measurement on the gradeable basis, and
  read STRONG (B3).** FDIC publishes a literal `0` where it did not compute a
  ratio. `_coerce_float(row, "EEFFR", absent=None)` correctly preserves a
  present `0.0` — `_is_missing` is intact and was never the defect. The fill
  arrives from FDIC already fabricated, and the `reported_*` short-circuit had
  no missing-value discipline of its own: `is not None` was true, so
  `metric_basis` returned `BASIS_FDIC` (gradeable), and because
  `efficiency_ratio` is `lower_is_better`, `0.0 <= 60` graded **STRONG**.

  Measured over all 4,313 active filers at REPDTE 20260630: EEFFR == 0 for 19
  (0.44%), NIMY == 0 for 22, ROA == 0 for 17. Two are real operating US banks
  inside the CDFI size band, and both rendered `Efficiency Ratio | 0.00% |
  STRONG`:

      CERT 33492 CRESCENT BANK         ASSET $1,065,126k  NIMY  4.481  ROA  8.336
      CERT 12013 UNION COUNTY SAVINGS  ASSET $1,478,885k  NIMY -0.368  ROA -1.450

  **The rule adopted, and why not the one the brief recommended.** The brief
  proposed trusting a published ratio only when the core financials it derives
  from are present, and asserted that this "happens to catch exactly the 19".
  It does not: **17** of the 19 are foreign branches whose `INTINC`/`NONIX` are
  absent, and the other **2 are exactly CERT 33492 and CERT 12013** — the two
  operating banks that make this a blocker. That rule misses the dangerous
  cases. A second test was needed:

    (a) UNVERIFIABLE  an input the ratio derives from is absent  -> 17 of 19
    (b) CONTRADICTED  a published 0 beside a non-zero numerator  -> the other 2

  (b) is not a magic-zero rule. A ratio is zero if and only if its numerator is
  zero, so a zero the financials SUPPORT is trusted — a break-even bank
  publishing `ROA == 0` with `NETINC == 0` keeps it, which is why "ROA == 0.00
  is plausible" does not defeat the rule. The zero is a fill rather than a
  rounding artifact because FDIC publishes full precision: the smallest non-zero
  magnitudes at 20260630 are 0.0373 (NIMY), 0.0118 (ROA) and 0.1494 (EEFFR).
  Both rejected banks turn out to have NEGATIVE revenue, which is precisely when
  FDIC declines to compute an efficiency ratio.

  Applied to all four `reported_*` fields, not the one that was noticed. A
  rejected value falls back to the computed proxy and renders that proxy's
  basis, through the existing machinery — no new path. Measured cost over the
  whole population: **zero** wrongful rejections (4,294 of 4,313 banks keep
  their published efficiency ratio; no row anywhere has an absent numerator
  input together with a non-zero published value).

  **What this rule gets wrong** is recorded on
  `InstitutionProfile.reported_is_trustworthy`: a non-zero sentinel passes; a
  filer with complete financials and a fabricated non-zero ratio passes; test
  (a) is stricter than "the value is wrong" and would degrade cells to N/A
  rather than fail loud if FDIC dropped a field; and it says nothing about the
  DENOMINATOR, so a bank with negative equity keeps a meaningless ROE.

- **The ratio-class plausibility bound rejected real leverage ratios.**
  `_RATIO_MAX` was 150. `RBC1AAJ` is Tier 1 capital over AVERAGE assets, so a de
  novo bank or one in wind-down legitimately exceeds 100%. Measured across six
  quarters over every active filer, the maximum was 105.01 / 117.66 / 117.29 /
  119.35 / 142.22 / **277.16** — 150 fit five quarters by luck and raised
  `FDICResponseError` on two real banks in the sixth (CERT 59379, equity 55.3%
  of assets; CERT 16281, 94.5%). This was unreachable while the peer query
  returned only the 55 largest banks in the window; fetching the whole window
  reaches them, and one such bank aborted the ENTIRE peer group — for subjects
  in the $25MM-$75MM range, squarely the CDFI size band. Bound widened to 1,000,
  which still catches the four-orders-of-magnitude swap the guard exists for
  (`RBCT1J` reaches 302,589,000). The comment claiming the guard separates the
  field classes has been corrected: `RBCT1J` is as low as $62k for a small
  filer, well inside the ratio band, so it cannot.

- **The threshold-attribution gate could not see what its own docstring
  claimed.** `test_house_thresholds_are_named_house_at_the_constant` states that
  a HOUSE threshold's numbers must come from `HOUSE_`-prefixed constants, then
  asserted `cfg[key] in house_values` — a set of VALUES. Replacing
  `HOUSE_ROAA_GOOD, HOUSE_ROAA_WARNING` with bare `1.0, 0.5` left the suite at
  **199 passed, 2 skipped**. Any literal equal to any HOUSE_ constant passed.
  Now asserted by AST over the source (`ast.walk`, not `.body`): each
  `good`/`warning`/`floor` node on a HOUSE entry must be a `Name` starting with
  `HOUSE_`, never a `Constant`. A companion gate additionally requires the
  constant to belong to ITS metric, closing a hole the prefix check alone left:
  `"roaa": {"good": HOUSE_NPL_GOOD}` is HOUSE_-prefixed and numerically
  identical (both 1.0), and would otherwise have graded return-on-assets against
  an asset-quality rule of thumb.

### Known limitations — carried forward, not fixed in this release

Recorded so the next round has a list rather than a search. Each is real; none
blocks this release.

1. **The peer median can mix bases.** `compute_peer_metrics` has no basis
   awareness: peer values enter `median()`/`quantile()` straight from
   `metrics_dict()`, and `BenchmarkResult.basis` carries the INSTITUTION's basis
   only. A median across two bases is a fabricated statistic even when every
   input is correct. Live frequency is low but non-zero, and B3 RAISES it
   slightly: rejected published ratios now fall back to a computed proxy, so a
   peer group containing one of the 19 zero-fill banks contributes a
   computed-basis value to an otherwise FDIC-basis median. Bounded — at most 19
   of 4,313 banks at 20260630, and the rejected efficiency values render None
   and drop out of the median entirely rather than entering it on a second
   basis.
2. **`_metric_label` applies the institution's basis to the whole row**,
   including the peer median and quartile columns. Same shape as (1), on the
   rendered face.
3. **No upper bound on a metric that lands absurd**, and this is NOT only a
   computed-metric problem as previously recorded. `reserve_coverage` 1e9% ->
   STRONG and `nim` 140 -> STRONG are computed, but FDIC *publishes* values that
   grade absurdly too: at 20260630 `EEFFR = -700` for CERT 58216 (BMO HARRIS
   CENTRAL NA) and `-5.615` for CERT 58590 (NANO BANC) — both grade **STRONG**
   because `efficiency_ratio` is `lower_is_better`. These are NOT sentinels and
   B3 deliberately does not touch them: they are FDIC's own correct arithmetic
   over a NEGATIVE noninterest expense, reproducible from the filed financials
   to 0.01 (`-28/4*100 = -700`). Grading a negative efficiency ratio STRONG is
   still wrong. This needs a ruling on what a grade means when the input is real
   but the comparison is not, not a clamp.
4. **`ASSET_BUCKETS` is an undisclosed house construct that renders on the
   report.** The five boundaries (50MM / 250MM / 1B / 5B) are this tool's own,
   exactly like the peer-selection parameters this release named, and the report
   prints `**Asset Bucket:** Large` with no attribution. It is descriptive only
   — no grade, threshold or peer-selection decision reads it — which is why it
   is recorded rather than fixed. It is the last member of the "unnamed house
   constant on the rendered face" family that this release did not close.
5. **`docs-check` is not adopted here. Ruled: not this release.** Three blockers
   was enough scope, and `docs-check` reads the README, which B1 and B2 both
   rewrote. It rides the next release. This is a decision, not an omission.

### Fixed (first pass)

The rest of this release, in the order it was built.

- **`loans_to_deposits` was graded backwards (B1).** The entry carried no
  `lower_is_better`, so `BenchmarkResult.status` took the `>=` branch: a bank
  lending **200% of its deposits graded STRONG** and one at **55% graded WEAK**,
  inverted against the README's own `<= 80%` row. Live on PyPI since at least
  0.2.0. `rank_institution` reads the same flag, so the **percentile was
  inverted too**.

  The direction flag alone is *not* the whole fix: it grades 20% STRONG, and a
  CDFI bank lending 20% of deposits is not deploying capital into its
  community. The risk is two-sided, so the metric is now graded as a **band**
  via a new optional `floor` key: `20 -> WEAK`, `55 -> STRONG`, `80 -> STRONG`,
  `95 -> ADEQUATE`, `130 -> WEAK`, `200 -> WEAK`.

  The direction of **all eight** metrics was then executed across the
  missing/NaN/zero/negative/absurd range. `loans_to_deposits` was the only
  inverted one; `reserve_coverage` (higher-is-better with `good` 100 >
  `warning` 50) and `tier1_ratio` are correct as they stand.

- **Every threshold now declares its provenance.** `tier1_ratio` was the only
  entry with a citation and it lived in a *comment*, where nothing could render
  or check it, while seven unsourced thresholds rendered beside it in the same
  `Benchmark:` column of the same report. Each entry now carries a
  machine-readable `source`; the seven are marked `"HOUSE"`, their numbers come
  from `HOUSE_`-prefixed constants, and the report renders them as *"this
  tool's own threshold (HOUSE), not a regulatory or supervisory standard"*.

  Ruling on the 80/95 loans-to-deposits boundary the brief asked for: it is a
  **house number and is now labelled as one**. There is no regulatory
  loans-to-deposits level — bank capital has published levels, funding ratios do
  not. No citation was invented.

  Calibration, measured not asserted: across the 50 banks nearest CERT 34352 in
  assets at `20260630` (selected from the 763 in its +/-50% window, retrieved
  2026-09-05), seven metrics grade sensibly (majority STRONG, small WEAK tail)
  while `loans_to_deposits` grades **13 of 50 WEAK, 11 of them for exceeding
  95%, with a peer median of 85.19% that grades ADEQUATE**. The boundaries are
  kept because they are what the README documents and are marked HOUSE; fitting
  them to a 50-bank sample would invent a number with a veneer of evidence.
  Recorded so a later release can recalibrate deliberately.

- **`nim`, `roaa` and `roae` divided YTD flows by point-in-time stocks and
  graded the result against annual thresholds (B2).** `INTINC`, `EINTEXP` and
  `NETINC` are year-to-date; at a Q1 `REPDTE` they cover three months. Measured
  against FDIC's own published series for CERT 34352 at `20260331`: computed
  values read **4.30x / 4.12x / 4.01x low**. A healthy bank graded WEAK for
  three quarters of every year.

  **Route taken — a fourth the brief did not list.** The FDIC `/financials`
  endpoint already publishes `NIMY`, `ROA`, `ROE` and `EEFFR`, already
  annualized and already over the correct *average* denominators, which is the
  basis the thresholds are calibrated to. These are now fetched and preferred.
  That is a **measurement, not an estimate** — no annualized figure is invented,
  and it resolves the period error, the denominator error and the labelling
  error in one move.

  When a published ratio is absent (a hand-built profile, or a field the API
  omitted) the computed proxy is kept, its **basis is rendered**, and it is
  **not graded** (`GRADEABLE_BASES`). Degrade the cell, not the number: the
  measured value is still reported, with an explicit `Not graded:` line.

- **NIM's denominator was total assets, and still is in the fallback (B2b).**
  FDIC's `NIMY` — and the 3.5% threshold calibrated to it — is over average
  *earning* assets, a strictly smaller denominator, so the computed proxy is
  biased low **even at Q4** (1.09x residual measured at `20251231`). Ruling: the
  computed NIM is **never graded at any period**, and renders as "Net Interest
  Margin over total assets (NIM)". Only FDIC's published `NIMY` is graded.

- **"Return on *Average* Assets/Equity" was computed on period-end balances
  (B2c).** A third labelling defect, independent of period and denominator. The
  averaged label is now used only when the value is FDIC's published `ROA`/`ROE`;
  the computed fallback renders "Return on Assets, period-end (ROAA)" and is
  graded only at a Q4 `REPDTE`, where the flow covers the full year.

- **`efficiency_ratio` did not match FDIC `EEFFR`, though its own comment said
  it did.** 0.2.1 corrected the denominator and left the numerator wrong: FDIC
  subtracts amortization of intangibles and goodwill-impairment losses
  (`EAMINTAN`) from noninterest expense. Verified against the live API for CERT
  34352 at five `REPDTE`s —

      EEFFR = (NONIX - EAMINTAN) / ((INTINC - EINTEXP) + NONII) * 100

  reproduces FDIC's published figure to **1e-9** at every one. The old formula
  read **191.06% where FDIC published 88.33%** (`20250930`, a goodwill-impairment
  quarter) — enough to move a bank from ADEQUATE to WEAK. `EAMINTAN` absent
  subtracts nothing; no figure is fabricated.

  **`efficiency_ratio` is period-neutral and is NOT annualized.** Numerator and
  denominator are YTD flows over the same period, so the period cancels exactly;
  annualizing it would introduce an error where there is none. Stated here so
  the next reader does not "complete" the B2 fix.

- **Peer groups were not pinned to a reporting period, and were mostly
  duplicates (B4).** `build_peer_group` never defaulted `report_date`, so
  `get_peer_financials` sent **no `REPDTE` filter at all**. The `/financials`
  endpoint is one row per institution-*quarter* (its own `ID` is
  `"<CERT>_<REPDTE>"`). Running the exact query the code built, 2026-08-30:

      before:  55 rows, 8 distinct CERTs, REPDTE 20030930..20260630,
               one CERT appearing 17 times
      after:   50 rows, 50 distinct CERTs, all at 20260630

  A "50-peer group" was **8 banks counted up to 17 times each across 23 years**,
  and the peer median, quartiles and percentile were computed over that — while
  the institution itself came from `get_financials` sorted `REPDTE DESC`, at its
  most recent quarter. This also compounded B2: a Q1 institution against Q4
  peers is a factor of four before any real difference in performance.
  `report_date` now defaults to the institution's own, and `_dedupe_by_cert`
  keeps the row nearest the target period as a defence that does not depend on
  the API honouring the filter.

- **The `same_state` fallback silently returned a different peer group (B3).**
  Three defects at one site: the caller asked for same-state peers and got a
  **national** group with nothing on the result or the report saying so; the
  fallback **overwrote** rather than supplemented, so an 8-peer same-state group
  could be replaced by a 3-peer national one **or by `[]`**; and `min_peers`
  read as a floor while only ever being a trigger. The comment said *"widen the
  asset range"* while the code widened the **geography**.

  `build_peer_group` now returns `PeerGroup` (a `list` subclass, so every
  existing consumer is unchanged) carrying `requested_state`,
  `state_constraint_dropped`, `min_peers`/`below_min_peers`, `report_dates`,
  `is_single_period` and a `caveats` list. The fallback keeps the **better** of
  the two groups. A shortfall below `min_peers` is disclosed, not silently
  returned.

- **`rank_institution` contradicted `status`, and its percentile could never
  reach 100.** Two defects found by executing the function across a value
  range, which had never been done. Measured against a 20-peer group before the
  fix:

      L/D  15%  status=WEAK      rank=1/21   percentile=95.2
      L/D  80%  status=STRONG    rank=13/21  percentile=38.1

  A bank lending 15% of its deposits was graded WEAK and simultaneously placed
  in the top 5% of its peer group **on the same metric** — the band defect
  surviving in the percentile path after the `status` path was fixed. A banded
  metric has no monotone better-direction, so it is now **not ranked at all**:
  `rank` and `percentile` are `None` and a `reason` says why. Ordering it by
  distance from the band would be a house construct stacked on already-house
  boundaries.

  Separately, `percentile` used `(1 - rank / N) * 100` over peers **plus** the
  institution, so a best-possible value scored **95.2, never 100**, and the
  worst was pinned at exactly 0. It is now the share of peers actually beaten
  and spans the full range. `peer_count` counted the institution itself, so the
  same key name meant peers-plus-one here and peers-only on `BenchmarkResult`;
  it is now peers-only in both, and a new `rank_of` names the denominator
  `rank` is out of.

- **The report rendered grades without their warrant.** It printed the
  institution's report date and the peer group *size* and nothing else about the
  peer group. It now renders **Peer Report Date** (or `MIXED — <dates>`),
  **Distinct Institutions**, a **Peer group caveats** block before any number,
  a **Basis:** line per metric, threshold provenance inline, and a **Not
  graded:** line explaining any present-but-ungraded value. `summary_table`
  gains `basis` and `threshold_source` columns.

- **`FDIC_API_BASE` pointed at a redirect.** `banks.data.fdic.gov/api` now
  answers HTTP 301 to `api.fdic.gov/banks`. `requests` follows it, so calls
  still succeeded — which is why this went unnoticed — at the cost of an extra
  round trip per call and a dependency on a redirect the FDIC is free to retire.
  Now calls the canonical host.

- **The README's Quickstart named the wrong bank, and it was a LIVE call.**
  It read *"Pull call report data for Broadway Federal Bank (CERT 57542)"*.
  **CERT 57542 is Toyota Financial Savings Bank**, Henderson NV, $16.8B —
  verified against the live FDIC `/institutions` endpoint. Broadway Federal is
  CERT 30306 and is inactive. This is worse than a sample-data problem: the
  block runs, succeeds, and prints a real, correctly-computed, graded report
  about an entirely different bank from the one named beside it. The same
  binding was in `tests/conftest.py` and, most emphatically, in the demo
  notebook, which attributed *"one of the largest Black-owned banks"* to it.
  All surfaces corrected; the Quickstart now uses CERT 34352 (City First Bank,
  N.A., a real CDFI/MDI) and every fixture uses a synthetic cert outside the
  FDIC's issued range.

- **The README's sample block attached invented financials to a real named
  institution** with no synthetic warning. It is now an unmistakably fictional
  bank with an explicit banner.

- **`build_sample_peer_group` seeded the GLOBAL RNG.** `random.seed(42)` reset
  the caller's process-wide random state as a side effect of building a sample
  peer group. Now uses a local `random.Random(42)`.

- **`pyproject.toml` still advertised CET1** in `description` — the text PyPI
  renders *above* the corrected README. 0.2.1 removed the claim everywhere else
  and left it here. Removed.

- **README corrections:** period-basis disclosure added (there was none — zero
  occurrences of "annualiz" or "YTD"); threshold provenance table added; the
  hand-typed "96 tests" count removed; the "CDFI banks and credit unions"
  audience line corrected, since credit unions are NCUA-regulated and are
  covered by neither this API nor this tool.

### Added

- `InstitutionProfile.fiscal_quarter`, `.metric_basis()`, `.basis_dict()`, and
  the fields `reported_nim`, `reported_roaa`, `reported_roae`,
  `reported_efficiency_ratio`, `intangible_amortization`.
- `BenchmarkResult.basis` and `.source`. A basis outside `GRADEABLE_BASES`
  degrades `status` to `N/A` while still reporting the value.
- `PeerGroup`, with `.caveats`, `.report_dates`, `.is_single_period`,
  `.below_min_peers`.
- `BENCHMARKS` entries gain `source` and, for banded metrics, `floor`.
- New gates, each run RED before the fix it covers:
  `tests/test_grading_direction.py`, `tests/test_threshold_attribution.py`,
  `tests/test_metric_basis.py`, `tests/test_basis_wiring.py`,
  `tests/test_peer_group_integrity.py`, `tests/test_report_disclosure.py`,
  `tests/test_package_claims.py`. The loans-to-deposits band gate was
  additionally proven to fail against the *naive* one-sided remedy, not only
  against the shipped bug.

### Refuted

- **`npl_ratio` does not need "fixing" to match FDIC `NPERFV`.** `NPERFV` is
  noncurrent loans over **ASSETS** (verified exactly at five `REPDTE`s), not
  over loans. The package's `NCLNLS / LNLSGR` is a different, standard, and
  period-neutral metric. Left unchanged deliberately.

### Version

Minor bump, not a patch: returned grades change, `build_peer_group` returns a
new type, and `InstitutionProfile` / `BenchmarkResult` gain fields.

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
