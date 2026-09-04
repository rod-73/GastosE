"""Supplier endpoints (V6-S1).

- POST /api/v1/suppliers: create a new supplier.
- GET /api/v1/suppliers: list suppliers with optional search/filter.
- GET /api/v1/suppliers/{id}: get a single supplier.
- PUT /api/v1/suppliers/{id}: update a supplier.
- POST /api/v1/suppliers/{id}/deactivate: deactivate a supplier.
"""
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session as DbSession

from backend.database import get_db
from backend.exceptions import ConflictException, NotFoundException
from backend.middleware.auth import get_session, require_role
from backend.models.session import Session
from backend.services import supplier_service

router = APIRouter(tags=["suppliers"])


# --- Schemas ---


class SupplierCreateRequest(BaseModel):
    """Request body for creating a supplier."""

    legal_name: str
    nif_cif: str
    tax_address: Optional[str] = None
    contact_data: Optional[str] = None


class SupplierUpdateRequest(BaseModel):
    """Request body for updating a supplier."""

    legal_name: Optional[str] = None
    nif_cif: Optional[str] = None
    tax_address: Optional[str] = None
    contact_data: Optional[str] = None


class DeactivateSupplierRequest(BaseModel):
    """Request body for deactivating a supplier."""

    reason: Optional[str] = None


class SupplierResponse(BaseModel):
    """A supplier."""

    id: uuid.UUID
    legal_name: str
    nif_cif: str
    tax_address: Optional[str]
    contact_data: Optional[str]
    state: str
    created_at: str
    updated_at: str


class SupplierListResponse(BaseModel):
    """List of suppliers."""

    count: int
    suppliers: List[SupplierResponse]


# --- Endpoints ---


@router.post(
    "/api/v1/suppliers",
    response_model=SupplierResponse,
    status_code=201,
    dependencies=[Depends(require_role("reader"))],
)
def create_supplier(
    body: SupplierCreateRequest,
    session: Session = Depends(get_session),
    db: DbSession = Depends(get_db),
) -> SupplierResponse:
    """Create a new supplier (FR-SUP-1, FR-SUP-2)."""
    try:
        supplier = supplier_service.create_supplier(
            owner_id=session.organization_id,
            user_id=session.user_id,
            legal_name=body.legal_name,
            nif_cif=body.nif_cif,
            tax_address=body.tax_address,
            contact_data=body.contact_data,
            db=db,
        )
    except ValueError as e:
        raise ConflictException(str(e))

    return SupplierResponse(
        id=supplier.id,
        legal_name=supplier.legal_name,
        nif_cif=supplier.nif_cif,
        tax_address=supplier.tax_address,
        contact_data=supplier.contact_data,
        state=supplier.state,
        created_at=supplier.created_at.isoformat(),
        updated_at=supplier.updated_at.isoformat(),
    )


@router.get(
    "/api/v1/suppliers",
    response_model=SupplierListResponse,
    dependencies=[Depends(require_role("reader"))],
)
def list_suppliers(
    search: Optional[str] = None,
    state: Optional[str] = None,
    session: Session = Depends(get_session),
    db: DbSession = Depends(get_db),
) -> SupplierListResponse:
    """List suppliers with optional search and state filter (FR-SUP-3)."""
    suppliers = supplier_service.list_suppliers(
        owner_id=session.organization_id,
        db=db,
        search=search,
        state=state,
    )
    return SupplierListResponse(
        count=len(suppliers),
        suppliers=[
            SupplierResponse(
                id=s.id,
                legal_name=s.legal_name,
                nif_cif=s.nif_cif,
                tax_address=s.tax_address,
                contact_data=s.contact_data,
                state=s.state,
                created_at=s.created_at.isoformat(),
                updated_at=s.updated_at.isoformat(),
            )
            for s in suppliers
        ],
    )


@router.get(
    "/api/v1/suppliers/{supplier_id}",
    response_model=SupplierResponse,
    dependencies=[Depends(require_role("reader"))],
)
def get_supplier(
    supplier_id: uuid.UUID,
    session: Session = Depends(get_session),
    db: DbSession = Depends(get_db),
) -> SupplierResponse:
    """Get a single supplier."""
    try:
        supplier = supplier_service.get_supplier(
            supplier_id=supplier_id,
            owner_id=session.organization_id,
            db=db,
        )
    except ValueError as e:
        raise NotFoundException(str(e))

    return SupplierResponse(
        id=supplier.id,
        legal_name=supplier.legal_name,
        nif_cif=supplier.nif_cif,
        tax_address=supplier.tax_address,
        contact_data=supplier.contact_data,
        state=supplier.state,
        created_at=supplier.created_at.isoformat(),
        updated_at=supplier.updated_at.isoformat(),
    )


@router.put(
    "/api/v1/suppliers/{supplier_id}",
    response_model=SupplierResponse,
    dependencies=[Depends(require_role("reader"))],
)
def update_supplier(
    supplier_id: uuid.UUID,
    body: SupplierUpdateRequest,
    session: Session = Depends(get_session),
    db: DbSession = Depends(get_db),
) -> SupplierResponse:
    """Update a supplier (FR-SUP-2: NIF/CIF validation on update)."""
    try:
        supplier = supplier_service.update_supplier(
            supplier_id=supplier_id,
            owner_id=session.organization_id,
            user_id=session.user_id,
            legal_name=body.legal_name,
            nif_cif=body.nif_cif,
            tax_address=body.tax_address,
            contact_data=body.contact_data,
            db=db,
        )
    except ValueError as e:
        raise ConflictException(str(e))

    return SupplierResponse(
        id=supplier.id,
        legal_name=supplier.legal_name,
        nif_cif=supplier.nif_cif,
        tax_address=supplier.tax_address,
        contact_data=supplier.contact_data,
        state=supplier.state,
        created_at=supplier.created_at.isoformat(),
        updated_at=supplier.updated_at.isoformat(),
    )


@router.post(
    "/api/v1/suppliers/{supplier_id}/deactivate",
    response_model=SupplierResponse,
    dependencies=[Depends(require_role("reader"))],
)
def deactivate_supplier(
    supplier_id: uuid.UUID,
    body: DeactivateSupplierRequest,
    session: Session = Depends(get_session),
    db: DbSession = Depends(get_db),
) -> SupplierResponse:
    """Deactivate a supplier (FR-SUP-4)."""
    try:
        supplier = supplier_service.deactivate_supplier(
            supplier_id=supplier_id,
            owner_id=session.organization_id,
            user_id=session.user_id,
            reason=body.reason,
            db=db,
        )
    except ValueError as e:
        raise ConflictException(str(e))

    return SupplierResponse(
        id=supplier.id,
        legal_name=supplier.legal_name,
        nif_cif=supplier.nif_cif,
        tax_address=supplier.tax_address,
        contact_data=supplier.contact_data,
        state=supplier.state,
        created_at=supplier.created_at.isoformat(),
        updated_at=supplier.updated_at.isoformat(),
    )
