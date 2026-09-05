"""
FDIC BankFind Suite API wrapper.
Free public API — no authentication required.
"""
import requests
import pandas as pd
from typing import Optional
from cdfibenchmark.data.schema import InstitutionProfile, FDIC_API_BASE
from cdfibenchmark.exceptions import FDICAPIError, FDICResponseError

TIMEOUT = 30


def _extract_records(payload, ctx: str) -> list:
    """Enforce the top-level "data" shape contract for every fetcher.

    The "data" key absent, null, or not a list is a wrong-shape response →
    FDICResponseError (names ``ctx``). A present empty list is the legitimate
    "zero rows" answer and is returned as-is for the caller to map to its own
    empty value (None / empty DataFrame / []).
    """
    if not isinstance(payload, dict):
        raise FDICResponseError(
            f"FDIC response for {ctx} was {type(payload).__name__}, not a JSON object"
        )
    if "data" not in payload:
        raise FDICResponseError(f"FDIC response for {ctx} is missing the 'data' key")
    data = payload["data"]
    if not isinstance(data, list):
        raise FDICResponseError(
            f"FDIC response 'data' for {ctx} was {type(data).__name__}, not a list"
        )
    return data


def get_institution(cert: int) -> Optional[dict]:
    """
    Fetch institution profile by FDIC certificate number.

    Returns the raw record dict, or None when no institution matches the cert
    (a legitimate "no such institution" answer). Raises FDICAPIError on a
    transport/decode failure and FDICResponseError if the response shape is
    unexpected.
    """
    url = f"{FDIC_API_BASE}/institutions"
    params = {
        "filters": f"CERT:{cert}",
        "fields": "CERT,NAME,CITY,STALP,ASSET,ACTIVE",
        "limit": 1,
        "format": "json",
    }

    try:
        r = requests.get(url, params=params, timeout=TIMEOUT)
        r.raise_for_status()
        payload = r.json()
    except (requests.exceptions.RequestException, ValueError) as e:
        raise FDICAPIError(f"get_institution failed for CERT {cert}: {e}") from e

    institutions = _extract_records(payload, f"CERT {cert}")
    if not institutions:
        return None
    try:
        return institutions[0].get("data", {})
    except (AttributeError, KeyError, TypeError, ValueError) as e:
        raise FDICResponseError(
            f"unexpected FDIC response shape for CERT {cert}: {e}"
        ) from e


def search_institutions(
    name: str = None,
    state: str = None,
    min_assets: int = None,
    max_assets: int = None,
    limit: int = 20,
) -> pd.DataFrame:
    """
    Search for FDIC-insured institutions by name, state, or asset size.
    Returns a DataFrame of matching institutions.
    """
    filters = ["ACTIVE:1"]
    if state:
        filters.append(f"STALP:{state.upper()}")
    if min_assets:
        filters.append(f"ASSET:[{min_assets} TO *]")
    if max_assets:
        filters.append(f"ASSET:[* TO {max_assets}]")

    filter_str = " AND ".join(filters)
    url = f"{FDIC_API_BASE}/institutions"
    params = {
        "filters": filter_str,
        "fields": "CERT,NAME,CITY,STALP,ASSET",
        "limit": limit,
        "sort_by": "ASSET",
        "sort_order": "DESC",
        "format": "json",
    }
    # Name matching goes through the `search` parameter, not a filter. An
    # exact-phrase filters=NAME:"<name>" never matches substrings; search=NAME:
    # does the substring/relevance match the FDIC API is designed for.
    if name:
        params["search"] = f"NAME:{name}"

    try:
        r = requests.get(url, params=params, timeout=TIMEOUT)
        r.raise_for_status()
        payload = r.json()
    except (requests.exceptions.RequestException, ValueError) as e:
        raise FDICAPIError(
            f"search_institutions failed for filters [{filter_str}]: {e}"
        ) from e

    records = _extract_records(payload, f"filters [{filter_str}]")
    if not records:
        return pd.DataFrame()
    try:
        rows = [item.get("data", {}) for item in records]
        df = pd.DataFrame(rows)
        if "ASSET" in df.columns:
            df["ASSET_MM"] = df["ASSET"] / 1_000
        return df
    except (AttributeError, KeyError, TypeError, ValueError) as e:
        raise FDICResponseError(
            f"unexpected FDIC response shape for filters [{filter_str}]: {e}"
        ) from e


def get_financials(
    cert: int,
    report_date: str = None,
    limit: int = 4,
) -> Optional[InstitutionProfile]:
    """
    Fetch call report financials for a single institution.

    Args:
        cert:        FDIC certificate number
        report_date: Specific date e.g. "20241231" (default: most recent)
        limit:       Number of periods to fetch

    Returns:
        InstitutionProfile with computed metrics
    """
    url = f"{FDIC_API_BASE}/financials"
    fields = [
        "REPDTE", "CERT", "NAME", "CITY", "STALP",
        "ASSET", "DEP", "LNLSNET", "NETINC",
        "INTINC", "EINTEXP", "NONII", "NONIX", "EQ",
        "RBC1AAJ", "RBCT1J", "LNLSGR", "NCLNLS", "LNATRES",
        # FDIC's own published ratios — already annualized and over the correct
        # average denominators, which is the basis the thresholds are
        # calibrated to. Preferred over the hand-computed proxy; see
        # InstitutionProfile.metric_basis.
        "NIMY", "ROA", "ROE", "EEFFR",
        # Amortization of intangibles + goodwill impairment: the EEFFR
        # numerator subtraction the package omitted through 0.2.1.
        "EAMINTAN",
    ]

    filters = f"CERT:{cert}"
    if report_date:
        filters += f" AND REPDTE:{report_date}"

    params = {
        "filters": filters,
        "fields": ",".join(fields),
        "limit": limit,
        "sort_by": "REPDTE",
        "sort_order": "DESC",
        "format": "json",
    }

    try:
        r = requests.get(url, params=params, timeout=TIMEOUT)
        r.raise_for_status()
        payload = r.json()
    except (requests.exceptions.RequestException, ValueError) as e:
        raise FDICAPIError(f"get_financials failed for CERT {cert}: {e}") from e

    records = _extract_records(payload, f"CERT {cert}")
    if not records:
        return None
    try:
        row = records[0].get("data", {})
    except (AttributeError, KeyError, TypeError, ValueError) as e:
        raise FDICResponseError(
            f"unexpected FDIC response shape for CERT {cert}: {e}"
        ) from e
    return _parse_institution(row)


#: Hard cap the FDIC /financials endpoint enforces on `limit`. Measured
#: 2026-09-05: limit=10000 returns 200; limit=20000 returns HTTP 400
#: ``validate:too_big`` — "Number must be less than or equal to 10000".
#: A caller that needs the WHOLE result set must therefore check whether the
#: row count came back at the cap, because the endpoint truncates silently.
FDIC_MAX_LIMIT = 10_000


def get_peer_financials(
    state: str = None,
    min_assets: int = None,
    max_assets: int = None,
    report_date: str = None,
    limit: int = 100,
    sort_order: str = "DESC",
) -> list:
    """
    Fetch call report financials for a group of peer institutions.

    Args:
        state:       Filter by state abbreviation e.g. "IL"
        min_assets:  Minimum assets in thousands
        max_assets:  Maximum assets in thousands
        report_date: Report date e.g. "20241231"
        limit:       Maximum number of institutions. The endpoint caps this at
                     FDIC_MAX_LIMIT and truncates in `sort_order` order without
                     saying so — see build_peer_group, which fetches the whole
                     asset window rather than a sorted slice of it.
        sort_order:  "ASC" or "DESC" over ASSET. Both are accepted by the
                     endpoint (measured 2026-09-05).

    Returns:
        List of InstitutionProfile objects
    """
    url = f"{FDIC_API_BASE}/financials"
    fields = [
        "REPDTE", "CERT", "NAME", "CITY", "STALP",
        "ASSET", "DEP", "LNLSNET", "NETINC",
        "INTINC", "EINTEXP", "NONII", "NONIX", "EQ",
        "RBC1AAJ", "RBCT1J", "LNLSGR", "NCLNLS", "LNATRES",
        # FDIC's own published ratios — already annualized and over the correct
        # average denominators, which is the basis the thresholds are
        # calibrated to. Preferred over the hand-computed proxy; see
        # InstitutionProfile.metric_basis.
        "NIMY", "ROA", "ROE", "EEFFR",
        # Amortization of intangibles + goodwill impairment: the EEFFR
        # numerator subtraction the package omitted through 0.2.1.
        "EAMINTAN",
    ]

    filters = ["ASSET:[1 TO *]"]
    if state:
        filters.append(f"STALP:{state.upper()}")
    if min_assets:
        filters.append(f"ASSET:[{min_assets} TO *]")
    if max_assets:
        filters.append(f"ASSET:[* TO {max_assets}]")
    if report_date:
        filters.append(f"REPDTE:{report_date}")

    filter_str = " AND ".join(filters)
    params = {
        "filters": filter_str,
        "fields": ",".join(fields),
        "limit": limit,
        "sort_by": "ASSET",
        "sort_order": sort_order,
        "format": "json",
    }

    try:
        r = requests.get(url, params=params, timeout=TIMEOUT)
        r.raise_for_status()
        payload = r.json()
    except (requests.exceptions.RequestException, ValueError) as e:
        raise FDICAPIError(
            f"get_peer_financials failed for filters [{filter_str}]: {e}"
        ) from e

    records = _extract_records(payload, f"filters [{filter_str}]")
    if not records:
        return []
    # No silent-skip guard: every record is parsed. A malformed record in the
    # batch signals a contract problem and raises (fail loud for the batch);
    # legitimately-sparse records (absent core → NaN, absent optional → None)
    # are kept, not dropped.
    try:
        return [_parse_institution(item.get("data")) for item in records]
    except (AttributeError, KeyError, TypeError, ValueError) as e:
        raise FDICResponseError(
            f"unexpected FDIC response shape for filters [{filter_str}]: {e}"
        ) from e


# Plausibility bound for percentage/ratio-class fields. This is a GROSS
# field-class drift guard — a Tier 1 CAPITAL figure ($k, up to 302,589,000 at
# 20260630) landing in the Tier 1 LEVERAGE RATIO slot — and nothing finer.
#
# The bound was [-100, 150] through 0.3.0 and that was too tight for a real
# leverage ratio. RBC1AAJ is Tier 1 capital over AVERAGE assets, so a de novo
# bank (whose average assets trail its period-end assets) or one in wind-down
# holding almost all equity can exceed 100% legitimately. Measured across six
# quarters, every active FDIC filer:
#
#   REPDTE     n     max RBC1AAJ    over 150
#   20260630   4313     277.16         2   <- CORNERSTONE COMMUNITY BANK (EQ/ASSET 55.3%)
#   20260331   4353     142.22         0      FIRST CITY BANK           (EQ/ASSET 94.5%)
#   20251231   4411     119.35         0
#   20250630   4494     117.29         0
#   20241231   4560     117.66         0
#   20231231   4658     105.01         0
#
# 150 fit five of six quarters by luck and raised FDICResponseError on two real
# banks in the sixth, aborting the whole peer group. 1000 admits every observed
# leverage ratio with room, and still catches the drift the guard is for.
#
# What this guard CANNOT do, stated because the old comment claimed otherwise:
# it cannot separate the field classes at the SMALL end. RBCT1J is as low as
# $62k for a tiny filer, which sits squarely inside the ratio band — so a
# dollar figure from a small institution mapped into a ratio slot passes this
# check. The field NAME is the real protection; this is defence in depth
# against a large-magnitude swap only.
_RATIO_MIN = -100.0
_RATIO_MAX = 1000.0


def _coerce_float(row: dict, key: str, *, absent, ratio_class: bool = False):
    """Coerce ``row[key]`` to float under the field-level empty-vs-error rule.

    absent / null  → ``absent`` (NaN for core financials, None for optional
                     ratios) — NEVER a fabricated 0.0.
    present & numeric → the float value, so a real present 0.0 is preserved.
    present & non-numeric → FDICResponseError naming the offending field.

    ``ratio_class`` fields carry a defense-in-depth plausibility bound: a value
    outside [-100, 150] cannot be a percentage and raises FDICResponseError,
    so a future wrong-field-class regression (e.g. a dollar field remapped into
    the ratio slot) fails loud instead of grading a nonsense value.
    """
    if key not in row or row[key] is None:
        return absent
    val = row[key]
    try:
        f = float(val)
    except (TypeError, ValueError) as e:
        raise FDICResponseError(
            f"FDIC field {key} is present but not float-coercible: {val!r}"
        ) from e
    if ratio_class and not (_RATIO_MIN <= f <= _RATIO_MAX):
        raise FDICResponseError(
            f"FDIC ratio-class field {key} value {f} cannot be a percentage — "
            f"wrong field class or API drift"
        )
    return f


def _parse_institution(row: dict) -> InstitutionProfile:
    """Parse a raw FDIC financials row into an InstitutionProfile, failing loud.

    Identity (CERT) absent/null/non-int-coercible → FDICResponseError — a
    record with no usable identity must never become a phantom cert=0 bank.
    Core financials absent/null → NaN (unknown, never a fabricated 0.0);
    present-but-garbage → FDICResponseError. Optional ratios absent/null →
    None; present-but-garbage → FDICResponseError. String fields are cosmetic
    and default to "" / "Unknown".
    """
    if not isinstance(row, dict):
        raise FDICResponseError(
            f"FDIC record is not an object (got {type(row).__name__}): {row!r}"
        )

    cert_raw = row.get("CERT")
    if cert_raw is None:
        raise FDICResponseError("FDIC record is missing its identity field CERT")
    try:
        cert = int(cert_raw)
    except (TypeError, ValueError) as e:
        raise FDICResponseError(
            f"FDIC field CERT is present but not int-coercible: {cert_raw!r}"
        ) from e

    return InstitutionProfile(
        cert=cert,
        name=str(row.get("NAME", "Unknown")),
        city=str(row.get("CITY", "")),
        state=str(row.get("STALP", "")),
        report_date=str(row.get("REPDTE", "")),
        total_assets=_coerce_float(row, "ASSET", absent=float("nan")),
        total_deposits=_coerce_float(row, "DEP", absent=float("nan")),
        net_loans=_coerce_float(row, "LNLSNET", absent=float("nan")),
        net_income=_coerce_float(row, "NETINC", absent=float("nan")),
        interest_income=_coerce_float(row, "INTINC", absent=float("nan")),
        interest_expense=_coerce_float(row, "EINTEXP", absent=float("nan")),
        non_interest_income=_coerce_float(row, "NONII", absent=float("nan")),
        non_interest_expense=_coerce_float(row, "NONIX", absent=float("nan")),
        total_equity=_coerce_float(row, "EQ", absent=float("nan")),
        # tier1_ratio holds the Tier 1 LEVERAGE ratio (RBC1AAJ, a percent) — a
        # ratio-class field. Never RBCT1J, which is Tier One Capital in dollars.
        tier1_ratio=_coerce_float(row, "RBC1AAJ", absent=None, ratio_class=True),
        # Loan fields are dollar-class (thousands) — not bounded.
        gross_loans=_coerce_float(row, "LNLSGR", absent=None),
        non_current_loans=_coerce_float(row, "NCLNLS", absent=None),
        loan_loss_allowance=_coerce_float(row, "LNATRES", absent=None),
        intangible_amortization=_coerce_float(row, "EAMINTAN", absent=None),
        # FDIC-published ratios. Deliberately NOT ratio_class-bounded: unlike a
        # leverage ratio these are not confined to [-100, 150]. An efficiency
        # ratio above 150% is ordinary for a bank with thin revenue (FDIC
        # published 104.08% for CERT 34352 at 20250630), and ROE runs
        # arbitrarily negative as equity approaches zero. Bounding them would
        # convert real values into FDICResponseError.
        reported_nim=_coerce_float(row, "NIMY", absent=None),
        reported_roaa=_coerce_float(row, "ROA", absent=None),
        reported_roae=_coerce_float(row, "ROE", absent=None),
        reported_efficiency_ratio=_coerce_float(row, "EEFFR", absent=None),
    )
