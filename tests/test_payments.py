"""Tests for payments (E12, VR-ARITH-5, PHASE3-004)."""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session as DbSession

from backend.models.expense import Expense
from backend.models.payment import Payment
from backend.services import payment_service


class TestPaymentService:
    """Unit tests for payment service."""

    def test_record_payment_single(self, db_session: DbSession, test_org, test_user):
        """Should record a single payment matching the total."""
        expense = Expense(
            id=uuid.uuid4(),
            owner_id=test_org.id,
            document_id=uuid.uuid4(),
            supplier_id=uuid.uuid4(),
            currency="EUR",
            total=Decimal("100.00"),
            state="draft",
        )
        db_session.add(expense)
        db_session.commit()

        payment = payment_service.record_payment(
            expense_id=expense.id,
            owner_id=test_org.id,
            payment_date=date(2024, 1, 15),
            amount_paid=Decimal("100.00"),
            db=db_session,
        )
        assert payment.id is not None
        assert payment.amount_paid == Decimal("100.00")
        assert payment.payment_date == date(2024, 1, 15)

    def test_record_payment_vr_arith_5_violation(self, db_session: DbSession, test_org, test_user):
        """VR-ARITH-5: single payment must match total within tolerance."""
        expense = Expense(
            id=uuid.uuid4(),
            owner_id=test_org.id,
            document_id=uuid.uuid4(),
            supplier_id=uuid.uuid4(),
            currency="EUR",
            total=Decimal("100.00"),
            state="draft",
        )
        db_session.add(expense)
        db_session.commit()

        with pytest.raises(ValueError, match="VR-ARITH-5"):
            payment_service.record_payment(
                expense_id=expense.id,
                owner_id=test_org.id,
                payment_date=date(2024, 1, 15),
                amount_paid=Decimal("90.00"),  # Too far from 100.00
                db=db_session,
            )

    def test_record_payment_with_tolerance(self, db_session: DbSession, test_org, test_user):
        """VR-ARITH-5: tolerance of 0.01 is allowed."""
        expense = Expense(
            id=uuid.uuid4(),
            owner_id=test_org.id,
            document_id=uuid.uuid4(),
            supplier_id=uuid.uuid4(),
            currency="EUR",
            total=Decimal("100.00"),
            state="draft",
        )
        db_session.add(expense)
        db_session.commit()

        # 100.01 is within tolerance.
        payment = payment_service.record_payment(
            expense_id=expense.id,
            owner_id=test_org.id,
            payment_date=date(2024, 1, 15),
            amount_paid=Decimal("100.01"),
            db=db_session,
        )
        assert payment.amount_paid == Decimal("100.01")

    def test_record_multiple_payments_not_supported_v1(self, db_session: DbSession, test_org, test_user):
        """V1: Only single payment supported (VR-ARITH-5). Multiple payments not allowed."""
        expense = Expense(
            id=uuid.uuid4(),
            owner_id=test_org.id,
            document_id=uuid.uuid4(),
            supplier_id=uuid.uuid4(),
            currency="EUR",
            total=Decimal("100.00"),
            state="draft",
        )
        db_session.add(expense)
        db_session.commit()

        # First payment: 100.00 (matches total).
        payment1 = payment_service.record_payment(
            expense_id=expense.id,
            owner_id=test_org.id,
            payment_date=date(2024, 1, 15),
            amount_paid=Decimal("100.00"),
            db=db_session,
        )

        # Second payment: should fail because expense already has a payment.
        # In V1, only single payment is supported.
        with pytest.raises(ValueError):
            payment_service.record_payment(
                expense_id=expense.id,
                owner_id=test_org.id,
                payment_date=date(2024, 2, 15),
                amount_paid=Decimal("50.00"),
                db=db_session,
            )

    def test_get_payments(self, db_session: DbSession, test_org, test_user):
        """Should list payments for an expense."""
        expense = Expense(
            id=uuid.uuid4(),
            owner_id=test_org.id,
            document_id=uuid.uuid4(),
            supplier_id=uuid.uuid4(),
            currency="EUR",
            total=Decimal("100.00"),
            state="draft",
        )
        db_session.add(expense)
        db_session.commit()

        payment_service.record_payment(
            expense_id=expense.id,
            owner_id=test_org.id,
            payment_date=date(2024, 1, 15),
            amount_paid=Decimal("100.00"),
            db=db_session,
        )

        payments = payment_service.get_payments(
            expense_id=expense.id,
            owner_id=test_org.id,
            db=db_session,
        )
        assert len(payments) == 1
        assert payments[0]["amount_paid"] == "100.00"

    def test_get_payments_isolated_by_org(self, db_session: DbSession, test_org, test_user):
        """Payments should be isolated by organization."""
        from backend.models.organization import Organization
        other_org = Organization(id=uuid.uuid4(), name="Other Org", state="active")
        db_session.add(other_org)
        db_session.commit()

        expense = Expense(
            id=uuid.uuid4(),
            owner_id=test_org.id,
            document_id=uuid.uuid4(),
            supplier_id=uuid.uuid4(),
            currency="EUR",
            total=Decimal("100.00"),
            state="draft",
        )
        db_session.add(expense)
        db_session.commit()

        payment_service.record_payment(
            expense_id=expense.id,
            owner_id=test_org.id,
            payment_date=date(2024, 1, 15),
            amount_paid=Decimal("100.00"),
            db=db_session,
        )

        # Query with other org should return empty.
        payments = payment_service.get_payments(
            expense_id=expense.id,
            owner_id=other_org.id,
            db=db_session,
        )
        assert len(payments) == 0


class TestPaymentAPI:
    """Integration tests for payments API."""

    @pytest.fixture()
    def reviewer_headers(self, client: TestClient, db_session: DbSession, test_org, test_user) -> dict:
        """Get auth headers for a user with reviewer role."""
        # Update the user's role to reviewer.
        test_user.role = "reviewer"
        db_session.commit()

        response = client.post(
            "/api/v1/auth/login",
            json={"username": "testuser", "password": "testpass123"},
        )
        assert response.status_code == 200
        token = response.json()["token"]
        return {"Authorization": f"Bearer {token}"}

    def test_create_payment_endpoint(self, client: TestClient, reviewer_headers, db_session, test_org, test_user):
        """POST /api/v1/expenses/{id}/payments should create a payment."""
        expense = Expense(
            id=uuid.uuid4(),
            owner_id=test_org.id,
            document_id=uuid.uuid4(),
            supplier_id=uuid.uuid4(),
            currency="EUR",
            total=Decimal("100.00"),
            state="draft",
        )
        db_session.add(expense)
        db_session.commit()

        resp = client.post(
            f"/api/v1/expenses/{expense.id}/payments",
            json={
                "payment_date": "2024-01-15",
                "amount_paid": "100.00",
            },
            headers=reviewer_headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["amount_paid"] == "100.00"
        assert data["payment_date"] == "2024-01-15"

    def test_create_payment_vr_arith_5_violation(self, client: TestClient, reviewer_headers, db_session, test_org, test_user):
        """POST /api/v1/expenses/{id}/payments should reject VR-ARITH-5 violations."""
        expense = Expense(
            id=uuid.uuid4(),
            owner_id=test_org.id,
            document_id=uuid.uuid4(),
            supplier_id=uuid.uuid4(),
            currency="EUR",
            total=Decimal("100.00"),
            state="draft",
        )
        db_session.add(expense)
        db_session.commit()

        resp = client.post(
            f"/api/v1/expenses/{expense.id}/payments",
            json={
                "payment_date": "2024-01-15",
                "amount_paid": "90.00",  # Too far from 100.00
            },
            headers=reviewer_headers,
        )
        assert resp.status_code == 400  # ValidationException

    def test_list_payments_endpoint(self, client: TestClient, auth_headers, db_session, test_org, test_user):
        """GET /api/v1/expenses/{id}/payments should list payments."""
        expense = Expense(
            id=uuid.uuid4(),
            owner_id=test_org.id,
            document_id=uuid.uuid4(),
            supplier_id=uuid.uuid4(),
            currency="EUR",
            total=Decimal("100.00"),
            state="draft",
        )
        db_session.add(expense)
        db_session.commit()

        payment_service.record_payment(
            expense_id=expense.id,
            owner_id=test_org.id,
            payment_date=date(2024, 1, 15),
            amount_paid=Decimal("100.00"),
            db=db_session,
        )

        resp = client.get(
            f"/api/v1/expenses/{expense.id}/payments",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["amount_paid"] == "100.00"
