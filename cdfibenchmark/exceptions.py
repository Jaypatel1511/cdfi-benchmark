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
