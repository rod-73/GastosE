"""Catalog endpoints (V6-S2).

Categories:
- POST /api/v1/categories: create a new category.
- GET /api/v1/categories: list categories.
- GET /api/v1/categories/{id}: get a single category.
- PUT /api/v1/categories/{id}: update a category.
- POST /api/v1/categories/{id}/deactivate: deactivate a category.

Payment Methods:
- POST /api/v1/payment-methods: create a new payment method.
- GET /api/v1/payment-methods: list payment methods.
- GET /api/v1/payment-methods/{id}: get a single payment method.
- PUT /api/v1/payment-methods/{id}: update a payment method.
- POST /api/v1/payment-methods/{id}/deactivate: deactivate a payment method.

Tax Rates:
- POST /api/v1/tax-rates: create a new tax rate.
- GET /api/v1/tax-rates: list tax rates.
- GET /api/v1/tax-rates/{id}: get a single tax rate.
- PUT /api/v1/tax-rates/{id}: update a tax rate.
- POST /api/v1/tax-rates/{id}/deactivate: deactivate a tax rate.

Currencies:
- GET /api/v1/currencies: list all currencies.
- GET /api/v1/currencies/{code}: get a single currency.
"""
import uuid
from datetime import date
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session as DbSession

from backend.database import get_db
from backend.exceptions import ConflictException, NotFoundException
from backend.middleware.auth import get_session, require_role
from backend.models.session import Session
from backend.services import catalog_service

router = APIRouter(tags=["catalogs"])


# --- Category Schemas ---


class CategoryCreateRequest(BaseModel):
    """Request body for creating a category."""

    name: str
    description: Optional[str] = None
    parent_id: Optional[uuid.UUID] = None


class CategoryUpdateRequest(BaseModel):
    """Request body for updating a category."""

    name: Optional[str] = None
    description: Optional[str] = None
    parent_id: Optional[uuid.UUID] = None


class DeactivateRequest(BaseModel):
    """Request body for deactivating an entity."""

    reason: Optional[str] = None


class CategoryResponse(BaseModel):
    """A category."""

    id: uuid.UUID
    name: str
    description: Optional[str]
    parent_id: Optional[uuid.UUID]
    state: str
    created_at: str
    updated_at: str


class CategoryListResponse(BaseModel):
    """List of categories."""

    count: int
    categories: List[CategoryResponse]


# --- Payment Method Schemas ---


class PaymentMethodCreateRequest(BaseModel):
    """Request body for creating a payment method."""

    name: str


class PaymentMethodUpdateRequest(BaseModel):
    """Request body for updating a payment method."""

    name: Optional[str] = None


class PaymentMethodResponse(BaseModel):
    """A payment method."""

    id: uuid.UUID
    name: str
    state: str
    created_at: str
    updated_at: str


class PaymentMethodListResponse(BaseModel):
    """List of payment methods."""

    count: int
    payment_methods: List[PaymentMethodResponse]


# --- Tax Rate Schemas ---


class TaxRateCreateRequest(BaseModel):
    """Request body for creating a tax rate."""

    code: str
    tax_type: str  # vat | withholding
    percentage: Decimal
    valid_from: date
    description: Optional[str] = None
    valid_until: Optional[date] = None
    jurisdiction: Optional[str] = None


class TaxRateUpdateRequest(BaseModel):
    """Request body for updating a tax rate."""

    code: Optional[str] = None
    description: Optional[str] = None
    percentage: Optional[Decimal] = None
    valid_until: Optional[date] = None


class TaxRateResponse(BaseModel):
    """A tax rate."""

    id: uuid.UUID
    code: str
    description: Optional[str]
    tax_type: str
    percentage: Decimal
    valid_from: str
    valid_until: Optional[str]
    jurisdiction: Optional[str]
    created_at: str
    updated_at: str


class TaxRateListResponse(BaseModel):
    """List of tax rates."""

    count: int
    tax_rates: List[TaxRateResponse]


# --- Currency Schemas ---


class CurrencyResponse(BaseModel):
    """A currency."""

    code: str
    name: str
    decimals: int


class CurrencyListResponse(BaseModel):
    """List of currencies."""

    count: int
    currencies: List[CurrencyResponse]


# --- Category Endpoints ---


@router.post(
    "/api/v1/categories",
    response_model=CategoryResponse,
    status_code=201,
    dependencies=[Depends(require_role("reader"))],
)
def create_category(
    body: CategoryCreateRequest,
    session: Session = Depends(get_session),
    db: DbSession = Depends(get_db),
) -> CategoryResponse:
    """Create a new category (FR-CAT-1)."""
    try:
        category = catalog_service.create_category(
            owner_id=session.organization_id,
            user_id=session.user_id,
            name=body.name,
            description=body.description,
            parent_id=body.parent_id,
            db=db,
        )
    except ValueError as e:
        raise ConflictException(str(e))

    return CategoryResponse(
        id=category.id,
        name=category.name,
        description=category.description,
        parent_id=category.parent_id,
        state=category.state,
        created_at=category.created_at.isoformat(),
        updated_at=category.updated_at.isoformat(),
    )


@router.get(
    "/api/v1/categories",
    response_model=CategoryListResponse,
    dependencies=[Depends(require_role("reader"))],
)
def list_categories(
    state: Optional[str] = None,
    session: Session = Depends(get_session),
    db: DbSession = Depends(get_db),
) -> CategoryListResponse:
    """List categories."""
    categories = catalog_service.list_categories(
        owner_id=session.organization_id,
        db=db,
        state=state,
    )
    return CategoryListResponse(
        count=len(categories),
        categories=[
            CategoryResponse(
                id=c.id,
                name=c.name,
                description=c.description,
                parent_id=c.parent_id,
                state=c.state,
                created_at=c.created_at.isoformat(),
                updated_at=c.updated_at.isoformat(),
            )
            for c in categories
        ],
    )


@router.get(
    "/api/v1/categories/{category_id}",
    response_model=CategoryResponse,
    dependencies=[Depends(require_role("reader"))],
)
def get_category(
    category_id: uuid.UUID,
    session: Session = Depends(get_session),
    db: DbSession = Depends(get_db),
) -> CategoryResponse:
    """Get a single category."""
    try:
        category = catalog_service.get_category(
            category_id=category_id,
            owner_id=session.organization_id,
            db=db,
        )
    except ValueError as e:
        raise NotFoundException(str(e))

    return CategoryResponse(
        id=category.id,
        name=category.name,
        description=category.description,
        parent_id=category.parent_id,
        state=category.state,
        created_at=category.created_at.isoformat(),
        updated_at=category.updated_at.isoformat(),
    )


@router.put(
    "/api/v1/categories/{category_id}",
    response_model=CategoryResponse,
    dependencies=[Depends(require_role("reader"))],
)
def update_category(
    category_id: uuid.UUID,
    body: CategoryUpdateRequest,
    session: Session = Depends(get_session),
    db: DbSession = Depends(get_db),
) -> CategoryResponse:
    """Update a category."""
    try:
        category = catalog_service.update_category(
            category_id=category_id,
            owner_id=session.organization_id,
            user_id=session.user_id,
            name=body.name,
            description=body.description,
            parent_id=body.parent_id,
            db=db,
        )
    except ValueError as e:
        raise ConflictException(str(e))

    return CategoryResponse(
        id=category.id,
        name=category.name,
        description=category.description,
        parent_id=category.parent_id,
        state=category.state,
        created_at=category.created_at.isoformat(),
        updated_at=category.updated_at.isoformat(),
    )


@router.post(
    "/api/v1/categories/{category_id}/deactivate",
    response_model=CategoryResponse,
    dependencies=[Depends(require_role("reader"))],
)
def deactivate_category(
    category_id: uuid.UUID,
    body: DeactivateRequest,
    session: Session = Depends(get_session),
    db: DbSession = Depends(get_db),
) -> CategoryResponse:
    """Deactivate a category."""
    try:
        category = catalog_service.deactivate_category(
            category_id=category_id,
            owner_id=session.organization_id,
            user_id=session.user_id,
            reason=body.reason,
            db=db,
        )
    except ValueError as e:
        raise ConflictException(str(e))

    return CategoryResponse(
        id=category.id,
        name=category.name,
        description=category.description,
        parent_id=category.parent_id,
        state=category.state,
        created_at=category.created_at.isoformat(),
        updated_at=category.updated_at.isoformat(),
    )


# --- Payment Method Endpoints ---


@router.post(
    "/api/v1/payment-methods",
    response_model=PaymentMethodResponse,
    status_code=201,
    dependencies=[Depends(require_role("reader"))],
)
def create_payment_method(
    body: PaymentMethodCreateRequest,
    session: Session = Depends(get_session),
    db: DbSession = Depends(get_db),
) -> PaymentMethodResponse:
    """Create a new payment method."""
    try:
        pm = catalog_service.create_payment_method(
            owner_id=session.organization_id,
            user_id=session.user_id,
            name=body.name,
            db=db,
        )
    except ValueError as e:
        raise ConflictException(str(e))

    return PaymentMethodResponse(
        id=pm.id,
        name=pm.name,
        state=pm.state,
        created_at=pm.created_at.isoformat(),
        updated_at=pm.updated_at.isoformat(),
    )


@router.get(
    "/api/v1/payment-methods",
    response_model=PaymentMethodListResponse,
    dependencies=[Depends(require_role("reader"))],
)
def list_payment_methods(
    state: Optional[str] = None,
    session: Session = Depends(get_session),
    db: DbSession = Depends(get_db),
) -> PaymentMethodListResponse:
    """List payment methods."""
    pms = catalog_service.list_payment_methods(
        owner_id=session.organization_id,
        db=db,
        state=state,
    )
    return PaymentMethodListResponse(
        count=len(pms),
        payment_methods=[
            PaymentMethodResponse(
                id=p.id,
                name=p.name,
                state=p.state,
                created_at=p.created_at.isoformat(),
                updated_at=p.updated_at.isoformat(),
            )
            for p in pms
        ],
    )


@router.get(
    "/api/v1/payment-methods/{pm_id}",
    response_model=PaymentMethodResponse,
    dependencies=[Depends(require_role("reader"))],
)
def get_payment_method(
    pm_id: uuid.UUID,
    session: Session = Depends(get_session),
    db: DbSession = Depends(get_db),
) -> PaymentMethodResponse:
    """Get a single payment method."""
    try:
        pm = catalog_service.get_payment_method(
            pm_id=pm_id,
            owner_id=session.organization_id,
            db=db,
        )
    except ValueError as e:
        raise NotFoundException(str(e))

    return PaymentMethodResponse(
        id=pm.id,
        name=pm.name,
        state=pm.state,
        created_at=pm.created_at.isoformat(),
        updated_at=pm.updated_at.isoformat(),
    )


@router.put(
    "/api/v1/payment-methods/{pm_id}",
    response_model=PaymentMethodResponse,
    dependencies=[Depends(require_role("reader"))],
)
def update_payment_method(
    pm_id: uuid.UUID,
    body: PaymentMethodUpdateRequest,
    session: Session = Depends(get_session),
    db: DbSession = Depends(get_db),
) -> PaymentMethodResponse:
    """Update a payment method."""
    try:
        pm = catalog_service.update_payment_method(
            pm_id=pm_id,
            owner_id=session.organization_id,
            user_id=session.user_id,
            name=body.name,
            db=db,
        )
    except ValueError as e:
        raise ConflictException(str(e))

    return PaymentMethodResponse(
        id=pm.id,
        name=pm.name,
        state=pm.state,
        created_at=pm.created_at.isoformat(),
        updated_at=pm.updated_at.isoformat(),
    )


@router.post(
    "/api/v1/payment-methods/{pm_id}/deactivate",
    response_model=PaymentMethodResponse,
    dependencies=[Depends(require_role("reader"))],
)
def deactivate_payment_method(
    pm_id: uuid.UUID,
    body: DeactivateRequest,
    session: Session = Depends(get_session),
    db: DbSession = Depends(get_db),
) -> PaymentMethodResponse:
    """Deactivate a payment method."""
    try:
        pm = catalog_service.deactivate_payment_method(
            pm_id=pm_id,
            owner_id=session.organization_id,
            user_id=session.user_id,
            reason=body.reason,
            db=db,
        )
    except ValueError as e:
        raise ConflictException(str(e))

    return PaymentMethodResponse(
        id=pm.id,
        name=pm.name,
        state=pm.state,
        created_at=pm.created_at.isoformat(),
        updated_at=pm.updated_at.isoformat(),
    )


# --- Tax Rate Endpoints ---


@router.post(
    "/api/v1/tax-rates",
    response_model=TaxRateResponse,
    status_code=201,
    dependencies=[Depends(require_role("reader"))],
)
def create_tax_rate(
    body: TaxRateCreateRequest,
    session: Session = Depends(get_session),
    db: DbSession = Depends(get_db),
) -> TaxRateResponse:
    """Create a new tax rate."""
    try:
        tax_rate = catalog_service.create_tax_rate(
            owner_id=session.organization_id,
            user_id=session.user_id,
            code=body.code,
            tax_type=body.tax_type,
            percentage=body.percentage,
            valid_from=body.valid_from,
            description=body.description,
            valid_until=body.valid_until,
            jurisdiction=body.jurisdiction,
            db=db,
        )
    except ValueError as e:
        raise ConflictException(str(e))

    return TaxRateResponse(
        id=tax_rate.id,
        code=tax_rate.code,
        description=tax_rate.description,
        tax_type=tax_rate.tax_type,
        percentage=tax_rate.percentage,
        valid_from=tax_rate.valid_from.isoformat(),
        valid_until=tax_rate.valid_until.isoformat() if tax_rate.valid_until else None,
        jurisdiction=tax_rate.jurisdiction,
        created_at=tax_rate.created_at.isoformat(),
        updated_at=tax_rate.updated_at.isoformat(),
    )


@router.get(
    "/api/v1/tax-rates",
    response_model=TaxRateListResponse,
    dependencies=[Depends(require_role("reader"))],
)
def list_tax_rates(
    tax_type: Optional[str] = None,
    session: Session = Depends(get_session),
    db: DbSession = Depends(get_db),
) -> TaxRateListResponse:
    """List tax rates."""
    tax_rates = catalog_service.list_tax_rates(
        owner_id=session.organization_id,
        db=db,
        tax_type=tax_type,
    )
    return TaxRateListResponse(
        count=len(tax_rates),
        tax_rates=[
            TaxRateResponse(
                id=t.id,
                code=t.code,
                description=t.description,
                tax_type=t.tax_type,
                percentage=t.percentage,
                valid_from=t.valid_from.isoformat(),
                valid_until=t.valid_until.isoformat() if t.valid_until else None,
                jurisdiction=t.jurisdiction,
                created_at=t.created_at.isoformat(),
                updated_at=t.updated_at.isoformat(),
            )
            for t in tax_rates
        ],
    )


@router.get(
    "/api/v1/tax-rates/{tax_rate_id}",
    response_model=TaxRateResponse,
    dependencies=[Depends(require_role("reader"))],
)
def get_tax_rate(
    tax_rate_id: uuid.UUID,
    session: Session = Depends(get_session),
    db: DbSession = Depends(get_db),
) -> TaxRateResponse:
    """Get a single tax rate."""
    try:
        tax_rate = catalog_service.get_tax_rate(
            tax_rate_id=tax_rate_id,
            owner_id=session.organization_id,
            db=db,
        )
    except ValueError as e:
        raise NotFoundException(str(e))

    return TaxRateResponse(
        id=tax_rate.id,
        code=tax_rate.code,
        description=tax_rate.description,
        tax_type=tax_rate.tax_type,
        percentage=tax_rate.percentage,
        valid_from=tax_rate.valid_from.isoformat(),
        valid_until=tax_rate.valid_until.isoformat() if tax_rate.valid_until else None,
        jurisdiction=tax_rate.jurisdiction,
        created_at=tax_rate.created_at.isoformat(),
        updated_at=tax_rate.updated_at.isoformat(),
    )


@router.put(
    "/api/v1/tax-rates/{tax_rate_id}",
    response_model=TaxRateResponse,
    dependencies=[Depends(require_role("reader"))],
)
def update_tax_rate(
    tax_rate_id: uuid.UUID,
    body: TaxRateUpdateRequest,
    session: Session = Depends(get_session),
    db: DbSession = Depends(get_db),
) -> TaxRateResponse:
    """Update a tax rate."""
    try:
        tax_rate = catalog_service.update_tax_rate(
            tax_rate_id=tax_rate_id,
            owner_id=session.organization_id,
            user_id=session.user_id,
            code=body.code,
            description=body.description,
            percentage=body.percentage,
            valid_until=body.valid_until,
            db=db,
        )
    except ValueError as e:
        raise ConflictException(str(e))

    return TaxRateResponse(
        id=tax_rate.id,
        code=tax_rate.code,
        description=tax_rate.description,
        tax_type=tax_rate.tax_type,
        percentage=tax_rate.percentage,
        valid_from=tax_rate.valid_from.isoformat(),
        valid_until=tax_rate.valid_until.isoformat() if tax_rate.valid_until else None,
        jurisdiction=tax_rate.jurisdiction,
        created_at=tax_rate.created_at.isoformat(),
        updated_at=tax_rate.updated_at.isoformat(),
    )


@router.post(
    "/api/v1/tax-rates/{tax_rate_id}/deactivate",
    response_model=TaxRateResponse,
    dependencies=[Depends(require_role("reader"))],
)
def deactivate_tax_rate(
    tax_rate_id: uuid.UUID,
    body: DeactivateRequest,
    session: Session = Depends(get_session),
    db: DbSession = Depends(get_db),
) -> TaxRateResponse:
    """Deactivate a tax rate (set valid_until to today)."""
    try:
        tax_rate = catalog_service.deactivate_tax_rate(
            tax_rate_id=tax_rate_id,
            owner_id=session.organization_id,
            user_id=session.user_id,
            reason=body.reason,
            db=db,
        )
    except ValueError as e:
        raise ConflictException(str(e))

    return TaxRateResponse(
        id=tax_rate.id,
        code=tax_rate.code,
        description=tax_rate.description,
        tax_type=tax_rate.tax_type,
        percentage=tax_rate.percentage,
        valid_from=tax_rate.valid_from.isoformat(),
        valid_until=tax_rate.valid_until.isoformat() if tax_rate.valid_until else None,
        jurisdiction=tax_rate.jurisdiction,
        created_at=tax_rate.created_at.isoformat(),
        updated_at=tax_rate.updated_at.isoformat(),
    )


# --- Currency Endpoints ---


@router.get(
    "/api/v1/currencies",
    response_model=CurrencyListResponse,
    dependencies=[Depends(require_role("reader"))],
)
def list_currencies(
    session: Session = Depends(get_session),
    db: DbSession = Depends(get_db),
) -> CurrencyListResponse:
    """List all currencies (global catalog)."""
    currencies = catalog_service.list_currencies(db=db)
    return CurrencyListResponse(
        count=len(currencies),
        currencies=[
            CurrencyResponse(
                code=c.code,
                name=c.name,
                decimals=c.decimals,
            )
            for c in currencies
        ],
    )


@router.get(
    "/api/v1/currencies/{code}",
    response_model=CurrencyResponse,
    dependencies=[Depends(require_role("reader"))],
)
def get_currency(
    code: str,
    session: Session = Depends(get_session),
    db: DbSession = Depends(get_db),
) -> CurrencyResponse:
    """Get a single currency by code."""
    try:
        currency = catalog_service.get_currency(code=code, db=db)
    except ValueError as e:
        raise NotFoundException(str(e))

    return CurrencyResponse(
        code=currency.code,
        name=currency.name,
        decimals=currency.decimals,
    )
