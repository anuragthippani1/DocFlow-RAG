from evaluation.runner import run_evaluation


def test_evaluation_runner_produces_metrics():
    report = run_evaluation("evaluation/dataset.sample.json", k=2)
    assert report["samples"] == 2
    assert "precision@2" in report
    assert "recall@2" in report
    assert "mrr" in report
    assert "rag_triad" in report
