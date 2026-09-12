"""Stored-date validation and legacy SQLite query resilience."""

from datetime import datetime, timezone

import pytest
from api_core import ensure_default_workspace, limiter
from contract_queries.business_time import sqlite_business_cancellation_julianday
from contract_queries.forms import parse_date_form
from main import app, get_current_user
from models import Contract, ContractPermission
from sqlmodel import select


@pytest.fixture(autouse=True)
def isolated_uploads(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    limiter.reset()


@pytest.mark.parametrize(
    "value",
    [
        "9999-12-31T23:59:59Z",
        "9999-12-31T22:59:59-01:00",
        "99991231T235959Z",
        "0001-01-01",
        "0001-01-01T00:00:00+01:00",
        "0001-01-02T12:00:00Z",
    ],
)
def test_create_rejects_unsafe_dates(auth_client, session, test_user, value):
    workspace = ensure_default_workspace(session, test_user.id)
    session.commit()
    response = auth_client.post(
        "/contracts",
        data={"title": "Invalid", "end_date": value, "list_id": workspace.id},
        files={"file": ("test.txt", b"plain text", "text/plain")},
    )
    assert response.status_code == 422, response.text
    assert session.exec(select(Contract)).all() == []


@pytest.mark.parametrize(
    "fields",
    [
        {"end_date": "9999-12-31T23:59:59Z"},
        {"end_date": "0001-01-02T12:00:00Z"},
        {"notice_period": "36500"},
    ],
)
def test_update_validates_merged_date_and_notice(
    auth_client, session, test_user, fields
):
    document = Contract(
        title="Original", file_path="uploads/test.txt",
        end_date=datetime(50, 1, 1, 12, tzinfo=timezone.utc), notice_period=30,
    )
    session.add(document)
    session.flush()
    session.add(ContractPermission(
        user_id=test_user.id, contract_id=document.id, permission_level="write"
    ))
    session.commit()
    response = auth_client.put(
        f"/contracts/{document.id}", data={"version": 1, **fields}
    )
    assert response.status_code == 422, response.text
    session.refresh(document)
    assert document.end_date.replace(tzinfo=timezone.utc) == datetime(
        50, 1, 1, 12, tzinfo=timezone.utc
    )
    assert document.notice_period == 30
    assert document.version == 1


@pytest.mark.parametrize(
    "value,notice",
    [
        ("9999-12-31T23:59:59Z", 30),
        ("0001-01-02T12:00:00Z", 30),
        ("0001-01-01T12:00:00Z", 0),
        ("2026-01-01T12:00:00Z", 10**30),
        ("invalid", 30),
        (None, 30),
    ],
)
def test_legacy_invalid_deadlines_are_unknown(value, notice):
    assert sqlite_business_cancellation_julianday(value, notice) is None


def test_legacy_dates_do_not_break_admin_views(client, session, admin_user, test_user):
    connection = session.connection().connection.driver_connection
    connection.create_function(
        "business_cancellation_julianday", 2, sqlite_business_cancellation_julianday
    )
    for end_date in [
        datetime(9999, 12, 31, 23, 59, 59, tzinfo=timezone.utc),
        datetime(1, 1, 2, 12, tzinfo=timezone.utc),
    ]:
        session.add(Contract(
            title="Legacy invalid date", file_path="uploads/test.txt",
            end_date=end_date, owner_user_id=test_user.id,
        ))
    session.commit()
    app.dependency_overrides[get_current_user] = lambda: admin_user
    for endpoint in [
        "/contracts/dashboard",
        "/contracts/page",
        "/contracts/calendar?start=2026-09-01&end=2026-10-01",
    ]:
        response = client.get(endpoint)
        assert response.status_code == 200, response.text
    dashboard = client.get("/contracts/dashboard").json()
    assert dashboard["summary"]["document_count"] == 2
    assert dashboard["summary"]["deadline_count"] == 0


@pytest.mark.parametrize("notice", [0, 30, 36500])
def test_normal_dates_remain_writable(auth_client, session, test_user, notice):
    workspace = ensure_default_workspace(session, test_user.id)
    session.commit()
    response = auth_client.post(
        "/contracts",
        data={
            "title": "Ordinary", "end_date": "2026-10-25",
            "notice_period": notice, "list_id": workspace.id,
        },
        files={"file": ("test.txt", b"plain text", "text/plain")},
    )
    assert response.status_code == 200, response.text
    document = response.json()
    response = auth_client.put(
        f"/contracts/{document['id']}",
        data={"version": document["version"], "end_date": "2026-11-01"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["end_date"] == "2026-10-31T23:00:00"


def test_timezone_and_dst_semantics_remain_intact():
    assert parse_date_form("") is None
    assert parse_date_form("2026-10-25") == datetime(2026, 10, 24, 22, tzinfo=timezone.utc)
    assert parse_date_form("2026-10-25T12:00:00+01:00") == datetime(
        2026, 10, 25, 11, tzinfo=timezone.utc
    )
    # Thirty local calendar days before the DST transition: midnight CEST.
    expected = datetime(2026, 9, 25, tzinfo=timezone.utc).timestamp() - 7200
    assert sqlite_business_cancellation_julianday(
        "2026-10-25T12:00:00Z", None
    ) == pytest.approx(expected / 86400 + 2440587.5)
