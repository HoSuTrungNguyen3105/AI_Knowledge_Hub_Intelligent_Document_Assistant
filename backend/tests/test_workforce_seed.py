"""Offline contracts for the workforce employee seed
(POST/DELETE /ai/seed/workforce).

Seeds the 50 demo employees from app/seed_data/workforce_employees.json
into the caller's own resources: idempotent by name, flagged is_demo,
removal touches only seeded records, and production refuses with
seed_disabled exactly like the demo seed.
"""

import pytest

SEED = "/api/v1/ai/seed/workforce"
RESOURCES = "/api/v1/ai/resources"


@pytest.fixture(autouse=True)
def dev_env(settings):
    settings.app_env = "development"


@pytest.fixture
def owner(client, register):
    assert register(client).status_code == 201
    return client


@pytest.fixture
def second(client_factory, register):
    client = client_factory()
    assert register(client, email="Second@Example.com", name="Second User").status_code == 201
    return client


def human_count(client):
    return len(client.get(RESOURCES, params={"type": "human"}).json()["resources"])


def test_seed_creates_50_then_is_idempotent(owner):
    response = owner.post(SEED)
    assert response.status_code == 200, response.text
    assert response.json() == {"created": 50, "skipped": 0, "total": 50}
    assert human_count(owner) == 50

    response = owner.post(SEED)
    assert response.json() == {"created": 0, "skipped": 50, "total": 50}
    assert human_count(owner) == 50


def test_seed_employees_have_profiles(owner):
    owner.post(SEED)
    resources = owner.get(RESOURCES, params={"type": "human"}).json()["resources"]
    roles = {resource["role"] for resource in resources}
    assert "Frontend Developer" in roles
    assert "QA Engineer" in roles
    assert all(resource["human"]["experience_years"] >= 1 for resource in resources)
    assert all(len(resource["skills"]) >= 3 for resource in resources)


def test_seed_remove_only_touches_demo_records(owner):
    manual = owner.post(RESOURCES, json={
        "type": "human", "name": "Người Thật", "role": "Developer",
        "skills": [{"name": "Python", "level": 4}],
        "human": {"experience_years": 5, "hours_per_week": 40, "current_project_count": 1},
    })
    assert manual.status_code == 201
    owner.post(SEED)
    assert human_count(owner) == 51

    response = owner.delete(SEED)
    assert response.status_code == 200
    assert response.json() == {"removed": 50}
    remaining = owner.get(RESOURCES, params={"type": "human"}).json()["resources"]
    assert [resource["name"] for resource in remaining] == ["Người Thật"]


def test_seed_refused_in_production(owner, settings):
    settings.app_env = "production"
    response = owner.post(SEED)
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "seed_disabled"
    assert owner.delete(SEED).status_code == 403
    assert human_count(owner) == 0


def test_seed_is_owner_scoped(owner, second):
    owner.post(SEED)
    assert human_count(second) == 0
    response = second.post(SEED)
    assert response.json()["created"] == 50
    assert human_count(owner) == 50
    assert human_count(second) == 50
