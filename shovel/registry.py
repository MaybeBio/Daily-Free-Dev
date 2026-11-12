from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from . import util


def normalize_url(url: str) -> str:
    text = str(url or "").strip()
    if not text:
        return ""
    if text.startswith("//"):
        text = "https:" + text
    if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", text):
        text = "https://" + text
    parts = urlsplit(text)
    host = (parts.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    netloc = host
    if parts.port:
        netloc = f"{host}:{parts.port}"
    path = parts.path.rstrip("/") or "/"
    query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if not key.lower().startswith("utm_")
    ]
    scheme = parts.scheme.lower() or "https"
    return urlunsplit((scheme, netloc, path, urlencode(query), ""))


def url_key(url: str) -> str:
    normalized = normalize_url(url)
    if not normalized:
        return ""
    parts = urlsplit(normalized)
    return f"{parts.netloc}{parts.path}" + (f"?{parts.query}" if parts.query else "")


def name_key(name: str) -> str:
    return re.sub(r"[^\w]+", "", str(name or "").lower())


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(value or "").lower()).strip("-")


def make_id(name: str, homepage: str, existing: set[str]) -> str:
    base = slugify(name)
    if not base:
        base = slugify(urlsplit(normalize_url(homepage)).hostname or "")
    if not base:
        base = "resource"
    candidate = base
    index = 2
    while candidate in existing:
        candidate = f"{base}-{index}"
        index += 1
    return candidate


def normalize_resource(item: dict, existing_ids: set[str] | None = None) -> dict:
    existing_ids = existing_ids or set()
    homepage = str(item.get("homepage") or item.get("official_url") or "").strip()
    official_url = str(item.get("official_url") or homepage or "").strip()
    name = str(item.get("name") or "").strip()
    resource_id = str(item.get("id") or "").strip()
    if not resource_id:
        resource_id = make_id(name, homepage, existing_ids)
    access = item.get("access") or {}
    tags = {str(tag) for tag in (item.get("tags") or []) if tag}
    return {
        "id": resource_id,
        "name": name,
        "provider": str(item.get("provider") or name).strip(),
        "kind": str(item.get("kind") or "other"),
        "tags": sorted(tags),
        "free_type": str(item.get("free_type") or "permanent"),
        "limits_text": str(item.get("limits_text") or "").strip(),
        "eligibility": str(item.get("eligibility") or "").strip(),
        "access": {
            "card": str(access.get("card") or "unknown"),
            "phone": str(access.get("phone") or "unknown"),
            "realname": str(access.get("realname") or "unknown"),
        },
        "homepage": homepage,
        "signup_url": str(item.get("signup_url") or "").strip(),
        "official_url": official_url,
        "source_refs": sorted({str(ref) for ref in (item.get("source_refs") or []) if ref}),
        "verified_at": str(item.get("verified_at") or util.today_iso()),
        "notes": str(item.get("notes") or "").strip(),
    }


def _merge_into(target: dict, incoming: dict) -> None:
    for field in ("provider", "limits_text", "eligibility", "homepage", "signup_url", "official_url", "notes"):
        if not target.get(field) and incoming.get(field):
            target[field] = incoming[field]
    if target.get("kind") in ("", "other") and incoming.get("kind") not in ("", "other"):
        target["kind"] = incoming["kind"]
    if not target.get("free_type") and incoming.get("free_type"):
        target["free_type"] = incoming["free_type"]
    for key in ("card", "phone", "realname"):
        current = (target.get("access") or {}).get(key, "unknown")
        value = (incoming.get("access") or {}).get(key, "unknown")
        if current == "unknown" and value != "unknown":
            target.setdefault("access", {})[key] = value
    target["tags"] = sorted(set(target.get("tags") or []) | set(incoming.get("tags") or []))
    target["source_refs"] = sorted(set(target.get("source_refs") or []) | set(incoming.get("source_refs") or []))
    if incoming.get("verified_at") and incoming["verified_at"] > (target.get("verified_at") or ""):
        target["verified_at"] = incoming["verified_at"]


def merge_resources(existing: list[dict], incoming: list[dict]) -> list[dict]:
    result = [normalize_resource(item) for item in existing]
    by_url: dict[str, dict] = {}
    by_name: dict[str, dict] = {}
    by_id: dict[str, dict] = {}
    for resource in result:
        by_id[resource["id"]] = resource
        key = url_key(resource.get("homepage") or resource.get("official_url") or "")
        if key:
            by_url.setdefault(key, resource)
        name = name_key(resource.get("name"))
        if name:
            by_name.setdefault(name, resource)

    for raw in incoming:
        item = normalize_resource(raw, set(by_id))
        target = None
        key = url_key(item.get("homepage") or item.get("official_url") or "")
        if key:
            target = by_url.get(key)
        if target is None and item.get("name"):
            target = by_name.get(name_key(item["name"]))
        if target is None:
            target = by_id.get(item["id"])
        if target is None:
            if item["id"] in by_id:
                item["id"] = make_id(item.get("name") or item["id"], item.get("homepage") or "", set(by_id))
            result.append(item)
            by_id[item["id"]] = item
            if key:
                by_url.setdefault(key, item)
            name = name_key(item.get("name"))
            if name:
                by_name.setdefault(name, item)
        else:
            _merge_into(target, item)
    return result


def build_registry(resources: list[dict], status: dict | None = None) -> dict:
    state = (status or {}).get("resources", {})
    records = []
    for resource in resources:
        entry = dict(resource)
        checked = state.get(resource["id"], {}) if isinstance(state, dict) else {}
        for field in ("status", "http_status", "final_url", "keyword_hit", "checked_at", "streak_gone"):
            if field in checked:
                entry[field] = checked[field]
        if int(checked.get("streak_gone") or 0) >= 3:
            entry["stale"] = True
        records.append(entry)

    def count(field: str) -> dict:
        values: dict[str, int] = {}
        for record in records:
            value = record.get(field) or "unknown"
            values[value] = values.get(value, 0) + 1
        return dict(sorted(values.items()))

    return {
        "schema_version": 1,
        "updated_at": util.now_utc(),
        "resources": records,
        "stats": {
            "resources": len(records),
            "kinds": count("kind"),
            "free_types": count("free_type"),
            "statuses": count("status"),
        },
    }


def canonical_lines(items: list[dict]) -> list[str]:
    lines = []
    for item in items:
        key = url_key(item.get("homepage") or item.get("official_url") or "") or name_key(item.get("name"))
        limits = re.sub(r"\s+", " ", item.get("limits_text") or "")[:300]
        lines.append(
            " | ".join(
                [
                    key,
                    str(item.get("name") or ""),
                    str(item.get("kind") or ""),
                    str(item.get("free_type") or ""),
                    limits,
                ]
            )
        )
    return sorted(set(lines))
