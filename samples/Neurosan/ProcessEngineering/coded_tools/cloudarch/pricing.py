"""Live catalog pricing with explicit inputs and documented baseline assumptions.

Catalog prices use a component's exact SKU and monthly usage when provided;
otherwise the provider catalog is tried using an identified service and
representative monthly baseline assumptions.
"""

import json
import logging
import os
import re
from difflib import SequenceMatcher
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlencode
from urllib.request import Request, urlopen

logger = logging.getLogger("ProcessArchitect.CloudArchPricing")

_MONTHLY_HOURS = 730
_HTTP_TIMEOUT_SECONDS = 5
_GOOGLE_COMPUTE_ENGINE_SERVICE_ID = "6F81-5844-456A"
_CATALOG_PAGE_LIMIT = 5
_AZURE_SERVICE_NAMES = {
    "virtual_machines": "Virtual Machines",
    "storage_accounts": "Storage",
    "managed_disks": "Storage",
    "sql_database": "SQL Database",
    "load_balancer": "Load Balancer",
    "application_gateway": "Application Gateway",
    "cdn": "Azure CDN",
    "functions": "Functions",
    "api_management": "API Management",
    "service_bus": "Service Bus",
    "event_hubs": "Event Hubs",
    "key_vault": "Key Vault",
    "monitor": "Azure Monitor",
    "virtual_network": "Virtual Network",
    "nat_gateway": "Virtual Network",
    "firewall": "Azure Firewall",
    "front_door": "Azure Front Door",
    "container_apps": "Azure Container Apps",
    "aks": "Azure Kubernetes Service",
    "app_service": "Azure App Service",
}

_AZURE_REGIONS = {
    "eastus": ("eastus", "east us"),
    "eastus2": ("eastus2", "east us 2"),
    "westus": ("westus", "west us"),
    "westus2": ("westus2", "west us 2"),
    "westus3": ("westus3", "west us 3"),
    "centralus": ("centralus", "central us"),
    "northcentralus": ("northcentralus", "north central us"),
    "southcentralus": ("southcentralus", "south central us"),
    "westcentralus": ("westcentralus", "west central us"),
    "westeurope": ("westeurope", "west europe"),
    "northeurope": ("northeurope", "north europe"),
    "uksouth": ("uksouth", "uk south"),
    "southeastasia": ("southeastasia", "southeast asia"),
    "japaneast": ("japaneast", "japan east"),
    "australiaeast": ("australiaeast", "australia east"),
    "canadacentral": ("canadacentral", "canada central"),
    "brazilsouth": ("brazilsouth", "brazil south"),
    "koreacentral": ("koreacentral", "korea central"),
    "southafricanorth": ("southafricanorth", "south africa north"),
    "uaenorth": ("uaenorth", "uae north"),
    "swedencentral": ("swedencentral", "sweden central"),
}

_GCP_MEMORY_GIB_PER_VCPU = {
    ("e2", "standard"): 4.0,
    ("e2", "highcpu"): 1.0,
    ("e2", "highmem"): 8.0,
    ("n1", "standard"): 3.75,
    ("n1", "highcpu"): 0.9,
    ("n1", "highmem"): 6.5,
    ("n2", "standard"): 4.0,
    ("n2", "highcpu"): 1.0,
    ("n2", "highmem"): 8.0,
    ("n2d", "standard"): 4.0,
    ("n2d", "highcpu"): 1.0,
    ("n2d", "highmem"): 8.0,
    ("c2", "standard"): 4.0,
    ("c2", "highcpu"): 2.0,
    ("c2d", "standard"): 4.0,
    ("c2d", "highcpu"): 2.0,
    ("c3", "standard"): 4.0,
    ("c3", "highcpu"): 2.0,
    ("c3", "highmem"): 8.0,
    ("t2d", "standard"): 4.0,
    ("t2d", "highcpu"): 1.0,
}


def _find_sku_and_region(
    provider: str, haystack: str
) -> Tuple[Optional[str], Optional[str]]:
    """Find a supported explicit VM SKU and region in component text."""
    provider = (provider or "").lower()
    if "aws" in provider:
        sku_match = re.search(
            r"\b[a-z][0-9][a-z]?\.(?:nano|micro|small|medium|large|xlarge|[0-9]+xlarge)\b",
            haystack,
            re.IGNORECASE,
        )
        region_match = re.search(r"\b[a-z]{2}(?:-gov)?-[a-z]+-\d+\b", haystack, re.IGNORECASE)
        return (
            sku_match.group(0).lower() if sku_match else None,
            region_match.group(0).lower() if region_match else None,
        )

    if "azure" in provider:
        sku_match = re.search(r"\bStandard_[A-Za-z0-9]+(?:_[A-Za-z0-9]+)*\b", haystack, re.IGNORECASE)
        region = None
        lowered = haystack.lower().replace("-", " ")
        for region_code, names in _AZURE_REGIONS.items():
            if any(re.search(rf"\b{re.escape(name)}\b", lowered) for name in names):
                region = region_code
                break
        return (sku_match.group(0) if sku_match else None, region)

    if "gcp" in provider:
        sku_match = re.search(
            r"\b(?:e2|n1|n2d?|c2d?|c3|t2d)-(?:standard|highcpu|highmem)-\d+\b",
            haystack,
            re.IGNORECASE,
        )
        region_match = re.search(
            r"\b(?:us|northamerica|southamerica|europe|asia|australia|africa|me)-[a-z]+[0-9]\b",
            haystack,
            re.IGNORECASE,
        )
        return (
            sku_match.group(0).lower() if sku_match else None,
            region_match.group(0).lower() if region_match else None,
        )
    return None, None


def _get_json(url: str) -> Dict[str, Any]:
    request = Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "ProcessEngineering-FinOps/1.0"},
    )
    with urlopen(request, timeout=_HTTP_TIMEOUT_SECONDS) as response:
        return json.load(response)


def _explicit_detail(haystack: str, field: str) -> Optional[str]:
    match = re.search(
        rf"(?:^|\s){re.escape(field)}\s*[:=]\s*([^;\n|]+)",
        haystack,
        re.IGNORECASE,
    )
    return match.group(1).strip(" ,") if match else None


def _explicit_usages(haystack: str) -> list[Tuple[float, str]]:
    usages = []
    for item in re.finditer(
        r"(?:^|\s)usage\s*[:=]\s*([^;\n|]+)",
        haystack,
        re.IGNORECASE,
    ):
        raw = item.group(1).strip(" ,")
        monthly = re.search(r"(?:/month|per month|monthly)\s*$", raw, re.IGNORECASE)
        if not monthly:
            continue
        raw = raw[:monthly.start()].strip()
        match = re.fullmatch(r"\s*([\d,]+(?:\.\d+)?)\s*([a-zA-Z][a-zA-Z0-9 ._-]*)\s*", raw)
        if not match:
            continue
        try:
            quantity = float(match.group(1).replace(",", ""))
            if quantity >= 0:
                usages.append((quantity, match.group(2).strip()))
        except ValueError:
            continue
    return usages


def _normalize_unit(unit: str) -> str:
    value = unit.lower().strip()
    value = re.sub(r"^\s*1\s+", "", value)
    value = value.replace("per month", "/month").replace("monthly", "/month")
    if value.endswith("/month"):
        value = value[:-6]
    value = value.replace("gibibyte", "gib").replace("gigabyte", "gb")
    value = value.replace("terabyte", "tb").replace("megabyte", "mb")
    value = value.replace("requests", "request").replace("operations", "operation")
    value = value.replace("hours", "hour").replace("hrs", "hour").replace("hr", "hour")
    value = value.replace("months", "month").replace("mos", "month")
    value = re.sub(r"[\s._-]+", "", value)
    return value


def _matching_quantity(catalog_unit: str, usage_unit: str) -> bool:
    rate_unit = _normalize_unit(catalog_unit)
    requested_unit = _normalize_unit(usage_unit)
    if not rate_unit or not requested_unit:
        return False
    if rate_unit == requested_unit:
        return True
    # Catalogs express similar units differently. Only accept well-known
    # aliases; never convert unlike dimensions or magnitudes.
    aliases = {
        "hour": {"hour", "h", "hr"},
        "request": {"request", "api call", "call"},
        "gib": {"gib", "gibibyte", "gibmonth", "gibmo"},
        "gb": {"gb", "gigabyte", "gbmonth", "gbmo"},
        "mib": {"mib", "mebibyte", "mibmonth", "mibmo"},
        "mb": {"mb", "megabyte", "mbmonth", "mbmo"},
        "tib": {"tib", "tebibyte", "tibmonth", "tibmo"},
        "tb": {"tb", "terabyte", "tbmonth", "tbmo"},
    }
    return any(
        rate_unit in {_normalize_unit(value) for value in equivalents}
        and requested_unit in {_normalize_unit(value) for value in equivalents}
        for equivalents in aliases.values()
    )


def _explicit_sku(haystack: str, provider: str) -> Optional[str]:
    explicit = _explicit_detail(haystack, "sku")
    if explicit:
        return explicit
    sku, _ = _find_sku_and_region(provider, haystack)
    return sku


def _record_matches_sku(record: Dict[str, Any], sku_hint: Optional[str]) -> bool:
    if not sku_hint:
        return False
    fields = (
        record.get("sku"),
        record.get("skuName"),
        record.get("armSkuName"),
        record.get("meterName"),
        record.get("description"),
        record.get("productName"),
    )
    wanted = re.sub(r"[^a-z0-9]+", "", sku_hint.lower())
    return any(
        re.sub(r"[^a-z0-9]+", "", str(value).lower()) == wanted
        for value in fields
        if value
    )


def _catalog_unit_price(records: list[Dict[str, Any]], haystack: str) -> Optional[Dict[str, Any]]:
    """Price all explicitly declared meters, rejecting ambiguous/incomplete matches."""
    usages = _explicit_usages(haystack)
    sku_hint = _explicit_detail(haystack, "sku")
    if not sku_hint or not usages:
        return None
    candidates = [record for record in records if _record_matches_sku(record, sku_hint)]
    if not candidates:
        return None

    rated = []
    used_records = set()
    for quantity, usage_unit in usages:
        matches = [
            (index, record)
            for index, record in enumerate(candidates)
            if index not in used_records
            and _matching_quantity(
                str(record.get("unit") or record.get("unitOfMeasure") or ""),
                usage_unit,
            )
        ]
        if len(matches) != 1:
            return None
        index, record = matches[0]
        try:
            rate = float(record.get("rate"))
        except (TypeError, ValueError):
            return None
        if rate < 0:
            return None
        used_records.add(index)
        rated.append((record, quantity, usage_unit, rate))

    total = sum(quantity * rate for _, quantity, _, rate in rated)
    record = rated[0][0]
    return {
        "monthly_cost_usd": round(total, 2),
        "usage_meters": [
            {
                "unit_rate_usd": rate,
                "usage_quantity": quantity,
                "usage_unit": usage_unit,
                "catalog_unit": meter.get("unit") or meter.get("unitOfMeasure"),
            }
            for meter, quantity, usage_unit, rate in rated
        ],
        "sku": sku_hint,
        "region": record.get("region"),
        "source": ", ".join(sorted({str(meter.get("source")) for meter, _, _, _ in rated if meter.get("source")})),
        "assumption": "Explicitly stated monthly usage: " + "; ".join(
            f"{quantity:g} {usage_unit}" for _, quantity, usage_unit, _ in rated
        ),
    }


def _default_catalog_unit_price(
    records: list[Dict[str, Any]], haystack: str, shape_slug: str, region: str
) -> Optional[Dict[str, Any]]:
    """Choose an unambiguous catalog product and apply a visible baseline usage."""
    stop_words = {"aws4", "gcp2", "azure", "sku", "usage", "region", "service"}
    hint_tokens = {
        token for token in re.findall(r"[a-z0-9]+", f"{shape_slug} {haystack}".lower())
        if token not in stop_words
    }
    grouped: Dict[str, list[Dict[str, Any]]] = {}
    for record in records:
        sku = str(record.get("sku") or record.get("productSku") or record.get("skuName") or "")
        if sku:
            grouped.setdefault(sku, []).append(record)

    ranked = []
    for sku, rows in grouped.items():
        description = " ".join(
            str(row.get(field) or "")
            for row in rows
            for field in ("sku", "productSku", "skuName", "description", "productName", "serviceName")
        )
        description_tokens = set(re.findall(r"[a-z0-9]+", description.lower()))
        overlap = len(hint_tokens & description_tokens) / max(1, len(hint_tokens))
        score = max(_name_score(shape_slug, description), overlap)
        if score >= 0.24:
            ranked.append((score, sku, rows))
    ranked.sort(key=lambda item: (item[0], item[1]))
    if not ranked or (len(ranked) > 1 and ranked[-1][0] - ranked[-2][0] < 0.08):
        return None

    _, sku, rows = ranked[-1]
    for record in rows:
        unit = str(record.get("unit") or record.get("unitOfMeasure") or "")
        normalized = _normalize_unit(unit)
        if normalized in {"hour", "hours", "h", "hr", "hrs"}:
            quantity, unit_name = 730.0, "hours"
        elif normalized in {"request", "requests", "apicall", "apicalls", "call", "calls"}:
            quantity, unit_name = 1_000_000.0, "requests"
        elif normalized in {
            "gib", "gibmonth", "gibmo", "gb", "gbmonth", "gbmo",
            "mib", "mibmonth", "mibmo", "mb", "mbmonth", "mbmo",
            "tib", "tibmonth", "tibmo", "tb", "tbmonth", "tbmo",
        }:
            quantity, unit_name = 100.0, unit
        elif normalized in {"month", "mo"}:
            quantity, unit_name = 1.0, "month"
        else:
            continue
        try:
            rate = float(record.get("rate"))
        except (TypeError, ValueError):
            continue
        if rate < 0:
            continue
        return {
            "monthly_cost_usd": round(quantity * rate, 2),
            "unit_rate_usd": rate,
            "usage_quantity": quantity,
            "usage_unit": unit_name,
            "usage_meters": [{
                "unit_rate_usd": rate,
                "usage_quantity": quantity,
                "usage_unit": unit_name,
                "catalog_unit": unit,
            }],
            "sku": sku,
            "region": record.get("region") or region,
            "source": record.get("source"),
            "assumption": (
                f"Catalog-grounded baseline assumption: {quantity:g} {unit_name} per month; "
                f"one matching catalog meter only, not a complete bill; region {region}."
            ),
            "pricing_basis": "provider_catalog_baseline",
        }
    return None


def _service_hint(haystack: str, shape_slug: str) -> str:
    explicit = (
        _explicit_detail(haystack, "service code")
        or _explicit_detail(haystack, "service id")
        or _explicit_detail(haystack, "service")
    )
    if explicit:
        return explicit
    return re.sub(r"[_-]+", " ", shape_slug or "").strip()


def _name_score(hint: str, candidate: str) -> float:
    hint_normalized = re.sub(r"[^a-z0-9]+", "", hint.lower())
    candidate_normalized = re.sub(r"[^a-z0-9]+", "", candidate.lower())
    if not hint_normalized or not candidate_normalized:
        return 0.0
    if hint_normalized in candidate_normalized or candidate_normalized in hint_normalized:
        return 1.0
    return SequenceMatcher(None, hint_normalized, candidate_normalized).ratio()


def _aws_service_code(hint: str) -> Optional[str]:
    from botocore.session import get_session

    client = get_session().create_client("pricing", region_name="us-east-1")
    services = []
    token = None
    for _ in range(_CATALOG_PAGE_LIMIT):
        arguments: Dict[str, Any] = {"FormatVersion": "aws_v1", "MaxResults": 100}
        if token:
            arguments["NextToken"] = token
        response = client.describe_services(**arguments)
        services.extend(response.get("Services", []))
        token = response.get("NextToken")
        if not token:
            break
    ranked = []
    for service in services:
        service_code = str(service.get("ServiceCode", ""))
        code_parts = re.sub(r"([a-z])([A-Z])", r"\1 \2", service_code)
        candidates = [service_code, code_parts]
        candidates.extend(str(value) for value in service.get("AttributeNames", []))
        ranked.append((max(_name_score(hint, candidate) for candidate in candidates), service_code))
    ranked.sort()
    if not ranked or ranked[-1][0] < 0.82:
        return None
    if len(ranked) > 1 and ranked[-1][0] - ranked[-2][0] < 0.08:
        return None
    return ranked[-1][1]


def _aws_catalog_records(
    service_code: str, region: Optional[str], sku_hint: Optional[str]
) -> list[Dict[str, Any]]:
    from botocore.session import get_session

    client = get_session().create_client("pricing", region_name="us-east-1")
    filters = []
    if region:
        filters.append({"Type": "TERM_MATCH", "Field": "regionCode", "Value": region})
    records = []
    token = None
    for _ in range(_CATALOG_PAGE_LIMIT):
        arguments: Dict[str, Any] = {
            "ServiceCode": service_code,
            "Filters": filters,
            "MaxResults": 100,
        }
        if token:
            arguments["NextToken"] = token
        response = client.get_products(**arguments)
        for product_text in response.get("PriceList", []):
            product = json.loads(product_text)
            attributes = product.get("product", {}).get("attributes", {})
            product_sku = product.get("product", {}).get("sku")
            description = " ".join(str(value) for value in attributes.values())
            for term in product.get("terms", {}).get("OnDemand", {}).values():
                for dimension in term.get("priceDimensions", {}).values():
                    records.append({
                        "sku": product_sku,
                        "skuName": attributes.get("instanceType")
                        or attributes.get("volumeType")
                        or attributes.get("storageClass"),
                        "description": description,
                        "unit": dimension.get("unit"),
                        "rate": dimension.get("pricePerUnit", {}).get("USD"),
                        "region": attributes.get("regionCode") or attributes.get("location"),
                        "source": "AWS Price List API (On-Demand)",
                    })
        token = response.get("NextToken")
        if not token:
            break
    return [
        record for record in records
        if not sku_hint or _record_matches_sku(record, sku_hint)
    ]


def _azure_catalog_records(
    sku_hint: Optional[str], region: Optional[str], service_hint: Optional[str]
) -> list[Dict[str, Any]]:
    records = []
    seen = set()
    escaped_sku = sku_hint.replace("'", "''") if sku_hint else None
    escaped_region = region.replace("'", "''") if region else None
    escaped_service = service_hint.replace("'", "''") if service_hint else None
    for sku_field in (("armSkuName", "skuName") if sku_hint else (None,)):
        filters = [f"{sku_field} eq '{escaped_sku}'"] if sku_field and escaped_sku else []
        if escaped_region:
            filters.append(f"armRegionName eq '{escaped_region}'")
        if escaped_service:
            filters.append(f"serviceName eq '{escaped_service}'")
        params = urlencode({
            "api-version": "2023-01-01-preview",
            "$filter": " and ".join(filters),
        })
        url = f"https://prices.azure.com/api/retail/prices?{params}"
        for _ in range(_CATALOG_PAGE_LIMIT):
            payload = _get_json(url)
            for item in payload.get("Items", []):
                if item.get("type", "Consumption") != "Consumption":
                    continue
                identity = (
                    item.get("meterId"),
                    item.get("productId"),
                    item.get("skuId"),
                    item.get("meterName"),
                    item.get("serviceName"),
                    item.get("unitOfMeasure"),
                    item.get("retailPrice"),
                    item.get("armRegionName"),
                )
                if identity in seen:
                    continue
                seen.add(identity)
                records.append({
                    **item,
                    "sku": item.get("armSkuName") or item.get("skuName"),
                    "unit": item.get("unitOfMeasure"),
                    "rate": item.get("retailPrice", item.get("unitPrice")),
                    "region": item.get("armRegionName") or item.get("location"),
                    "source": "Azure Retail Prices API",
                })
            url = payload.get("NextPageLink")
            if not url:
                break
    return records


def _google_service_id(hint: str, api_key: str) -> Optional[str]:
    page_token = None
    services = []
    for _ in range(_CATALOG_PAGE_LIMIT):
        params = {"key": api_key, "pageSize": "200"}
        if page_token:
            params["pageToken"] = page_token
        payload = _get_json(
            "https://cloudbilling.googleapis.com/v1/services?" + urlencode(params)
        )
        services.extend(payload.get("services", []))
        page_token = payload.get("nextPageToken")
        if not page_token:
            break
    ranked = sorted(
        (_name_score(hint, str(service.get("displayName", ""))), service.get("serviceId"))
        for service in services
    )
    if not ranked or ranked[-1][0] < 0.82:
        return None
    if len(ranked) > 1 and ranked[-1][0] - ranked[-2][0] < 0.08:
        return None
    return ranked[-1][1]


def _google_catalog_records(
    service_id: str, region: Optional[str], sku_hint: Optional[str], api_key: str
) -> list[Dict[str, Any]]:
    page_token = None
    records = []
    for _ in range(_CATALOG_PAGE_LIMIT):
        params = {"key": api_key, "currencyCode": "USD", "pageSize": "5000"}
        if page_token:
            params["pageToken"] = page_token
        payload = _get_json(
            f"https://cloudbilling.googleapis.com/v1/services/{service_id}/skus?"
            + urlencode(params)
        )
        for item in payload.get("skus", []):
            taxonomy = item.get("geoTaxonomy", {})
            regions = {
                str(value).lower()
                for value in (taxonomy.get("regions") or item.get("serviceRegions", []))
            }
            if region and regions and region.lower() not in regions:
                continue
            pricing_infos = item.get("pricingInfo", [])
            if not pricing_infos:
                continue
            info = sorted(
                pricing_infos,
                key=lambda value: value.get("effectiveTime", ""),
                reverse=True,
            )[0]
            expression = info.get("pricingExpression", {})
            unit_price = _google_unit_price(item)
            records.append({
                "sku": item.get("skuId"),
                "skuName": item.get("description"),
                "description": item.get("description"),
                "unit": unit_price[1] if unit_price else (
                    expression.get("usageUnitDescription") or expression.get("usageUnit")
                ),
                "rate": unit_price[0] if unit_price else None,
                "region": ", ".join(sorted(regions)) if regions else None,
                "source": "Google Cloud Billing Catalog API",
            })
    return [
        record for record in records
        if not sku_hint or _record_matches_sku(record, sku_hint)
    ]


def _azure_service_hint(shape_slug: str) -> str:
    slug = re.sub(r"^azure[._-]+", "", (shape_slug or "").lower())
    return _AZURE_SERVICE_NAMES.get(slug, re.sub(r"[_-]+", " ", slug).title())


def lookup_catalog_resource_price(
    shape_provider: str,
    shape_slug: str,
    haystack: str,
    cache: Optional[Dict[Tuple[str, ...], Optional[Dict[str, Any]]]] = None,
) -> Optional[Dict[str, Any]]:
    """Use catalog prices for explicit details, or try a default catalog baseline."""
    provider = (shape_provider or "").lower()
    sku_hint = _explicit_detail(haystack, "sku")
    usages = _explicit_usages(haystack)
    explicit_details = bool(sku_hint and usages)
    region = _explicit_detail(haystack, "region") or _find_sku_and_region(provider, haystack)[1]
    pricing_region = region or (
        "us-east-1" if "aws" in provider else "eastus" if "azure" in provider else "us-central1"
    )
    service_hint = _service_hint(haystack, shape_slug)
    windows = "windows" in haystack.lower()
    usage_key = "|".join(f"{quantity:g}:{unit}" for quantity, unit in usages)
    cache_key = (provider, sku_hint or "", pricing_region, windows, service_hint, usage_key)
    if cache is not None and cache_key in cache:
        return cache[cache_key]

    try:
        if "azure" in provider:
            service_hint = _explicit_detail(haystack, "service") or _azure_service_hint(shape_slug)
            records = _azure_catalog_records(sku_hint, pricing_region, service_hint)
        elif "aws" in provider:
            explicit_code = _explicit_detail(haystack, "service code")
            service_code = explicit_code or _aws_service_code(service_hint)
            if not service_code:
                return None
            records = _aws_catalog_records(service_code, pricing_region, sku_hint)
        elif "gcp" in provider:
            api_key = os.environ.get("GOOGLE_CLOUD_BILLING_API_KEY") or os.environ.get("GOOGLE_API_KEY")
            if not api_key:
                return None
            explicit_id = _explicit_detail(haystack, "service id")
            service_id = explicit_id or _google_service_id(service_hint, api_key)
            if not service_id:
                return None
            records = _google_catalog_records(service_id, pricing_region, sku_hint, api_key)
        else:
            return None
        result = (
            _catalog_unit_price(records, haystack)
            if explicit_details
            else _default_catalog_unit_price(records, haystack, shape_slug, pricing_region)
        )
        if result is not None and not region:
            result["assumption"] += f" Default region assumed: {pricing_region}."
    except Exception as exc:
        logger.info(
            "Live %s catalog lookup unavailable for SKU %s (%s)",
            provider,
            sku_hint or shape_slug,
            type(exc).__name__,
        )
        result = None
    if cache is not None:
        cache[cache_key] = result
    return result


def _azure_hourly_price(sku: str, region: str, windows: bool) -> Optional[float]:
    filters = (
        f"serviceName eq 'Virtual Machines' and armRegionName eq '{region}' "
        f"and armSkuName eq '{sku}'"
    )
    params = urlencode({"api-version": "2023-01-01-preview", "$filter": filters})
    payload = _get_json(f"https://prices.azure.com/api/retail/prices?{params}")
    items = payload.get("Items", [])

    def operating_system_matches(item: Dict[str, Any]) -> bool:
        description = " ".join(
            str(item.get(field, "")) for field in ("productName", "skuName", "meterName")
        ).lower()
        is_windows = "windows" in description
        return is_windows == windows

    candidates = [
        item for item in items
        if item.get("type", "Consumption") == "Consumption"
        and operating_system_matches(item)
        and "hour" in str(item.get("unitOfMeasure", "")).lower()
        and not any(
            token in " ".join(
                str(item.get(field, "")) for field in ("skuName", "meterName")
            ).lower()
            for token in ("spot", "low priority")
        )
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda item: item.get("effectiveStartDate", ""), reverse=True)
    try:
        price = candidates[0].get("retailPrice")
        if price is None:
            price = candidates[0]["unitPrice"]
        return float(price)
    except (KeyError, TypeError, ValueError):
        return None


def _aws_hourly_price(sku: str, region: str, windows: bool) -> Optional[float]:
    from botocore.session import get_session

    client = get_session().create_client("pricing", region_name="us-east-1")
    response = client.get_products(
        ServiceCode="AmazonEC2",
        Filters=[
            {"Type": "TERM_MATCH", "Field": "regionCode", "Value": region},
            {"Type": "TERM_MATCH", "Field": "instanceType", "Value": sku},
            {"Type": "TERM_MATCH", "Field": "operatingSystem", "Value": "Windows" if windows else "Linux"},
            {"Type": "TERM_MATCH", "Field": "tenancy", "Value": "Shared"},
            {"Type": "TERM_MATCH", "Field": "preInstalledSw", "Value": "NA"},
            {"Type": "TERM_MATCH", "Field": "capacitystatus", "Value": "Used"},
            {"Type": "TERM_MATCH", "Field": "productFamily", "Value": "Compute Instance"},
        ],
        MaxResults=100,
    )
    for product_text in response.get("PriceList", []):
        product = json.loads(product_text)
        for term in product.get("terms", {}).get("OnDemand", {}).values():
            for dimension in term.get("priceDimensions", {}).values():
                if dimension.get("unit", "").lower() not in {"hrs", "hour", "hours"}:
                    continue
                value = dimension.get("pricePerUnit", {}).get("USD")
                try:
                    return float(value)
                except (TypeError, ValueError):
                    continue
    return None


def _google_unit_hourly_rate(sku: Dict[str, Any]) -> Optional[float]:
    pricing_infos = sku.get("pricingInfo", [])
    if not pricing_infos:
        return None
    current = [
        item for item in pricing_infos
        if item.get("effectiveTime", "") <= datetime.now(timezone.utc).isoformat()
    ]
    if not current:
        current = pricing_infos
    current.sort(key=lambda item: item.get("effectiveTime", ""), reverse=True)
    for info in current:
        expression = info.get("pricingExpression", {})
        unit = " ".join(
            str(expression.get(field, "")) for field in ("usageUnit", "usageUnitDescription")
        ).lower()
        if not any(token in unit for token in ("hour", "hours", " h", "h ")):
            continue
        rates = expression.get("tieredRates", [])
        rates.sort(key=lambda rate: float(rate.get("startUsageAmount", 0)))
        for rate in rates:
            price = rate.get("unitPrice", {})
            try:
                if price.get("currencyCode", "USD") != "USD":
                    continue
                return float(price.get("units", 0)) + float(price.get("nanos", 0)) / 1_000_000_000
            except (TypeError, ValueError):
                continue
    return None


def _google_unit_price(sku: Dict[str, Any]) -> Optional[Tuple[float, str]]:
    pricing_infos = sku.get("pricingInfo", [])
    current = [
        item for item in pricing_infos
        if item.get("effectiveTime", "") <= datetime.now(timezone.utc).isoformat()
    ]
    if not current:
        current = pricing_infos
    current.sort(key=lambda item: item.get("effectiveTime", ""), reverse=True)
    for info in current:
        expression = info.get("pricingExpression", {})
        unit = str(
            expression.get("usageUnitDescription")
            or expression.get("usageUnit")
            or ""
        )
        rates = expression.get("tieredRates", [])
        if not rates:
            continue
        try:
            tiers = sorted(rates, key=lambda rate: float(rate.get("startUsageAmount", 0)))
            tier_prices = []
            for tier in tiers:
                price = tier.get("unitPrice", {})
                if price.get("currencyCode", "USD") != "USD":
                    tier_prices = []
                    break
                tier_prices.append(
                    float(price.get("units", 0))
                    + float(price.get("nanos", 0)) / 1_000_000_000
                )
            # This generic adapter has no tiered-usage calculator. Do not
            # present the first tier as the rate for all monthly usage.
            if not tier_prices or any(price != tier_prices[0] for price in tier_prices[1:]):
                continue
            return tier_prices[0], unit
        except (TypeError, ValueError):
            continue
    return None


def _google_compute_hourly_price(sku: str, region: str, api_key: str) -> Optional[float]:
    machine = re.fullmatch(r"([a-z0-9]+)-(standard|highcpu|highmem)-(\d+)", sku)
    if not machine:
        return None
    family, machine_class, vcpus_text = machine.groups()
    memory_per_vcpu = _GCP_MEMORY_GIB_PER_VCPU.get((family, machine_class))
    if memory_per_vcpu is None:
        return None

    page_token = None
    core_rate = ram_rate = None
    for _ in range(10):
        params = {"key": api_key, "currencyCode": "USD", "pageSize": "5000"}
        if page_token:
            params["pageToken"] = page_token
        url = (
            f"https://cloudbilling.googleapis.com/v1/services/"
            f"{_GOOGLE_COMPUTE_ENGINE_SERVICE_ID}/skus?{urlencode(params)}"
        )
        payload = _get_json(url)
        for item in payload.get("skus", []):
            taxonomy = item.get("geoTaxonomy", {})
            regions = {
                str(value).lower()
                for value in (taxonomy.get("regions") or item.get("serviceRegions", []))
            }
            if region not in regions:
                continue
            description = str(item.get("description", "")).lower()
            instance_label = (
                rf"\b{re.escape(family)} (?:predefined )?instance\b"
            )
            if not re.search(instance_label, description):
                continue
            if "instance core" in description:
                core_rate = _google_unit_hourly_rate(item)
            elif "instance ram" in description or "instance memory" in description:
                ram_rate = _google_unit_hourly_rate(item)
        if core_rate is not None and ram_rate is not None:
            return core_rate * int(vcpus_text) + ram_rate * int(vcpus_text) * memory_per_vcpu
        page_token = payload.get("nextPageToken")
        if not page_token:
            break
    return None


def lookup_compute_price(
    shape_provider: str,
    haystack: str,
    cache: Optional[Dict[Tuple[str, ...], Optional[Dict[str, Any]]]] = None,
) -> Optional[Dict[str, Any]]:
    """Return a monthly on-demand catalog estimate, or None for fallback."""
    provider = (shape_provider or "").lower()
    sku, region = _find_sku_and_region(provider, haystack)
    if not sku or not region:
        return None
    windows = "windows" in haystack.lower()
    cache_key = (provider, sku, region, windows)
    if cache is not None and cache_key in cache:
        return cache[cache_key]
    try:
        if "aws" in provider:
            hourly = _aws_hourly_price(sku, region, windows)
            source = "AWS Price List API (On-Demand)"
        elif "azure" in provider:
            hourly = _azure_hourly_price(sku, region, windows)
            source = "Azure Retail Prices API"
        elif "gcp" in provider:
            api_key = os.environ.get("GOOGLE_CLOUD_BILLING_API_KEY") or os.environ.get("GOOGLE_API_KEY")
            if not api_key:
                return None
            hourly = _google_compute_hourly_price(sku, region, api_key)
            source = "Google Cloud Billing Catalog API"
        else:
            return None
    except Exception as exc:
        logger.info(
            "Live %s price lookup unavailable for %s in %s (%s)",
            provider,
            sku,
            region,
            type(exc).__name__,
        )
        if cache is not None:
            cache[cache_key] = None
        return None

    if hourly is None or hourly < 0:
        if cache is not None:
            cache[cache_key] = None
        return None
    result = {
        "monthly_cost_usd": round(hourly * _MONTHLY_HOURS, 2),
        "hourly_rate_usd": round(hourly, 8),
        "sku": sku,
        "region": region,
        "source": source,
        "assumption": (
            f"One VM; {'Windows' if windows else 'Linux'} on-demand; "
            "730 operating hours per month"
        ),
    }
    if cache is not None:
        cache[cache_key] = result
    return result
