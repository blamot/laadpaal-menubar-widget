#!/usr/bin/env python3
import argparse
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

import requests
from bs4 import BeautifulSoup


DEFAULT_CACHE_TTL_SECONDS = 60
DEFAULT_TIMEOUT_SECONDS = 12
USER_AGENT = "laadpaal-checker/1.0"


@dataclass
class StatusResult:
    status: str
    raw: Optional[str] = None


@dataclass
class FetchResult:
    statuses: Dict[str, StatusResult]
    summary: Optional[str] = None


def load_config(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def normalize_status(text: str, available_texts, occupied_texts) -> StatusResult:
    lowered = (text or "").strip().lower()
    for entry in available_texts:
        if entry.lower() in lowered:
            return StatusResult("vrij", text)
    for entry in occupied_texts:
        if entry.lower() in lowered:
            return StatusResult("bezet", text)
    return StatusResult("unknown", text)


def read_cache(cache_path: str, ttl_seconds: int) -> Optional[Dict[str, Any]]:
    if not os.path.exists(cache_path):
        return None
    try:
        with open(cache_path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if time.time() - payload.get("timestamp", 0) > ttl_seconds:
            return None
        return payload.get("data")
    except (OSError, json.JSONDecodeError):
        return None


def write_cache(cache_path: str, data: Dict[str, Any]) -> None:
    payload = {"timestamp": time.time(), "data": data}
    with open(cache_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)


def request_json(url: str, headers: Dict[str, str], timeout_seconds: int) -> Any:
    response = None
    for attempt in range(2):
        response = requests.get(url, headers=headers, timeout=timeout_seconds)
        if response.status_code == 200:
            return response.json()
        if attempt == 0:
            time.sleep(1)
    if response is not None:
        raise RuntimeError(
            f"HTTP {response.status_code} bij GET {url}: {response.text[:500]}"
        )
    raise RuntimeError("Geen response ontvangen van endpoint")


def match_poi(poi: Dict[str, Any], site_match: str) -> bool:
    if not site_match:
        return True
    address = poi.get("AddressInfo", {})
    candidates = [
        address.get("Title", ""),
        address.get("AddressLine1", ""),
        address.get("Town", ""),
    ]
    lowered = site_match.lower()
    return any(lowered in (candidate or "").lower() for candidate in candidates)


def match_connection(connection: Dict[str, Any], connector_match: str) -> bool:
    if not connector_match:
        return False
    candidates = [
        str(connection.get("ID", "")),
        str(connection.get("Reference", "")),
        str(connection.get("ConnectionID", "")),
    ]
    lowered = connector_match.lower()
    return any(lowered == candidate.lower() for candidate in candidates)


def status_from_connection(connection: Dict[str, Any]) -> StatusResult:
    status = connection.get("StatusType", {})
    title = str(status.get("Title", ""))
    if re.search(r"available|free", title, re.IGNORECASE):
        return StatusResult("vrij", title)
    if re.search(r"in use|occupied|charging", title, re.IGNORECASE):
        return StatusResult("bezet", title)
    return StatusResult("unknown", title)


def fetch_openchargemap(config: Dict[str, Any]) -> FetchResult:
    source = config["source"]
    api_key = source.get("api_key", "")
    if not api_key:
        raise ValueError("Open Charge Map api_key ontbreekt in config.json")

    params = source.get("params", {})
    base_url = source.get("base_url", "https://api.openchargemap.io/v3/poi/")
    query = "&".join(f"{key}={value}" for key, value in params.items())
    url = f"{base_url}?key={api_key}&{query}"

    headers = {"User-Agent": USER_AGENT}
    data = request_json(
        url,
        headers=headers,
        timeout_seconds=source.get("timeout", DEFAULT_TIMEOUT_SECONDS),
    )

    site_match = source.get("site_match", "")
    connector_map = config.get("connectors", {})
    results = {name: StatusResult("unknown") for name in connector_map}

    for poi in data:
        if not match_poi(poi, site_match):
            continue
        for connection in poi.get("Connections", []) or []:
            for local_name, connector_match in connector_map.items():
                if match_connection(connection, connector_match):
                    results[local_name] = status_from_connection(connection)
    return FetchResult(results)


def fetch_grid_raw(config: Dict[str, Any]) -> Any:
    source = config["source"]
    api_key = source.get("subscription_key", "")
    if not api_key:
        raise ValueError("Grid subscription_key ontbreekt in config.json")

    params = source.get("params", {})
    base_url = source.get(
        "base_url", "https://api.grid.com/Locations/ChargingLocations"
    )
    query = "&".join(f"{key}={value}" for key, value in params.items())
    url = f"{base_url}?{query}" if query else base_url

    headers = {
        "User-Agent": USER_AGENT,
        "Ocp-Apim-Subscription-Key": api_key,
    }
    method = source.get("method", "GET").upper()
    timeout_seconds = source.get("timeout", DEFAULT_TIMEOUT_SECONDS)
    params_in_body = bool(source.get("params_in_body"))

    if method == "POST":
        response = requests.post(
            base_url,
            headers=headers,
            json=params if params_in_body else None,
            params=None if params_in_body else params,
            timeout=timeout_seconds,
        )
        if response.status_code != 200:
            raise RuntimeError(
                f"HTTP {response.status_code} bij POST {base_url}: {response.text[:500]}"
            )
        return response.json()

    return request_json(url, headers=headers, timeout_seconds=timeout_seconds)


def fetch_grid(config: Dict[str, Any]) -> FetchResult:
    source = config["source"]
    data = fetch_grid_raw(config)

    connector_map = config.get("connectors", {})
    results = {name: StatusResult("unknown") for name in connector_map}
    summary = None

    markers = extract_grid_markers(data)
    if markers:
        for marker in markers:
            if not isinstance(marker, dict):
                continue
            marker_id = str(marker.get("id", ""))
            availability = str(marker.get("availability", ""))
            available_count = marker.get("available")
            status_text = availability
            if isinstance(available_count, int):
                status_text = "available" if available_count > 0 else "occupied"
            for local_name, connector_match in connector_map.items():
                if connector_match == marker_id:
                    results[local_name] = normalize_status(
                        status_text,
                        source.get("available_texts", ["available", "free"]),
                        source.get(
                            "occupied_texts", ["occupied", "in use", "charging"]
                        ),
                    )
        return FetchResult(results)

    detail = extract_grid_detail(data)
    if detail:
        location_id = str(detail.get("locationId", ""))
        available = detail.get("available")
        total = detail.get("total")
        overall_status = status_from_counts(available, total)
        if isinstance(available, int) and isinstance(total, int):
            summary = f"{available}/{total} {overall_status.status}"
        for local_name, connector_match in connector_map.items():
            if (
                connector_match in ("location", "overall")
                or connector_match == f"location:{location_id}"
            ):
                results[local_name] = overall_status

        chargers = detail.get("chargers", []) or []
        for charger in chargers:
            if not isinstance(charger, dict):
                continue
            charger_id = str(charger.get("chargerId", ""))
            charger_status = status_from_counts(
                charger.get("available"), charger.get("total")
            )
            for local_name, connector_match in connector_map.items():
                if connector_match == f"charger:{charger_id}":
                    results[local_name] = charger_status
        return FetchResult(results, summary=summary)

    locations = extract_locations(data)
    for location in locations:
        if not isinstance(location, dict):
            continue
        for charger in location.get("chargers", []) or []:
            if not isinstance(charger, dict):
                continue
            for connector in charger.get("connectors", []) or []:
                if not isinstance(connector, dict):
                    continue
                connector_id = str(connector.get("id", ""))
                connector_ref = str(connector.get("reference", ""))
                status_text = str(connector.get("status", ""))
                for local_name, connector_match in connector_map.items():
                    if connector_match in (connector_id, connector_ref):
                        results[local_name] = normalize_status(
                            status_text,
                            source.get("available_texts", ["available", "free"]),
                            source.get(
                                "occupied_texts", ["occupied", "in use", "charging"]
                            ),
                        )
    return FetchResult(results)


def extract_locations(data: Any) -> list:
    if isinstance(data, dict):
        if isinstance(data.get("locations"), list):
            return data["locations"]
        if isinstance(data.get("data"), list):
            return data["data"]
        if isinstance(data.get("result"), list):
            return data["result"]
        return []
    if isinstance(data, list):
        return data
    return []


def extract_grid_detail(data: Any) -> Dict[str, Any]:
    if isinstance(data, dict) and isinstance(data.get("data"), dict):
        return data["data"]
    return {}


def extract_grid_markers(data: Any) -> list:
    if not isinstance(data, dict):
        return []
    locations = data.get("data", {}).get("locations", {})
    markers = locations.get("markers")
    if isinstance(markers, list):
        return markers
    return []


def status_from_counts(available: Any, total: Any) -> StatusResult:
    if isinstance(available, int) and isinstance(total, int):
        if available > 0:
            return StatusResult("vrij", f"{available}/{total}")
        return StatusResult("bezet", f"{available}/{total}")
    return StatusResult("unknown")


def fetch_scrape(config: Dict[str, Any]) -> FetchResult:
    source = config["source"]
    page_url = source.get("page_url")
    if not page_url:
        raise ValueError("page_url ontbreekt in config.json")

    headers = {"User-Agent": USER_AGENT}
    response = requests.get(
        page_url,
        headers=headers,
        timeout=source.get("timeout", DEFAULT_TIMEOUT_SECONDS),
    )
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    available_texts = source.get("available_texts", ["available", "vrij"])
    occupied_texts = source.get("occupied_texts", ["occupied", "bezet", "in use"])

    results = {}
    for local_name, selector in source.get("connector_selectors", {}).items():
        element = soup.select_one(selector)
        text = element.get_text(" ", strip=True) if element else ""
        results[local_name] = normalize_status(text, available_texts, occupied_texts)

    return FetchResult(results)


def format_output(result: FetchResult) -> Dict[str, Any]:
    output = {name: status.status for name, status in result.statuses.items()}
    if result.summary:
        output["summary"] = result.summary
    return output


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check bezet/vrij status voor laadpalen"
    )
    parser.add_argument("--config", default="config.json", help="Path naar config.json")
    parser.add_argument("--no-cache", action="store_true", help="Negeer cache")
    parser.add_argument(
        "--dump-grid",
        action="store_true",
        help="Print ruwe Grid response en stop",
    )
    args = parser.parse_args()

    config_path = os.path.abspath(args.config)
    config = load_config(config_path)

    cache_ttl = config.get("cache_ttl_seconds", DEFAULT_CACHE_TTL_SECONDS)
    cache_path = os.path.join(os.path.dirname(config_path), ".cache.json")

    if args.dump_grid:
        if config.get("source", {}).get("type") != "grid":
            raise ValueError("--dump-grid werkt alleen met source.type 'grid'")
        data = fetch_grid_raw(config)
        print(json.dumps(data, indent=2))
        return 0

    if not args.no_cache:
        cached = read_cache(cache_path, cache_ttl)
        if cached:
            print(json.dumps(cached, indent=2))
            return 0

    source_type = config.get("source", {}).get("type")
    if source_type == "openchargemap":
        results = fetch_openchargemap(config)
    elif source_type == "grid":
        results = fetch_grid(config)
    elif source_type == "scrape":
        results = fetch_scrape(config)
    else:
        raise ValueError("source.type moet 'grid', 'openchargemap' of 'scrape' zijn")

    output = format_output(results)
    write_cache(cache_path, output)
    print(json.dumps(output, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
