from __future__ import annotations

import json
import re

from . import classify, util

FREE_FOR_DEV_REF = "https://github.com/ripienaar/free-for-dev"
GPU_GRANTS_REF = "https://github.com/eric-prog/GPU-Grants"
AWESOME_GPU_REF = "https://github.com/Enterprise-AI-Atlas/awesome-gpu-cloud"
STUDENT_REF = "https://github.com/HeyAvijitRoy/free-cloud-ai-resources-for-students"
DEEP_LEARNING_REF = "https://github.com/zszazi/Deep-learning-in-cloud"
VPS_REF = "https://github.com/SyntaxScribe/Awesome-Server-VPS-Hosting-Providers"

FREE_FOR_DEV_SECTIONS = {"Major Cloud Providers", "PaaS", "IaaS"}
TRACKER = re.compile(r"(tracker|price comparison|price table|price list|comparison|open-data|no sign-up)", re.I)


def _anchor(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")


def _make(
    name: str,
    url: str,
    text: str,
    source_ref: str,
    *,
    kind: str | None = None,
    free_type: str | None = None,
    limits: str | None = None,
    eligibility: str = "",
    provider: str | None = None,
) -> dict:
    clean_name = classify.strip_markdown(name)
    combined = f"{clean_name} {text}"
    resolved_kind = kind or classify.classify_kind(combined)
    resolved_free = free_type or classify.classify_free_type(text)
    tags = classify.infer_tags(combined, resolved_kind, resolved_free)
    access = classify.access_from_text(combined)
    return {
        "name": clean_name,
        "provider": classify.strip_markdown(provider) if provider else clean_name,
        "kind": resolved_kind,
        "tags": tags,
        "free_type": resolved_free,
        "limits_text": classify.strip_markdown(limits if limits is not None else text)[:1200],
        "eligibility": classify.strip_markdown(eligibility),
        "access": access,
        "homepage": url,
        "signup_url": "",
        "official_url": url,
        "source_refs": [source_ref],
        "verified_at": util.today_iso(),
        "notes": "",
    }


def parse_free_for_dev(text: str) -> list[dict]:
    items: list[dict] = []
    section = ""
    current: dict | None = None

    def flush() -> None:
        nonlocal current
        if not current:
            return
        subs = [sub for sub in current["subs"] if classify.is_compute(sub)]
        body = "；".join(subs) if subs else current["desc"]
        combined = f"{current['name']} {body}"
        if body and classify.is_compute(combined):
            ref = f"{FREE_FOR_DEV_REF}#{_anchor(section)}"
            items.append(
                _make(
                    current["name"],
                    current["url"],
                    body,
                    ref,
                    kind="cpu" if section == "Major Cloud Providers" else None,
                    provider=current["name"],
                )
            )
        current = None

    for line in text.splitlines():
        heading = re.match(r"^##\s+(.+?)\s*$", line)
        if heading:
            flush()
            section = heading.group(1).strip()
            continue
        if section not in FREE_FOR_DEV_SECTIONS:
            continue
        if section == "Major Cloud Providers":
            top = re.match(r"^ {2}\* \[([^\]]+)\]\(([^)]+)\)(.*)$", line)
            if top:
                flush()
                current = {"name": top.group(1), "url": top.group(2), "desc": top.group(3).strip(), "subs": []}
                continue
            sub = re.match(r"^ {4,}\* (.+)$", line)
            if sub and current:
                current["subs"].append(sub.group(1).strip())
            continue
        bullet = re.match(r"^\s{2}\*\s+\[([^\]]+)\]\(([^)]+)\)\s*(?:[-–—:]\s*)?(.*)$", line)
        if bullet:
            name, url, desc = bullet.group(1), bullet.group(2), bullet.group(3)
            combined = f"{name} {desc}"
            if classify.is_compute(combined):
                ref = f"{FREE_FOR_DEV_REF}#{_anchor(section)}"
                items.append(_make(name, url, desc, ref, provider=name))
    flush()
    return items


def parse_gpu_grants(text: str) -> list[dict]:
    lines = text.splitlines()
    items: list[dict] = []
    heading = re.compile(r"^\s*(?:✨\s*)?\[([^\]]+)\]\s*\(([^)]+)\)\s*$")
    for index, line in enumerate(lines):
        match = heading.match(line)
        if not match:
            continue
        name, url = match.group(1).strip(), match.group(2).strip()
        body = []
        cursor = index + 1
        while cursor < len(lines) and not lines[cursor].strip().startswith("```"):
            cursor += 1
        if cursor < len(lines):
            cursor += 1
            while cursor < len(lines) and not lines[cursor].strip().startswith("```"):
                body.append(lines[cursor].strip())
                cursor += 1
        description = " ".join(part for part in body if part)
        if not description:
            continue
        items.append(
            _make(
                name,
                url,
                description,
                GPU_GRANTS_REF,
                kind="gpu",
                free_type=classify.classify_free_type(description, default="grant"),
                limits=description,
            )
        )
    return items


def parse_awesome_gpu_cloud(text: str) -> list[dict]:
    items: list[dict] = []
    section = ""
    current: dict | None = None

    def flush() -> None:
        nonlocal current
        if not current:
            return
        combined = f"{current['name']} {current['desc']}"
        if classify.has_free_evidence(combined, "awesome-gpu-cloud") and classify.is_compute(combined):
            kind = classify.SECTION_HINTS.get(section, "gpu")
            items.append(
                _make(
                    current["name"],
                    current["url"],
                    combined,
                    f"{AWESOME_GPU_REF}#{_anchor(section)}",
                    kind=kind,
                )
            )
        current = None

    for line in text.splitlines():
        heading = re.match(r"^##\s+(.+?)\s*$", line)
        if heading:
            flush()
            section = heading.group(1).strip()
            continue
        if section not in classify.SECTION_HINTS:
            continue
        bullet = re.match(r"^- \*\*\[([^\]]+)\]\(([^)]+)\)\*\*\s*(.*)$", line)
        if bullet:
            flush()
            rest = re.sub(r"^`(?:Official|Community)`\s*", "", bullet.group(3).strip())
            rest = rest.lstrip("—–- ").strip()
            current = {"name": bullet.group(1), "url": bullet.group(2), "desc": rest}
            continue
        extra = re.match(r"^\s{2,}- (.+)$", line)
        if extra and current:
            current["desc"] += " " + extra.group(1).strip()
    flush()
    return items


def parse_student_json(content: str) -> list[dict]:
    try:
        document = json.loads(content)
    except ValueError:
        return []
    if not isinstance(document, dict):
        return []
    items: list[dict] = []
    for section in ("cloud-platforms-compute-credits", "aiml-tools-free-gpu-access", "developer-tools"):
        block = document.get(section) or {}
        tools = block.get("tools") if isinstance(block, dict) else None
        if not isinstance(tools, list):
            continue
        for tool in tools:
            if not isinstance(tool, dict):
                continue
            name = str(tool.get("name") or "").strip()
            link = str(tool.get("link") or "").strip()
            short = str(tool.get("short_desc") or "").strip()
            benefit = str(tool.get("benefit") or "").strip()
            verification = str(tool.get("verification") or "").strip()
            if not name or not link:
                continue
            combined = f"{name} {short} {benefit}"
            if not classify.is_compute(combined):
                continue
            kind = classify.classify_kind(combined)
            limits = short if not benefit else f"{short} {benefit}"
            item = _make(
                name,
                link,
                combined,
                f"{STUDENT_REF}#{section}",
                kind=kind,
                free_type="student",
                limits=limits,
                eligibility=verification,
            )
            item["tags"] = sorted(set(item["tags"]) | {"student"})
            items.append(item)
    return items


def parse_deep_learning(text: str) -> list[dict]:
    items: list[dict] = []
    active = False
    for line in text.splitlines():
        stripped = line.strip()
        if "Free Trial / Free Credits" in stripped:
            active = True
            continue
        if not active:
            continue
        if not stripped.startswith("|"):
            if items:
                break
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if len(cells) < 4:
            continue
        if re.fullmatch(r"[-: ]+", cells[0]):
            continue
        name_cell, website, pricing, free = cells[0], cells[1], cells[2], cells[3]
        if name_cell.lower().startswith("cloud vendor"):
            continue
        free_text = classify.strip_markdown(free)
        if not free_text or free_text in {"-", "—", "–"}:
            continue
        combined = f"{name_cell} {pricing} {free_text}"
        if TRACKER.search(combined):
            continue
        url = _extract_url(website) or _extract_url(name_cell)
        if not url:
            continue
        kind = classify.classify_kind(combined)
        if kind == "other":
            kind = "gpu"
        items.append(
            _make(
                name_cell,
                url,
                combined,
                f"{DEEP_LEARNING_REF}#free-credits-and-perksoffer",
                kind=kind,
                free_type=classify.classify_free_type(free_text),
                limits=free_text,
            )
        )
    return items


def parse_vps_list(text: str) -> list[dict]:
    items: list[dict] = []
    section = ""
    for line in text.splitlines():
        heading = re.match(r"^##\s+(.+?)\s*$", line)
        if heading:
            section = heading.group(1).strip()
            continue
        if section not in classify.SECTION_HINTS:
            continue
        bullet = re.match(r"^- \*\*\[([^\]]+)\]\(([^)]+)\)\*\*\s*[–—-]\s*(.*)$", line)
        if not bullet:
            continue
        name, url, desc = bullet.group(1), bullet.group(2), bullet.group(3)
        combined = f"{name} {desc}"
        if not classify.has_free_evidence(combined, "awesome-server-vps") or not classify.is_compute(combined):
            continue
        items.append(
            _make(
                name,
                url,
                combined,
                f"{VPS_REF}#{_anchor(section)}",
                kind=classify.SECTION_HINTS.get(section, "vps"),
            )
        )
    return items


def _extract_url(cell: str) -> str:
    match = re.search(r"\((https?://[^)\s]+)\)", cell)
    if not match:
        match = re.search(r"(https?://[^\s|)]+)", cell)
    if not match:
        return ""
    return match.group(1).rstrip(".,;)")


PARSERS = {
    "free_for_dev": parse_free_for_dev,
    "gpu_grants": parse_gpu_grants,
    "awesome_gpu_cloud": parse_awesome_gpu_cloud,
    "student_json": parse_student_json,
    "deep_learning_cloud": parse_deep_learning,
    "vps_list": parse_vps_list,
}


def parse_source(source: dict, content: str) -> list[dict]:
    parser = PARSERS.get(source.get("kind", ""))
    if parser is None:
        return []
    return parser(content)
