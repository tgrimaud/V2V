#!/usr/bin/env python3
"""Merge per-candidate benchmark JSONs into the ADR-0045 comparison table (TASK-BE-033).

Reads one or more ``bench-<label>.json`` files produced by ``run_benchmark.py`` and emits a
single comparison JSON + Markdown: latency (client TTFC + server llm_first_token /
backend_first_token p50/p95), grounding/confidence, DEC-002 amount-mention flags, and the
static residency / egress / cost metadata each candidate carries. ``mistral-small`` is the
baseline; a ``Δp95`` column shows the backend-first-token change vs it. This is the artifact
ADR-0045 needs to move from Proposed to Accepted; it does NOT choose a provider by itself.

Cost is intentionally NOT reduced to a single fabricated figure: published per-1M-token
pricing + residency + egress impact are recorded so the trade-off (latency vs sovereignty vs
cost, OQ-009) stays explicit for the human decision.

Usage:
    python3 scripts/llm_benchmark/compare.py scripts/llm_benchmark/reports/bench-*.json \
        --out-dir scripts/llm_benchmark/reports
"""

from __future__ import annotations

import argparse
import datetime as dt
import glob
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASELINE = "mistral-small"

# Static, referenced metadata (not measured). Residency/egress feed ADR-0039 + OQ-009;
# pricing is the published public rate at the time of the spike (USD / 1M tokens) — verify
# before quoting. Keys match the --label passed to run_benchmark.py.
CANDIDATE_META = {
    "mistral-small": {
        "residency": "EU (Mistral)", "egress": "api.mistral.ai:443 (already allowlisted)",
        "hop": "remote cloud", "price_in_per_m": 0.10, "price_out_per_m": 0.30,
        "pricing_ref": "https://mistral.ai/pricing", "notes": "current baseline"},
    "mistral-large": {
        "residency": "EU (Mistral)", "egress": "api.mistral.ai:443 (already allowlisted)",
        "hop": "remote cloud", "price_in_per_m": 2.00, "price_out_per_m": 6.00,
        "pricing_ref": "https://mistral.ai/pricing", "notes": "same residency, larger model"},
    "ollama": {
        "residency": "on-prem (co-located)", "egress": "none (no chat egress)",
        "hop": "local", "price_in_per_m": None, "price_out_per_m": None,
        "pricing_ref": "amortized GPU/CPU infra", "notes": "infra cost + quality unproven on FR billing"},
    "openai-gpt-4o-mini": {
        "residency": "US (OpenAI)", "egress": "api.openai.com:443 (NEW — OQ-009 compliance)",
        "hop": "remote cloud", "price_in_per_m": 0.15, "price_out_per_m": 0.60,
        "pricing_ref": "https://openai.com/api/pricing", "notes": "US chat egress — residency decision, not only latency"},
}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="ADR-0045 candidate comparison (TASK-BE-033).")
    p.add_argument("reports", nargs="+", help="bench-*.json files (globs allowed).")
    p.add_argument("--out-dir", default=str(HERE / "reports"))
    p.add_argument("--label", default=dt.date.today().isoformat(), help="Comparison filename label.")
    return p.parse_args()


def load_reports(patterns: list[str]) -> list[dict]:
    paths: list[str] = []
    for pat in patterns:
        paths.extend(sorted(glob.glob(pat)))
    reports = [json.loads(Path(p).read_text(encoding="utf-8")) for p in dict.fromkeys(paths)]
    if not reports:
        raise SystemExit("No benchmark reports matched.")
    return reports


def _meta_for(label: str) -> dict:
    for key, meta in CANDIDATE_META.items():
        if label.startswith(key):
            return meta
    return {"residency": "n/a", "egress": "n/a", "hop": "n/a",
            "price_in_per_m": None, "price_out_per_m": None, "pricing_ref": "n/a", "notes": ""}


def _server_bft(agg: dict) -> dict | None:
    return agg.get("server_backend_first_token_ms") or None


def build_rows(reports: list[dict]) -> list[dict]:
    baseline_bft = None
    for r in reports:
        if r["candidate"]["label"] == BASELINE:
            s = _server_bft(r["aggregate"])
            baseline_bft = (s or {}).get("p95") or r["aggregate"]["client_ttfc_ms"].get("p95")
    rows = []
    for r in reports:
        agg = r["aggregate"]
        label = r["candidate"]["label"]
        server_bft = _server_bft(agg)
        bft_p95 = (server_bft or {}).get("p95") if server_bft else agg["client_ttfc_ms"].get("p95")
        rows.append({
            "label": label, "model": r["candidate"].get("model", ""),
            "meta": _meta_for(label),
            "client_ttfc": agg["client_ttfc_ms"], "client_total": agg["client_total_ms"],
            "server_llm_first_token": agg.get("server_llm_first_token_ms"),
            "server_backend_first_token": server_bft,
            "grounded_rate": agg["grounded_rate"], "confidence_mean": agg["confidence_mean"],
            "amount_mentions_total": agg["amount_mentions_total"], "errors": agg["errors"],
            "bft_p95": bft_p95,
            "delta_bft_p95_vs_baseline":
                (round(bft_p95 - baseline_bft, 1) if bft_p95 is not None and baseline_bft is not None else None),
        })
    return rows


def _cell(slices: dict | None) -> str:
    if not slices or not slices.get("n"):
        return "—"
    return f"{slices['p50']} / {slices['p95']}"


def build_markdown(rows: list[dict], label: str) -> str:
    lines = [
        "# ADR-0045 LLM candidate comparison (TASK-BE-033)",
        "",
        f"- **Date:** {label} | **Baseline:** `{BASELINE}`",
        "> Latency cells are **p50 / p95 (ms)**. Server slices come from backend `[TELEMETRY]`; "
        "client TTFC is the fallback proxy. `Δbft p95` is the backend-first-token p95 change vs the "
        "Mistral-small baseline (negative = faster). Cost/residency are recorded for the human "
        "decision — the harness does not pick a provider.",
        "",
        "## Latency + quality",
        "",
        "| Candidate | model | llm_first_token | backend_first_token | client TTFC | Δbft p95 | grounded | conf | €-flags | err |",
        "|---|---|---|---|---|---:|---:|---:|---:|---:|",
    ]
    for r in rows:
        lines.append(
            f"| `{r['label']}` | {r['model'] or 'n/a'} | {_cell(r['server_llm_first_token'])} | "
            f"{_cell(r['server_backend_first_token'])} | {_cell(r['client_ttfc'])} | "
            f"{r['delta_bft_p95_vs_baseline'] if r['delta_bft_p95_vs_baseline'] is not None else '—'} | "
            f"{r['grounded_rate']} | {r['confidence_mean']} | {r['amount_mentions_total']} | {r['errors']} |")
    lines += ["", "## Cost / residency / egress (ADR-0039, OQ-009)", "",
              "| Candidate | residency | hop | egress | $/1M in | $/1M out | notes |",
              "|---|---|---|---|---:|---:|---|"]
    for r in rows:
        m = r["meta"]
        lines.append(
            f"| `{r['label']}` | {m['residency']} | {m['hop']} | {m['egress']} | "
            f"{m['price_in_per_m'] if m['price_in_per_m'] is not None else '—'} | "
            f"{m['price_out_per_m'] if m['price_out_per_m'] is not None else '—'} | {m['notes']} |")
    lines += ["", "> **Decision (fill on completion):** chosen provider/model or 'keep Mistral small', "
              "then move ADR-0045 Proposed → Accepted with this table as evidence.", ""]
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    reports = load_reports(args.reports)
    rows = build_rows(reports)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {"generated": dt.datetime.now().isoformat(timespec="seconds"),
               "ticket": "TASK-BE-033", "baseline": BASELINE, "candidates": rows}
    (out_dir / f"comparison-{args.label}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / f"comparison-{args.label}.md").write_text(
        build_markdown(rows, args.label), encoding="utf-8")
    print(f"Compared {len(rows)} candidate(s) -> {out_dir}/comparison-{args.label}.{{json,md}}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
