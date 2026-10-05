"""Optional contract fields retain the distinction between unknown and zero."""

from datetime import UTC, datetime

import pytest
from sqlmodel import select

from api_core import ensure_default_workspace, limiter
from models import Contract, ContractPermission

OPTIONAL_FIELDS = (
    "start_date", "end_date", "value", "annual_value", "notice_period",
)


@pytest.fixture(autouse=True)
def isolated_uploads(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    limiter.reset()


@pytest.fixture
def workspace_id(session, test_user):
    workspace = ensure_default_workspace(session, test_user.id)
    session.commit()
    return workspace.id


@pytest.fixture
def existing_contract(session, test_user):
    document = Contract(
        title="Original",
        file_path="uploads/test.txt",
        start_date=datetime(2026, 1, 1, 12, tzinfo=UTC),
        end_date=datetime(2026, 12, 31, 12, tzinfo=UTC),
        value=1200.0,
        annual_value=600.0,
        notice_period=30,
    )
    session.add(document)
    session.flush()
    session.add(ContractPermission(
        user_id=test_user.id, contract_id=document.id, permission_level="write",
    ))
    session.commit()
    session.refresh(document)
    return document


def optional_values(document):
    return {field: getattr(document, field) for field in OPTIONAL_FIELDS}


def create_document(auth_client, workspace_id, fields):
    return auth_client.post(
        "/contracts",
        data={"title": "Optional fields", "list_id": workspace_id, **fields},
        files={"file": ("test.txt", b"plain text", "text/plain")},
    )


def update_document(auth_client, document_id, fields, encoding):
    data = {"version": 1, **fields}
    if encoding == "multipart":
        return auth_client.put(
            f"/contracts/{document_id}",
            files=[(name, (None, str(value))) for name, value in data.items()],
        )
    return auth_client.put(f"/contracts/{document_id}", data=data)


@pytest.mark.parametrize(
    "fields", [{}, dict.fromkeys(OPTIONAL_FIELDS, "")], ids=["omitted", "empty"],
)
def test_create_without_optional_fields_stores_null(
    auth_client, session, workspace_id, fields,
):
    response = create_document(auth_client, workspace_id, fields)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert {field: payload[field] for field in OPTIONAL_FIELDS} == dict.fromkeys(
        OPTIONAL_FIELDS,
    )
    document = session.get(Contract, payload["id"])
    assert optional_values(document) == dict.fromkeys(OPTIONAL_FIELDS)


def test_create_with_dates_and_value_does_not_require_notice_period(
    auth_client, session, workspace_id,
):
    response = create_document(auth_client, workspace_id, {
        "start_date": "2026-10-05",
        "end_date": "2050-01-01",
        "value": "1",
    })
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["start_date"] == "2026-10-04T22:00:00"
    assert payload["end_date"] == "2049-12-31T23:00:00"
    assert payload["value"] == 1.0
    assert payload["notice_period"] is None
    document = session.get(Contract, payload["id"])
    assert document.notice_period is None
    assert document.annual_value is None


@pytest.mark.parametrize("encoding", ["urlencoded", "multipart"])
@pytest.mark.parametrize("field", OPTIONAL_FIELDS)
def test_update_empty_field_clears_only_that_field(
    auth_client, session, existing_contract, field, encoding,
):
    expected = optional_values(existing_contract)
    expected[field] = None
    response = update_document(
        auth_client, existing_contract.id, {field: ""}, encoding,
    )
    assert response.status_code == 200, response.text
    assert response.json()[field] is None
    session.refresh(existing_contract)
    assert optional_values(existing_contract) == expected
    assert existing_contract.version == 2


@pytest.mark.parametrize("encoding", ["urlencoded", "multipart"])
def test_update_omitted_fields_keeps_existing_values(
    auth_client, session, existing_contract, encoding,
):
    expected = optional_values(existing_contract)
    response = update_document(
        auth_client, existing_contract.id, {"title": "Renamed"}, encoding,
    )
    assert response.status_code == 200, response.text
    session.refresh(existing_contract)
    assert existing_contract.title == "Renamed"
    assert optional_values(existing_contract) == expected
    assert existing_contract.version == 2


def test_create_explicit_zero_remains_zero(auth_client, session, workspace_id):
    fields = {"value": "0", "annual_value": "0", "notice_period": "0"}
    response = create_document(auth_client, workspace_id, fields)
    assert response.status_code == 200, response.text
    payload = response.json()
    document = session.get(Contract, payload["id"])
    for field in fields:
        assert payload[field] == 0
        assert getattr(document, field) == 0


def test_update_explicit_zero_remains_zero(auth_client, session, existing_contract):
    fields = {"value": "0", "annual_value": "0", "notice_period": "0"}
    response = update_document(auth_client, existing_contract.id, fields, "multipart")
    assert response.status_code == 200, response.text
    session.refresh(existing_contract)
    for field in fields:
        assert response.json()[field] == 0
        assert getattr(existing_contract, field) == 0
    assert existing_contract.version == 2


@pytest.mark.parametrize("fields", [
    {"start_date": "invalid"},
    {"end_date": "invalid"},
    {"value": "invalid"},
    {"value": "-1"},
    {"annual_value": "nan"},
    {"notice_period": "-1"},
])
def test_invalid_optional_fields_still_reject_create(
    auth_client, session, workspace_id, fields,
):
    response = create_document(auth_client, workspace_id, fields)
    assert response.status_code == 422, response.text
    assert session.exec(select(Contract)).all() == []


@pytest.mark.parametrize("fields", [
    {"start_date": "invalid"},
    {"end_date": "invalid"},
    {"value": "invalid"},
    {"value": "-1"},
    {"annual_value": "nan"},
    {"notice_period": "-1"},
])
def test_invalid_optional_fields_do_not_change_existing_contract(
    auth_client, session, existing_contract, fields,
):
    expected = optional_values(existing_contract)
    response = update_document(
        auth_client, existing_contract.id, {"title": "Rejected", **fields}, "multipart",
    )
    assert response.status_code == 422, response.text
    session.refresh(existing_contract)
    assert existing_contract.title == "Original"
    assert optional_values(existing_contract) == expected
    assert existing_contract.version == 1
