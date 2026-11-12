from __future__ import annotations

import os
import time
from pathlib import Path

from . import adapters, diff, registry as registry_mod, util


def _fetch(url: str, timeout: float, attempts: int = 3) -> tuple[int, str, dict]:
    code, body, headers = 0, "", {}
    for attempt in range(attempts):
        code, body, headers = util.http_request("GET", url, timeout=timeout)
        if code and code < 500 and code != 429:
            return code, body, headers
        if attempt + 1 < attempts:
            time.sleep(2 * (attempt + 1))
    return code, body, headers


def _source_ext(source: dict) -> str:
    if source.get("kind") == "student_json":
        return "json"
    return "md"


def _store_raw(
    source_id: str,
    content: str,
    ext: str,
    daily_dir: Path,
    date: str,
) -> tuple[str, str]:
    digest = util.sha8(content)
    day_dir = daily_dir / date
    filename = f"{source_id}-{digest}.{ext}"
    today_raw = day_dir / "raw" / filename
    if today_raw.exists():
        return digest, f"raw/{filename}"
    if daily_dir.exists():
        for previous in sorted((p for p in daily_dir.iterdir() if p.is_dir()), reverse=True):
            if previous.name >= date:
                continue
            manifest = util.read_json(previous / "manifest.json", default={}) or {}
            entry = (manifest.get("sources") or {}).get(source_id) or {}
            if entry.get("hash") == digest and entry.get("raw"):
                target = previous / entry["raw"]
                if target.exists():
                    relative = os.path.relpath(target, day_dir).replace(os.sep, "/")
                    return digest, relative
    util.atomic_write(today_raw, content)
    return digest, f"raw/{filename}"


def import_local(source: dict, base_dir: Path) -> list[dict]:
    local = source.get("local")
    if not local:
        return []
    path = Path(base_dir) / local
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return []
    return adapters.parse_source(source, content)


def update_external(
    sources_config: dict,
    timeout: float = 20.0,
    daily_dir: Path | None = None,
) -> tuple[list[dict], list[dict], list[dict]]:
    daily_dir = daily_dir or util.DAILY_DIR
    date = util.today_iso()
    day_dir = daily_dir / date
    manifest_path = day_dir / "manifest.json"
    manifest = util.read_json(manifest_path, default=None) or {"date": date, "sources": {}}
    manifest.setdefault("sources", {})

    discovered: list[dict] = []
    changes: list[dict] = []
    reports: list[dict] = []

    for source in sources_config.get("sources", []):
        if not source.get("enabled", True):
            continue
        source_id = source.get("id") or source.get("kind") or "source"
        name = source.get("name") or source_id
        report = {"id": source_id, "name": name, "ok": False}
        url = source.get("url") or ""
        code, body, headers = _fetch(url, timeout)
        if not code or code >= 400:
            report["error"] = f"HTTP {code}" if code else "网络错误"
            reports.append(report)
            manifest["sources"][source_id] = {"ok": False, "error": report["error"]}
            util.log(f"{name}: 失败 {report['error']}")
            continue

        ext = _source_ext(source)
        digest, raw_ref = _store_raw(source_id, body, ext, daily_dir, date)
        try:
            items = adapters.parse_source(source, body)
        except Exception as exc:
            report["error"] = f"解析失败: {exc}"
            reports.append(report)
            manifest["sources"][source_id] = {"ok": False, "hash": digest, "raw": raw_ref, "error": report["error"]}
            util.log(f"{name}: 解析失败 {exc}")
            continue

        min_items = int(source.get("min_items") or 0)
        if min_items and len(items) < min_items:
            report["error"] = f"条目数 {len(items)} < 阈值 {min_items}"
            reports.append(report)
            manifest["sources"][source_id] = {"ok": False, "hash": digest, "raw": raw_ref, "error": report["error"]}
            util.log(f"{name}: {report['error']}")
            continue

        canonical = registry_mod.canonical_lines(items)
        snapshot_text = "\n".join(canonical) + ("\n" if canonical else "")
        result = diff.update_snapshot(
            source_id,
            snapshot_text,
            archive_dir=day_dir / "snapshots",
        )
        if result.get("anomaly"):
            report["error"] = (
                f"内容骤降: {result.get('previous_items')} -> {result.get('items')}，保留旧快照"
            )
            reports.append(report)
            manifest["sources"][source_id] = {"ok": False, "hash": digest, "raw": raw_ref, "error": report["error"]}
            util.log(f"{name}: {report['error']}")
            continue

        record = diff.append_changes(util.DATA_DIR / "changes.jsonl", source_id, name, result)
        if record:
            changes.append(record)
        discovered.extend(items)
        report.update(
            ok=True,
            items=len(items),
            baseline=bool(result.get("baseline")),
            added=result.get("added_count", 0),
            removed=result.get("removed_count", 0),
        )
        reports.append(report)
        manifest["sources"][source_id] = {
            "ok": True,
            "hash": digest,
            "raw": raw_ref,
            "items": len(items),
        }

    util.write_json(manifest_path, manifest)
    return discovered, changes, reports
