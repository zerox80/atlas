"""Contract collection API package and compatibility exports."""

from fastapi import APIRouter

from .collection_routes import router as collection_router
from .filters import build_contract_query
from .forms import (
    ensure_ai_supported_contract_file,
    parse_date_form,
    parse_float_form,
    parse_int_form,
    parse_tags_form,
    validate_contract_form,
    validation_error_detail,
)
from .overview_routes import router as overview_router


router = APIRouter()
router.include_router(overview_router)
router.include_router(collection_router)

__all__ = [
    "build_contract_query",
    "ensure_ai_supported_contract_file",
    "parse_date_form",
    "parse_float_form",
    "parse_int_form",
    "parse_tags_form",
    "router",
    "validate_contract_form",
    "validation_error_detail",
]
