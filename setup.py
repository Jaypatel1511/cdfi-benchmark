"""A PEP 517 shim. Every packaging field lives in pyproject.toml's [project] table.

WHY THIS FILE STATES NOTHING
----------------------------
It used to carry `name`, `version` and `install_requires` of its own. Nothing
read them. `pyproject.toml` declares `build-backend = "setuptools.build_meta"`
and a PEP 621 `[project]` table, and PEP 621 metadata wins over anything a
setup() call passes -- so the duplicates were inert copies that could only ever
drift out of date, and they did: this file said `version="0.2.1"` while two
further releases went out, and the sdist shipped that stale number to PyPI
inside every one of them. No gate read it, so nothing went red.

The fix is not to bump the copy. A second version site that must be edited by
hand and that no gate reads is the same class of defect as the stale comments
`tests/test_bound_claims.py` exists to scan for -- it will simply go stale
again. So the copy is gone and there is now exactly ONE declared version, in
pyproject.toml. `cdfibenchmark.__version__` derives from installed package
metadata, so it tracks that one automatically.

WHY THE FILE ITSELF SURVIVES, RATHER THAN BEING DELETED
-------------------------------------------------------
Deleting it is safe for the BUILD and unsafe for the GATES, and those are
different questions.

Build, measured -- `git archive HEAD` into a clean tree with setup.py removed,
then `python -m build`:

    wheel:  15 entries, top_level.txt = ['cdfibenchmark'], zero tests/* entries
    sdist:  file list identical to the baseline except for setup.py itself

Byte-for-byte the same distribution. Package discovery does NOT depend on this
file's `find_packages(exclude=["tests", "tests.*"])`: setuptools' automatic
flat-layout discovery already excludes `tests`, which the top_level.txt above
confirms.

Gates, also measured: `setup.py` is named in `tests/_layout.py`'s SURFACES map
and in `test_package_claims._REQUIRED_SURFACES`, and it is one of the seven
surfaces the wrong-cert scan sweeps. Deleting it would make
`test_every_surface_this_module_reads_is_present_or_declared_absent` fail by
name in every source tree -- correctly, because from a gate's point of view an
undeclared missing surface IS a deletion -- and would silently shrink the cert
scan by one surface. Removing it therefore means editing gate logic and
narrowing a scan, which is a bigger change than it looks and does not belong in
a release that is otherwise metadata and prose. Recorded as a 0.3.2 candidate.
"""
from setuptools import setup

setup()
