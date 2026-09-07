"""Tests for manual corrections (E14, INV-7, PHASE3-003)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session as DbSession

from backend.models.expense import Expense
from backend.models.manual_correction import ManualCorrection
from backend.services import manual_correction_service


class TestManualCorrectionService:
    """Unit tests for manual correction service."""

    def test_record_correction(self, db_session: DbSession, test_org, test_user):
        """Should record a correction with all required fields."""
        # Create a minimal expense.
        expense = Expense(
            id=uuid.uuid4(),
            owner_id=test_org.id,
            document_id=uuid.uuid4(),
            supplier_id=uuid.uuid4(),
            currency="EUR",
            total=100.00,
            state="draft",
        )
        db_session.add(expense)
        db_session.commit()

        correction = manual_correction_service.record_correction(
            expense_id=expense.id,
            owner_id=test_org.id,
            field="total",
            old_value="100.00",
            new_value="120.00",
            corrected_by=test_user.id,
            reason="Typo in original",
            db=db_session,
        )
        assert correction.id is not None
        assert correction.field == "total"
        assert correction.old_value == "100.00"
        assert correction.new_value == "120.00"
        assert correction.reason == "Typo in original"

    def test_record_correction_requires_old_value(self, db_session: DbSession, test_org, test_user):
        """INV-7: old_value is NOT NULL."""
        expense = Expense(
            id=uuid.uuid4(),
            owner_id=test_org.id,
            document_id=uuid.uuid4(),
            supplier_id=uuid.uuid4(),
            currency="EUR",
            total=100.00,
            state="draft",
        )
        db_session.add(expense)
        db_session.commit()

        with pytest.raises(ValueError, match="old_value is required"):
            manual_correction_service.record_correction(
                expense_id=expense.id,
                owner_id=test_org.id,
                field="total",
                old_value="",
                new_value="120.00",
                corrected_by=test_user.id,
                db=db_session,
            )

    def test_record_correction_requires_new_value(self, db_session: DbSession, test_org, test_user):
        """INV-7: new_value is NOT NULL."""
        expense = Expense(
            id=uuid.uuid4(),
            owner_id=test_org.id,
            document_id=uuid.uuid4(),
            supplier_id=uuid.uuid4(),
            currency="EUR",
            total=100.00,
            state="draft",
        )
        db_session.add(expense)
        db_session.commit()

        with pytest.raises(ValueError, match="new_value is required"):
            manual_correction_service.record_correction(
                expense_id=expense.id,
                owner_id=test_org.id,
                field="total",
                old_value="100.00",
                new_value="",
                corrected_by=test_user.id,
                db=db_session,
            )

    def test_get_corrections(self, db_session: DbSession, test_org, test_user):
        """Should list corrections for an expense."""
        expense = Expense(
            id=uuid.uuid4(),
            owner_id=test_org.id,
            document_id=uuid.uuid4(),
            supplier_id=uuid.uuid4(),
            currency="EUR",
            total=100.00,
            state="draft",
        )
        db_session.add(expense)
        db_session.commit()

        # Record two corrections.
        manual_correction_service.record_correction(
            expense_id=expense.id,
            owner_id=test_org.id,
            field="total",
            old_value="100.00",
            new_value="120.00",
            corrected_by=test_user.id,
            db=db_session,
        )
        manual_correction_service.record_correction(
            expense_id=expense.id,
            owner_id=test_org.id,
            field="date",
            old_value="2024-01-01",
            new_value="2024-01-02",
            corrected_by=test_user.id,
            reason="Wrong date",
            db=db_session,
        )

        corrections = manual_correction_service.get_corrections(
            expense_id=expense.id,
            owner_id=test_org.id,
            db=db_session,
        )
        assert len(corrections) == 2
        assert corrections[0]["field"] == "total"
        assert corrections[1]["field"] == "date"
        assert corrections[1]["reason"] == "Wrong date"

    def test_get_corrections_isolated_by_org(self, db_session: DbSession, test_org, test_user):
        """Corrections should be isolated by organization."""
        # Create another org.
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
            total=100.00,
            state="draft",
        )
        db_session.add(expense)
        db_session.commit()

        manual_correction_service.record_correction(
            expense_id=expense.id,
            owner_id=test_org.id,
            field="total",
            old_value="100.00",
            new_value="120.00",
            corrected_by=test_user.id,
            db=db_session,
        )

        # Query with other org should return empty.
        corrections = manual_correction_service.get_corrections(
            expense_id=expense.id,
            owner_id=other_org.id,
            db=db_session,
        )
        assert len(corrections) == 0


class TestManualCorrectionAPI:
    """Integration tests for manual corrections API."""

    def test_list_corrections_endpoint(self, client: TestClient, auth_headers, db_session, test_org, test_user):
        """GET /api/v1/expenses/{id}/corrections should return corrections."""
        # Create an expense.
        expense = Expense(
            id=uuid.uuid4(),
            owner_id=test_org.id,
            document_id=uuid.uuid4(),
            supplier_id=uuid.uuid4(),
            currency="EUR",
            total=100.00,
            state="draft",
        )
        db_session.add(expense)
        db_session.commit()

        # Record a correction.
        manual_correction_service.record_correction(
            expense_id=expense.id,
            owner_id=test_org.id,
            field="total",
            old_value="100.00",
            new_value="120.00",
            corrected_by=test_user.id,
            db=db_session,
        )

        # Query via API.
        resp = client.get(
            f"/api/v1/expenses/{expense.id}/corrections",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["field"] == "total"
        assert data[0]["old_value"] == "100.00"
        assert data[0]["new_value"] == "120.00"

    def test_list_corrections_empty(self, client: TestClient, auth_headers, db_session, test_org):
        """GET /api/v1/expenses/{id}/corrections should return empty list if no corrections."""
        expense = Expense(
            id=uuid.uuid4(),
            owner_id=test_org.id,
            document_id=uuid.uuid4(),
            supplier_id=uuid.uuid4(),
            currency="EUR",
            total=100.00,
            state="draft",
        )
        db_session.add(expense)
        db_session.commit()

        resp = client.get(
            f"/api/v1/expenses/{expense.id}/corrections",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json() == []
