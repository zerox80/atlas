"""Strict, versioned extraction records; contract storage remains unchanged."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

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
PIPELINE_VERSION = 2


class StrictRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, strict=True)


class Evidence(StrictRecord):
    page: int = Field(ge=1)
    quote: str = Field(min_length=1, max_length=2000)


class Observation(StrictRecord):
    scope: Scope
    value: float | int | str | list[str]
    kind: Literal["explicit", "derived", "ambiguous"]
    confidence: float = Field(ge=0, le=1)
    reason: str = Field(min_length=1, max_length=1000)
    evidence: Evidence | None
    entity: Literal["document", "component", "other_contract"]
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    billing_interval: Literal["month", "quarter", "year", "once", "unknown"] | None = None

    @model_validator(mode="after")
    def validate_value(self):
        value = self.value
        if self.scope in MONEY_SCOPES | {"tax_rate", "notice_period"}:
            if type(value) not in {int, float} or not 0 <= value <= 1_000_000_000_000_000:
                raise ValueError("Amounts and durations must be nonnegative JSON numbers")
            if self.scope == "tax_rate" and value > 100:
                raise ValueError("Tax rate must be a percentage")
            if self.scope == "notice_period" and (int(value) != value or value > 36_500):
                raise ValueError("Notice period must be whole days")
        elif self.scope == "tags":
            if not isinstance(value, list) or len(value) > 50 or any(not 0 < len(tag.strip()) <= 50 for tag in value):
                raise ValueError("Invalid categories")
        elif not isinstance(value, str) or not value.strip() or len(value) > 2000:
            raise ValueError("Expected a nonempty string")
        if self.scope in DATE_SCOPES:
            date.fromisoformat(str(value))
            if len(str(value)) != 10:
                raise ValueError("Dates must be YYYY-MM-DD")
        if self.scope == "title" and len(str(value)) > 255:
            raise ValueError("Title too long")
        return self


class Component(StrictRecord):
    name: str = Field(min_length=1, max_length=255)
    evidence: Evidence
    amount_net: float | None = Field(default=None, ge=0, le=1_000_000_000_000_000)
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    separate_contract_reasons: list[Literal[
        "different_contract_number", "different_counterparty", "independent_term",
        "independent_termination", "independent_renewal", "independent_obligation",
    ]] = Field(default_factory=list, max_length=6)


class ReviewExtraction(StrictRecord):
    document_type: SourceType
    observations: list[Observation] = Field(max_length=200)
    components: list[Component] = Field(max_length=100)
    warnings: list[str] = Field(max_length=20)

    @model_validator(mode="after")
    def bounded_warnings(self):
        if any(len(warning) > 1000 for warning in self.warnings):
            raise ValueError("Warning too long")
        return self
