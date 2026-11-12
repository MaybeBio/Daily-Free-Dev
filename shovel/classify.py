from __future__ import annotations

import re

COMPUTE = re.compile(
    r"\b(gpu|gpus|cpu|vcpu|compute|instance|instances|vps|vm|"
    r"virtual machine|virtual machines|bare metal|dedicated server|cloud server|cloud run|"
    r"cloud functions|lambda|functions|serverless|container|containers|kubernetes|"
    r"k8s|notebooks|jupyter|colab|kaggle|sagemaker|vertex ai|ec2|tpu|"
    r"h100|h200|h800|a100|l4|l40|t4|rtx|nvidia|mi300|ampere|arm)\b",
    re.I,
)

BLACKLIST = re.compile(
    r"\b(database|databases|object storage|cloud storage|file storage|backup|cdn|"
    r"dns|domain|domains|email|monitoring|logging|analytics|pdf|image|images|video|"
    r"authentication|search api|forms|cms|font|fonts|design|evernote|note-taking|note taking)\b",
    re.I,
)

STRONG = re.compile(
    r"\b(gpu|gpus|cpu|vcpu|compute|instance|instances|vps|vm|"
    r"virtual machine|virtual machines|bare metal|dedicated server|cloud server|serverless|"
    r"container|containers|kubernetes|k8s|notebooks|jupyter|colab|kaggle|"
    r"functions|cloud run|cloud functions|tpu|ec2|h100|h200|h800|a100|l4|l40|t4|rtx|nvidia|mi300)\b",
    re.I,
)

FREE_EVIDENCE = re.compile(
    r"(free tier|free plan|free forever|always[- ]free|free trial|free credits?|"
    r"free gpu|free compute|free access|generous free|免费|试用|额度|赠金|白嫖)",
    re.I,
)

FREE_NEGATIVE = re.compile(
    r"(free[- ]speech|free speech|freely|free guide|free newsletter|free egress)",
    re.I,
)

KIND_RULES = (
    ("notebook", re.compile(r"\b(notebooks|jupyter|colab|kaggle|deepnote)\b", re.I)),
    (
        "serverless",
        re.compile(
            r"\b(serverless|scale[- ]to[- ]zero|cloud run|cloud functions|functions|lambda|"
            r"containers?|inference endpoint|inference endpoints)\b",
            re.I,
        ),
    ),
    (
        "vps",
        re.compile(
            r"\b(vps|virtual machine|virtual machines|droplet|droplets|bare metal|"
            r"dedicated server|cloud server|vm)\b",
            re.I,
        ),
    ),
    (
        "gpu",
        re.compile(
            r"\b(gpu|gpus|nvidia|h100|h200|h800|a100|l4|l40|t4|rtx|tesla|tpu|mi300|ampere)\b",
            re.I,
        ),
    ),
    (
        "cpu",
        re.compile(r"\b(cpu|vcpu|compute engine|ec2|instance|instances|machine|machines|compute|core|cores)\b", re.I),
    ),
)

SECTION_HINTS = {
    "Bare Metal (Dedicated)": "vps",
    "Cloud IaaS & Developer Clouds": "cpu",
    "VPS (Unmanaged)": "vps",
    "Managed VPS & “Platform” VPS": "vps",
    "Niche / Specialty Providers": "vps",
    "Regional Highlights": "vps",
    "Major Cloud Providers": "gpu",
    "Serverless GPU Inference": "serverless",
    "GPU Cloud Marketplaces": "gpu",
    "Kubernetes GPU Platforms": "serverless",
    "Budget / Consumer GPU Cloud": "gpu",
    "Enterprise HPC Cloud": "gpu",
    "AI Training Platforms": "gpu",
}


def strip_markdown(text: str) -> str:
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = text.replace("**", "").replace("`", "")
    text = re.sub(r"[:!][a-z0-9_+-]+:", "", text)
    return re.sub(r"\s+", " ", text).strip()


def is_compute(text: str) -> bool:
    if not COMPUTE.search(text):
        return False
    if BLACKLIST.search(text) and not STRONG.search(text):
        return False
    return True


def has_free_evidence(text: str, source_id: str = "") -> bool:
    if source_id in {"free-for-dev", "gpu-grants", "free-cloud-ai-resources"}:
        return True
    return bool(FREE_EVIDENCE.search(text)) and not bool(FREE_NEGATIVE.search(text))


def classify_kind(text: str, hint: str | None = None) -> str:
    if hint:
        return hint
    for kind, pattern in KIND_RULES:
        if pattern.search(text):
            return kind
    return "other"


def classify_free_type(text: str, default: str = "permanent") -> str:
    value = text.lower()
    if re.search(r"(always[- ]free|free forever|永久免费|永久|forever)", value):
        return "permanent"
    if re.search(
        r"(renew|renewable|monthly credits|credits? (each|every) month|可续期|每月.*(重置|续))",
        value,
    ):
        return "renewable"
    if re.search(r"(trial|试用|free credits?|credits?|赠金|试用金|signup credit)", value):
        return "trial_credit"
    if re.search(r"(\bgrants?\b|\bfunding\b|research program|research credits|资助)", value):
        return "grant"
    if re.search(r"(\bstudents?\b|\.edu|学生)", value):
        return "student"
    if re.search(r"(expires?|expiry|到期|限时|ends on|valid until)", value):
        return "limited"
    return default


def access_from_text(text: str) -> dict:
    value = text.lower()
    if re.search(r"(no|without) (a )?(credit |debit )?card|no credit card|无需信用卡|不需要信用卡", value):
        card = "not_required"
    elif re.search(
        r"(credit|debit) card (required|needed)|card required|requires? (a )?(credit|debit) card|"
        r"需(要)?信用卡|需要信用卡",
        value,
    ):
        card = "required"
    else:
        card = "unknown"
    phone = "required" if re.search(r"phone (number )?(verification|verified)|phone verification|手机号验证", value) else "unknown"
    realname = "required" if re.search(r"identity verification|real[- ]name|实名", value) else "unknown"
    return {"card": card, "phone": phone, "realname": realname}


def infer_tags(text: str, kind: str, free_type: str) -> list[str]:
    value = text.lower()
    tags = set()
    if free_type == "permanent":
        tags.add("free-tier")
    if free_type == "trial_credit":
        tags.add("trial")
    if free_type == "renewable":
        tags.add("renewable")
    if free_type == "grant":
        tags.add("grant")
    if free_type == "student":
        tags.add("student")
    for token in ("h100", "h200", "h800", "a100", "l4", "l40", "t4", "rtx", "mi300", "tpu", "arm"):
        if re.search(rf"\b{token}\b", value):
            tags.add(token)
    if re.search(r"\b(k8s|kubernetes)\b", value):
        tags.add("k8s")
    if kind == "notebook":
        tags.add("notebook")
    if re.search(r"\bbare[- ]metal\b", value):
        tags.add("bare-metal")
    access = access_from_text(text)
    if access["card"] == "required":
        tags.add("card-required")
    if access["card"] == "not_required":
        tags.add("no-card")
    if access["phone"] == "required":
        tags.add("phone-required")
    if access["realname"] == "required":
        tags.add("realname")
    if kind == "other":
        tags.add("needs-review")
    return sorted(tags)
