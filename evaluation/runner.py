import json
from pathlib import Path
from typing import Any

from evaluation.metrics import (
    answer_correctness,
    mrr,
    precision_at_k,
    rag_triad_scores,
    recall_at_k,
)


def load_dataset(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def run_evaluation(dataset_path: str, k: int = 5) -> dict[str, Any]:
    rows = load_dataset(Path(dataset_path))
    if not rows:
        return {"message": "No evaluation samples found.", "samples": 0}

    precisions: list[float] = []
    recalls: list[float] = []
    correctness: list[float] = []
    retrieved_lists: list[list[str]] = []
    relevant_union: set[str] = set()

    for row in rows:
        retrieved = row.get("retrieved_sources") or []
        relevant = set(row.get("relevant_sources") or [])
        relevant_union |= relevant
        retrieved_lists.append(retrieved)
        precisions.append(precision_at_k(retrieved, relevant, k))
        recalls.append(recall_at_k(retrieved, relevant, k))
        correctness.append(
            answer_correctness(
                str(row.get("predicted_answer", "")),
                str(row.get("expected_answer", "")),
            )
        )

    triad = rag_triad_scores(
        context_relevance=sum(precisions) / len(precisions),
        groundedness=sum(correctness) / len(correctness),
        answer_relevance=sum(recalls) / len(recalls),
    )

    report = {
        "samples": len(rows),
        f"precision@{k}": round(sum(precisions) / len(precisions), 4),
        f"recall@{k}": round(sum(recalls) / len(recalls), 4),
        "mrr": round(mrr(retrieved_lists, relevant_union), 4),
        "answer_correctness_avg": round(sum(correctness) / len(correctness), 4),
        "rag_triad": triad,
    }
    return report


def write_report(report: dict[str, Any], output_path: str) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return path


if __name__ == "__main__":
    result = run_evaluation("evaluation/dataset.sample.json")
    target = write_report(result, "evaluation/reports/latest.json")
    print(json.dumps(result, indent=2))
    print(f"Report written to {target}")
