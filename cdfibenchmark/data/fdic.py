"""
FDIC BankFind Suite API wrapper.
Free public API — no authentication required.
"""
import requests
import pandas as pd
from typing import Optional
from cdfibenchmark.data.schema import (
    InstitutionProfile, FDIC_API_BASE, FDIC_FIELDS
)
from cdfibenchmark.exceptions import FDICAPIError, FDICResponseError

TIMEOUT = 30


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
        "fields": "CERT,INSTNAME,CITY,STALP,ASSET,ACTIVE",
        "limit": 1,
        "format": "json",
    }

    try:
        r = requests.get(url, params=params, timeout=TIMEOUT)
        r.raise_for_status()
        payload = r.json()
    except (requests.exceptions.RequestException, ValueError) as e:
        raise FDICAPIError(f"get_institution failed for CERT {cert}: {e}") from e

    try:
        institutions = payload.get("data", [])
        if not institutions:
            return None
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
    if name:
        filters.append(f'INSTNAME:"{name}"')
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
        "fields": "CERT,INSTNAME,CITY,STALP,ASSET",
        "limit": limit,
        "sort_by": "ASSET",
        "sort_order": "DESC",
        "format": "json",
    }

    try:
        r = requests.get(url, params=params, timeout=TIMEOUT)
        r.raise_for_status()
        payload = r.json()
    except (requests.exceptions.RequestException, ValueError) as e:
        raise FDICAPIError(
            f"search_institutions failed for filters [{filter_str}]: {e}"
        ) from e

    try:
        records = payload.get("data", [])
        if not records:
            return pd.DataFrame()
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
        "REPDTE", "CERT", "INSTNAME", "CITY", "STALP",
        "ASSET", "DEP", "LNLSNET", "NETINC",
        "INTINC", "EINTEXP", "NONII", "NONIX", "EQ",
        "RBCT1J", "LNLSGR", "NCLNLS", "LNATRES",
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

    try:
        records = payload.get("data", [])
        if not records:
            return None
        row = records[0].get("data", {})
        return _parse_institution(row)
    except (AttributeError, KeyError, TypeError, ValueError) as e:
        raise FDICResponseError(
            f"unexpected FDIC response shape for CERT {cert}: {e}"
        ) from e


def get_peer_financials(
    state: str = None,
    min_assets: int = None,
    max_assets: int = None,
    report_date: str = None,
    limit: int = 100,
) -> list:
    """
    Fetch call report financials for a group of peer institutions.

    Args:
        state:       Filter by state abbreviation e.g. "IL"
        min_assets:  Minimum assets in thousands
        max_assets:  Maximum assets in thousands
        report_date: Report date e.g. "20241231"
        limit:       Maximum number of institutions

    Returns:
        List of InstitutionProfile objects
    """
    url = f"{FDIC_API_BASE}/financials"
    fields = [
        "REPDTE", "CERT", "INSTNAME", "CITY", "STALP",
        "ASSET", "DEP", "LNLSNET", "NETINC",
        "INTINC", "EINTEXP", "NONII", "NONIX", "EQ",
        "RBCT1J", "LNLSGR", "NCLNLS", "LNATRES",
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
        "sort_order": "DESC",
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

    try:
        records = payload.get("data", [])
        if not records:
            return []
        return [_parse_institution(item.get("data", {}))
                for item in records if item.get("data")]
    except (AttributeError, KeyError, TypeError, ValueError) as e:
        raise FDICResponseError(
            f"unexpected FDIC response shape for filters [{filter_str}]: {e}"
        ) from e


def _parse_institution(row: dict) -> InstitutionProfile:
    """Parse a raw FDIC API response row into an InstitutionProfile."""
    def safe_float(key, default=0.0):
        val = row.get(key)
        try:
            return float(val) if val is not None else default
        except (TypeError, ValueError):
            return default

    return InstitutionProfile(
        cert=int(row.get("CERT", 0)),
        name=str(row.get("INSTNAME", "Unknown")),
        city=str(row.get("CITY", "")),
        state=str(row.get("STALP", "")),
        report_date=str(row.get("REPDTE", "")),
        total_assets=safe_float("ASSET"),
        total_deposits=safe_float("DEP"),
        net_loans=safe_float("LNLSNET"),
        net_income=safe_float("NETINC"),
        interest_income=safe_float("INTINC"),
        interest_expense=safe_float("EINTEXP"),
        non_interest_income=safe_float("NONII"),
        non_interest_expense=safe_float("NONIX"),
        total_equity=safe_float("EQ"),
        tier1_ratio=safe_float("RBCT1J") or None,
        gross_loans=safe_float("LNLSGR") or None,
        non_current_loans=safe_float("NCLNLS") or None,
        loan_loss_allowance=safe_float("LNATRES") or None,
    )
