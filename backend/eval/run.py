"""Eval harness (plan section 10).

    uv run python -m eval.run [--mode graph|vector|both] [--layer retrieval|generation|all]
                              [--limit N] [--runs N] [--fake-llm]

Layers (each measured separately, so a bad answer can be traced to its layer):
  retrieval       search + rerank only (no model writes anything): recall@5 of `expected_sources`
                  and how many forbidden ids come back.
  generation      runs lore.ask.ask(): key facts present, claims cited, refusals correct, leaks.
  investigations  runs the 4-agent supervisor on eval/investigations.jsonl (included in `all`).
Plus a leak check: every persona x every question, no forbidden id may ever come back.

Modes: "graph" = Graph ON (vector + full-text + graph-scoped search, reranked).
       "vector" = Graph OFF baseline (vector search only, ordered by similarity).

Scoring is deterministic string/id matching (eval/scoring.py), no LLM judge.
Needs a running FalkorDB with the Kettle graph loaded; generation also needs a Gemini key.

Input files (JSONL):
  eval/golden.jsonl         {"id","type","persona","question","expected_sources":[ids],
                             "must_include":[...],"must_not_include_ids":[ids],"should_refuse":bool}
  eval/investigations.jsonl {"id","alert_id","persona","expected_root_cause",
                             "expected_rejected":[ids],"expected_severity","expected_page",
                             "expected_consult":[ids],"expected_notify":[ids]}
                            (this shape is an assumption: adjust scoring.score_investigation)
Output: eval/report.md (overwritten) and one line per mode appended to eval/history.csv.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from eval import scoring as sc

EVAL_DIR = Path(__file__).parent
EVAL_NOW = 1791927000  # 2026-10-14 03:00 IST, the time of alert A-3001: "now" for recency
RETRIEVE_LIMIT = 20  # ids returned per search (recall uses the first 5, leaks look at all 20)
# Extra questions for the leak check: they aim straight at the restricted sources.
TRAP_PROBES = [
    "What are the vendor contract rates for the pricing tax API?",
    "What happened with the leaked payments API key in the public gist?",
    "Why did Marco Bianchi move from Pricing to Data?",
    "What was discussed in #pricing-private about the cache TTL?",
]
HISTORY_COLUMNS = [
    "timestamp", "mode", "cases", "recall_at_5", "retrieval_forbidden", "must_include", "cited",
    "refusal_ok", "generation_forbidden", "root_cause_ok", "leaks", "llm",
]


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


# --------------------------------------------------------------------------- the three layers


async def retrieve(ctx, llm, question: str, mode: str) -> tuple[list[str], list[str]]:
    """The product's own Ask retrieval + rerank (ask._retrieve), no answer written.

    Returns (ids in the top 5 sources, ids in the top 20 sources). A graph-facts source counts
    the related ids its text names too ("pr:482 was AUTHORED by person:priya"), because those are
    in the context the model reads. Graph OFF = vector search ranked by similarity only.
    """
    from lore import ask, rerank

    qvec = (await llm.embed([question], "query"))[0]
    found = await ask._retrieve(ctx, question, qvec, mode)
    weights = None
    if mode == "vector":
        weights = {"meaning": 1.0, "keyword": 0.0, "graph": 0.0, "recency": 0.0}
    ranked = rerank.rerank(found, EVAL_NOW, weights) if weights else rerank.rerank(found, EVAL_NOW)

    def flat(cands):
        return list(dict.fromkeys(i for c in cands for i in (c.id, *c.related_ids)))

    return flat(ranked[:5]), flat(ranked[:RETRIEVE_LIMIT])


def make_ctx(graph, persona: str, mode: str):
    from lore.permissions import viewer_for
    from lore.tools import ToolContext

    return ToolContext(viewer=viewer_for(persona), graph=graph, mode=mode, now_ts=EVAL_NOW)


async def run_retrieval(cases, graph, llm, mode) -> list[dict[str, Any]]:
    rows = []
    for case in cases:
        ctx = make_ctx(graph, case["persona"], mode)
        top5, top20 = await retrieve(ctx, llm, case["question"], mode)
        row = sc.score_retrieval(case, top5, k=len(top5) or 5)
        row["forbidden"] = sc.score_retrieval(case, top20, k=len(top20) or 5)["forbidden"]
        rows.append({**row, "returned": top5[:12]})
    return rows


async def run_generation(cases, graph, llm, mode) -> list[dict[str, Any]]:
    from lore import ask as ask_module
    from lore.permissions import viewer_for

    rows = []
    for case in cases:
        start = time.perf_counter()
        error = None
        try:
            answer = await ask_module.ask(
                case["question"], viewer_for(case["persona"]), mode=mode, llm=llm, graph=graph
            )
            answer = answer.model_dump()
        except Exception as exc:  # a crash counts as a failed case, the run goes on
            error = f"{type(exc).__name__}: {exc}"
            answer = {"refused": False, "claims": [], "sources": []}
        row = sc.score_generation(case, answer)
        rows.append({**row, "ms": (time.perf_counter() - start) * 1000, "error": error})
    return rows


async def run_leak_check(golden, graph, llm) -> list[dict[str, Any]]:
    """Every persona asks every question (plus the trap questions) and must get no forbidden id."""
    from lore.permissions import PERSONAS

    probes = [c["question"] for c in golden] + TRAP_PROBES
    rows = []
    for persona in PERSONAS:
        ctx = make_ctx(graph, persona, "graph")
        leaks: set[str] = set()
        for question in probes:
            _, ids = await retrieve(ctx, llm, question, "graph")  # top 20, incl. graph facts
            leaks |= set(sc.forbidden_hits(ids, sc.FORBIDDEN_BY_PERSONA[persona]))
        rows.append({"persona": persona, "probes": len(probes), "leaks": sorted(leaks)})
    return rows


async def run_investigations(cases, graph, llm, mode, runs) -> list[dict[str, Any]]:
    from lore.agents import supervisor
    from lore.permissions import viewer_for

    rows = []
    for case in cases:
        for _ in range(runs):
            async def drop(event):  # events are not needed here, only the final report
                return None

            try:
                report, summary = await supervisor.run_investigation(
                    case["alert_id"], viewer_for(case["persona"]),
                    mode=mode, llm=llm, graph=graph, emit=drop,
                )
                rows.append(sc.score_investigation(case, report.model_dump(), summary.model_dump()))
            except Exception as exc:
                rows.append({**sc.score_investigation(case, None, None), "error": str(exc)})
    return rows


# --------------------------------------------------------------------------- report


def pct(v):
    return sc.fmt(v, percent=True)


def render_report(results: dict[str, Any], meta: dict[str, Any]) -> str:
    out = ["# Lore eval report", "",
           f"Generated {meta['when']} · modes: {', '.join(meta['modes'])} · "
           f"layers: {', '.join(meta['layers'])} · LLM: {meta['llm']} · "
           f"questions: {meta['n_cases']}", "",
           "Graph ON = vector + full-text + graph-scoped search with rerank. "
           "Graph OFF = vector search only. Scoring is deterministic (no LLM judge).", ""]
    ret, gen, inv = (results.get(k, {}) for k in ("retrieval", "generation", "investigations"))

    if ret:
        out += ["## Retrieval (top 5, forbidden ids counted over the top 20)", ""]
        out.append(sc.markdown_table(
            ["mode", "questions", "recall@5", "forbidden ids"],
            [[m, s["cases"], pct(s["recall"]), s["forbidden"]]
             for m, s in ((m, sc.summarise_retrieval(r)) for m, r in ret.items())]))
        out += ["", "Recall@5 by question type:", ""]
        types = sorted({r["type"] for rows in ret.values() for r in rows})
        per_mode = {m: sc.by_type(rows, "recall") for m, rows in ret.items()}
        out.append(sc.markdown_table(
            ["type"] + list(ret), [[t] + [pct(per_mode[m].get(t)) for m in ret] for t in types]))
        out.append("")

    if gen:
        out += ["## Generation (ask)", ""]
        out.append(sc.markdown_table(
            ["mode", "questions", "key facts", "claims cited", "refusals correct", "leaks",
             "errors"],
            [[m, s["cases"], pct(s["must_include"]), pct(s["cited"]), pct(s["refusal_ok"]),
              s["forbidden"], sum(1 for r in rows if r.get("error"))]
             for m, rows in gen.items() for s in [sc.summarise_generation(rows)]]))
        out.append("")

    if inv:
        out += ["## Investigations", ""]
        out.append(sc.markdown_table(
            ["mode", "runs", "root cause", "red herring rejected", "severity", "people",
             "avg steps", "avg seconds", "avg cost $"],
            [[m, s["runs"], pct(s["root_cause"]), pct(s["red_herring"]), pct(s["severity"]),
              pct(s["people"]), sc.fmt(s["steps"]), sc.fmt(s["seconds"]), sc.fmt(s["cost_usd"])]
             for m, rows in inv.items() for s in [sc.summarise_investigations(rows)]]))
        out.append("")

    if len(ret) == 2 or len(gen) == 2:
        out += ["## Graph ON vs OFF", ""]
        rows = []
        if len(ret) == 2:
            on, off = sc.summarise_retrieval(ret["graph"]), sc.summarise_retrieval(ret["vector"])
            rows.append(["retrieval recall@5", pct(on["recall"]), pct(off["recall"])])
            rows.append(["forbidden ids returned", on["forbidden"], off["forbidden"]])
        if len(gen) == 2:
            on, off = sc.summarise_generation(gen["graph"]), sc.summarise_generation(gen["vector"])
            rows.append(["answers with key facts", pct(on["must_include"]),
                         pct(off["must_include"])])
            rows.append(["claims cited", pct(on["cited"]), pct(off["cited"])])
            rows.append(["refusals correct", pct(on["refusal_ok"]), pct(off["refusal_ok"])])
        out += [sc.markdown_table(["metric", "Graph ON", "Graph OFF"], rows), ""]

    leak = results.get("leaks")
    if leak is not None:
        out += ["## Permission leak check (must be 0)", "",
                sc.markdown_table(["persona", "probe questions", "forbidden ids returned"],
                                  [[r["persona"], r["probes"], ", ".join(r["leaks"]) or "0"]
                                   for r in leak]), ""]

    failures = []
    for m, rows in ret.items():
        failures += [f"- retrieval/{m} {r['id']}: recall {pct(r['recall'])}, "
                     f"forbidden {r['forbidden']}"
                     for r in rows if (r["recall"] is not None and r["recall"] < 1)
                     or r["forbidden"]]
    for m, rows in gen.items():
        failures += [f"- generation/{m} {r['id']}: facts {pct(r['must_include'])}, "
                     f"cited {pct(r['cited'])}, refusal_ok {r['refusal_ok']}, "
                     f"forbidden {r['forbidden']} {r.get('error') or ''}".rstrip()
                     for r in rows if not r["refusal_ok"] or r["forbidden"] or r.get("error")
                     or (r["must_include"] or 1) < 1 or (r["cited"] or 1) < 1]
    out += ["## What failed (read this first)", ""] + (failures[:60] or ["Nothing failed."])
    if meta.get("notes"):
        out += ["", "## Notes", ""] + [f"- {n}" for n in meta["notes"]]
    return "\n".join(out) + "\n"


def append_history(path: Path, results: dict[str, Any], meta: dict[str, Any]) -> None:
    """One CSV line per mode, so progress over the days can be plotted."""
    leaks = sum(len(r["leaks"]) for r in results.get("leaks") or [])
    new_file = not path.exists()
    with path.open("a", newline="") as f:
        writer = csv.writer(f)
        if new_file:
            writer.writerow(HISTORY_COLUMNS)
        for mode in meta["modes"]:
            r = sc.summarise_retrieval(results["retrieval"][mode]) if mode in results.get(
                "retrieval", {}) else {}
            g = sc.summarise_generation(results["generation"][mode]) if mode in results.get(
                "generation", {}) else {}
            i = sc.summarise_investigations(results["investigations"][mode]) if mode in results.get(
                "investigations", {}) else {}
            writer.writerow([
                meta["when"], mode, meta["n_cases"], _num(r.get("recall")), r.get("forbidden", ""),
                _num(g.get("must_include")), _num(g.get("cited")), _num(g.get("refusal_ok")),
                g.get("forbidden", ""), _num(i.get("root_cause")), leaks, meta["llm"],
            ])


def _num(v):
    return "" if v is None else round(v, 4)


# --------------------------------------------------------------------------- main


def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Lore eval harness")
    p.add_argument("--mode", choices=["graph", "vector", "both"], default="both")
    p.add_argument("--layer", choices=["retrieval", "generation", "investigations", "all"],
                   default="all")
    p.add_argument("--limit", type=int, default=None, help="only the first N golden questions")
    p.add_argument("--runs", type=int, default=1, help="repeats per investigation (plan: 5)")
    p.add_argument("--fake-llm", action="store_true", help="offline embeddings; no generation")
    p.add_argument("--out", type=Path, default=EVAL_DIR / "report.md")
    return p.parse_args(argv)


async def amain(args: argparse.Namespace) -> int:
    from lore import db
    from lore.config import get_settings

    golden = load_jsonl(EVAL_DIR / "golden.jsonl")[: args.limit]
    investigations = load_jsonl(EVAL_DIR / "investigations.jsonl")
    if not golden:
        print("eval/golden.jsonl is missing or empty: nothing to evaluate.", file=sys.stderr)
        return 2
    try:
        graph = db.get_graph()
        graph.ro("RETURN 1")
    except Exception as exc:
        print(f"Cannot reach FalkorDB ({exc}). Start it and load the Kettle graph first.",
              file=sys.stderr)
        return 2

    settings = get_settings()
    if args.fake_llm:
        from lore.llm import FakeLLM

        llm, llm_name = FakeLLM(), "fake"
    else:
        from lore.llm import get_llm

        llm, llm_name = get_llm(settings), settings.model_pro

    modes = ["graph", "vector"] if args.mode == "both" else [args.mode]
    layers = ["retrieval", "generation", "investigations"] if args.layer == "all" else [args.layer]
    notes: list[str] = []
    if args.fake_llm and ("generation" in layers or "investigations" in layers):
        layers = [name for name in layers if name == "retrieval"]
        notes.append("--fake-llm can only run the retrieval layer; other layers were skipped.")
    if "investigations" in layers and not investigations:
        layers.remove("investigations")
        notes.append("eval/investigations.jsonl is missing or empty: investigations skipped.")

    results: dict[str, Any] = {"retrieval": {}, "generation": {}, "investigations": {}}
    for mode in modes:
        if "retrieval" in layers:
            results["retrieval"][mode] = await run_retrieval(golden, graph, llm, mode)
        if "generation" in layers:
            results["generation"][mode] = await run_generation(golden, graph, llm, mode)
        if "investigations" in layers:
            results["investigations"][mode] = await run_investigations(
                investigations, graph, llm, mode, args.runs)
    results["leaks"] = await run_leak_check(golden, graph, llm)

    meta = {"when": datetime.now().strftime("%Y-%m-%d %H:%M"), "modes": modes, "layers": layers,
            "llm": llm_name, "n_cases": len(golden), "notes": notes}
    args.out.write_text(render_report(results, meta))
    append_history(EVAL_DIR / "history.csv", results, meta)
    print(f"wrote {args.out} and appended to {EVAL_DIR / 'history.csv'}")
    leaks = sum(len(r["leaks"]) for r in results["leaks"])
    print(f"permission leaks: {leaks}")
    return 1 if leaks else 0


def main() -> None:
    sys.exit(asyncio.run(amain(parse_args())))


if __name__ == "__main__":
    main()
