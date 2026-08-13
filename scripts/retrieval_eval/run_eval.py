#!/usr/bin/env python3
"""Retrieval-quality eval runner (TASK-BE-027, ADR-0032 gate).

Calls POST /api/conversation/retrieve for every question variant in the eval set, scores
recall@4/@8, MRR and phrasing-stability with the pure functions in ``metrics``, and writes
a JSON + Markdown baseline report. Offline and deterministic: it only needs the backend
(+ pgvector + loaded corpus) reachable; no pilot/external access.

Usage:
    python3 scripts/retrieval_eval/run_eval.py \
        --base-url http://localhost:8080 --top-k 8 --out-dir scripts/retrieval_eval/reports
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

from metrics import Aggregate, VariantResult, aggregate

HERE = Path(__file__).resolve().parent
ACCEPTANCE_RECALL8 = 0.9
ACCEPTANCE_STABILITY = 0.9


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Retrieval-quality eval harness (TASK-BE-027).")
    p.add_argument("--base-url", default="http://localhost:8080")
    p.add_argument("--eval-set", default=str(HERE / "eval_set.json"))
    p.add_argument("--top-k", type=int, default=8)
    p.add_argument("--domain-mode", choices=["none", "intended"], default="none",
                   help="'none' sends no domain filter (retrieval ceiling); "
                        "'intended' sends each question's domain (mirrors routing).")
    p.add_argument("--api-key", default=None, help="Optional x-api-key header value.")
    p.add_argument("--out-dir", default=str(HERE / "reports"))
    p.add_argument("--label", default=None, help="Report filename label; default = today.")
    return p.parse_args()


def retrieve(base_url: str, question: str, top_k: int, domain: str | None,
             api_key: str | None) -> tuple[list[str], str | None]:
    """Return (ranked source_ids, error). error is None on success."""
    payload: dict[str, object] = {"question": question, "top_k": top_k}
    if domain:
        payload["domain"] = domain
    body = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["x-api-key"] = api_key
    req = urllib.request.Request(f"{base_url}/api/conversation/retrieve", data=body,
                                 headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        return [], f"{type(exc).__name__}: {exc}"
    ranked = [str(e.get("source_id")) for e in data.get("evidence", [])]
    return ranked, None


def run(args: argparse.Namespace) -> tuple[list[VariantResult], dict]:
    spec = json.loads(Path(args.eval_set).read_text(encoding="utf-8"))
    results: list[VariantResult] = []
    for q in spec["questions"]:
        acceptable = frozenset(str(s) for s in q["acceptable_source_ids"])
        domain = q["domain"] if args.domain_mode == "intended" else None
        for variant in q["variants"]:
            ranked, error = retrieve(args.base_url, variant, args.top_k, domain, args.api_key)
            results.append(VariantResult(
                question_id=q["id"], variant=variant, language=q["language"],
                domain=q["domain"], ranked_source_ids=tuple(ranked),
                acceptable=acceptable, error=error))
    return results, spec


def _subset(results: list[VariantResult], key: str, value: str) -> list[VariantResult]:
    return [r for r in results if getattr(r, key) == value]


def _breakdown(results: list[VariantResult], key: str) -> dict[str, Aggregate]:
    values = sorted({getattr(r, key) for r in results})
    return {v: aggregate(_subset(results, key, v)) for v in values}


def _agg_row(name: str, a: Aggregate) -> str:
    return (f"| {name} | {a.recall_at_4:.2f} | {a.recall_at_8:.2f} | {a.mrr:.2f} | "
            f"{a.phrasing_stability:.2f} | {a.question_count} | {a.variant_count} |")


def build_markdown(results: list[VariantResult], spec: dict, args: argparse.Namespace,
                   overall: Aggregate) -> str:
    lines: list[str] = []
    lines.append("# Retrieval-quality baseline report (TASK-BE-027 / ADR-0032)")
    lines.append("")
    lines.append(f"- **Date:** {dt.date.today().isoformat()}")
    lines.append(f"- **Base URL:** {args.base_url}")
    lines.append(f"- **top_k:** {args.top_k} | **domain-mode:** {args.domain_mode}")
    lines.append(f"- **Eval set:** v{spec['version']} ({overall.question_count} questions, "
                 f"{overall.variant_count} variants)")
    lines.append(f"- **Config under test:** fixed chunker (BUG-003) + top-K over-fetch, "
                 f"dense-only (no MMR/hybrid/rerank)")
    errors = [r for r in results if r.error]
    if errors:
        lines.append(f"- **Request errors:** {len(errors)} (see JSON report)")
    lines.append("")
    lines.append("## Acceptance check (ADR-0032 proposed bar)")
    lines.append("")
    r8 = "PASS" if overall.recall_at_8 >= ACCEPTANCE_RECALL8 else "FAIL"
    st = "PASS" if overall.phrasing_stability >= ACCEPTANCE_STABILITY else "FAIL"
    lines.append(f"- recall@8 ≥ {ACCEPTANCE_RECALL8}: **{r8}** ({overall.recall_at_8:.2f})")
    lines.append(f"- phrasing-stability ≥ {ACCEPTANCE_STABILITY}: **{st}** "
                 f"({overall.phrasing_stability:.2f})")
    if overall.unstable_question_ids:
        lines.append(f"- Flipped (phrasing-brittle) questions: "
                     f"{', '.join(overall.unstable_question_ids)}")
    lines.append("")
    header = ("| Scope | recall@4 | recall@8 | MRR | stability | questions | variants |\n"
              "|---|---|---|---|---|---|---|")
    lines.append("## Aggregates")
    lines.append("")
    lines.append(header)
    lines.append(_agg_row("overall", overall))
    for lang, a in _breakdown(results, "language").items():
        lines.append(_agg_row(f"language={lang}", a))
    for dom, a in _breakdown(results, "domain").items():
        lines.append(_agg_row(f"domain={dom}", a))
    lines.append("")
    lines.append("## Per-question (top-8)")
    lines.append("")
    lines.append("| Question | lang | domain | variants pass@8 | best rank | flips? |")
    lines.append("|---|---|---|---|---|---|")
    lines.extend(_question_rows(results))
    lines.append("")
    return "\n".join(lines)


def _question_rows(results: list[VariantResult]) -> list[str]:
    by_q: dict[str, list[VariantResult]] = {}
    for r in results:
        by_q.setdefault(r.question_id, []).append(r)
    rows: list[str] = []
    for qid, variants in by_q.items():
        passes = sum(1 for v in variants if v.recall_at_k(8))
        ranks = [v.first_hit_rank() for v in variants if v.first_hit_rank() is not None]
        best = min(ranks) if ranks else "—"
        flips = "yes" if len({v.recall_at_k(8) for v in variants}) > 1 else "no"
        v0 = variants[0]
        rows.append(f"| {qid} | {v0.language} | {v0.domain} | {passes}/{len(variants)} | "
                    f"{best} | {flips} |")
    return rows


def to_json(results: list[VariantResult], overall: Aggregate, args: argparse.Namespace) -> dict:
    return {
        "generated": dt.datetime.now().isoformat(timespec="seconds"),
        "base_url": args.base_url,
        "top_k": args.top_k,
        "domain_mode": args.domain_mode,
        "acceptance": {"recall_at_8": ACCEPTANCE_RECALL8, "stability": ACCEPTANCE_STABILITY},
        "overall": vars(overall),
        "by_language": {k: vars(v) for k, v in _breakdown(results, "language").items()},
        "by_domain": {k: vars(v) for k, v in _breakdown(results, "domain").items()},
        "variants": [
            {
                "question_id": r.question_id, "variant": r.variant, "language": r.language,
                "domain": r.domain, "ranked_source_ids": list(r.ranked_source_ids),
                "acceptable": sorted(r.acceptable), "first_hit_rank": r.first_hit_rank(),
                "recall_at_4": r.recall_at_k(4), "recall_at_8": r.recall_at_k(8),
                "reciprocal_rank": round(r.reciprocal_rank(), 4), "error": r.error,
            }
            for r in results
        ],
    }


def main() -> int:
    args = parse_args()
    results, spec = run(args)
    overall = aggregate(results)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    label = args.label or dt.date.today().isoformat()
    (out_dir / f"baseline-{label}.md").write_text(
        build_markdown(results, spec, args, overall), encoding="utf-8")
    (out_dir / f"baseline-{label}.json").write_text(
        json.dumps(to_json(results, overall, args), ensure_ascii=False, indent=2),
        encoding="utf-8")
    print(f"recall@4={overall.recall_at_4:.2f} recall@8={overall.recall_at_8:.2f} "
          f"MRR={overall.mrr:.2f} stability={overall.phrasing_stability:.2f} "
          f"({overall.question_count}q/{overall.variant_count}v) -> {out_dir}")
    errors = [r for r in results if r.error]
    if errors:
        print(f"WARNING: {len(errors)} request error(s); first: {errors[0].error}",
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
