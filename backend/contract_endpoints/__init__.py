"""Composed router for contract document and lifecycle operations."""

from fastapi import APIRouter

from contract_endpoints.documents import router as document_router
from contract_endpoints.lifecycle import router as lifecycle_router
from contract_endpoints.trash import router as trash_router

router = APIRouter()
router.include_router(document_router)
router.include_router(lifecycle_router)
router.include_router(trash_router)

__all__ = ["router"]
