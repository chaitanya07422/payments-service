import os

os.environ.setdefault("ALLOW_MOCK_PROVIDER", "true")
os.environ.setdefault("PAYMENTS_KEY_SCANLEAD", "test-key")
os.environ.setdefault("PAYMENTS_ADMIN_KEY", "admin-key")

from fastapi.testclient import TestClient

from payments_service.main import create_app


def test_health_and_mock_checkout_and_grant():
    app = create_app()
    client = TestClient(app)
    h = client.get("/v1/health")
    assert h.status_code == 200
    assert h.json()["ok"] is True

    plans = client.get("/v1/products/scanlead/plans")
    assert plans.status_code == 200
    assert any(p["id"] == "pro_monthly" for p in plans.json()["plans"])

    co = client.post(
        "/v1/checkout",
        headers={"X-Product-Key": "test-key"},
        json={
            "product_id": "scanlead",
            "user_ref": "user-1",
            "plan_id": "pro_monthly",
            "success_url": "https://example.com/ok",
        },
    )
    assert co.status_code == 200
    assert co.json()["mock"] is True
    assert "checkout_url" in co.json()

    grant = client.post(
        "/v1/admin/grant",
        headers={"X-Admin-Key": "admin-key"},
        json={"product_id": "scanlead", "user_ref": "user-1", "plan": "pro", "days": 30},
    )
    assert grant.status_code == 200

    ent = client.get(
        "/v1/entitlements",
        params={"product_id": "scanlead", "user_ref": "user-1"},
        headers={"X-Product-Key": "test-key"},
    )
    assert ent.status_code == 200
    assert ent.json()["active"] is True
    assert ent.json()["plan"] == "pro"


def test_polar_webhook_applies_metadata():
    app = create_app()
    client = TestClient(app)
    payload = {
        "id": "evt_test_1",
        "type": "order.paid",
        "data": {
            "id": "ord_1",
            "metadata": {
                "product_id": "scanlead",
                "user_ref": "user-2",
                "plan_id": "pro_yearly",
            },
        },
    }
    res = client.post("/v1/webhooks/polar", json=payload)
    assert res.status_code == 200
    assert res.json()["ok"] == "applied"

    ent = client.get(
        "/v1/entitlements",
        params={"product_id": "scanlead", "user_ref": "user-2"},
        headers={"X-Product-Key": "test-key"},
    )
    assert ent.json()["plan"] == "pro"
