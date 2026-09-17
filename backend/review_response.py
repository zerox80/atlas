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
    safe_fields = {"document_type", "observations", "components", "warnings", "scope", "value", "kind", "confidence",
                   "reason", "evidence", "entity", "currency", "billing_interval", "page", "quote", "name",
                   "amount_net", "separate_contract_reasons"}
    return [
        ".".join(str(part) if isinstance(part, int) or part in safe_fields else "unbekanntes Feld" for part in issue["loc"])
        + ": " + issue["type"] for issue in exc.errors(include_input=False, include_context=False, include_url=False)[:5]
    ]


def correction_prompt(exc: Exception) -> str:
    issues = "; ".join(validation_issues(exc)) if isinstance(exc, ValidationError) else "unvollständiges oder ungültiges JSON"
    return (
        "Die vorherige Antwort konnte nicht validiert werden: " + issues + ". "
        "Extrahiere den ursprünglichen OCR-Abschnitt erneut vollständig gemäß dem Schema. "
        "Alle Pflichtfelder müssen vorhanden sein. observations enthält ausschließlich Objekte, keine Zeichenketten. "
        "Jede Beobachtung benötigt entity und evidence; components und warnings sind auch als leere Listen anzugeben. "
        "Behalte alle belegten Angaben bei. Erfinde keine Werte oder Belege, um das Schema zu erfüllen. "
        "Gib nur das vollständige JSON-Objekt zurück."
    )
