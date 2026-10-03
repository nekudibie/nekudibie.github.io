"""Retrieval evaluation: measures recall@k and MRR of the vault's search on a labelled set.

Run with ``companion-vault eval`` (defaults to the fixture set in tests/fixtures/retrieval).
Numbers from this harness, not intuition, decide whether embeddings are worth adding (ADR 0002).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from companion_contracts.common import Provenance
from companion_contracts.vault import DocumentImport, SearchRequest
from companion_core.db import Database

from .service import VaultService


@dataclass
class EvalResult:
    queries: int
    recall_at_1: float
    recall_at_3: float
    recall_at_5: float
    mrr: float
    misses: list[dict[str, Any]] = field(default_factory=list)
    strategies: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "queries": self.queries,
            "recall_at_1": round(self.recall_at_1, 3),
            "recall_at_3": round(self.recall_at_3, 3),
            "recall_at_5": round(self.recall_at_5, 3),
            "mrr": round(self.mrr, 3),
            "strategies": self.strategies,
            "misses": self.misses,
        }


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def run_evaluation(corpus: list[dict[str, Any]], queries: list[dict[str, Any]], *, db_path: str | Path = ":memory:") -> EvalResult:
    svc = VaultService(Database(db_path))
    svc.migrate()
    id_map: dict[str, str] = {}
    for doc in corpus:
        imp = DocumentImport(
            title=doc.get("title", ""), text=doc["text"], kind=doc.get("kind", "note"),
            provenance=Provenance(source_type=doc.get("source_type", "note"), source_ref=doc["id"]),
            idempotency_key=f"eval:{doc['id']}",
        )
        id_map[doc["id"]] = svc.import_document(imp, actor="eval").id
    hits1 = hits3 = hits5 = 0
    rr_total = 0.0
    misses: list[dict[str, Any]] = []
    strategies: dict[str, int] = {}
    for q in queries:
        expected = {id_map[e] for e in q["expected"]}
        res = svc.search(SearchRequest(query=q["query"], limit=5), scopes=["owner", "shared"])
        strategies[res.strategy] = strategies.get(res.strategy, 0) + 1
        ranked_docs: list[str] = []
        for h in res.hits:
            if h.document_id not in ranked_docs:
                ranked_docs.append(h.document_id)
        rank = next((i for i, d in enumerate(ranked_docs, start=1) if d in expected), None)
        if rank is not None:
            rr_total += 1.0 / rank
            hits1 += rank <= 1
            hits3 += rank <= 3
            hits5 += rank <= 5
        else:
            misses.append({"query": q["query"], "expected": q["expected"], "got": [k for k, v in id_map.items() if v in ranked_docs][:5], "strategy": res.strategy})
    n = max(1, len(queries))
    return EvalResult(len(queries), hits1 / n, hits3 / n, hits5 / n, rr_total / n, misses, strategies)


def default_fixture_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "retrieval"
