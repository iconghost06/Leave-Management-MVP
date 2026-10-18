"""H1 (SHOULD): /health is public and reports ok."""


def test_h1_health_without_token_returns_ok(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
