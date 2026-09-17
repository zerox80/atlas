"""The provider contract rejects the same malformed field types as local validation."""

import re
from copy import deepcopy

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from pydantic import ValidationError
from test_review_response import response
from test_review_semantics import observation

from review_response import review_response_format, validation_issues
from review_schema import ReviewExtraction


def wire_reply(fact):
    return ReviewExtraction.model_validate({"document_type": "contract", "observations": [fact], "warnings": []}).model_dump()


@pytest.mark.parametrize("scope,valid,invalid,reason", [
    ("invoice_total_gross", 119, "119,00 EUR", "JSON-Zahl"),
    ("tax_rate", 19, 119, "Prozent"),
    ("notice_period", 30, 1.5, "ganzen Tagen"),
    ("contract_start_date", "2018-03-01", "01.03.2018", "YYYY-MM-DD"),
    ("contract_start_date", "2018-03-01", "2018-02-30", "YYYY-MM-DD"),
    ("tags", ["Backup"], "Backup", "Liste"),
    ("title", "Cloud Backup", "x" * 256, "255"),
])
def test_field_types_are_enforced_before_and_after_generation(scope, valid, invalid, reason):
    schema = review_response_format()["json_schema"]["schema_definition"]
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    payload = wire_reply(observation(scope, valid, "PRIVATE_QUOTE"))
    validator.validate(payload)
    bad = deepcopy(payload)
    bad["observations"][0]["value"] = invalid
    assert list(validator.iter_errors(bad)), "The provider schema must reject invalid local field types"
    with pytest.raises(ValidationError) as raised:
        ReviewExtraction.model_validate(bad)
    feedback = " ".join(validation_issues(raised.value))
    assert "observations.0" in feedback and reason in feedback
    assert "PRIVATE_QUOTE" not in feedback and "value_error" not in feedback


@pytest.mark.parametrize("scope,value", [
    ("title", "ESET Protect Complete Lizenz-Erweiterung"),
    ("title", "IT"),
    ("title", "E.ON – Stromlieferung"),
    ("description", "ESET Protect Complete: zusätzliche Lizenzen.\nInklusive Wartung und Support."),
    ("description", "  Lizenz-Erweiterung mit Wartung.\n"),
    ("tags", "IT-Sicherheit"),
    ("tags", "Software und Wartung"),
    ("currency", "EUR"),
    ("billing_interval", "year"),
])
def test_text_patterns_allow_complete_values_during_generation(scope, value):
    schema = review_response_format()["json_schema"]["schema_definition"]
    variant = next(item for item in schema["$defs"]["Observation"]["anyOf"]
                   if scope in item["properties"]["scope"]["enum"])
    text_schema = variant["properties"]["value"]
    if scope == "tags":
        text_schema = text_schema["items"]
    # JSON Schema searches for a match; constrained generators may instead build
    # the entire string from this regex. Both must allow the complete field.
    assert re.fullmatch(text_schema["pattern"], value)
    payload = wire_reply(observation(scope, [value] if scope == "tags" else value, "Originalbeleg"))
    Draft202012Validator(schema).validate(payload)
    for blank in ("", " ", "\n\t"):
        assert not re.search(text_schema["pattern"], blank)
        with pytest.raises(ValidationError):
            wire_reply(observation(scope, [blank] if scope == "tags" else blank, "Originalbeleg"))


async def test_split_proposals_use_the_same_single_whole_document_response(monkeypatch):
    from unittest.mock import AsyncMock

    import review_analysis
    from review_analysis import Section, analyze_bundle

    reply = {"document_type": "unknown", "observations": [], "warnings": [], "document_suggestions": [
        {"title": title, "document_type": kind, "pages": [{"document": 1, "page": page}],
         "reason": "Eigenständig", "evidence": {"document": 1, "page": page, "quote": title}, "observations": []}
        for page, title, kind in [(1, "Veeam Rechnung", "invoice"), (2, "VMware Vertrag", "contract")]
    ]}
    complete = AsyncMock(return_value=response(reply))
    monkeypatch.setattr(review_analysis, "complete_chat_with_timeout", complete)
    monkeypatch.setattr(review_analysis, "get_client", lambda: object())
    result = await analyze_bundle([Section(1, "mixed.pdf", 1, 2, b"pdf", {1: "Veeam Rechnung", 2: "VMware Vertrag"})], lambda _: None)
    complete.assert_awaited_once()
    assert len(result[0]["split_proposals"]) == 2


@pytest.mark.parametrize("fault", ["overlap", "foreign_page", "empty_quote", "invented_quote"])
def test_unverified_splits_are_not_offered(fault):
    from review_schema import DocumentSuggestion
    from review_splits import verify_suggestions

    proposals = [{"title": title, "document_type": "invoice", "pages": [{"document": 1, "page": page}],
                  "reason": "Eigenständig", "evidence": {"document": 1, "page": page, "quote": title}, "observations": []}
                 for page, title in [(1, "Veeam"), (2, "VMware")]]
    if fault == "overlap":
        proposals[1]["pages"] = [{"document": 1, "page": 1}]
    if fault == "foreign_page":
        proposals[1]["pages"] = [{"document": 1, "page": 99}]
    if fault == "empty_quote":
        proposals[1]["evidence"]["quote"] = "   "
    if fault == "invented_quote":
        proposals[1]["evidence"]["quote"] = "Oracle"
    assert verify_suggestions([DocumentSuggestion.model_validate(proposal) for proposal in proposals],
                              {1: {1: "Veeam", 2: "VMware"}}, {1: "original.pdf"}) == []
