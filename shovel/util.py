from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib import error as urlerror
from urllib import request as urlrequest

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = BASE_DIR / "config"
DATA_DIR = BASE_DIR / "data"
SITE_DIR = BASE_DIR / "site"
RESOURCES_DIR = BASE_DIR / "resources"
SNAPSHOT_DIR = DATA_DIR / "snapshots"
DAILY_DIR = DATA_DIR / "daily"
SIGNAL_DIR = DATA_DIR / "signals"

CST = timezone(timedelta(hours=8))
USER_AGENT = "shovel/1.0 (+https://github.com/)"


def ensure_dirs() -> None:
    for path in (CONFIG_DIR, DATA_DIR, SNAPSHOT_DIR, DAILY_DIR, SIGNAL_DIR, SITE_DIR):
        path.mkdir(parents=True, exist_ok=True)


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def now_cst() -> str:
    return datetime.now(CST).strftime("%Y-%m-%dT%H:%M:%S+08:00")


def today_iso() -> str:
    return datetime.now(CST).strftime("%Y-%m-%d")


def log(message: str) -> None:
    print(message, flush=True)


def atomic_write(path: Path, text: str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def read_json(path: Path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def write_json(path: Path, payload) -> None:
    atomic_write(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def read_jsonl(path: Path) -> list[dict]:
    records = []
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except OSError:
        return records
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            value = json.loads(line)
        except ValueError:
            continue
        if isinstance(value, dict):
            records.append(value)
    return records


def append_jsonl(path: Path, record: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def sha8(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:8]


def http_request(
    method: str,
    url: str,
    timeout: float = 15.0,
    headers: dict | None = None,
    data: bytes | None = None,
    transport=None,
) -> tuple[int, str, dict]:
    if transport is not None:
        return transport(method, url, timeout, headers, data)
    request_headers = {"User-Agent": USER_AGENT, "Accept": "*/*"}
    if headers:
        request_headers.update(headers)
    request = urlrequest.Request(url, data=data, method=method, headers=request_headers)
    try:
        with urlrequest.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", "replace")
            result_headers = dict(response.headers)
            result_headers["X-Final-URL"] = response.geturl()
            return response.status, body, result_headers
    except urlerror.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8", "replace")
        except Exception:
            pass
        result_headers = dict(exc.headers or {})
        result_headers["X-Final-URL"] = exc.geturl()
        return exc.code, body, result_headers
    except Exception as exc:
        return 0, str(exc), {}


def human_size(path: Path) -> str:
    total = 0
    path = Path(path)
    if path.exists():
        for item in path.rglob("*"):
            if item.is_file():
                total += item.stat().st_size
    size = float(total)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{int(size)} B" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"
