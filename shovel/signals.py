from __future__ import annotations

import html
import json
import re
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from pathlib import Path

from . import registry, util

TAG = re.compile(r"<[^>]+>")


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(TAG.sub(" ", str(text or "")))).strip()


def _normalize_date(value: str | None) -> str:
    value = str(value or "").strip()
    if not value:
        return ""
    try:
        return parsedate_to_datetime(value).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (TypeError, ValueError):
        return value


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _parse_xml(body: str) -> list[dict]:
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        return []
    records = []
    for element in root.iter():
        name = _local(element.tag)
        if name not in {"entry", "item"}:
            continue
        title = ""
        link = ""
        published = ""
        summary = ""
        for child in element:
            child_name = _local(child.tag)
            if child_name == "title":
                title = _clean(child.text)
            elif child_name == "link":
                link = child.get("href") or (child.text or "").strip()
            elif child_name in {"updated", "published", "pubDate"} and not published:
                published = _normalize_date(child.text)
            elif child_name in {"summary", "content", "description"} and not summary:
                summary = _clean(child.text)
            elif child_name == "link" and not link:
                link = (child.text or "").strip()
        if title or link:
            records.append(
                {"title": title, "url": link, "published_at": published, "summary": summary}
            )
    return records


def _parse_hn(body: str) -> list[dict]:
    try:
        document = json.loads(body)
    except ValueError:
        return []
    records = []
    for hit in document.get("hits") or []:
        if not isinstance(hit, dict):
            continue
        url = hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID')}"
        records.append(
            {
                "title": _clean(hit.get("title") or hit.get("story_title") or ""),
                "url": url,
                "published_at": _normalize_date(hit.get("created_at")),
                "summary": _clean(hit.get("story_text") or ""),
            }
        )
    return records


def _parse_feed(kind: str, body: str) -> list[dict]:
    if kind == "hn":
        return _parse_hn(body)
    return _parse_xml(body)


def _matches(text: str, keywords: list[str], excludes: list[str]) -> list[str]:
    lowered = text.lower()
    if any(word and word.lower() in lowered for word in excludes):
        return []
    return [word for word in keywords if word.lower() in lowered]


def ingest(
    config: dict,
    timeout: float = 20.0,
    signal_dir: Path | None = None,
    transport=None,
) -> list[dict]:
    signal_dir = signal_dir or util.SIGNAL_DIR
    keywords = [str(word) for word in (config.get("keywords") or []) if word]
    excludes = [str(word) for word in (config.get("exclude") or []) if word]
    limit = int(config.get("max_per_day") or 200)
    fetched_at = util.now_utc()

    collected: list[dict] = []
    for feed in config.get("feeds", []):
        if not feed.get("enabled", True):
            continue
        code, body, _ = util.http_request(
            "GET", feed.get("url", ""), timeout=timeout, transport=transport
        )
        if not code or code >= 400:
            util.log(f"信号 {feed.get('id')}: 失败 HTTP {code}")
            continue
        for record in _parse_feed(feed.get("kind", "rss"), body):
            text = f"{record['title']} {record['summary']}"
            matched = _matches(text, keywords, excludes)
            if not matched:
                continue
            record.update(
                source=feed.get("id", ""),
                fetched_at=fetched_at,
                matched_keywords=matched,
                summary=(record["summary"] or record["title"])[:200],
            )
            collected.append(record)

    path = signal_dir / f"{util.today_iso()}.jsonl"
    merged: dict[str, dict] = {}
    for record in util.read_jsonl(path):
        key = registry.url_key(record.get("url")) or record.get("title", "")
        if key:
            merged.setdefault(key, record)
    for record in collected:
        key = registry.url_key(record.get("url")) or record.get("title", "")
        if key:
            merged.setdefault(key, record)

    records = sorted(
        merged.values(),
        key=lambda item: item.get("published_at") or item.get("fetched_at") or "",
        reverse=True,
    )[:limit]
    text = "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records)
    util.atomic_write(path, text)
    return records
