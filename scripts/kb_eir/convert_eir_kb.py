#!/usr/bin/env python3
"""Convert the scraped eir help-centre markdown dump into the canonical KB format.

TASK-BE-069 (approach A): a one-shot preprocessing step. The raw corpus
(``www.eir.ie_helpandsupport_*.md``) carries only ``url`` + ``title`` front-matter and
~85-90% navigation/footer boilerplate around the real article body. This script:

- strips the mega-nav header, the sibling-nav links and the shared footer;
- keeps the real prose/steps (drops pure-link and nav-label lines);
- derives ``domain`` deterministically from the URL path (ADR-0030 domains);
- sets ``language: en`` and ``audience: customer`` (ADR-0034 — all eir help-centre
  content is public/customer-facing; the backend still fail-closes on audience);
- writes canonical markdown into ``knowledge-base/eir/`` so the existing
  ``MarkdownFolderConnector`` (recursive since TASK-BE-069) ingests it unchanged.

Scope: the **core support/billing subset**. The 832 per-device smartphone tutorials
(URL segment ``smartphonehelp``) are excluded for now (near-duplicate per device →
would flood the billing-focused V1 RAG); import them later by flipping ``--include-devices``.

Usage::

    python3 scripts/kb_eir/convert_eir_kb.py \
        --source ~/Workspace/factrure/01a10c1b-695f-715a-8415-ae4f4b501181 \
        --out knowledge-base/eir
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

# URL path segment (right after ".../helpandsupport/") -> ADR-0030 domain.
_DOMAIN_BY_SEGMENT = {
    "billing": "billing",
    "moving-home": "commercial",
    "my-order": "commercial",
    # everything else customer-support/technical:
    "fibre-broadband": "support",
    "broadband": "support",
    "mobile": "support",
    "eirtv": "support",
    "home-phone": "support",
    "webmail": "support",
    "eir-app": "support",
    "myeir": "support",
    "smartphonehelp": "support",
    "service-update": "support",
    "broadbandspeedtest": "support",
}

# URL segments that are per-device tutorials — excluded from the core subset.
_DEVICE_SEGMENTS = {"smartphonehelp"}

# Standalone nav/footer labels (case-insensitive) dropped wherever they appear.
_NAV_LABELS = {
    "skip to main content", "featured", "shop", "learn more", "need help?",
    "help by product", "customer support, your way", "chat", "back to the top",
    "our products", "support", "our websites", "eir group", "join the conversation",
    "third party plugins", "messenger launcher", "messenger", "cookie settings",
    "specifications", "personal", "business",
}

_FRONT_MATTER = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)
_LINK_TOKEN = re.compile(r"!?\[[^\]]*\]\([^)]*\)")
_URL = re.compile(r"https?://\S+")
_FOOTER_BLURB = re.compile(r"^(eir and open eir are trading names|©\s*\d{4}|VAT number)", re.IGNORECASE)
_HEADING = re.compile(r"^#{1,6}\s+(.*\S)\s*$")


def _is_scaffolding_only(stripped: str) -> bool:
    """True if, after removing markdown link tokens and URLs, only link/list scaffolding
    remains. Catches nav tiles (``[![alt](img)](url)``), image rows (``![](a)![](b)](url)``)
    and the dangling ``](url)`` / ``[ \\`` tails of multi-line mangled links — all boilerplate.
    A prose line with an inline link keeps its words and is NOT scaffolding-only."""
    s = re.sub(r"^[-*]\s+", "", stripped)
    prev = None
    while prev != s:  # peel nested/stacked link tokens
        prev = s
        s = _LINK_TOKEN.sub("", s).strip()
    s = _URL.sub("", s)
    s = re.sub(r"[\[\]()\\*\-|>\s]", "", s)
    return s == ""


def _is_link_only(stripped: str) -> bool:
    return _is_scaffolding_only(stripped)


def _parse_front_matter(raw: str) -> tuple[dict[str, str], str]:
    match = _FRONT_MATTER.match(raw)
    if not match:
        return {}, raw
    meta: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            meta[key.strip()] = value.strip().strip('"').strip()
    return meta, match.group(2)


def domain_from_url(url: str) -> str:
    """Map an eir help-centre URL to an ADR-0030 domain (default: support)."""
    parts = [p for p in re.sub(r"[?#].*$", "", url).split("/") if p]
    if "helpandsupport" in parts:
        idx = parts.index("helpandsupport")
        if idx + 1 < len(parts):
            return _DOMAIN_BY_SEGMENT.get(parts[idx + 1], "support")
    return "support"


def url_segment(url: str) -> str:
    """Return the first path segment after ``helpandsupport`` (``""`` if none)."""
    parts = [p for p in re.sub(r"[?#].*$", "", url).split("/") if p]
    if "helpandsupport" in parts:
        idx = parts.index("helpandsupport")
        if idx + 1 < len(parts):
            return parts[idx + 1]
    return ""


def slug_from_url(url: str) -> str:
    """Build a readable, collision-safe filename slug from the URL path."""
    path = re.sub(r"[?#].*$", "", url)
    parts = [p for p in path.split("/") if p and p not in ("https:", "http:", "www.eir.ie")]
    if parts and parts[0] == "helpandsupport":
        parts = parts[1:]
    slug = "-".join(parts) or "index"
    slug = re.sub(r"[^a-z0-9-]+", "-", slug.lower()).strip("-")
    return slug or "index"


def _is_boilerplate_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False  # blank lines are structural; collapsed later
    if stripped.lower() in _NAV_LABELS:
        return True
    if "![" in stripped:
        return True  # any image embed is a nav tile / banner / screenshot (no text-RAG value)
    if _FOOTER_BLURB.match(stripped):
        return True
    if _is_scaffolding_only(stripped):
        return True
    return False


def clean_body(body: str) -> str:
    """Strip the eir nav header, sibling-nav links and shared footer, keep the article.

    1. Cut the head before the page H1 (``# ...``) — the mega-nav has no H1.
    2. Cut the footer at the first standalone ``Back to the top``.
    3. Drop pure-link and nav-label lines from what remains; collapse blank runs.
    """
    lines = body.splitlines()

    # (1) head: start at the first content heading of any level (the mega-nav has none);
    # eir core pages title the article with #, ## or ###.
    start = 0
    for i, line in enumerate(lines):
        if re.match(r"^#{1,6}\s+\S", line):
            start = i
            break
    lines = lines[start:]

    # (2) footer: cut at the first "Back to the top" (shared across every page).
    for i, line in enumerate(lines):
        if line.strip().lower() == "back to the top":
            lines = lines[:i]
            break

    # (3) drop boilerplate lines, collapse consecutive blanks.
    kept: list[str] = []
    blank = False
    for line in lines:
        if _is_boilerplate_line(line):
            continue
        if not line.strip():
            if blank:
                continue
            blank = True
        else:
            blank = False
        kept.append(line.rstrip())
    return "\n".join(kept).strip()


def derive_title(body: str, fm_title: str | None) -> str:
    """Prefer the first content heading; fall back to the cleaned front-matter title."""
    for line in body.splitlines():
        m = _HEADING.match(line)
        if m:
            return m.group(1).strip()
    title = (fm_title or "").strip()
    # Front-matter titles look like "Support | My bundle allowances" — keep the leaf.
    if "|" in title:
        title = title.split("|")[-1].strip()
    return title or "eir help"


def _yaml_escape(value: str) -> str:
    return value.replace('"', "'")


def build_document(raw: str, *, min_chars: int) -> tuple[str, dict[str, str]] | None:
    """Return (canonical_markdown, meta) or None if the file is nav-only / out of scope."""
    meta, body = _parse_front_matter(raw)
    url = meta.get("url", "")
    if not url:
        return None
    cleaned = clean_body(body)
    if len(cleaned) < min_chars:
        return None  # pure landing/index page — no real article content
    domain = domain_from_url(url)
    title = derive_title(cleaned, meta.get("title"))
    front = (
        "---\n"
        f"domain: {domain}\n"
        "language: en\n"
        "audience: customer\n"
        f'title: "{_yaml_escape(title)}"\n'
        f'url: "{_yaml_escape(url)}"\n'
        "source: eir-helpcentre\n"
        "---\n\n"
    )
    return front + cleaned + "\n", {"domain": domain, "url": url, "title": title}


def convert(source: Path, out: Path, *, include_devices: bool, min_chars: int) -> dict[str, int]:
    out.mkdir(parents=True, exist_ok=True)
    stats = {"written": 0, "skipped_device": 0, "skipped_empty": 0, "skipped_no_url": 0}
    by_domain: dict[str, int] = {}
    for path in sorted(source.glob("*.md")):
        raw = path.read_text(encoding="utf-8")
        meta, _ = _parse_front_matter(raw)
        url = meta.get("url", "")
        if not url:
            stats["skipped_no_url"] += 1
            continue
        if not include_devices and url_segment(url) in _DEVICE_SEGMENTS:
            stats["skipped_device"] += 1
            continue
        built = build_document(raw, min_chars=min_chars)
        if built is None:
            stats["skipped_empty"] += 1
            continue
        content, info = built
        slug = slug_from_url(url)
        (out / f"{slug}.md").write_text(content, encoding="utf-8")
        stats["written"] += 1
        by_domain[info["domain"]] = by_domain.get(info["domain"], 0) + 1
    stats.update({f"domain_{k}": v for k, v in by_domain.items()})
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert the eir help-centre dump to canonical KB markdown.")
    parser.add_argument("--source", required=True, type=Path, help="Folder of scraped eir .md files")
    parser.add_argument("--out", required=True, type=Path, help="Output folder (e.g. knowledge-base/eir)")
    parser.add_argument("--include-devices", action="store_true",
                        help="Also convert the per-device smartphone tutorials (default: excluded)")
    parser.add_argument("--min-chars", type=int, default=200,
                        help="Drop pages whose cleaned body is shorter than this (nav-only pages)")
    args = parser.parse_args()
    stats = convert(args.source.expanduser(), args.out.expanduser(),
                    include_devices=args.include_devices, min_chars=args.min_chars)
    print("eir KB conversion:")
    for key in sorted(stats):
        print(f"  {key}: {stats[key]}")


if __name__ == "__main__":
    main()
