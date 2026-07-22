#!/usr/bin/env python3
"""TASK-BE-017 — Translate the English CSV KB corpus to French for dev RAG coverage.

Reads ``articles.csv`` (document_id,title,content with HTML content), converts the
HTML to plain text, translates title + content to French via the Mistral chat API,
and writes ``articles-fr.csv`` with the SAME ``document_id`` so it can be ingested as
a distinct ``csv-article-fr`` KB source (language ``fr``).

Dev tooling only — machine translation is not production-grade (see TASK-BE-017).

Usage:
    python3 scripts/translate_csv_kb.py                 # translate all articles (resumable)
    python3 scripts/translate_csv_kb.py --limit 5       # first 5 rows (smoke test)
    python3 scripts/translate_csv_kb.py --ids 14,21,326 # only these document_ids

Resumable: rows whose document_id is already present in the output are skipped, so a
re-run continues where an interrupted run stopped.

The Mistral API key is read from the MISTRAL_API_KEY env var, else from ./.env.
No third-party dependencies (stdlib only): urllib for HTTP, html.parser for HTML.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT = REPO_ROOT / "articles.csv"
DEFAULT_OUTPUT = REPO_ROOT / "articles-fr.csv"

MISTRAL_URL = "https://api.mistral.ai/v1/chat/completions"
MISTRAL_MODEL = "mistral-small-latest"
# Keep each translation request comfortably inside the model context and fast; long
# articles are split on paragraph boundaries and re-joined after translation.
MAX_CHARS_PER_CALL = 4000
MAX_RETRIES = 5
BASE_BACKOFF_S = 2.0
PACE_S = 0.4  # small delay between calls to be gentle on rate limits

csv.field_size_limit(sys.maxsize)


# --------------------------------------------------------------------------- HTML
class _TextExtractor(HTMLParser):
    """Collapse HTML into readable plain text, inserting blank lines on block tags."""

    _BLOCK = {"p", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6",
              "blockquote", "section", "article", "br"}

    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in self._BLOCK:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self._BLOCK:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        self._parts.append(data)

    def text(self) -> str:
        raw = "".join(self._parts)
        raw = re.sub(r"[ \t]+", " ", raw)
        raw = re.sub(r"\n[ \t]+", "\n", raw)
        raw = re.sub(r"\n{3,}", "\n\n", raw)
        return raw.strip()


def html_to_text(html: str) -> str:
    if not html or not html.strip():
        return ""
    parser = _TextExtractor()
    parser.feed(html)
    return parser.text()


# ------------------------------------------------------------------------ Mistral
def _api_key() -> str:
    key = os.environ.get("MISTRAL_API_KEY")
    if key:
        return key.strip()
    env_file = REPO_ROOT / ".env"
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("MISTRAL_API_KEY="):
                return line.split("=", 1)[1].strip()
    sys.exit("MISTRAL_API_KEY not found in environment or .env")


_SYSTEM_PROMPT = (
    "You are a professional English-to-French translator for a telecom customer-support "
    "knowledge base. Translate the user's text into natural, fluent French. Preserve line "
    "breaks and list structure. Keep product names, phone numbers, URLs and codes unchanged. "
    "Output ONLY the French translation, with no preamble, quotes or commentary."
)


def _post(payload: dict, key: str) -> str:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(MISTRAL_URL, data=data, method="POST")
    req.add_header("Authorization", f"Bearer {key}")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=120) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    return body["choices"][0]["message"]["content"].strip()


def translate_text(text: str, key: str) -> str:
    """Translate a single text blob (already within the per-call size budget)."""
    payload = {
        "model": MISTRAL_MODEL,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
    }
    last_err: Exception | None = None
    for attempt in range(MAX_RETRIES):
        try:
            out = _post(payload, key)
            time.sleep(PACE_S)
            return out
        except urllib.error.HTTPError as exc:
            last_err = exc
            if exc.code in (429, 500, 502, 503, 504):
                wait = BASE_BACKOFF_S * (2 ** attempt)
                sys.stderr.write(f"  http {exc.code}, retry in {wait:.0f}s\n")
                time.sleep(wait)
                continue
            raise
        except (urllib.error.URLError, OSError) as exc:
            # OSError covers ConnectionResetError / ConnectionError / socket errors that
            # can surface un-wrapped from getresponse(); all are transient -> retry.
            last_err = exc
            wait = BASE_BACKOFF_S * (2 ** attempt)
            sys.stderr.write(f"  network error ({type(exc).__name__}), retry in {wait:.0f}s\n")
            time.sleep(wait)
    raise RuntimeError(f"translation failed after {MAX_RETRIES} retries: {last_err}")


def _split_paragraphs(text: str, budget: int) -> list[str]:
    """Split text into chunks <= budget chars on paragraph, then line boundaries."""
    chunks: list[str] = []
    current = ""
    for para in text.split("\n\n"):
        piece = para if not current else current + "\n\n" + para
        if len(piece) <= budget:
            current = piece
            continue
        if current:
            chunks.append(current)
        if len(para) <= budget:
            current = para
        else:  # a single huge paragraph: hard-wrap on lines
            current = ""
            for line in para.split("\n"):
                cand = line if not current else current + "\n" + line
                if len(cand) <= budget:
                    current = cand
                else:
                    if current:
                        chunks.append(current)
                    current = line[:budget]
    if current:
        chunks.append(current)
    return chunks


def translate_long(text: str, key: str) -> str:
    if len(text) <= MAX_CHARS_PER_CALL:
        return translate_text(text, key)
    parts = _split_paragraphs(text, MAX_CHARS_PER_CALL)
    return "\n\n".join(translate_text(part, key) for part in parts)


# --------------------------------------------------------------------------- main
def load_done_ids(output: Path) -> set[str]:
    if not output.is_file():
        return set()
    done: set[str] = set()
    with output.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            if row.get("document_id"):
                done.add(row["document_id"].strip())
    return done


def main() -> int:
    ap = argparse.ArgumentParser(description="Translate the CSV KB corpus to French.")
    ap.add_argument("--input", default=str(DEFAULT_INPUT))
    ap.add_argument("--output", default=str(DEFAULT_OUTPUT))
    ap.add_argument("--limit", type=int, default=0, help="only the first N pending rows")
    ap.add_argument("--ids", default="", help="comma-separated document_ids to translate")
    args = ap.parse_args()

    input_path, output_path = Path(args.input), Path(args.output)
    if not input_path.is_file():
        sys.exit(f"input not found: {input_path}")

    key = _api_key()
    wanted = {i.strip() for i in args.ids.split(",") if i.strip()} if args.ids else None
    done = load_done_ids(output_path)
    new_file = not output_path.is_file()

    with input_path.open(encoding="utf-8", newline="") as fin, \
            output_path.open("a", encoding="utf-8", newline="") as fout:
        writer = csv.writer(fout, quoting=csv.QUOTE_ALL)
        if new_file:
            writer.writerow(["document_id", "title", "content"])
        translated = 0
        for row in csv.DictReader(fin):
            doc_id = (row.get("document_id") or "").strip()
            if not doc_id or doc_id in done:
                continue
            if wanted is not None and doc_id not in wanted:
                continue
            title = (row.get("title") or "").strip()
            content = html_to_text(row.get("content") or "")
            if not content:
                continue
            sys.stderr.write(f"[{translated + 1}] doc {doc_id}: {title[:60]}\n")
            fr_title = translate_text(title, key) if title else ""
            fr_content = translate_long(content, key)
            writer.writerow([doc_id, fr_title, fr_content])
            fout.flush()
            done.add(doc_id)
            translated += 1
            if args.limit and translated >= args.limit:
                break

    sys.stderr.write(f"done: {translated} article(s) translated -> {output_path}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
