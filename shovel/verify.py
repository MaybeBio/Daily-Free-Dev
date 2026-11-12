from __future__ import annotations

import random
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlsplit

from . import util

FREE_KEYWORDS = re.compile(r"(free|trial|credit|grant|student|免费|试用|额度|赠金)", re.I)


class _HostLocks:
    def __init__(self) -> None:
        self._locks: dict[str, threading.Lock] = {}
        self._guard = threading.Lock()

    def get(self, host: str) -> threading.Lock:
        with self._guard:
            return self._locks.setdefault(host, threading.Lock())


def check_resource(resource: dict, timeout: float, transport=None) -> dict:
    url = resource.get("official_url") or resource.get("signup_url") or resource.get("homepage") or ""
    if not url:
        return {
            "status": "unknown",
            "http_status": 0,
            "final_url": "",
            "keyword_hit": False,
            "checked_at": util.now_utc(),
        }
    code, body, headers = util.http_request("GET", url, timeout=timeout, transport=transport)
    lower_headers = {str(key).lower(): value for key, value in (headers or {}).items()}
    final_url = lower_headers.get("x-final-url") or url
    keyword_hit = bool(FREE_KEYWORDS.search(body or ""))
    if code == 0:
        status = "error"
    elif code in (401, 403, 429):
        status = "blocked"
    elif code in (404, 410):
        status = "gone"
    elif 200 <= code < 300:
        status = "online" if keyword_hit else "suspect"
    else:
        status = "error"
    return {
        "status": status,
        "http_status": code,
        "final_url": final_url,
        "keyword_hit": keyword_hit,
        "checked_at": util.now_utc(),
    }


def run_verify(
    resources: list[dict],
    previous: dict | None = None,
    only: set[str] | None = None,
    workers: int = 8,
    timeout: float = 15.0,
    transport=None,
    jitter: float = 0.2,
    status_path=None,
) -> dict:
    previous_state = (previous or {}).get("resources", {})
    selected = [
        resource
        for resource in resources
        if not only or resource.get("id") in only
    ]
    locks = _HostLocks()

    def check(resource: dict) -> tuple[str, dict]:
        url = resource.get("official_url") or resource.get("signup_url") or resource.get("homepage") or ""
        host = urlsplit(url).netloc.lower() if url else ""
        lock = locks.get(host) if host else threading.Lock()
        with lock:
            if jitter:
                time.sleep(random.uniform(0, jitter))
            result = check_resource(resource, timeout, transport)
        previous_streak = int((previous_state.get(resource["id"]) or {}).get("streak_gone") or 0)
        result["streak_gone"] = previous_streak + 1 if result["status"] == "gone" else 0
        return resource["id"], result

    results: dict[str, dict] = {}
    if selected:
        with ThreadPoolExecutor(max_workers=max(1, min(workers, len(selected)))) as pool:
            for resource_id, result in pool.map(check, selected):
                results[resource_id] = result

    summary: dict[str, int] = {}
    for result in results.values():
        summary[result["status"]] = summary.get(result["status"], 0) + 1
    payload = {
        "generated_at": util.now_utc(),
        "summary": dict(sorted(summary.items())),
        "resources": results,
    }
    if status_path is not None:
        util.write_json(status_path, payload)
    return payload
