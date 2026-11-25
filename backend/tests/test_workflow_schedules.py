"""Offline contracts for workflow schedules (Scheduler spec, phase 1).

Phase 1 is configuration only: CRUD, validation, pause/resume and
next-run previews. Covers the pure time engine (timezone math, monthly
day-31 skipping, cron weekday rules) and the owner-scoped API surface.
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.services.schedule_time import ScheduleInvalid, compute_next_runs

BASE = "/api/v1/ai/workflow-schedules"
AFTER = datetime(2026, 11, 25, 3, 0, tzinfo=UTC)  # 10:00 in Ho Chi Minh


def engine(**overrides):
    kwargs = {
        "schedule_type": "daily",
        "config": {"hour": 8, "minute": 0},
        "cron_expression": None,
        "timezone": "Asia/Ho_Chi_Minh",
        "start_at": None,
        "end_at": None,
        "after": AFTER,
        "count": 3,
    }
    kwargs.update(overrides)
    return compute_next_runs(**kwargs)


def test_daily_runs_are_in_the_schedule_timezone():
    runs = engine()
    assert [run.strftime("%H:%M") for run in runs] == ["08:00"] * 3
    assert runs[0].utcoffset() == timedelta(hours=7)
    assert runs[0].day == 26  # 08:00 on the 25th already passed at 10:00


def test_weekly_skips_to_the_next_matching_weekday():
    runs = engine(
        schedule_type="weekly", config={"hour": 9, "minute": 0, "weekdays": [1]}
    )
    assert all(run.isoweekday() == 1 for run in runs)
    assert runs[0].day == 30  # Monday 30/11/2026


def test_monthly_day_31_skips_months_without_that_day():
    runs = engine(
        schedule_type="monthly", config={"hour": 8, "minute": 0, "day_of_month": 31}
    )
    assert [(run.month, run.day) for run in runs] == [(12, 31), (1, 31), (3, 31)]


def test_cron_weekday_expression_skips_the_weekend():
    runs = engine(schedule_type="cron", config={}, cron_expression="0 8 * * 1-5")
    assert all(run.isoweekday() <= 5 for run in runs)


def test_once_in_the_past_produces_no_runs():
    runs = engine(
        schedule_type="once", config={"run_at": "2026-11-20T14:00:00"}, count=1
    )
    assert runs == []


def test_invalid_cron_is_rejected():
    with pytest.raises(ScheduleInvalid):
        engine(schedule_type="cron", config={}, cron_expression="99 8 * * *")


def test_unknown_timezone_is_rejected():
    with pytest.raises(ScheduleInvalid):
        engine(timezone="Mars/Olympus")


@pytest.fixture
def owner(client, register):
    assert register(client).status_code == 201
    return client


def payload(**overrides):
    body = {
        "name": "Digest sáng thứ Hai",
        "description": "Chạy factory mỗi sáng thứ Hai",
        "factory_request": {"requirement": "Viết bản tin tuần", "domain": ["news"]},
        "schedule_type": "weekly",
        "config": {"hour": 7, "minute": 30, "weekdays": [1]},
        "timezone": "Asia/Ho_Chi_Minh",
    }
    body.update(overrides)
    return body


def test_create_computes_next_run_and_description(owner):
    created = owner.post(BASE, json=payload())
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["status"] == "active"
    assert body["next_run_at"] is not None
    assert "Thứ Hai" in body["description_text"]
    assert body["run_count"] == 0


def test_create_once_in_the_past_is_rejected(owner):
    past = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    created = owner.post(
        BASE, json=payload(schedule_type="once", config={"run_at": past})
    )
    assert created.status_code == 422
    assert created.json()["detail"]["code"] == "schedule_in_past"


def test_create_with_invalid_cron_is_rejected(owner):
    created = owner.post(
        BASE,
        json=payload(schedule_type="cron", config={}, cron_expression="0 25 * * *"),
    )
    assert created.status_code == 422
    assert created.json()["detail"]["code"] == "schedule_invalid"


def test_list_stats_pause_resume_and_delete(owner):
    first = owner.post(BASE, json=payload()).json()
    owner.post(BASE, json=payload(name="Lịch hai", schedule_type="daily",
                                  config={"hour": 8, "minute": 0}))
    listing = owner.get(BASE).json()
    assert listing["total"] == 2
    assert listing["stats"] == {"total": 2, "active": 2, "paused": 0, "completed": 0}

    paused = owner.post(f"{BASE}/{first['id']}/pause").json()
    assert paused["status"] == "paused"
    assert paused["next_run_at"] is None

    resumed = owner.post(f"{BASE}/{first['id']}/resume").json()
    assert resumed["status"] == "active"
    assert resumed["next_run_at"] is not None

    assert owner.delete(f"{BASE}/{first['id']}").status_code == 204
    assert owner.get(f"{BASE}/{first['id']}").status_code == 404


def test_patch_recomputes_next_run(owner):
    created = owner.post(BASE, json=payload()).json()
    patched = owner.patch(
        f"{BASE}/{created['id']}",
        json={"config": {"hour": 9, "minute": 0, "weekdays": [3]}},
    )
    assert patched.status_code == 200
    assert "Thứ Tư" in patched.json()["description_text"]


def test_preview_returns_five_runs_and_warnings(owner):
    preview = owner.post(
        f"{BASE}/preview",
        json={
            "schedule_type": "monthly",
            "config": {"hour": 8, "minute": 0, "day_of_month": 31},
            "timezone": "Asia/Ho_Chi_Minh",
        },
    )
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert len(body["next_runs"]) == 5
    assert any("bỏ qua" in warning for warning in body["warnings"])


def test_schedules_are_owner_scoped(owner, client, register):
    created = owner.post(BASE, json=payload()).json()
    assert register(client, email="second@example.com").status_code == 201
    assert client.get(f"{BASE}/{created['id']}").status_code == 404
    assert client.get(BASE).json()["total"] == 0
