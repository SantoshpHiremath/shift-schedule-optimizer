"""
tests/test_api.py
------------------

Tests the FastAPI service through its actual HTTP interface (FastAPI's
TestClient), verifying the solver + independent validator are wired
correctly end-to-end through the API layer, not just at the Python
function level.
"""

import pytest
from fastapi.testclient import TestClient

from src.api import create_app


@pytest.fixture
def client():
    return TestClient(create_app())


class TestHealth:
    def test_health_returns_200(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


class TestScheduleDefault:
    def test_schedule_default_returns_200(self, client):
        resp = client.post("/schedule/default", params={"num_staff": 15, "num_days": 7})
        assert resp.status_code == 200

    def test_schedule_default_is_independently_valid(self, client):
        resp = client.post("/schedule/default", params={"num_staff": 15, "num_days": 7})
        body = resp.json()
        assert body["independent_validation"]["valid"] is True
        assert body["independent_validation"]["violations"] == []

    def test_schedule_default_contains_assignments(self, client):
        resp = client.post("/schedule/default", params={"num_staff": 15, "num_days": 7})
        body = resp.json()
        assert len(body["schedule"]) > 0
        entry = body["schedule"][0]
        assert set(entry.keys()) == {"staff_id", "day", "shift"}


class TestScheduleCustom:
    def _minimal_request(self):
        return {
            "staff": [
                {"staff_id": "S00", "name": "A", "contract": "FULL_TIME", "qualified_for_night": True, "requested_days_off": []},
                {"staff_id": "S01", "name": "B", "contract": "FULL_TIME", "qualified_for_night": True, "requested_days_off": []},
                {"staff_id": "S02", "name": "C", "contract": "FULL_TIME", "qualified_for_night": True, "requested_days_off": []},
            ],
            "num_days": 3,
            "min_staff_early": 1,
            "min_staff_late": 1,
            "min_staff_night": 1,
        }

    def test_custom_schedule_solves_and_validates(self, client):
        resp = client.post("/schedule", json=self._minimal_request())
        assert resp.status_code == 200
        body = resp.json()
        assert body["solver_status"] in ("OPTIMAL", "FEASIBLE")
        assert body["independent_validation"]["valid"] is True

    def test_custom_schedule_reports_infeasible_when_impossible(self, client):
        req = self._minimal_request()
        req["min_staff_night"] = 10  # only 3 staff exist -- impossible
        resp = client.post("/schedule", json=req)
        body = resp.json()
        assert body["solver_status"] == "INFEASIBLE"
        assert body["schedule"] == []

    def test_custom_schedule_rejects_too_many_days(self, client):
        req = self._minimal_request()
        req["num_days"] = 999  # exceeds the Field(le=28) validation limit
        resp = client.post("/schedule", json=req)
        assert resp.status_code == 422

    def test_custom_schedule_rejects_zero_min_staffing(self, client):
        req = self._minimal_request()
        req["min_staff_early"] = 0  # exceeds the Field(gt=0) validation limit
        resp = client.post("/schedule", json=req)
        assert resp.status_code == 422


class TestNotFound:
    def test_unknown_route_returns_404(self, client):
        resp = client.get("/nonexistent")
        assert resp.status_code == 404
