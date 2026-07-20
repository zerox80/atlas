"""Contract deletion and protection endpoints."""

import logging
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Request,
    Response,
    status,
)
from sqlmodel import Session, col, delete, update

from api_core import (
    check_contract_permission,
    contract_read_for_user,
    get_current_user,
)
from database import get_session
from file_utils import delete_upload_file
from models import (
    Contract,
    ContractListLink,
    ContractPermission,
    ContractTagLink,
    User,
)
from schemas import ContractRead
from security_utils import log_audit

router = APIRouter()
logger = logging.getLogger(__name__)


@router.delete("/contracts/{contract_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_contract(
    contract_id: int,
    request: Request,
    version: Annotated[int, Query(ge=1)],
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    contract = session.get(Contract, contract_id)
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")
    if not check_contract_permission(current_user, contract_id, "full", session):
        raise HTTPException(status_code=404, detail="Contract not found")
    if contract.is_protected:
        raise HTTPException(
            status_code=403,
            detail=(
                "This contract is protected. You must unprotect it from the "
                "Protected Contracts page before deleting."
            ),
        )

    expected_version = version
    if expected_version != contract.version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Contract was changed by another request; reload and retry",
        )

    file_path_to_delete = contract.file_path
    contract_title = contract.title
    try:
        session.exec(
            delete(ContractTagLink).where(
                col(ContractTagLink.contract_id) == contract_id
            )
        )
        session.exec(
            delete(ContractListLink).where(
                col(ContractListLink.contract_id) == contract_id
            )
        )
        session.exec(
            delete(ContractPermission).where(
                col(ContractPermission.contract_id) == contract_id
            )
        )
        log_audit(
            session,
            current_user.id,
            "DELETE_CONTRACT",
            f"[CID:{contract_id}] Deleted contract {contract_title}",
            request.client.host if request.client else "unknown",
            request.headers.get("user-agent"),
            contract_id=contract_id,
            commit=False,
        )
        session.exec(
            update(Contract)
            .where(col(Contract.parent_id) == contract_id)
            .values(parent_id=None)
        )
        delete_result = session.exec(
            delete(Contract)
            .where(
                col(Contract.id) == contract_id,
                col(Contract.version) == expected_version,
                col(Contract.is_protected).is_(False),
            )
            .execution_options(synchronize_session=False)
        )
        if delete_result.rowcount != 1:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Contract was changed or protected by another request; "
                    "reload and retry"
                ),
            )
        session.commit()
    except Exception:
        session.rollback()
        raise

    if file_path_to_delete:
        try:
            delete_upload_file(file_path_to_delete)
        except Exception:
            logger.exception("Could not delete file for contract %s", contract_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/contracts/{contract_id}/toggle-protection", response_model=ContractRead)
def toggle_contract_protection(
    contract_id: int,
    request: Request,
    version: Annotated[int, Query(ge=1)],
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    contract = session.get(Contract, contract_id)
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")
    if not check_contract_permission(current_user, contract_id, "full", session):
        raise HTTPException(status_code=404, detail="Contract not found")

    expected_version = version
    if expected_version != contract.version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Contract was changed by another request; reload and retry",
        )
    next_protection = not contract.is_protected
    try:
        claim_result = session.exec(
            update(Contract)
            .where(
                col(Contract.id) == contract_id,
                col(Contract.version) == expected_version,
            )
            .values(
                is_protected=next_protection,
                version=expected_version + 1,
            )
            .execution_options(synchronize_session=False)
        )
        if claim_result.rowcount != 1:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Contract was changed by another request; reload and retry",
            )
        action = "PROTECTED" if next_protection else "UNPROTECTED"
        log_audit(
            session,
            current_user.id,
            f"CONTRACT_{action}",
            f"[CID:{contract_id}] Contract {action}",
            request.client.host if request.client else "unknown",
            request.headers.get("user-agent", "unknown"),
            contract_id=contract_id,
            commit=False,
        )
        session.commit()
    except Exception:
        session.rollback()
        raise
    session.refresh(contract)
    return contract_read_for_user(contract, current_user, session)
