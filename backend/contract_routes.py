"""Compatibility entry point for the composed contract router."""

from contract_endpoints import router
from contract_endpoints.documents import (
    create_contract,
    download_contract,
    update_contract,
)
from contract_endpoints.helpers import (
    UPLOAD_RATE_ITEM,
    UPLOAD_RATE_LIMIT,
    enforce_upload_rate_limit as _enforce_upload_rate_limit,
    resolve_tags as _resolve_tags,
)
from contract_endpoints.lifecycle import (
    delete_contract,
    toggle_contract_protection,
)

__all__ = [
    "router",
    "UPLOAD_RATE_ITEM",
    "UPLOAD_RATE_LIMIT",
    "_enforce_upload_rate_limit",
    "_resolve_tags",
    "create_contract",
    "download_contract",
    "update_contract",
    "delete_contract",
    "toggle_contract_protection",
]
