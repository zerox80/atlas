"""Contract trash and protection endpoints."""

from datetime import datetime, timezone
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
from sqlmodel import Session, col, select, update

from api_core import (
    check_contract_permission,
    contract_read_for_user,
    get_current_user,
)
from database import get_session
from models import Contract, User
from schemas import (
    ContractProtectionBulkResult,
    ContractRead,
    ContractSelection,
)
from security_utils import log_audit

router = APIRouter()


@router.put(
    "/contracts/bulk-protect",
    response_model=ContractProtectionBulkResult,
)
def protect_contracts(
    selection: ContractSelection,
    request: Request,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Protect every selected document in one atomic operation."""
    contract_ids = selection.contract_ids
    contracts = session.exec(
        select(Contract).where(
            col(Contract.id).in_(contract_ids),
            col(Contract.deleted_at).is_(None),
        )
    ).all()
    contracts_by_id = {contract.id: contract for contract in contracts}

    if len(contracts_by_id) != len(contract_ids) or any(
        not check_contract_permission(current_user, contract_id, "full", session)
        for contract_id in contract_ids
    ):
        raise HTTPException(
            status_code=404,
            detail="One or more selected documents were not found",
        )

    contracts_to_protect = [
        contracts_by_id[contract_id]
        for contract_id in contract_ids
        if not contracts_by_id[contract_id].is_protected
    ]
    try:
        for contract in contracts_to_protect:
            expected_version = contract.version
            claim_result = session.exec(
                update(Contract)
                .where(
                    col(Contract.id) == contract.id,
                    col(Contract.version) == expected_version,
                    col(Contract.is_protected).is_(False),
                    col(Contract.deleted_at).is_(None),
                )
                .values(
                    is_protected=True,
                    version=expected_version + 1,
                )
                .execution_options(synchronize_session=False)
            )
            if claim_result.rowcount != 1:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        "A selected document was changed by another request; "
                        "reload and retry"
                    ),
                )
            document_label = (
                "invoice" if contract.document_type == "invoice" else "contract"
            )
            log_audit(
                session,
                current_user.id,
                "CONTRACT_PROTECTED",
                f"[CID:{contract.id}] {document_label.capitalize()} PROTECTED",
                request.client.host if request.client else "unknown",
                request.headers.get("user-agent", "unknown"),
                contract_id=contract.id,
                commit=False,
            )
        session.commit()
    except Exception:
        session.rollback()
        raise

    return ContractProtectionBulkResult(
        changed_count=len(contracts_to_protect),
        already_protected_count=len(contract_ids) - len(contracts_to_protect),
    )


@router.delete("/contracts/{contract_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_contract(
    contract_id: int,
    request: Request,
    version: Annotated[int, Query(ge=1)],
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    contract = session.get(Contract, contract_id)
    if not contract or contract.deleted_at is not None:
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

    deleted_at = datetime.now(timezone.utc)
    try:
        delete_result = session.exec(
            update(Contract)
            .where(
                col(Contract.id) == contract_id,
                col(Contract.version) == expected_version,
                col(Contract.is_protected).is_(False),
                col(Contract.deleted_at).is_(None),
            )
            .values(
                deleted_at=deleted_at,
                deleted_by_user_id=current_user.id,
                version=expected_version + 1,
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
        document_label = (
            "invoice" if contract.document_type == "invoice" else "contract"
        )
        log_audit(
            session,
            current_user.id,
            "MOVE_TO_TRASH",
            f"[CID:{contract_id}] Moved {document_label} {contract.title} to trash",
            request.client.host if request.client else "unknown",
            request.headers.get("user-agent"),
            contract_id=contract_id,
            commit=False,
        )
        session.commit()
    except Exception:
        session.rollback()
        raise
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
    if not contract or contract.deleted_at is not None:
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
