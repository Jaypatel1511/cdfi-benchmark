"""G-P7: the no-grade-moves tripwire's snapshot, runnable under ANY version.

0.3.4 changes what the page SHOWS of a peer statistic, never its value or any
grade. This module computes, through the public API that 0.3.3 already had
(`benchmark_institution`, `summary_table`), `status` and every field that
`BenchmarkResult` and `summary_table` carry IN 0.3.3, for every metric, at
report dates 20241231 and 20260630 only (no date the 0.3.4 N6 or N8 fixes
touch), at peer_count 1, 4, 5 and 20, plus the CERT-16583-shaped group whose
per-metric n are 1, 4, 7 and 19.

It is a regression tripwire, not a proof: it can only see the inputs below.

Run as a script under an installed version to print its snapshot:

    cd /tmp && ~/v033/bin/python /path/to/tests/_gp7.py > v033.py

It must import `cdfibenchmark` from that interpreter's site-packages, never
from a checkout -- `main()` prints the path it imported from to stderr, and
refuses to run if the module came from a directory containing this file's
parent. `tests/_gp7_v033.py` is that output for the published 0.3.3 wheel;
`tests/test_peer_n.py` compares the build against it with no network and no
second interpreter.
"""
import math

DATES = ("20241231", "20260630")
PEER_COUNTS = (1, 4, 5, 20)

#: Fields `BenchmarkResult` has in 0.3.3, by name. `peer_group_size` (0.3.4)
#: is deliberately NOT here; the test checks it separately against len(peers).
RESULT_FIELDS = (
    "metric", "institution_value", "peer_median", "peer_25th", "peer_75th",
    "peer_count", "unit", "lower_is_better", "basis", "source", "report_date",
    "vs_median", "status", "not_graded_reason",
)
#: The 11 `summary_table` columns 0.3.3 has. 0.3.4's 12th
#: (`report_withholds_peer_stats`) is not part of the comparison.
TABLE_COLUMNS = (
    "metric", "institution", "peer_median", "peer_25th", "peer_75th",
    "vs_median", "status", "peer_count", "basis", "threshold_source",
    "not_graded_reason",
)


def _norm(v):
    """Exact, literal-safe form: floats by their hex, NaN and None by name."""
    try:
        import numpy as np
        if isinstance(v, np.generic):
            v = v.item()
    except ImportError:  # pragma: no cover
        pass
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    if isinstance(v, float):
        return "nan" if math.isnan(v) else float.hex(v)
    if isinstance(v, int):
        return v
    return str(v)


def _profile(InstitutionProfile, cert, repdte, i, **over):
    """A bank whose every metric is defined and varies with `i`."""
    a = 100_000.0 + 1_000.0 * i
    base = dict(
        cert=cert, name=f"Bank {cert}", city="Oakland", state="CA",
        report_date=repdte, total_assets=a,
        total_deposits=a * (0.80 + 0.01 * i), net_loans=a * (0.60 + 0.013 * i),
        net_income=a * (0.004 + 0.0003 * i),
        interest_income=a * (0.030 + 0.0007 * i),
        interest_expense=a * (0.006 + 0.0002 * i),
        non_interest_income=a * 0.005, non_interest_expense=a * (0.020 + 0.0004 * i),
        total_equity=a * (0.09 + 0.002 * i), tier1_ratio=8.5 + 0.37 * i,
        gross_loans=a * (0.61 + 0.013 * i),
        non_current_loans=a * (0.002 + 0.0007 * i),
        loan_loss_allowance=a * (0.008 + 0.0003 * i),
        reported_nim=3.1 + 0.11 * i, reported_roaa=0.4 + 0.07 * i,
        reported_roae=4.0 + 0.6 * i, reported_efficiency_ratio=88.0 - 1.3 * i,
    )
    base.update(over)
    return InstitutionProfile(**base)


def cert16583_shaped(InstitutionProfile, repdte="20260630"):
    """(subject, peers): a 19-peer group shaped like CERT 16583 at 20260630.

    SYNTHETIC values; the SHAPE is the audit's live measurement (2026-09-30):
    12 uninsured trust companies with no loans and no deposits, 3 insured
    peers with deposits but no loans, and 4 lending peers of which ONE has
    non-current loans. So reserve_coverage n = 1 (60.24%), npl_ratio n = 4
    (median 0.00%), loans_to_deposits n = 7, and every other metric n = 19.
    """
    subject = _profile(InstitutionProfile, 16583, repdte, 3,
                       non_current_loans=173.0, gross_loans=6834.0,
                       loan_loss_allowance=150.0)
    peers = []
    for k in range(12):   # trust companies: no loans, no deposits
        peers.append(_profile(InstitutionProfile, 80000 + k, repdte, k,
                              total_deposits=0.0, net_loans=0.0,
                              gross_loans=0.0, non_current_loans=0.0,
                              loan_loss_allowance=0.0))
    for k in range(3):    # insured, deposits, no loans
        peers.append(_profile(InstitutionProfile, 81000 + k, repdte, k,
                              net_loans=0.0, gross_loans=0.0,
                              non_current_loans=0.0, loan_loss_allowance=0.0))
    lenders = ((83.0, 6226.0, 50.0), (0.0, 2241.0, 30.0),
               (0.0, 3053.0, 40.0), (0.0, 9755.0, 90.0))
    for k, (ncl, gross, lla) in enumerate(lenders):
        peers.append(_profile(InstitutionProfile, 82000 + k, repdte, k,
                              non_current_loans=ncl, gross_loans=gross,
                              net_loans=gross * 0.99, loan_loss_allowance=lla))
    return subject, peers


def cases(InstitutionProfile):
    """(case id, subject, peers) for every snapshot case."""
    out = []
    for d in DATES:
        for k in PEER_COUNTS:
            subject = _profile(InstitutionProfile, 1, d, 7)
            peers = [_profile(InstitutionProfile, 9000 + i, d, i)
                     for i in range(k)]
            out.append((f"{d}/n{k}", subject, peers))
        subject, peers = cert16583_shaped(InstitutionProfile, d)
        out.append((f"{d}/cert16583-shape", subject, peers))
    return out


def snapshot():
    from cdfibenchmark import (
        InstitutionProfile, benchmark_institution, summary_table,
    )
    snap = {}
    for cid, subject, peers in cases(InstitutionProfile):
        results = benchmark_institution(subject, peers)
        snap[cid + "/results"] = [
            {f: _norm(getattr(r, f)) for f in RESULT_FIELDS} for r in results
        ]
        df = summary_table(subject, peers)
        snap[cid + "/table"] = [
            {c: _norm(row[c]) for c in TABLE_COLUMNS}
            for _, row in df.iterrows()
        ]
    return snap


def main():
    import os
    import pprint
    import sys
    import cdfibenchmark
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    where = os.path.abspath(cdfibenchmark.__file__)
    print(f"# cdfibenchmark {cdfibenchmark.__version__} from {where}",
          file=sys.stderr)
    if where.startswith(here + os.sep):
        sys.exit(f"refusing: cdfibenchmark imported from the checkout {here}")
    print('"""G-P7 snapshot of the PUBLISHED cdfi-benchmark '
          f'{cdfibenchmark.__version__} wheel.\n\nGenerated by tests/_gp7.py '
          'under a venv holding only that wheel; do not edit by hand.\n"""')
    print(f"VERSION = {cdfibenchmark.__version__!r}")
    print("SNAPSHOT = " + pprint.pformat(snapshot(), width=100, sort_dicts=True))


if __name__ == "__main__":
    main()
