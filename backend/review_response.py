"""Provider schema and content-free feedback for invalid review responses."""

from pydantic import ValidationError

from review_schema import ReviewExtraction


def review_response_format() -> dict:
    schema = ReviewExtraction.model_json_schema()

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
                   "document", "source_type"}
    return [
        ".".join(str(part) if isinstance(part, int) or part in safe_fields else "unbekanntes Feld" for part in issue["loc"])
        + ": " + issue["type"] for issue in exc.errors(include_input=False, include_context=False, include_url=False)[:5]
    ]

