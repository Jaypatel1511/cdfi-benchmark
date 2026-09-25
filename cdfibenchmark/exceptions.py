"""
Typed exceptions for cdfi-benchmark.

The data layer must fail loud on transport/schema problems rather than
swallowing them and returning empty — in an early-warning / anomaly-detection
pipeline a silent empty result reads as "nothing anomalous", masking outages.
A successful request that legitimately returns zero rows still returns empty;
only transport and schema failures raise.
"""


class CDFIBenchmarkError(Exception):
    """Base class for all cdfi-benchmark errors."""


class FDICAPIError(CDFIBenchmarkError):
    """Couldn't get or parse a response from the FDIC API.

    Raised on transport failures, HTTP errors, and JSON decode failures —
    anything that means we never obtained a valid response body.
    """


class FDICResponseError(CDFIBenchmarkError):
    """Got valid JSON from the FDIC API but its structure is unexpected.

    Raised when a response decodes successfully but does not match the shape
    the parser requires (wrong types, missing keys). Distinct from
    FDICAPIError so callers can tell "the API is unreachable" apart from
    "the API changed its contract".
    """


class CBLRScheduleError(CDFIBenchmarkError, RuntimeError):
    """The CBLR period schedule shipped in this package is internally broken.

    Raised at import by `cdfibenchmark.data.schema._check_cblr_schedule` when a
    pure data invariant of the schedule constants fails (an unparseable or
    unordered floor, a verified-through date before the last row, a relief
    range outside the first row's span, or a PCA cite that starts after the
    framework). Also raised by `_cblr_at` if a date passes every refusal check
    yet precedes the first row, which correct code cannot reach.

    Deliberately NOT an ImportError: an `except ImportError:` fallback would
    read a broken schedule as "package not installed". It subclasses
    RuntimeError so generic handlers see a runtime-integrity failure. None of
    these checks reads the user's clock, so it can fire only if the package
    shipped broken.
    """
