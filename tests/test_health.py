def test_health_endpoint_reports_service_status(client):
    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["service"] == "DocFlow RAG API"
    assert "version" in payload
    assert "vector_db_ready" in payload


def test_stats_endpoint_reports_cache_metrics(client):
    response = client.get("/stats")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_queries"] == 0
    assert payload["cache_hits"] == 0
    assert payload["cache_size"] == 0
    assert payload["cache_enabled"] is True
