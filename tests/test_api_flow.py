"""Kiểm thử luồng nghiệp vụ đầy đủ qua API: đăng nhập -> dữ liệu -> dự báo -> AI -> kịch bản -> báo cáo."""

from __future__ import annotations

TRAIN_MODELS = ["seasonal_naive", "moving_average", "gradient_boosting"]


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] in {"sqlite", "postgresql"}


def test_login_with_wrong_password_is_rejected(client):
    response = client.post("/api/auth/login", json={"email": "admin@example.com", "password": "sai-mat-khau"})
    assert response.status_code == 401


def test_protected_endpoint_requires_token(client):
    assert client.get("/api/dashboard/summary").status_code == 401


def test_admin_profile(client, auth_headers):
    response = client.get("/api/auth/me", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["role"] == "admin"


def test_models_catalog(client, auth_headers):
    response = client.get("/api/forecast/models", headers=auth_headers)
    assert response.status_code == 200
    catalog = {item["name"]: item for item in response.json()}
    assert "prophet" in catalog
    assert catalog["seasonal_naive"]["available"] is True


def test_viewer_cannot_train(client, auth_headers):
    created = client.post(
        "/api/users",
        headers=auth_headers,
        json={
            "email": "viewer@example.com",
            "password": "Viewer@12345",
            "full_name": "Chỉ xem",
            "role": "viewer",
        },
    )
    assert created.status_code in (201, 409)

    login = client.post(
        "/api/auth/login", json={"email": "viewer@example.com", "password": "Viewer@12345"}
    )
    assert login.status_code == 200
    viewer_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    # Viewer xem được dashboard nhưng không được huấn luyện
    assert client.get("/api/dashboard/summary", headers=viewer_headers).status_code == 200
    forbidden = client.post(
        "/api/forecast/train", headers=viewer_headers, json={"horizon": 7, "wait": True}
    )
    assert forbidden.status_code == 403


def test_data_stats_after_seeding(client, auth_headers, seeded_data):
    assert seeded_data["rows_inserted"] > 0
    response = client.get("/api/data/stats", headers=auth_headers)
    assert response.status_code == 200
    stats = response.json()
    assert stats["total_rows"] > 0
    assert stats["products"] == 3
    assert stats["regions"] == 2
    assert stats["channels"] == 2


def test_dashboard_summary(client, auth_headers, seeded_data):
    response = client.get("/api/dashboard/summary", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["total_units"] > 0
    assert len(body["kpis"]) >= 5


def test_full_forecast_flow(client, auth_headers, seeded_data):
    # --- Huấn luyện (chạy đồng bộ để test) ---
    train = client.post(
        "/api/forecast/train",
        headers=auth_headers,
        json={
            "name": "Kiểm thử tự động",
            "models": TRAIN_MODELS,
            "horizon": 14,
            "granularity": "product",
            "backtest_folds": 2,
            "test_size": 14,
            "wait": True,
        },
    )
    assert train.status_code == 202, train.text
    run = train.json()
    assert run["status"] == "completed", run.get("error_message")
    run_id = run["id"]
    assert run["metrics"]["mape"] is not None
    assert run["leaderboard"]

    # --- So sánh mô hình ---
    leaderboard = client.get(f"/api/forecast/runs/{run_id}/leaderboard", headers=auth_headers)
    assert leaderboard.status_code == 200
    body = leaderboard.json()
    assert body["leaderboard"]
    assert any(item["is_best"] for item in body["leaderboard"])

    # --- Kết quả dự báo ---
    result = client.get(f"/api/forecast/runs/{run_id}/result", headers=auth_headers)
    assert result.status_code == 200
    payload = result.json()
    assert payload["points"], "Phải có điểm dự báo"
    assert payload["total_forecast_units"] > 0
    assert payload["history"], "Phải có dữ liệu lịch sử để đối chiếu"

    # --- AI giải thích (fallback vì LLM_PROVIDER=none) ---
    explain = client.post("/api/ai/explain", headers=auth_headers, json={"run_id": run_id})
    assert explain.status_code == 200, explain.text
    explanation = explain.json()
    assert explanation["summary"]
    assert explanation["reasons"]
    assert explanation["recommended_actions"]
    assert explanation["provider"] == "fallback"
    assert explanation["grounded_numbers"]["total_forecast_units"] > 0
    assert explanation["warnings"] == []

    # Lần gọi thứ 2 phải lấy từ cache
    cached = client.post("/api/ai/explain", headers=auth_headers, json={"run_id": run_id})
    assert cached.status_code == 200
    assert cached.json()["cached"] is True

    # --- Scenario planning ---
    scenario = client.post(
        "/api/scenario",
        headers=auth_headers,
        json={
            "base_run_id": run_id,
            "name": "Tăng khuyến mãi 20%",
            "assumptions": {
                "promo_uplift_pct": 20,
                "price_change_pct": -5,
                "demand_shift_pct": 5,
                "lead_time_days": 10,
                "safety_stock_pct": 30,
            },
        },
    )
    assert scenario.status_code == 201, scenario.text
    scenario_body = scenario.json()
    assert scenario_body["status"] == "completed"
    assert scenario_body["summary"]["scenario_total_units"] > 0
    assert scenario_body["points"]
    assert scenario_body["inventory_plan"]

    # --- Cảnh báo ---
    alerts = client.post("/api/alerts/recompute", headers=auth_headers)
    assert alerts.status_code == 200, alerts.text

    listed = client.get("/api/alerts", headers=auth_headers)
    assert listed.status_code == 200

    # --- Xuất báo cáo ---
    for export_format, expected_prefix in (
        ("xlsx", b"PK"),
        ("csv", b"\xef\xbb\xbf"),  # UTF-8 BOM cho Excel
        ("pdf", b"%PDF"),
    ):
        exported = client.get(
            f"/api/reports/runs/{run_id}/export",
            headers=auth_headers,
            params={"format": export_format},
        )
        assert exported.status_code == 200, export_format
        assert exported.content.startswith(expected_prefix), export_format

    # --- Dữ liệu lịch sử theo ngày ---
    series = client.get("/api/data/daily-series", headers=auth_headers, params={"last_n": 30})
    assert series.status_code == 200
    assert len(series.json()["items"]) == 30
