"""Strict, versioned extraction records; contract storage remains unchanged."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic_core import PydanticCustomError

ReviewStatus = Literal[
    "CONFIRMED", "EXPLICIT_CONFLICT", "NOT_EVIDENCED", "NEW_INFORMATION",
    "AMBIGUOUS", "DERIVED", "WRONG_SCOPE",
]
SourceType = Literal["contract", "amendment", "order_confirmation", "invoice", "delivery_note", "unknown"]
Scope = Literal[
    "title", "description", "tags", "contract_value_net", "contract_value_gross",
    "invoice_total_net", "invoice_total_gross", "recurring_amount", "annual_value",
    "line_item_net", "line_item_gross", "unit_price", "currency", "tax_rate",
    "billing_interval", "contract_start_date", "service_start_date", "invoice_date",
    "order_date", "delivery_date", "contract_end_date", "notice_period",
]
MONEY_SCOPES = {
    "contract_value_net", "contract_value_gross", "invoice_total_net", "invoice_total_gross",
    "recurring_amount", "annual_value", "line_item_net", "line_item_gross", "unit_price",
}
DATE_SCOPES = {
    "contract_start_date", "service_start_date", "invoice_date", "order_date",
    "delivery_date", "contract_end_date",
}
REVIEW_FIELDS = ("title", "description", "value", "annual_value", "start_date", "end_date", "notice_period", "tags")
PIPELINE_VERSION = 3


class StrictRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, strict=True)


class Evidence(StrictRecord):
    document: int = Field(default=1, ge=1)
    page: int = Field(ge=1)
    quote: str = Field(min_length=1, max_length=2000)


class Observation(StrictRecord):
    scope: Scope
    value: float | int | str | list[str]
    kind: Literal["explicit", "derived", "ambiguous"]
    confidence: float = Field(ge=0, le=1)
    reason: str = Field(min_length=1, max_length=1000)
    evidence: Evidence | None
    entity: Literal["document", "line_item", "other_source"]
    source_type: SourceType | None = None
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    billing_interval: Literal["month", "quarter", "year", "once", "unknown"] | None = None

    @model_validator(mode="after")
    def validate_value(self):
        value = self.value
        if self.scope in MONEY_SCOPES | {"tax_rate", "notice_period"}:
            if type(value) not in {int, float} or not 0 <= value <= 1_000_000_000_000_000:
                raise PydanticCustomError("review_number", "Betrag oder Frist muss eine nichtnegative JSON-Zahl sein")
            if self.scope == "tax_rate" and value > 100:
                raise PydanticCustomError("review_tax", "Steuersatz muss zwischen 0 und 100 Prozent liegen")
            if self.scope == "notice_period" and (int(value) != value or value > 36_500):
                raise PydanticCustomError("review_days", "Kündigungsfrist muss in ganzen Tagen vorliegen (maximal 36500)")
        elif self.scope == "tags":
            if not isinstance(value, list) or len(value) > 50 or any(not 0 < len(tag.strip()) <= 50 for tag in value):
                raise PydanticCustomError("review_tags", "Kategorien müssen eine Liste mit höchstens 50 kurzen Namen sein")
        elif not isinstance(value, str) or not value.strip() or len(value) > 2000:
            raise PydanticCustomError("review_text", "Textangabe muss zwischen 1 und 2000 Zeichen enthalten")
        if self.scope in DATE_SCOPES:
            try:
                date.fromisoformat(str(value))
                if len(str(value)) != 10:
                    raise ValueError()
            except ValueError as exc:
                raise PydanticCustomError("review_date", "Datum muss gültig sein und das Format YYYY-MM-DD haben") from exc
        if self.scope == "title" and len(str(value)) > 255:
            raise PydanticCustomError("review_title", "Titel darf höchstens 255 Zeichen enthalten")
        return self


class SplitPage(StrictRecord):
    document: int = Field(ge=1)
    page: int = Field(ge=1)


class DocumentSuggestion(StrictRecord):
    title: str = Field(min_length=1, max_length=255)
    document_type: Literal["contract", "invoice"]
    pages: list[SplitPage] = Field(min_length=1, max_length=1000)
    reason: str = Field(min_length=1, max_length=1000)
    evidence: Evidence
    observations: list[Observation] = Field(max_length=16)


class ReviewExtraction(StrictRecord):
    document_type: SourceType
    observations: list[Observation] = Field(max_length=64)
    warnings: list[str] = Field(max_length=20)
    document_suggestions: list[DocumentSuggestion] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def bounded_warnings(self):
        if any(len(warning) > 1000 for warning in self.warnings):
            raise ValueError("Warning too long")
        return self
