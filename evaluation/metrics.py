from typing import Any


def precision_at_k(retrieved: list[str], relevant: set[str], k: int) -> float:
    if k <= 0:
        return 0.0
    top = retrieved[:k]
    if not top:
        return 0.0
    hits = sum(1 for item in top if item in relevant)
    return hits / len(top)


def recall_at_k(retrieved: list[str], relevant: set[str], k: int) -> float:
    if not relevant:
        return 0.0
    top = retrieved[:k]
    hits = sum(1 for item in top if item in relevant)
    return hits / len(relevant)


def mrr(retrieved_lists: list[list[str]], relevant: set[str]) -> float:
    for ranked in retrieved_lists:
        for idx, item in enumerate(ranked, start=1):
            if item in relevant:
                return 1.0 / idx
    return 0.0


def rag_triad_scores(
    *,
    context_relevance: float,
    groundedness: float,
    answer_relevance: float,
) -> dict[str, float]:
    return {
        "context_relevance": context_relevance,
        "groundedness": groundedness,
        "answer_relevance": answer_relevance,
        "triad_average": round(
            (context_relevance + groundedness + answer_relevance) / 3, 4
        ),
    }


def answer_correctness(predicted: str, expected: str) -> float:
    pred_tokens = set(predicted.lower().split())
    exp_tokens = set(expected.lower().split())
    if not exp_tokens:
        return 0.0
    overlap = pred_tokens & exp_tokens
    return round(len(overlap) / len(exp_tokens), 4)
