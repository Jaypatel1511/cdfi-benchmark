# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

> History prior to 0.2.0 predates this changelog and is not documented here.

## [0.3.1] - 2026-09-07

Packaging, release metadata and prose. **No library code changed.**
`cdfibenchmark/` in this release is byte-identical to the package inside the
published 0.3.0 wheel:

    sha256 3f90077f200206a1d09929b868df2af43a6da325eb3e695da35f6f4ebbde9083

A digest is only evidence if it can be recomputed, so here is exactly how it is
aggregated — every `.py` under the package directory, ordered by its path
RELATIVE TO THAT DIRECTORY, each path fed to the hash before its bytes. Run from
the repository root, with the published wheel downloaded from PyPI beside it:

    python3 - <<'PY'
    import hashlib, pathlib, zipfile
    def digest(pairs):
        h = hashlib.sha256()
        for name, data in sorted(pairs):
            h.update(name.encode()); h.update(data)
        return h.hexdigest()
    pkg = pathlib.Path("cdfibenchmark")
    print("tree :", digest((str(p.relative_to(pkg)), p.read_bytes())
                           for p in pkg.rglob("*.py")))
    z = zipfile.ZipFile("cdfi_benchmark-0.3.0-py3-none-any.whl")
    print("wheel:", digest((n[len("cdfibenchmark/"):], z.read(n)) for n in z.namelist()
                           if n.startswith("cdfibenchmark/") and n.endswith(".py")))
    PY
    -> tree : 3f90077f200206a1d09929b868df2af43a6da325eb3e695da35f6f4ebbde9083
       wheel: 3f90077f200206a1d09929b868df2af43a6da325eb3e695da35f6f4ebbde9083

11 files on each side. The number was published in this section without its
method, which made it unreproducible: the two most obvious aggregations (bytes
alone, and repository-relative paths plus bytes) give
`0e1728af…` and `f10659e3…` instead.

No metric, grade, threshold, peer-selection rule or rendered value moves.
Nothing computed under 0.3.0 needs re-running.

**If you installed with `pip install`, this release changes nothing for you.**
It matters only if you downloaded the 0.3.0 *source tarball* and ran the test
suite that ships inside it.

### Fixed

- **`PKG-INFO` was checked by filename, so a stray one excused real deletions —
  and said something false about the tree while doing it.** The rule that lets a
  distribution excuse a missing surface identified an unpacked sdist as
  `(ROOT / "PKG-INFO").is_file()`. In a git checkout, python3.10:

      : > PKG-INFO && rm -rf examples
      PYTHONPATH=. pytest tests -q   ->  328 passed, 4 skipped   exit 0

  A zero-byte file forgave a deleted directory, and the skip it printed read
  *"this is an unpacked sdist root (PKG-INFO is present)"* with `.git` sitting
  right there. The identification now tests three things and needs all of them:
  the file parses as RFC-822 distribution metadata with `Metadata-Version` and
  `Name`; that `Name` matches `[project].name` in this tree's `pyproject.toml`
  (PEP 503 normalised); and there is no `.git`. The reason string quotes what
  was observed rather than announcing a conclusion, so a skip printed here can
  no longer assert something untrue about the tree it is printed in. Each part
  is load-bearing, measured on the same mutation: zero-byte file in a checkout
  → 2 failed; a *valid* PKG-INFO copied from the real sdist into a checkout →
  2 failed; another package's PKG-INFO with no `.git` → 2 failed; the genuine
  sdist tree (valid PKG-INFO, no `.git`) → 328 passed, 4 skipped, still
  correctly excused. `.git` is a disqualifier only — it can refuse an excuse,
  never grant one — because on its own it would leave a forged PKG-INFO
  excusing deletions anywhere outside a checkout. Verified that no routine
  command puts PKG-INFO in a checkout root: `setup.py sdist`, `setup.py
  egg_info`, `python -m build`, `python -m build --sdist` and
  `pip install -e .` all write it under `cdfi_benchmark.egg-info/` or not at
  all.

- **The wrong-cert scan passed vacuously when a surface's glob matched
  nothing.** `layout.require` can only answer "the directory is there"; the
  glob inside it decided what was actually read, and an empty match returned an
  empty dict that the gate then asserted over. Measured at the previous commit,
  python3.10, in a full checkout:

      mv examples/cdfi_benchmarking_demo.ipynb examples/cdfi_benchmarking_demo.ipynb.bak
      PYTHONPATH=. pytest tests -q   ->  329 passed, 3 skipped  (control: identical)
      PYTHONPATH=. pytest tests/test_package_claims.py -q -k wrong_institution
                                     ->  7 passed, 14 deselected

  The `examples/` leg passed having read nothing — no skip, no reason. That leg
  is the only automated defence on the demo notebook (retired claims are not
  swept over `examples/`), and it is the gate that caught the fabricated peer
  row this release removes. It disarmed on a rename, and would equally on a
  jupytext conversion or an emptied directory. A surface that contributes zero
  files to a scan is now RED by name, and there is no declaration that can
  excuse it — `MANIFEST.in` declares absence, and this surface is present.
  Red-proven four ways: rename → 1 failed; conversion to `.md` → 1 failed;
  emptied directory → 1 failed; and the same shape forced on `tests/` → 1
  failed.

- **One line in `MANIFEST.in` could absorb the deletion of almost anything.**
  The guard on the excusing mechanism named three never-excusable surfaces by
  hand, leaving six of the nine in `SURFACES` absorbable. Re-derived at the root
  of the 0.3.1 tarball, python3.10 — unpack, append the line, delete the file,
  `PYTHONPATH=. pytest tests/ -q`:

      control                                        328 passed,  4 skipped
      rm CHANGELOG.md                                  9 FAILED, 314 passed
      prune CHANGELOG.md      + rm CHANGELOG.md      316 passed, 11 skipped
      exclude setup.py        + rm setup.py          327 passed,  5 skipped
      exclude CONTRIBUTING.md + rm CONTRIBUTING.md   327 passed,  5 skipped

  One appended line turned nine named failures into exit 0. Which surfaces a
  distribution may omit is a policy, and nothing in the tree states it except
  the very file being edited, so it is now written down once as
  `layout.EXCUSABLE_SURFACES` and consulted by the excusing rule itself:
  `MANIFEST.in` can only ever narrow the excuse, never widen it. The guard walks
  all of `SURFACES` against that set instead of a shortlist, so a surface added
  to `SURFACES` is never-excusable by default. A second gate fails on the
  MANIFEST edit itself, in the pull request that makes it, rather than one
  release later inside an artifact. With both in place the three absorptions
  above give 10 failed, 3 failed and 3 failed.

- **A gate that could not fail, and a claim in `README.md` that it could.**
  `test_readme_does_not_claim_credit_union_coverage` asserted
  `"credit union" not in text or "not" in text`; the second limb is true of
  every README ever written, so the assertion had no red state. Appending
  *"We proudly serve credit unions and CDFI loan funds."* left it PASSED while
  its sibling gate failed on the same text. It is deleted rather than repaired,
  because the honest version of it is the sibling. `README.md`'s "Every gate in
  this suite was run RED before the fix it covers was written" could not be true
  of it, and that sentence now records the exception instead of implying none.
  The surviving gate had a vacuity of its own — its assertion sits inside a loop
  over lines mentioning credit unions, so a README that stopped mentioning them
  would have passed while certifying nothing — and it now requires the exclusion
  to be stated. Red-proven both ways: the "we proudly serve" line → 1 failed;
  deleting every credit-union line → 1 failed.

- **`[build-system].requires` said `setuptools>=42`, and setuptools cannot read
  this project's metadata until 61.0.0.** Every packaging field lives in the PEP
  621 `[project]` table; setuptools older than 61 ignores that table entirely
  and falls back to what `setup()` passes, which since this release is nothing.
  The result is not an error. Measured, python3.10, on the unpacked 0.3.1 sdist:

      pip wheel --no-deps --no-build-isolation, venv pinned per version
        setuptools 60.10.0 -> "Successfully built UNKNOWN"
                              UNKNOWN-0.0.0-py3-none-any.whl containing only
                              its own dist-info — no package code — exit 0
        setuptools 61.0.0  -> "Successfully built cdfi-benchmark"

      python -m build --wheel --no-isolation, system setuptools 59.6.0
        requires = ["setuptools>=42"] -> built UNKNOWN-0.0.0, exit 0
        requires = ["setuptools>=61"] -> ERROR Unmet dependencies:
                                         setuptools>=61, found 59.6.0

  The floor is now 61 and a gate holds it there. No CI job could have seen this:
  `python -m build` on a clean runner provisions the newest setuptools, so the
  declared floor is never the version that runs. Stated precisely, because a
  build requirement is a declaration and not every tool enforces it: `python -m
  build` now refuses instead of shipping an empty wheel, `pip` with isolation
  resolves the correct setuptools, and `pip wheel --no-build-isolation` checks
  no build requirement at all and is unaffected by either floor.

- **The test suite shipped inside the sdist failed when run from the tarball
  root, and no CI job in the release that shipped it could see the failure.**
  Three claim-gate modules asked one global question — "is a source tree present
  here?" — and then used that single answer for every surface they read. An
  unpacked sdist contains `cdfibenchmark/`, so it answered "yes"; but
  `examples/` is pruned from the sdist deliberately (`MANIFEST.in` says so in
  words), so those gates then demanded a directory the tarball is designed never
  to contain. Reproduced against the artifact on PyPI, python3.11:

      curl -L <the 0.3.0 sdist from files.pythonhosted.org> | tar xz
      cd cdfi_benchmark-0.3.0 && PYTHONPATH=. pytest tests/ -q
      -> 2 failed, 319 passed, 3 skipped

  The gates now ask the question per surface — *is this surface readable here,
  and if not, has the artifact I am standing in DECLARED that it omits it?* Only
  an unpacked sdist can declare an omission (it is identified by `PKG-INFO`, and
  the declaration is read from the `MANIFEST.in` that ships inside it), and only
  for the surfaces it names. Anything else missing is still red. That logic
  lives in the new `tests/_layout.py`, so it exists once rather than in three
  copies that could drift.

- **Why no CI job saw it.** Every artifact-layout check lived in `release.yml`,
  which triggers on a *tag push* — the irreversible step. So a layout defect
  could only ever be discovered by a release that had already happened, and
  0.3.0 is exactly that: it shipped with its own suite red at the tarball root
  and all eight of `release.yml`'s artifact jobs green, because every one of
  them ran the suite from a constructed directory that structurally cannot reach
  that layout. The layout jobs now live in a reusable
  `.github/workflows/artifact-layouts.yml` called by BOTH `ci.yml` (on pull
  request and push to main) and `release.yml` (on a tag), so the check that runs
  before the tag is literally the same code as the check that runs at it, and a
  commit cannot reach a tag without the wheel, sdist, constructed-directory and
  tarball-root layouts having been exercised on it. A step that runs the shipped
  suite from the tarball root — the layout `README.md` documents under "Running
  Tests" — was added, because that is the layout none of the previous jobs could
  reach.

- **`setup.py` declared `version="0.2.1"` and shipped that inside the sdist of
  every release since.** Nothing read it — `pyproject.toml` carries a PEP 621
  `[project]` table and PEP 621 metadata wins over anything `setup()` passes, so
  the copy was inert and free to rot, and no gate covered it. It is not bumped;
  the duplicated `name`, `version` and `install_requires` are removed and the
  file is now a bare PEP 517 shim, so there is exactly one declared version in
  the repository. Verified that the distribution is unaffected: with the shim in
  place `python -m build` produces a wheel of the same 15 entries with
  `top_level.txt = ['cdfibenchmark']` and no `tests/*`, and an sdist whose file
  list is unchanged.

- **Two stale measured claims in the demo notebook, both live on GitHub.**
  `examples/cdfi_benchmarking_demo.ipynb` advertised "CET1" among the metrics it
  computes. This package computes no CET1 and never has: `tier1_ratio` is the
  Tier 1 *leverage* ratio, a different regulatory measure. The same claim was
  struck from `pyproject.toml`'s `description` in 0.3.0 for that reason; the
  notebook was missed because the gate that catches retired claims reads only
  pyproject's `[project]` table. Separately, the notebook's opening markdown had
  been left half-edited by the 0.3.0 correction — three sentences interleaved,
  including a fragment describing a real Los Angeles MDI that had been carried
  over from the wrong-cert binding 0.3.0 removed. The fragment is deleted rather
  than repaired: it made a claim about a real institution that nothing in this
  package establishes.

- **The notebook attributed invented financials to a real, named institution.**
  0.3.0's correction replaced the wrong cert/name binding in the notebook's
  first two cells and in its own claim gate, and its commit message said "all
  surfaces corrected". That was not true. The side-by-side comparison table
  further down still carried a real MDI by name and CERT, with entirely
  fabricated assets, NIM, efficiency ratio, ROAA, Tier 1 and NPL figures,
  printed under the heading "MDI Peer Comparison Table" — and, worse, sitting
  directly beneath a row explicitly labelled `(SYNTHETIC)`, which made the
  unlabelled row read as real by contrast. Every institution in that table is
  now synthetic, with a cert outside the FDIC's issued range and a name carrying
  the `(SYNTHETIC)` marker, and the cell and its heading say so. The existing
  wrong-cert gate could not catch this: it scans for one specific known-false
  pairing, not for real institutions carrying made-up numbers.

- **The notebook told users to pull live data for a cert that is not issued.**
  Its closing example read `get_financials(cert=99001)` under "To pull live
  financials for any institution" — 99001 being the synthetic cert the same
  notebook states is outside the FDIC's issued range. It now points at the same
  real cert the README's Quickstart uses.

- **The notebook still cited the retired API host.** Its footer gave
  `banks.data.fdic.gov/api`, which now answers HTTP 301. 0.3.0 moved the package
  and the README to `api.fdic.gov/banks` and left the notebook behind.

### Known issues in 0.3.0 — published, not yanked

0.3.0 remains on PyPI and is **not** being yanked. Yanking would push pinned
users back to 0.2.1, which still carries the substantive correctness defects
0.3.0 fixed — the grading direction, the period basis and the peer-composition
errors — and those are far more consequential than this one.

**What is wrong with 0.3.0.** The test suite inside the 0.3.0 **source tarball**
fails when run from the tarball root:

    cd cdfi_benchmark-0.3.0 && PYTHONPATH=. pytest tests/ -q
    -> 2 failed, 319 passed, 3 skipped

The two failures, on their own lines so they can be copied and run:

    tests/test_package_claims.py::test_every_surface_these_gates_need_is_present_in_a_repo_tree
    tests/test_package_claims.py::test_no_surface_binds_a_cert_to_the_wrong_institution[57542-Broadway Federal]

Both fail for the same reason and it is a defect in the *gates*, not in the package: they
demanded `examples/`, a directory `MANIFEST.in` deliberately prunes from the
sdist. Nothing they were testing is actually wrong in 0.3.0.

**What is NOT affected — stated precisely, so this caveat is not read more
broadly than it is.** All measured against the published 0.3.0 artifacts,
python3.11:

- **The installed library.** The 0.3.0 wheel contains no tests at all (15
  entries, top-level `cdfibenchmark` and `cdfi_benchmark-0.3.0.dist-info`), and
  its package code is byte-identical to this release's. Every metric, grade,
  threshold, peer group and report 0.3.0 produces is correct as documented.
- **`pip install cdfi-benchmark==0.3.0`.** Unaffected in every respect. There is
  nothing to do.
- **Running the suite against the installed 0.3.0 wheel** — `294 passed, 25
  skipped`, no failures.
- **Running the shipped suite from a directory holding `tests/`, `README.md` and
  `pyproject.toml`** (the layout every 0.3.0 CI job used) — `295 passed, 24
  skipped`, no failures.

So the defect is reachable by exactly one action: unpacking the 0.3.0 source
tarball and running its suite from the tarball root. 0.3.1 fixes it; the same
invocation against 0.3.1 passes.

### Changed

- **A deferral's stated scope was wrong and is corrected.** The round-3 commit
  message describing the cert gate's per-line negation exemption said it was
  "latent for line-shaped files, real for minified JSON". It is real for
  ordinary Markdown. Appending one line to `README.md`, python3.10,
  `PYTHONPATH=. pytest tests -q -k wrong_institution`:

      "CERT 57542 is Broadway Federal Bank, and the sky was blue."  -> 7 passed
      "CERT 57542 is Broadway Federal Bank, and the sky is  blue."  -> 1 failed
      "CERT 57542 is Broadway Federal Bank. It was reported elsewhere."
                                                                   -> 7 passed

  Every wrapped prose paragraph is line-shaped for this purpose, so the hole is
  live on the surfaces the gate most needs to cover. The deferral itself stands
  — narrowing the exemption is gate logic and belongs in 0.3.2 with its own
  red-proofs — but it is now deferred on an accurate description of what it
  leaves open, recorded beside the code it describes rather than in a commit
  message. A commit message cannot be corrected in place; this can.

- The floor guarding against a silently-deselected sdist suite was re-derived.
  Its justification still read "96 tests executed under this job's exact
  invocation, half is 48, so the floor is 45" — a measurement the suite had
  outgrown by more than a factor of three. Re-measured from the junit XML the
  job itself emits: 309 executed, so the floor is now 150 by the same
  already-written rule. This raises the threshold rather than lowering it; the
  old floor let 264 of 309 tests be deselected without complaint. Two further
  stale measurements in the same workflow, and one demonstration in it that had
  become false outright, were re-run and rewritten with the command that
  produced each number beside it.

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

- **The ratio-class plausibility bound rejected real leverage ratios, and its
  own justification was false.** `_RATIO_MAX` was 150. `RBC1AAJ` is Tier 1
  capital over adjusted AVERAGE assets, so a de novo bank or one in wind-down
  legitimately exceeds 100%; 150 fit five of six measured quarters by luck and
  raised `FDICResponseError` on two real banks in the sixth (CERT 59379,
  equity 55.3% of assets, 277.16; CERT 16281, 94.5%, 194.25 — **both at
  20260630**, which an earlier note in this file misattributed across two
  quarters). This was unreachable while the peer query returned only the 55
  largest banks in the window; fetching the whole window reaches them, and one
  such bank aborted the ENTIRE peer group — for subjects in the $25MM-$75MM
  range, squarely the CDFI size band.

  The bound was then widened to 1,000 with the comment *"1000 admits every
  observed leverage ratio with room"*. **That was false in both halves, and the
  package's own sweep refutes it.** Every REPDTE the endpoint serves, 1984Q1
  through 2026Q2 — 169 quarters, swept 2026-09-05:

  | population | min `RBC1AAJ` | max `RBC1AAJ` |
  |---|---|---|
  | 1984Q1–2026Q2 (169 quarters) | **-1,524.07** (CERT 34128, 19960331) | **466,500.00** (CERT 27213, 19880331) |
  | 2015Q1–2026Q2 (46 quarters) | -6.20 (CERT 9956, 20160331) | **951.11** (CERT 59287, 20220331) |

  So (a) 1,000 does not admit every observed value — the observed maximum is
  466,500, a real filing; and (b) it does not have room even on the modern
  population, where ENTREBANK filed 951.11 at 20220331 on $33,708k of assets —
  **5.1% below the bound, on a bank squarely inside the CDFI size band.** The
  earlier six-quarter measurement stopped at 277.16 and 1,000 read as 3.6x
  headroom; it is 1.05x.

  **No scalar band separates the two field classes.** A band reaching 466,500
  would admit more than 80% of the `RBCT1J` dollar values in the population; at
  1,000 the guard refuses 4,295 of the 4,296 `RBCT1J` values at 20260630 and
  zero real `RBC1AAJ` values. 1,000 is kept — it is the largest bound that holds
  dollar-magnitude detection above 99.8% — but it is now documented as **a
  magnitude heuristic calibrated to the modern population**, with the
  measurement table beside it, not as a class separator.

  **A breach now DEGRADES THE FIELD instead of raising.** `tier1_ratio` becomes
  `None` (status N/A, dropped from the peer median), and the rest of the row,
  the request and the peer group are untouched. Raising put the cost of a thin
  heuristic on eight metrics for every peer, over one optional field on one
  institution — worse than the single nonsense cell it avoided, and the same
  degrade-the-cell doctrine `GRADEABLE_BASES` and `reported_is_trustworthy`
  already follow. A SYSTEMATIC field swap stays loud: every peer breaches and
  the metric goes N/A across the whole group.

  **What degrading gets wrong, and what was added because of it:** a value the
  user does not see rejected. So a refusal is recorded, never swallowed —
  `InstitutionProfile.implausible_fields` names the field, `metric_basis`
  returns `BASIS_REJECTED_IMPLAUSIBLE` (distinct from `BASIS_UNREPORTED`, so a
  refusal can never read as "FDIC published nothing"), the metric detail renders
  a **Not shown** note saying the bound is this tool's heuristic and the
  published value was a real filing, and the peer group carries a caveat
  counting how many peers it happened to.

  **`_RATIO_MIN` is derived rather than hand-set.** It was `-100.0`, never
  derived from any measurement and never exercised by any test — the guard's
  only parametrized case was 277.16 / 194.25 / 142.22, all positive, so neither
  end of the floor was covered at any value. It refused real filed values in 42
  of the 169 swept quarters. It is now `-_RATIO_MAX`, the mirror of the ceiling,
  because what the guard detects is magnitude and there is no measured basis for
  an asymmetric floor; exactly one quarter in 42 years still breaches it, and
  under the degrade rule that costs one cell rather than a group.

- **`tier1_ratio` rendered a false basis line.** `metric_basis` handled `nim` /
  `roaa` / `roae` / `efficiency_ratio` explicitly and **fell through** to
  `BASIS_STOCK` — "computed from period-end balances". That fall-through is
  correct for `loans_to_deposits`, `npl_ratio` and `reserve_coverage` and was
  wrong for `tier1_ratio`, which is FDIC's published `RBC1AAJ` carried through
  verbatim: nothing computed it, it is not from period-end balances, and the
  quantity that sentence names is a different number (CERT 16584 at 20260630:
  value **14.9877**, EQ/ASSET **15.19%**). No grade changed — both bases are
  gradeable — but the false line rendered on the one FDIC-published value in the
  group and the only metric carrying a CFR citation, under a docstring promising
  that "a value and the basis rendered beside it can never disagree about where
  the value came from". `BASIS_FDIC` was not usable either: it says
  "annualized", and a capital ratio has no flow period. New
  `BASIS_FDIC_LEVERAGE` states what the value is, and `tier1_ratio` reports
  three distinct states — published, unreported, refused.

  **The fall-through itself is gone**, which is the actual fix. `metric_basis`
  reaches `BASIS_STOCK` through an explicit `_STOCK_RATIO_METRICS` set and ends
  at `BASIS_UNRULED`, which is **not** gradeable. A metric added without ruling
  its basis now degrades loudly instead of inheriting whichever branch happened
  to be written last. Each of the three remaining stock metrics is gated by
  recomputing it from the two balance-sheet fields its basis claims, so
  `BASIS_STOCK` is a checked claim rather than an assumed one.

- **The Status column never consults the peer columns, and the page never said
  so.** `status` compares the institution's value to the fixed thresholds and
  does not read the peer median or percentiles printed beside it. Measured at
  20260630, CERT 58490's NPL ratio of 2.53% is 6.2x its peer median (0.41%) and
  above the 75th percentile (0.71%), while its reserve coverage is 22% of the
  peer median and below the 25th percentile — **both grade ADEQUATE**; CERT
  16584's ROAA is below its peer median, prints *"0.12% below median"*, and
  grades STRONG. Every grade is correct. What was missing is the sentence, now
  rendered directly beneath the Performance Summary table and in the README.

- **Printed arithmetic that did not add up on 4 of 16 rows.** `vs_median` was
  computed on raw values and rounded independently of the operands the page
  prints, so CERT 16584's NIM rendered `4.36%`, `3.94%` and `0.41% above
  median`. The RENDERED difference is now the difference of the RENDERED
  operands; `BenchmarkResult.vs_median` stays exact for programmatic consumers.

- **Asset figures carried no thousands separator.** `$2027.0MM`,
  `$4091315.0MM`. Now `$2,027.0MM` and `$4,091,315.0MM`.

- **The most prominently disclosed peer-selection constant is the one that does
  nothing.** `selection_basis` led with *"out of 828 in a +/-50% asset window"*.
  Measured at 20260630, `HOUSE_ASSET_TOLERANCE` is **inert for 4,232 of 4,313
  filers (98.1%)**: for CERT 16584 the group is the identical 50 CERTs at a
  tolerance of 0.5, 0.2, 0.1, 0.05 and 0.03, and first changes at 0.02. The
  group's actual breadth is set by `HOUSE_MAX_PEERS` and measured
  **-3.00%/+2.92%** (CERT 16584) and **-5.55%/+5.45%** (CERT 58490) — roughly an
  order of magnitude tighter than the window a reader was being shown. The
  realized span now leads the sentence, and the window is described as what it
  is: a bound on the candidate pool that usually does not bind.

- **A caveat that was false of its own document.** At zero peers — reachable
  from an ordinary typo, a `report_date` on which no institution filed — the
  report rendered *"Percentiles over so few peers are not a reliable
  benchmark"* while containing no percentiles at all, every peer column N/A, and
  `STRONG` still printed under the title *CDFI Peer Benchmarking Report*. n=0
  now gets its own caveat saying no benchmarking was performed, and the small-n
  sentence is reserved for the small-but-nonzero groups it describes.

- **`ASSET_BUCKETS` named something on the report face with no attribution.**
  `**Asset Bucket:** Large` was the only classifying constant rendering there
  with no HOUSE marker, no boundaries and no attribution, while fifteen
  constants beside it carried all three — and "Large" is a supervisory word
  under CRA and in the FDIC's own definitions, neither of which this band is.
  Renamed `HOUSE_ASSET_BUCKETS` (`ASSET_BUCKETS` kept as an alias and still
  exported), and the line now renders its boundaries and its attribution.
  Separately, `asset_bucket`'s bare `return "mega"` fall-through was a claim
  about two sets and only one had been thought about: a profile with NEGATIVE
  total assets rendered **Asset Bucket: Mega**. Below the lowest band now
  answers "unknown".

- **A gate that scans instead of working from a list.**
  `tests/test_bound_claims.py` tokenizes every `.py` in the tree (comments and
  strings only, so a list literal is not read as a claim) and reads every `.md`,
  and fails on any prose stating a numeric bound the constants contradict —
  unless the sentence is marked as history, or sits under a released version
  header in this file. This defect class has recurred six times here, and both
  the audit that found it and the brief that ordered the fix named their sites
  by hand and missed some. The scan found two the hand-typed list did not: the
  `RBC1AAJ` contrast comment in `_parse_institution`, and the misattribution of
  FIRST CITY BANK to 20260331 in the evidence table. It also **cleared one the
  list had condemned**: where the 0.2.1 section of this file says the bound
  was `[-100, 150]`, that is correct — at tag `v0.2.1` the bound really was
  `[-100.0, 150.0]` and really did raise, so rewriting that entry would replace
  a true statement with a false one.

### Considered and rejected

- **UBPR peer groups as the peer-selection construct.** UBPR is what a bank
  supervisor would reach for, and not adopting it costs comparability with how
  examiners talk about peers. It is rejected on **availability and shape, not on
  quality**:

  - *Availability.* FDIC BankFind exposes no UBPR peer-group assignment.
    `PEERGROUP` and `UBPRPG` return HTTP 200 with the field silently absent
    while real fields on the same request return values; `/banks/ubpr`,
    `/banks/peers` and `/banks/peergroups` all 404. Adopting it would require
    the FFIEC CDR — a bulk-download portal, not a queryable API — as a second
    data provider for a single field.
  - *Shape.* UBPR groups on FIXED asset bands, which put a $111.2MM and a
    $249MM CDFI in one group. Nearest-neighbour selection puts the subject at
    percentile 52 of a group spanning ±3%, which is a tighter comparison for
    the size range this tool serves.

  **Residual:** this is a real loss of comparability with supervisory practice,
  recorded rather than left as drift. Revisit if FFIEC exposes peer-group
  assignment through an API.

### Known and carried forward, unfixed

- The peer median is computed across a MIXED basis: peers whose published
  ratios are trusted contribute FDIC's measurement while peers falling back to
  the computed proxy contribute a differently-measured number, and the median
  does not say which.
- `_metric_label` applies the INSTITUTION's basis to the peer columns, so a peer
  column can be labelled with a basis that is not the peers'.
- Published values that are absurd but real are graded as filed. FDIC's `EEFFR`
  of -700 and -5.615 are FDIC's own correct arithmetic over negative
  noninterest expense, reproducible from the filed financials, and they grade
  STRONG. `reported_is_trustworthy` catches only an exact-zero fill; it is not
  a sanity bound and was deliberately not turned into one under the ratio-class
  guard, which is calibrated for `RBC1AAJ` alone.
- A `docs-check` job is not yet in CI; the prose gates run in the test matrix.

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
