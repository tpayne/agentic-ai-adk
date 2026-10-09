"""Provider catalog pricing with explicit inputs and documented baseline assumptions."""

import json
import logging
import os
import re
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlencode
from urllib.request import Request, urlopen

logger = logging.getLogger("ProcessArchitect.CloudArchPricing")
_TIMEOUT_SECONDS = 5
_PAGE_LIMIT = 5
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


def _get_json(url: str) -> Dict[str, Any]:
    request = Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "ProcessEngineering-FinOps/1.0"},
    )
    with urlopen(request, timeout=_TIMEOUT_SECONDS) as response:
        return json.load(response)


def _detail(text: str, field: str) -> Optional[str]:
    match = re.search(
        rf"(?:^|\s){re.escape(field)}\s*[:=]\s*"
        r"([^;\n|]*?)(?=\s+(?:sku|usage|region|service(?: code| id)?)\s*[:=]|[;\n|]|$)",
        text,
        re.IGNORECASE,
    )
    return match.group(1).strip(" ,") if match else None


def _usages(text: str) -> List[Tuple[float, str]]:
    usages = []
    for item in re.finditer(
        r"(?:^|\s)usage\s*[:=]\s*"
        r"([^;\n|]*?)(?=\s+(?:sku|usage|region|service(?: code| id)?)\s*[:=]|[;\n|]|$)",
        text,
        re.IGNORECASE,
    ):
        raw = item.group(1).strip(" ,")
        monthly = re.search(r"(?:/month|per month|monthly)\s*$", raw, re.IGNORECASE)
        if not monthly:
            continue
        match = re.fullmatch(
            r"\s*([\d,]+(?:\.\d+)?)\s*([a-zA-Z][a-zA-Z0-9 ._-]*)\s*",
            raw[:monthly.start()].strip(),
        )
        if not match:
            continue
        quantity = float(match.group(1).replace(",", ""))
        if quantity >= 0:
            usages.append((quantity, match.group(2).strip()))
    return usages


def _normalize_unit(unit: str) -> str:
    value = unit.lower().strip()
    value = re.sub(r"^\s*1\s+", "", value)
    value = value.replace("per month", "/month").replace("monthly", "/month")
    value = re.sub(r"/month$", "", value)
    for old, new in (
        ("gibibyte", "gib"), ("gigabyte", "gb"), ("mebibyte", "mib"),
        ("megabyte", "mb"), ("tebibyte", "tib"), ("terabyte", "tb"),
        ("requests", "request"), ("operations", "operation"),
        ("hours", "hour"), ("hrs", "hour"), ("hr", "hour"),
    ):
        value = value.replace(old, new)
    return re.sub(r"[\s._-]+", "", value)


def _units_match(catalog_unit: str, usage_unit: str) -> bool:
    rate = _normalize_unit(catalog_unit)
    requested = _normalize_unit(usage_unit)
    if not rate or not requested:
        return False
    if rate == requested:
        return True
    aliases = (
        {"hour", "h"}, {"request", "api call", "call"},
        {"gib", "gibmonth", "gibmo"}, {"gb", "gbmonth", "gbmo"},
        {"mib", "mibmonth", "mibmo"}, {"mb", "mbmonth", "mbmo"},
        {"tib", "tibmonth", "tibmo"}, {"tb", "tbmonth", "tbmo"},
    )
    return any(
        rate in {_normalize_unit(unit) for unit in group}
        and requested in {_normalize_unit(unit) for unit in group}
        for group in aliases
    )


def _record_matches_sku(record: Dict[str, Any], sku: str) -> bool:
    wanted = re.sub(r"[^a-z0-9]+", "", sku.lower())
    fields = (
        "sku",
        "productSku",
        "skuName",
        "armSkuName",
        "meterName",
        "description",
        "productName",
    )
    return any(
        re.sub(r"[^a-z0-9]+", "", str(record.get(field, "")).lower()) == wanted
        for field in fields
    )


def _catalog_price(records: List[Dict[str, Any]], text: str) -> Optional[Dict[str, Any]]:
    sku = _detail(text, "sku")
    usages = _usages(text)
    if not sku or not usages:
        return None
    candidates = [record for record in records if _record_matches_sku(record, sku)]
    rated = []
    used = set()
    for quantity, usage_unit in usages:
        matches = [
            (index, row) for index, row in enumerate(candidates)
            if index not in used and _units_match(
                str(row.get("unit") or row.get("unitOfMeasure") or ""), usage_unit
            )
        ]
        if len(matches) != 1:
            return None
        index, row = matches[0]
        try:
            rate = float(row["rate"])
        except (KeyError, TypeError, ValueError):
            return None
        if rate < 0:
            return None
        used.add(index)
        rated.append((row, quantity, usage_unit, rate))
    return {
        "monthly_cost_usd": round(sum(quantity * rate for _, quantity, _, rate in rated), 2),
        "sku": sku,
        "region": rated[0][0].get("region"),
        "source": ", ".join(sorted({row["source"] for row, _, _, _ in rated if row.get("source")})),
        "usage_meters": [
            {
                "usage_quantity": quantity,
                "usage_unit": usage_unit,
                "catalog_unit": row.get("unit") or row.get("unitOfMeasure"),
                "unit_rate_usd": rate,
            }
            for row, quantity, usage_unit, rate in rated
        ],
        "assumption": "Explicitly stated monthly usage: " + "; ".join(
            f"{quantity:g} {unit}" for _, quantity, unit, _ in rated
        ),
    }


def _default_catalog_price(
    records: List[Dict[str, Any]], text: str, shape_slug: str, region: str
) -> Optional[Dict[str, Any]]:
    """Estimate a representative baseline from an unambiguous catalog match."""
    stop_words = {"aws4", "gcp2", "azure", "sku", "usage", "region", "service"}
    hint_tokens = {
        token for token in re.findall(r"[a-z0-9]+", f"{shape_slug} {text}".lower())
        if token not in stop_words
    }
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for row in records:
        sku = str(row.get("sku") or row.get("productSku") or row.get("skuName") or "")
        if not sku:
            continue
        grouped.setdefault(sku, []).append(row)

    ranked = []
    for sku, rows in grouped.items():
        searchable = " ".join(
            str(row.get(field) or "")
            for row in rows
            for field in ("sku", "skuName", "description", "productName", "serviceName", "service")
        )
        searchable_tokens = set(re.findall(r"[a-z0-9]+", searchable.lower()))
        overlap = len(hint_tokens & searchable_tokens) / max(1, len(hint_tokens))
        score = max(_name_score(shape_slug, searchable), overlap)
        if score >= 0.24:
            ranked.append((score, sku, rows))
    ranked.sort(key=lambda item: (item[0], item[1]))
    if not ranked or (len(ranked) > 1 and ranked[-1][0] - ranked[-2][0] < 0.08):
        return None

    _, sku, rows = ranked[-1]
    for row in rows:
        unit = str(row.get("unit") or row.get("unitOfMeasure") or "")
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
            rate = float(row.get("rate"))
        except (TypeError, ValueError):
            continue
        if rate < 0:
            continue
        return {
            "monthly_cost_usd": round(quantity * rate, 2),
            "sku": sku,
            "region": row.get("region") or region,
            "source": row.get("source"),
            "usage_meters": [{
                "usage_quantity": quantity,
                "usage_unit": unit_name,
                "catalog_unit": unit,
                "unit_rate_usd": rate,
            }],
            "assumption": (
                f"Catalog-grounded baseline assumption: {quantity:g} {unit_name} per month; "
                f"one matching catalog meter only, not a complete bill; region {region}."
            ),
            "pricing_basis": "provider_catalog_baseline",
        }
    return None


def _name_score(hint: str, candidate: str) -> float:
    normalize = lambda value: re.sub(r"[^a-z0-9]+", "", value.lower())
    left, right = normalize(hint), normalize(candidate)
    if not left or not right:
        return 0.0
    if left in right or right in left:
        return 1.0
    return SequenceMatcher(None, left, right).ratio()


def _aws_service_code(hint: str) -> Optional[str]:
    from botocore.session import get_session

    client = get_session().create_client("pricing", region_name="us-east-1")
    services, token = [], None
    for _ in range(_PAGE_LIMIT):
        args = {"FormatVersion": "aws_v1", "MaxResults": 100}
        if token:
            args["NextToken"] = token
        response = client.describe_services(**args)
        services.extend(response.get("Services", []))
        token = response.get("NextToken")
        if not token:
            break
    ranked = []
    for item in services:
        code = str(item.get("ServiceCode", ""))
        spaced = re.sub(r"([a-z])([A-Z])", r"\1 \2", code)
        score = max([_name_score(hint, code), _name_score(hint, spaced)] + [
            _name_score(hint, str(name)) for name in item.get("AttributeNames", [])
        ])
        ranked.append((score, code))
    ranked.sort()
    if not ranked or ranked[-1][0] < 0.82:
        return None
    if len(ranked) > 1 and ranked[-1][0] - ranked[-2][0] < 0.08:
        return None
    return ranked[-1][1]


def _aws_records(service_code: str, region: Optional[str]) -> List[Dict[str, Any]]:
    from botocore.session import get_session

    client = get_session().create_client("pricing", region_name="us-east-1")
    filters = []
    if region:
        filters.append({"Type": "TERM_MATCH", "Field": "regionCode", "Value": region})
    rows, token = [], None
    for _ in range(_PAGE_LIMIT):
        args = {"ServiceCode": service_code, "Filters": filters, "MaxResults": 100}
        if token:
            args["NextToken"] = token
        response = client.get_products(**args)
        for product_text in response.get("PriceList", []):
            product = json.loads(product_text)
            attrs = product.get("product", {}).get("attributes", {})
            description = " ".join(str(value) for value in attrs.values())
            for term in product.get("terms", {}).get("OnDemand", {}).values():
                for dimension in term.get("priceDimensions", {}).values():
                    amount = dimension.get("pricePerUnit", {}).get("USD")
                    if amount is None:
                        continue
                    rows.append({
                        "sku": attrs.get("instanceType") or attrs.get("volumeType")
                        or attrs.get("storageClass") or product.get("product", {}).get("sku"),
                        "productSku": product.get("product", {}).get("sku"),
                        "skuName": attrs.get("instanceType") or attrs.get("volumeType")
                        or attrs.get("storageClass"),
                        "description": description,
                        "unit": dimension.get("unit"),
                        "rate": amount,
                        "region": attrs.get("regionCode") or attrs.get("location"),
                        "source": "AWS Price List API (On-Demand)",
                    })
        token = response.get("NextToken")
        if not token:
            break
    return rows


def _azure_records(sku: Optional[str], region: Optional[str], service: Optional[str]) -> List[Dict[str, Any]]:
    rows, seen = [], set()
    fields = ("armSkuName", "skuName") if sku else (None,)
    for field in fields:
        filters = []
        if sku and field:
            escaped_sku = sku.replace("'", "''")
            filters.append(f"{field} eq '{escaped_sku}'")
        if region:
            escaped_region = region.replace("'", "''")
            filters.append(f"armRegionName eq '{escaped_region}'")
        if service:
            escaped_service = service.replace("'", "''")
            filters.append(f"serviceName eq '{escaped_service}'")
        query = {"api-version": "2023-01-01-preview"}
        if filters:
            query["$filter"] = " and ".join(filters)
        params = urlencode(query)
        url = f"https://prices.azure.com/api/retail/prices?{params}"
        for _ in range(_PAGE_LIMIT):
            payload = _get_json(url)
            for item in payload.get("Items", []):
                if item.get("type", "Consumption") != "Consumption":
                    continue
                identity = (item.get("meterId"), item.get("skuId"), item.get("meterName"),
                            item.get("unitOfMeasure"), item.get("retailPrice"), item.get("armRegionName"))
                if identity in seen:
                    continue
                seen.add(identity)
                rows.append({
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
    return rows


def _azure_service_hint(shape_slug: str) -> str:
    slug = re.sub(r"^azure[._-]+", "", (shape_slug or "").lower())
    return _AZURE_SERVICE_NAMES.get(slug, re.sub(r"[_-]+", " ", slug).title())


def _google_service_id(hint: str, api_key: str) -> Optional[str]:
    rows, token = [], None
    for _ in range(_PAGE_LIMIT):
        params = {"key": api_key, "pageSize": "200"}
        if token:
            params["pageToken"] = token
        payload = _get_json("https://cloudbilling.googleapis.com/v1/services?" + urlencode(params))
        rows.extend(payload.get("services", []))
        token = payload.get("nextPageToken")
        if not token:
            break
    ranked = sorted(
        (_name_score(hint, str(row.get("displayName", ""))), row.get("serviceId"))
        for row in rows
    )
    if not ranked or ranked[-1][0] < 0.82:
        return None
    if len(ranked) > 1 and ranked[-1][0] - ranked[-2][0] < 0.08:
        return None
    return ranked[-1][1]


def _google_unit_price(item: Dict[str, Any]) -> Optional[Tuple[float, str]]:
    infos = item.get("pricingInfo", [])
    infos.sort(key=lambda info: info.get("effectiveTime", ""), reverse=True)
    for info in infos:
        expression = info.get("pricingExpression", {})
        tiers = sorted(
            expression.get("tieredRates", []),
            key=lambda tier: float(tier.get("startUsageAmount", 0)),
        )
        prices = []
        for tier in tiers:
            amount = tier.get("unitPrice", {})
            if amount.get("currencyCode", "USD") != "USD":
                prices = []
                break
            prices.append(float(amount.get("units", 0)) + float(amount.get("nanos", 0)) / 1e9)
        # Tiered prices require a usage-breakdown calculator; refuse to use
        # the first tier as if it applied to all of the stated consumption.
        if prices and all(price == prices[0] for price in prices):
            return prices[0], str(
                expression.get("usageUnitDescription") or expression.get("usageUnit") or ""
            )
    return None


def _google_records(
    service_id: str, region: Optional[str], sku: Optional[str], api_key: str
) -> List[Dict[str, Any]]:
    rows, token = [], None
    for _ in range(_PAGE_LIMIT):
        params = {"key": api_key, "currencyCode": "USD", "pageSize": "5000"}
        if token:
            params["pageToken"] = token
        payload = _get_json(
            f"https://cloudbilling.googleapis.com/v1/services/{service_id}/skus?"
            + urlencode(params)
        )
        for item in payload.get("skus", []):
            if sku and not _record_matches_sku(
                {"sku": item.get("skuId"), "skuName": item.get("description")}, sku
            ):
                continue
            geography = item.get("geoTaxonomy", {})
            regions = {
                str(value).lower()
                for value in (geography.get("regions") or item.get("serviceRegions", []))
            }
            if region and regions and region.lower() not in regions:
                continue
            price = _google_unit_price(item)
            if not price:
                continue
            rows.append({
                "sku": item.get("skuId"),
                "skuName": item.get("description"),
                "description": item.get("description"),
                "unit": price[1],
                "rate": price[0],
                "region": ", ".join(sorted(regions)) if regions else None,
                "source": "Google Cloud Billing Catalog API",
            })
    return rows


def lookup_catalog_resource_price(
    provider: str, shape_slug: str, haystack: str,
    cache: Optional[Dict[Tuple[str, ...], Optional[Dict[str, Any]]]] = None,
    diagnostics: Optional[Dict[str, str]] = None,
) -> Optional[Dict[str, Any]]:
    """Find explicit catalog-priced meters for an AWS, Azure, or GCP resource."""
    sku, usages = _detail(haystack, "sku"), _usages(haystack)
    provider = (provider or "").lower()
    service_hint = (
        _detail(haystack, "service code")
        or _detail(haystack, "service id")
        or _detail(haystack, "service")
        or re.sub(r"[_-]+", " ", shape_slug or "")
    )
    service_code = _detail(haystack, "service code")
    service_id = _detail(haystack, "service id")
    region = _detail(haystack, "region")
    pricing_region = region or ("us-east-1" if "aws" in provider else "eastus" if "azure" in provider else "us-central1")
    usage_key = "|".join(f"{amount:g}:{unit}" for amount, unit in usages)
    key = (provider, sku or "", pricing_region, service_hint, usage_key)
    if cache is not None and key in cache:
        cached = cache[key]
        if cached and "__lookup_failure_reason__" in cached:
            if diagnostics is not None:
                diagnostics["reason"] = str(cached["__lookup_failure_reason__"])
            return None
        if diagnostics is not None and cached is not None:
            diagnostics["reason"] = ""
        return cached
    reason = ""
    try:
        if "azure" in provider:
            service_hint = _detail(haystack, "service") or _azure_service_hint(shape_slug)
            records = _azure_records(sku, pricing_region, service_hint)
        elif "aws" in provider:
            service_code = service_code or _aws_service_code(service_hint)
            records = _aws_records(service_code, pricing_region) if service_code else []
        elif "gcp" in provider:
            api_key = os.environ.get("GOOGLE_CLOUD_BILLING_API_KEY") or os.environ.get("GOOGLE_API_KEY")
            if not api_key:
                reason = "Google Cloud catalog lookup was skipped: set GOOGLE_CLOUD_BILLING_API_KEY or GOOGLE_API_KEY."
                records = []
                service_id = None
            else:
                service_id = service_id or _google_service_id(service_hint, api_key)
                records = _google_records(service_id, pricing_region, sku, api_key) if service_id else []
        else:
            records = []
            reason = f"No provider pricing catalog is configured for provider '{provider or 'unknown'}'."
        if "aws" in provider and not service_code:
            reason = "AWS catalog lookup could not uniquely identify the service; add an explicit service code."
        if "gcp" in provider and api_key and not service_id:
            reason = "Google Cloud catalog lookup could not uniquely identify the service; add an explicit service id."
        result = (
            _catalog_price(records, haystack)
            if sku and usages
            else _default_catalog_price(records, haystack, shape_slug, pricing_region)
        )
        if result is not None and not region:
            result["assumption"] += f" Default region assumed: {pricing_region}."
        if result is None and not reason:
            if sku and usages:
                reason = (
                    "The provider catalog was queried, but no unique USD rate matched the stated SKU "
                    "and every monthly usage meter."
                )
            else:
                reason = (
                    "The provider catalog was queried, but the component name did not resolve to one "
                    "unambiguous billable SKU and supported catalog unit."
                )
    except Exception as exc:
        logger.info("Live %s price lookup unavailable for SKU %s (%s)", provider, sku or shape_slug, type(exc).__name__)
        result = None
        reason = _catalog_failure_reason(provider, exc)
    if cache is not None:
        cache[key] = result if result is not None else {"__lookup_failure_reason__": reason}
    if diagnostics is not None:
        diagnostics["reason"] = reason
    return result


def _catalog_failure_reason(provider: str, exc: Exception) -> str:
    error_type = type(exc).__name__
    if error_type in {"NoCredentialsError", "PartialCredentialsError"}:
        return "AWS catalog request failed: AWS credentials are not configured or are incomplete."
    response = getattr(exc, "response", {})
    code = str(response.get("Error", {}).get("Code", "")) if isinstance(response, dict) else ""
    if code.startswith("AccessDenied") or code in {"UnauthorizedOperation", "UnrecognizedClientException"}:
        return "AWS catalog request was denied; check credentials and pricing:GetProducts/DescribeServices permissions."
    if error_type == "HTTPError":
        status = getattr(exc, "code", None)
        if status in (401, 403):
            return f"{provider} catalog request was unauthorized (HTTP {status}); check API credentials and access."
        return f"{provider} catalog request failed with HTTP {status}."
    if error_type in {"TimeoutError", "URLError", "ConnectionError"}:
        return f"{provider} catalog request could not complete because of a timeout or network connection failure."
    if code:
        return f"{provider} catalog request failed ({code})."
    return f"{provider} catalog request failed ({error_type}); the heuristic estimate was retained."
