from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

from . import diff, registry as registry_mod, render, signals as signals_mod, sources, util, verify

DEFAULT_SOURCES = {
    "note": "外部发现源。enabled=false 的源不会抓取；min_items 首次 import 时自动校准。",
    "sources": [
        {
            "id": "free-for-dev",
            "name": "free-for-dev",
            "kind": "free_for_dev",
            "url": "https://raw.githubusercontent.com/ripienaar/free-for-dev/master/README.md",
            "local": "resources/free-for-dev/README.md",
            "enabled": True,
            "min_items": 0,
        },
        {
            "id": "gpu-grants",
            "name": "GPU Grants",
            "kind": "gpu_grants",
            "url": "https://raw.githubusercontent.com/eric-prog/GPU-Grants/main/README.md",
            "local": "resources/GPU-Grants/README.md",
            "enabled": True,
            "min_items": 0,
        },
        {
            "id": "awesome-gpu-cloud",
            "name": "Awesome GPU Cloud",
            "kind": "awesome_gpu_cloud",
            "url": "https://raw.githubusercontent.com/Enterprise-AI-Atlas/awesome-gpu-cloud/main/README.md",
            "local": "resources/awesome-gpu-cloud/README.md",
            "enabled": True,
            "min_items": 0,
        },
        {
            "id": "free-cloud-ai-resources",
            "name": "学生免费云资源",
            "kind": "student_json",
            "url": "https://raw.githubusercontent.com/HeyAvijitRoy/free-cloud-ai-resources-for-students/main/data.json",
            "local": "resources/free-cloud-ai-resources-for-students/data.json",
            "enabled": True,
            "min_items": 0,
        },
        {
            "id": "deep-learning-in-cloud",
            "name": "Deep Learning in Cloud",
            "kind": "deep_learning_cloud",
            "url": "https://raw.githubusercontent.com/zszazi/Deep-learning-in-cloud/master/README.md",
            "local": "resources/Deep-learning-in-cloud/README.md",
            "enabled": True,
            "min_items": 0,
        },
        {
            "id": "awesome-server-vps",
            "name": "Awesome Server / VPS",
            "kind": "vps_list",
            "url": "https://raw.githubusercontent.com/SyntaxScribe/Awesome-Server-VPS-Hosting-Providers/main/readme.md",
            "local": "resources/Awesome-Server-VPS-Hosting-Providers/readme.md",
            "enabled": True,
            "min_items": 0,
        },
    ],
}

DEFAULT_SIGNALS = {
    "note": "候选信号只做展示，不自动进入主清单。",
    "keywords": ["free", "gpu", "cpu", "vps", "credit", "grant", "trial", "免费", "试用", "额度", "赠金", "白嫖", "学生"],
    "exclude": ["hiring", "job", "sale", "free speech"],
    "max_per_day": 200,
    "feeds": [
        {"id": "free-for-dev-commits", "kind": "atom", "url": "https://github.com/ripienaar/free-for-dev/commits.atom", "enabled": True},
        {"id": "gpu-grants-commits", "kind": "atom", "url": "https://github.com/eric-prog/GPU-Grants/commits.atom", "enabled": True},
        {"id": "awesome-gpu-cloud-commits", "kind": "atom", "url": "https://github.com/Enterprise-AI-Atlas/awesome-gpu-cloud/commits.atom", "enabled": True},
        {"id": "student-resources-commits", "kind": "atom", "url": "https://github.com/HeyAvijitRoy/free-cloud-ai-resources-for-students/commits.atom", "enabled": True},
        {"id": "deep-learning-commits", "kind": "atom", "url": "https://github.com/zszazi/Deep-learning-in-cloud/commits.atom", "enabled": True},
        {"id": "vps-list-commits", "kind": "atom", "url": "https://github.com/SyntaxScribe/Awesome-Server-VPS-Hosting-Providers/commits.atom", "enabled": True},
        {"id": "cgpu-commits", "kind": "atom", "url": "https://github.com/RohanAdwankar/cgpu/commits.atom", "enabled": True},
        {"id": "kaggle-fuel-commits", "kind": "atom", "url": "https://github.com/uddinsaad70/kaggle-fuel/commits.atom", "enabled": True},
        {"id": "hn", "kind": "hn", "url": "https://hn.algolia.com/api/v1/search_by_date?query=free%20gpu&tags=story", "enabled": True},
        {"id": "reddit-localllama", "kind": "rss", "url": "https://www.reddit.com/r/LocalLLaMA/.rss", "enabled": True},
        {"id": "nodeseek", "kind": "rss", "url": "https://www.nodeseek.com/rss.xml", "enabled": True},
    ],
}

DEFAULT_RESOURCES = {
    "schema_version": 1,
    "updated_at": util.now_utc(),
    "note": "唯一事实源，可手动编辑。运行 update 只追加与补空字段。",
    "resources": [],
}


def ensure_configs() -> None:
    util.ensure_dirs()
    defaults = {
        "resources.json": DEFAULT_RESOURCES,
        "sources.json": DEFAULT_SOURCES,
        "signals.json": DEFAULT_SIGNALS,
    }
    for name, content in defaults.items():
        path = util.CONFIG_DIR / name
        if not path.exists():
            util.write_json(path, content)
    sources_path = util.CONFIG_DIR / "sources.json"
    document = util.read_json(sources_path, default={"sources": []}) or {"sources": []}
    known = {item.get("id") for item in document.get("sources", [])}
    added = [item for item in DEFAULT_SOURCES["sources"] if item.get("id") not in known]
    if added:
        document.setdefault("sources", []).extend(added)
        util.write_json(sources_path, document)
    signals_path = util.CONFIG_DIR / "signals.json"
    signal_config = util.read_json(signals_path, default={"feeds": []}) or {"feeds": []}
    signal_ids = {item.get("id") for item in signal_config.get("feeds", [])}
    signal_added = [item for item in DEFAULT_SIGNALS["feeds"] if item.get("id") not in signal_ids]
    if signal_added:
        signal_config.setdefault("feeds", []).extend(signal_added)
        util.write_json(signals_path, signal_config)


def _resources() -> list[dict]:
    document = util.read_json(util.CONFIG_DIR / "resources.json", default={"resources": []}) or {}
    return document.get("resources", [])


def _write_resources(resources: list[dict], note: str = "") -> None:
    document = util.read_json(util.CONFIG_DIR / "resources.json", default={}) or {}
    util.write_json(
        util.CONFIG_DIR / "resources.json",
        {
            "schema_version": 1,
            "updated_at": util.now_utc(),
            "note": note or document.get("note") or DEFAULT_RESOURCES["note"],
            "resources": resources,
        },
    )


def _load_registry(status: dict | None = None) -> dict:
    if status is None:
        status = util.read_json(util.DATA_DIR / "status.json", default=None)
    return registry_mod.build_registry(_resources(), status)


def _latest_signals() -> list[dict]:
    if not util.SIGNAL_DIR.exists():
        return []
    files = sorted(util.SIGNAL_DIR.glob("*.jsonl"))
    return util.read_jsonl(files[-1])[:200] if files else []


def _report(registry: dict, status: dict | None = None, signals: list[dict] | None = None) -> dict:
    changes = util.read_jsonl(util.DATA_DIR / "changes.jsonl")[-20:]
    return render.render_all(registry, status, changes, signals if signals is not None else _latest_signals())


def cmd_init(args) -> int:
    ensure_configs()
    util.log(f"配置目录: {util.CONFIG_DIR}")
    util.log(f"数据目录: {util.DATA_DIR}")
    return 0


def cmd_import(args) -> int:
    ensure_configs()
    config = util.read_json(util.CONFIG_DIR / "sources.json", default=DEFAULT_SOURCES) or DEFAULT_SOURCES
    existing = _resources()
    discovered: list[dict] = []
    for source in config.get("sources", []):
        if not source.get("enabled", True):
            continue
        items = sources.import_local(source, util.BASE_DIR)
        if not items and source.get("local"):
            util.log(f"{source.get('name', source.get('id'))}: 本地文件缺失或无条目")
        discovered.extend(items)
        if items and not int(source.get("min_items") or 0):
            source["min_items"] = max(1, int(len(items) * 0.8))
        util.log(f"{source.get('name', source.get('id'))}: {len(items)} 条")
    merged = registry_mod.merge_resources(existing, discovered)
    _write_resources(merged)
    util.write_json(util.CONFIG_DIR / "sources.json", config)
    registry = _load_registry()
    if not args.no_report:
        _report(registry)
    util.log(f"主清单: {registry['stats']['resources']} 条")
    return 0


def cmd_update(args) -> int:
    ensure_configs()
    config = util.read_json(util.CONFIG_DIR / "sources.json", default=DEFAULT_SOURCES) or DEFAULT_SOURCES
    discovered, changes, reports = sources.update_external(config, timeout=args.timeout)
    if discovered:
        merged = registry_mod.merge_resources(_resources(), discovered)
        _write_resources(merged)

    signal_count = 0
    signal_config = util.read_json(util.CONFIG_DIR / "signals.json", default=DEFAULT_SIGNALS) or DEFAULT_SIGNALS
    try:
        signal_count = len(signals_mod.ingest(signal_config, timeout=args.timeout))
    except Exception as exc:
        util.log(f"信号抓取失败: {exc}")

    registry = _load_registry()
    util.write_json(
        util.DAILY_DIR / util.today_iso() / "summary.json",
        {
            "date": util.today_iso(),
            "generated_at": util.now_utc(),
            "registry": registry.get("stats", {}),
            "sources": reports,
            "changes": changes,
            "signals": signal_count,
        },
    )
    diff.append_history(
        util.DATA_DIR / "history.jsonl",
        {
            "at": util.now_cst(),
            "resources": registry["stats"]["resources"],
            "kinds": registry["stats"]["kinds"],
            "free_types": registry["stats"]["free_types"],
            "sources": reports,
            "changes": [
                {"source": item["source"], "added": item["added_count"], "removed": item["removed_count"]}
                for item in changes
            ],
            "signals": signal_count,
        },
    )
    for report in reports:
        if report.get("ok"):
            suffix = "（基线）" if report.get("baseline") else f"，+{report.get('added', 0)} / -{report.get('removed', 0)}"
            util.log(f"{report['name']}: {report.get('items', 0)} 条{suffix}")
        else:
            util.log(f"{report['name']}: 失败 {report.get('error')}")
            if os.environ.get("GITHUB_ACTIONS"):
                print(f"::warning::{report['name']}: {report.get('error')}")
    if not args.no_report:
        _report(registry)
    ok_sources = [report for report in reports if report.get("ok")]
    if reports and not ok_sources:
        return 1
    return 0


def cmd_verify(args) -> int:
    ensure_configs()
    resources = _resources()
    only = {item.strip() for item in (args.only or "").split(",") if item.strip()} or None
    previous = util.read_json(util.DATA_DIR / "status.json", default={})
    status = verify.run_verify(
        resources,
        previous=previous,
        only=only,
        workers=args.workers,
        timeout=args.timeout,
        status_path=util.DATA_DIR / "status.json",
    )
    util.log(f"校验摘要: {status.get('summary')}")
    registry = _load_registry(status)
    if not args.no_report:
        _report(registry, status)
    summary_path = util.DAILY_DIR / util.today_iso() / "summary.json"
    summary = util.read_json(summary_path, default=None)
    if summary is not None:
        summary["registry"] = registry.get("stats", {})
        summary["verified_at"] = util.now_utc()
        util.write_json(summary_path, summary)
    return 0


def cmd_report(args) -> int:
    ensure_configs()
    registry = _load_registry()
    status = util.read_json(util.DATA_DIR / "status.json", default=None)
    result = _report(registry, status)
    util.log(f"README: {result['readme']}")
    util.log(f"CSV: {result['csv']}")
    util.log(f"面板: {result['site']}")
    util.log(f"RSS: {result['feed']}")
    return 0


def cmd_serve(args) -> int:
    ensure_configs()
    if not (util.SITE_DIR / "index.html").exists():
        _report(_load_registry())
    handler = partial(SimpleHTTPRequestHandler, directory=str(util.SITE_DIR))
    server = ThreadingHTTPServer((args.host, args.port), handler)
    util.log(f"面板: http://{args.host}:{args.port}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


def cmd_doctor(args) -> int:
    ensure_configs()
    resources = _resources()
    registry = _load_registry()
    stats = registry.get("stats", {})
    util.log(
        f"资源 {stats.get('resources', 0)} / 类型 {stats.get('kinds', {})} / "
        f"免费类型 {stats.get('free_types', {})}"
    )
    ids = [item.get("id") for item in resources]
    duplicates = sorted({item for item in ids if ids.count(item) > 1})
    util.log(f"重复 id: {duplicates or '无'}")
    missing_url = [item.get("id") for item in resources if not (item.get("official_url") or item.get("homepage"))]
    util.log(f"缺少官网链接: {missing_url or '无'}")
    util.log(f"data 体积: {util.human_size(util.DATA_DIR)}")

    status_path = util.DATA_DIR / "status.json"
    if status_path.exists():
        age = datetime.now() - datetime.fromtimestamp(status_path.stat().st_mtime)
        util.log(f"status.json 年龄: {age.total_seconds() / 3600:.1f} 小时")
        if age.total_seconds() > 48 * 3600:
            util.log("提示: 状态超过 48 小时未更新，建议运行 verify。")
    else:
        util.log("status.json 不存在（尚未校验）。")

    config = util.read_json(util.CONFIG_DIR / "sources.json", default=DEFAULT_SOURCES) or DEFAULT_SOURCES
    for source in config.get("sources", []):
        local = util.BASE_DIR / str(source.get("local") or "")
        local_state = "OK" if source.get("local") and local.exists() else "MISS"
        util.log(f"  {local_state} {source.get('id'):32} {source.get('url', '')}")
        if args.network:
            code, _, _ = util.http_request("GET", source.get("url", ""), timeout=args.timeout)
            util.log(f"       网络: HTTP {code}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="shovel",
        description="每日免费算力资源：采集、校验、差异追踪与静态面板。",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="创建配置与数据目录")
    init.set_defaults(func=cmd_init)

    import_cmd = sub.add_parser("import", help="从本地 resources/ 播种主清单")
    import_cmd.add_argument("--no-report", action="store_true")
    import_cmd.set_defaults(func=cmd_import)

    update = sub.add_parser("update", help="抓外部源、差异追踪并每日归档")
    update.add_argument("--timeout", type=float, default=20.0)
    update.add_argument("--no-report", action="store_true")
    update.set_defaults(func=cmd_update)

    verify_cmd = sub.add_parser("verify", help="校验官方页可达性与免费关键词")
    verify_cmd.add_argument("--only", default="", help="逗号分隔的资源 id")
    verify_cmd.add_argument("--timeout", type=float, default=15.0)
    verify_cmd.add_argument("--workers", type=int, default=8)
    verify_cmd.add_argument("--no-report", action="store_true")
    verify_cmd.set_defaults(func=cmd_verify)

    report = sub.add_parser("report", help="生成 README / CSV / 面板 / RSS")
    report.set_defaults(func=cmd_report)

    serve = sub.add_parser("serve", help="本地预览面板")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8757)
    serve.set_defaults(func=cmd_serve)

    doctor = sub.add_parser("doctor", help="检查配置、数据体积与源可达性")
    doctor.add_argument("--network", action="store_true")
    doctor.add_argument("--timeout", type=float, default=10.0)
    doctor.set_defaults(func=cmd_doctor)

    return parser


def main(argv: list[str] | None = None) -> int:
    sys.setrecursionlimit(10000)
    args = build_parser().parse_args(argv)
    return int(args.func(args) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
