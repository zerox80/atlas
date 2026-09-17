"""Provider schema and content-free feedback for invalid review responses."""

from copy import deepcopy
from typing import get_args

from pydantic import ValidationError

from review_schema import DATE_SCOPES, MONEY_SCOPES, ReviewExtraction, Scope


def review_response_format() -> dict:
    schema = ReviewExtraction.model_json_schema()
    observation = schema["$defs"]["Observation"]
    number = {"type": "number", "minimum": 0, "maximum": 1_000_000_000_000_000}
    # Describe the whole string, including spaces and newlines. A bare \S is
    # valid for JSON Schema's substring search, but permits only one character
    # when a constrained decoder uses it as the full generation grammar.
    nonblank_text = r"^[\s\S]*\S[\s\S]*$"
    text = {"type": "string", "minLength": 1, "maxLength": 2000, "pattern": nonblank_text}
    groups = [
        (MONEY_SCOPES, number),
        ({"tax_rate"}, {"type": "number", "minimum": 0, "maximum": 100}),
        ({"notice_period"}, {"type": "integer", "minimum": 0, "maximum": 36500}),
        (DATE_SCOPES, {"type": "string", "format": "date", "pattern": r"^\d{4}-\d{2}-\d{2}$"}),
        ({"title"}, {**text, "maxLength": 255}),
        ({"tags"}, {"type": "array", "maxItems": 50,
                      "items": {"type": "string", "minLength": 1, "maxLength": 50, "pattern": nonblank_text}}),
        (set(get_args(Scope)) - MONEY_SCOPES - DATE_SCOPES - {"tax_rate", "notice_period", "title", "tags"}, text),
    ]
    variants = []
    for scopes, value in groups:
        variant = deepcopy(observation)
        variant["properties"]["scope"] = {"type": "string", "enum": sorted(scopes)}
        variant["properties"]["value"] = value
        variants.append(variant)
    # Express scope/value relationships in the provider schema, not only a local validator.
    schema["$defs"]["Observation"] = {"anyOf": variants}

    def require_properties(node):
        if isinstance(node, dict):
            node.pop("default", None)
            if node.get("type") == "object":
                node["additionalProperties"] = False
                node["required"] = list(node.get("properties", {}))
            for child in node.values():
                require_properties(child)
        elif isinstance(node, list):
            for child in node:
                require_properties(child)

    require_properties(schema)
    # The Mistral SDK serializes schema_definition as the wire field "schema".
    return {"type": "json_schema", "json_schema": {
        "name": "ReviewExtraction", "schema_definition": schema, "strict": True,
    }}


def validation_issues(exc: ValidationError) -> list[str]:
    safe_fields = {"document_type", "observations", "warnings", "scope", "value", "kind", "confidence",
                   "reason", "evidence", "entity", "currency", "billing_interval", "page", "quote", "name",
                   "document", "source_type", "document_suggestions", "pages", "title"}
    return [
        ".".join(str(part) if isinstance(part, int) or part in safe_fields else "unbekanntes Feld" for part in issue["loc"])
        + ": " + (issue["msg"] if issue["type"].startswith("review_") else issue["type"])
        for issue in exc.errors(include_input=False, include_context=False, include_url=False)[:5]
    ]

