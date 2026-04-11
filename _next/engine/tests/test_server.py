from server import app


def test_missing_grammar_returns_404() -> None:
    client = app.test_client()
    resp = client.get("/api/grammar/does_not_exist")
    assert resp.status_code == 404
    assert "error" in resp.get_json()


def test_invalid_payload_returns_400_on_evaluate() -> None:
    client = app.test_client()
    resp = client.post("/api/evaluate", json={"seed": {}})
    assert resp.status_code == 400
    assert "error" in resp.get_json()

