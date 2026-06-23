# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

> History prior to 0.2.0 predates this changelog and is not documented here.

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
