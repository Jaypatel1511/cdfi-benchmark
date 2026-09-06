"""Claims written into the PACKAGE SOURCE, read through the installed module.

Split out of `test_bound_claims.py` in the 0.3.0 release cycle. That module
SCANS THE REPOSITORY TREE for stale numeric bounds; these two assertions do
not scan anything. They are about text that ships inside the wheel, so they
must run in `test-wheel` and `test-sdist` too — the jobs that test the very
artifact the comment ships in — and a module-level skip on the scan would have
switched them off in exactly those jobs.

The resolution rule, taken from `test_threshold_attribution.py:38` and
`test_peer_selection_bias.py:189`, which already did this correctly:

    read the source through ``<module>.__file__``, never through a repo path

`__file__` points at whatever copy is actually imported — the wheel's copy under
site-packages in `test-wheel`, the installed sdist's copy in `test-sdist`, the
checkout in ci.yml's `test` job. A repo path is only right in the last of those,
which is how `(ROOT / "cdfibenchmark" / "data" / "fdic.py").read_text()` raised
FileNotFoundError in all eight release jobs of run 34002310309.

Verified, not assumed: in both release layouts `fdic.__file__` resolves under
`site-packages/`, `cdfibenchmark` is a regular package (not a namespace package),
and the file is readable — so the two wrinkles worth worrying about, a `__file__`
of None and a package imported out of a zip, do not apply here. `_module_source`
asserts both rather than trusting them, because if either ever did apply the
honest outcome is a red gate, not a quiet one: a gate that cannot read the
source it certifies must say so, not pass.
"""
import pathlib

from cdfibenchmark.data import fdic


def _module_source(module) -> str:
    """The source text of the module as actually imported.

    Deliberately assert-and-fail rather than skip. A skip here would mean "the
    package under test is not a plain filesystem package, so we certified
    nothing" — reported as success. That is the false-assurance class this
    suite exists to close.
    """
    origin = getattr(module, "__file__", None)
    assert origin, (
        f"{module.__name__}.__file__ is {origin!r}, so this gate cannot read the "
        f"source it certifies. Reading a repo path instead is not the fix — that "
        f"is the defect this module was split out of."
    )
    path = pathlib.Path(origin)
    assert path.is_file(), (
        f"{module.__name__}.__file__ is {origin!r}, which is not a readable "
        f"file. The package may be imported from a zip or a namespace shim; "
        f"this gate cannot certify source it cannot read."
    )
    return path.read_text()


def test_the_guard_no_longer_claims_it_separates_the_field_classes():
    """The specific false justification this round was ordered to correct.

    "1000 admits every observed leverage ratio with room" was refuted by the
    package's own sweep: the observed maximum over 1984Q1-2026Q2 is 466,500.
    A false justification for a WIDENED safety bound is the strongest form of
    the comment-that-becomes-a-claim defect, so the sentence must not come back.

    This comment SHIPS INSIDE THE WHEEL, which is why the assertion belongs
    here and not behind the scan's skip.
    """
    text = _module_source(fdic)
    assert "admits every observed leverage ratio" not in text, (
        "fdic.py still claims the bound admits every OBSERVED leverage ratio. "
        "The observed maximum is 466,500 (CERT 27213, 19880331); the claim is "
        "true only of the modern population and must say so."
    )
    assert "466,500" in text, (
        "fdic.py does not state the whole-history maximum it was corrected with"
    )
    assert "951.11" in text, (
        "fdic.py does not state the MODERN maximum the bound is calibrated "
        "against — which is 5.1% below the bound, not the 3.6x the retracted "
        "comment implied"
    )


def test_the_floor_is_derived_from_the_ceiling_not_hand_set():
    """`_RATIO_MIN` was -100.0, never derived and never exercised.

    Whatever it is, it must stop being a bare number with no relationship to
    anything. It is now the mirror of `_RATIO_MAX`, because what the guard
    detects is magnitude.

    Reads no files at all, so it runs in every context unconditionally.
    """
    assert fdic._RATIO_MIN == -fdic._RATIO_MAX
