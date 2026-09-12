"""Compatibility entry point for the composed contract router."""

from contract_endpoints import router
from contract_endpoints.documents import (
    create_contract,
    download_contract,
    read_contract,
    update_contract,
)
from contract_endpoints.helpers import (
    UPLOAD_RATE_ITEM,
    UPLOAD_RATE_LIMIT,
)
from contract_endpoints.helpers import (
    enforce_upload_rate_limit as _enforce_upload_rate_limit,
)
from contract_endpoints.helpers import (
    resolve_tags as _resolve_tags,
)
from contract_endpoints.lifecycle import (
    delete_contract,
    protect_contracts,
    toggle_contract_protection,
)

__all__ = [
    "UPLOAD_RATE_ITEM",
    "UPLOAD_RATE_LIMIT",
    "_enforce_upload_rate_limit",
    "_resolve_tags",
    "create_contract",
    "delete_contract",
    "download_contract",
    "protect_contracts",
    "read_contract",
    "router",
    "toggle_contract_protection",
    "update_contract",
]
