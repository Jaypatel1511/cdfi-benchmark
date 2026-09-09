"""
FDIC BankFind Suite API wrapper.
Free public API — no authentication required.
"""
import datetime

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


# ── Ratio-class plausibility bound ────────────────────────────────────────────
# A GROSS field-class drift guard: a Tier 1 CAPITAL figure in dollars landing in
# the Tier 1 LEVERAGE RATIO slot. Nothing finer, and — stated up front because a
# previous version of this comment claimed otherwise — it does NOT separate the
# two field classes. It is a MAGNITUDE HEURISTIC CALIBRATED TO THE MODERN
# POPULATION, and both halves of that sentence are load-bearing.
#
# WHAT WAS MEASURED. Every REPDTE the /financials endpoint serves, 1984Q1
# through 2026Q2 — 169 quarters with data, swept 2026-09-05 by querying each
# quarter sorted on RBC1AAJ ascending and descending:
#
#   population                      min RBC1AAJ            max RBC1AAJ
#   1984Q1-2026Q2 (169 quarters)      -1,524.07              466,500.00
#                                     CERT 34128 19960331    CERT 27213 19880331
#   2015Q1-2026Q2  (46 quarters)          -6.20                  951.11
#                                     CERT  9956 20160331    CERT 59287 20220331
#
# The whole-history maximum is 466,500 — a real filed leverage ratio, not drift:
# MERCHANT NATIONAL BANK, ASSET $6,414k against Tier 1 capital $4,665k, where
# FDIC's average-assets denominator collapsed toward zero. So NO scalar band
# admits every legitimate RBC1AAJ and still catches a dollar figure. Measured at
# 20260630, a band reaching 466,500 (or even 165,900) would let through more than
# 80% of the RBCT1J values in the population — the guard would be decoration.
#
# WHAT THE BOUND ACTUALLY BUYS. Real values rejected (r) against dollar values
# missed (m), over every filer at four modern quarters:
#
#   band [-B, B]      B=277.16     B=951.11      B=1000       B=2000      B=10000
#   20260630 (4,313)   0r / 0m      0r / 1m      0r / 1m     0r / 14m    0r / 403m
#   20220331 (4,861)   1r / 0m      0r / 6m      0r / 6m     0r / 22m    0r / 714m
#   20201231 (5,067)   0r / 0m      0r / 7m      0r / 7m     0r / 31m    0r / 837m
#   20161231 (5,983)   0r / 0m      0r / 7m      0r / 8m     0r / 75m   0r / 1377m
#
# 1,000 is the LARGEST bound that still rejects better than 99.8% of dollar
# magnitudes; the next step up multiplies the misses. It is not a bound chosen
# "with room" — the comment it replaces said 1,000 "admits every observed
# leverage ratio with room", and that was false in both halves. It admits every
# leverage ratio observed IN THE MODERN POPULATION, by 5.1%: ENTREBANK (CERT
# 59287) filed 951.11 at 20220331 on $33,708k of assets against $32,138k of Tier
# 1 capital — a de novo bank squarely inside the CDFI size band, not a 1990
# thrift. The margin here is thin on purpose, because widening it is not free.
#
# BECAUSE THE MARGIN IS THIN, A BREACH MUST NOT BE FATAL. An out-of-band value
# DEGRADES THE FIELD to None and is recorded on the profile; it does not raise.
# Raising put the cost of this heuristic being wrong on the whole peer group: one
# real bank out of band aborted all eight metrics for every peer, over one
# optional field on one institution. That is the failure the 150 bound produced
# on live 2026Q2 data, and 1,000 only moves it, it does not remove it.
#
# WHAT THE GUARD CANNOT DO, kept from the previous comment because it is still
# true: it cannot separate the field classes at the SMALL end. RBCT1J is as low
# as $62k for a tiny filer (20260331), which sits squarely inside the ratio band,
# so a dollar figure from a small institution mapped into a ratio slot passes.
# The field NAME is the real protection; this is defence in depth against a
# large-magnitude swap only.

#: Upper bound, derived from the table above: the largest band that keeps
#: dollar-magnitude detection above 99.8% on the modern population.
_RATIO_MAX = 1000.0
#: Lower bound, derived as the MIRROR of the upper one, because what this guard
#: detects is magnitude and there is no measured basis for an asymmetric floor.
#: The previous -100.0 was never derived and never exercised by any test: it
#: rejected real filed values in 42 of the 169 swept quarters (deepest -1,524.07),
#: while costing nothing at the modern end, where the deepest value in 46
#: quarters is -6.20. At -1,000 exactly one quarter in 42 years still breaches,
#: and under the degrade rule above that costs one cell rather than a group.
_RATIO_MIN = -_RATIO_MAX


def _coerce_float(row: dict, key: str, *, absent, ratio_class: bool = False,
                  rejected: list = None):
    """Coerce ``row[key]`` to float under the field-level empty-vs-error rule.

    absent / null  → ``absent`` (NaN for core financials, None for optional
                     ratios) — NEVER a fabricated 0.0.
    present & numeric → the float value, so a real present 0.0 is preserved.
    present & non-numeric → FDICResponseError naming the offending field.

    ``ratio_class`` fields carry the defence-in-depth plausibility bound
    documented above. A value outside [_RATIO_MIN, _RATIO_MAX] DEGRADES THE
    FIELD: it returns ``absent`` and appends ``key`` to ``rejected``, so the
    caller can record on the profile that a value arrived and was refused.

    Why degrade rather than raise. The bound is a heuristic with a measured 5.1%
    margin over the modern population's maximum, not a class separator, so it
    WILL eventually be wrong about a real bank. Raising made one wrong call cost
    the entire peer group — eight metrics for every peer aborted over one
    optional field on one institution — which is strictly worse than the nonsense
    value it was avoiding, because that nonsense value would have been confined
    to a single cell. This is also the package's own doctrine everywhere else:
    an ungradeable basis degrades the cell (GRADEABLE_BASES), an uncorroborated
    published ratio degrades the cell (`reported_is_trustworthy`).

    WHAT DEGRADING GETS WRONG: the user does not see the rejection happen. A
    number FDIC really published is discarded, and without the `rejected` record
    the cell would be indistinguishable from a field FDIC never published. That
    is why the rejection is recorded rather than swallowed — see
    `InstitutionProfile.implausible_fields`, `BASIS_REJECTED_IMPLAUSIBLE`, and
    the peer-group caveat that counts rejected peers. A SYSTEMATIC field swap
    stays loud without raising: every peer breaches, the metric goes N/A across
    the whole group, and the caveat names how many.
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
        if rejected is not None:
            rejected.append(key)
        return absent
    return f



def _utc_now() -> str:
    """The moment a row was read off the wire, as YYYY-MM-DD HH:MM:SS UTC.

    Recorded at PARSE time rather than at request time because parsing is the
    last point that is per-row: a peer fetch returns hundreds of rows from one
    request, and stamping them all with the request moment would be close
    enough to true never to be questioned and still not be what it says.
    """
    return datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%d %H:%M:%S UTC")

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

    #: Ratio-class fields whose present value the plausibility bound refused.
    #: Collected here and carried onto the profile so a refusal is never
    #: indistinguishable from a field FDIC did not publish.
    rejected = []

    return InstitutionProfile(
        cert=cert,
        retrieved_at=_utc_now(),
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
        tier1_ratio=_coerce_float(row, "RBC1AAJ", absent=None, ratio_class=True,
                                  rejected=rejected),
        # Loan fields are dollar-class (thousands) — not bounded.
        gross_loans=_coerce_float(row, "LNLSGR", absent=None),
        non_current_loans=_coerce_float(row, "NCLNLS", absent=None),
        loan_loss_allowance=_coerce_float(row, "LNATRES", absent=None),
        intangible_amortization=_coerce_float(row, "EAMINTAN", absent=None),
        # FDIC-published ratios. Deliberately NOT ratio_class-bounded — and the
        # reason is NOT that a leverage ratio is confined while these are not.
        # It is not: RBC1AAJ reaches 466,500 over the sweep above. The reason is
        # that the bound is a magnitude heuristic whose calibration was measured
        # for RBC1AAJ only. An efficiency ratio above 150% is ordinary for a bank
        # with thin revenue (FDIC published 104.08% for CERT 34352 at 20250630),
        # and ROE runs arbitrarily negative as equity approaches zero, so the
        # same band would degrade real values on a population it was never fit
        # to. `reported_is_trustworthy` is what guards these instead.
        reported_nim=_coerce_float(row, "NIMY", absent=None),
        reported_roaa=_coerce_float(row, "ROA", absent=None),
        reported_roae=_coerce_float(row, "ROE", absent=None),
        reported_efficiency_ratio=_coerce_float(row, "EEFFR", absent=None),
        implausible_fields=tuple(rejected),
    )
