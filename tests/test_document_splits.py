"""Tests for document splits (E19, INV-4, PHASE3-005)."""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session as DbSession

from backend.models.document import SourceDocument
from backend.models.document_split import DocumentSplit, SplitExpense
from backend.models.expense import Expense
from backend.services import document_split_service


class TestDocumentSplitService:
    """Unit tests for document split service."""

    def _create_document(self, db_session: DbSession, test_org, test_user) -> SourceDocument:
        """Helper to create a test document."""
        document = SourceDocument(
            id=uuid.uuid4(),
            owner_id=test_org.id,
            safe_name="test.pdf",
            original_filename="test.pdf",
            fingerprint_sha256="abc123" * 8,  # 64 chars
            doc_type="invoice",
            format_detected="pdf",
            size_bytes=1024,
            uploaded_by=test_user.id,
            state="uploaded",
        )
        db_session.add(document)
        db_session.commit()
        return document

    def test_create_split(self, db_session: DbSession, test_org, test_user):
        """Should create a document split."""
        document = self._create_document(db_session, test_org, test_user)

        split = document_split_service.create_split(
            document_id=document.id,
            owner_id=test_org.id,
            created_by=test_user.id,
            justification="Document contains multiple expenses",
            db=db_session,
        )
        assert split.id is not None
        assert split.document_id == document.id
        assert split.justification == "Document contains multiple expenses"

    def test_create_split_duplicate(self, db_session: DbSession, test_org, test_user):
        """Should reject duplicate splits for the same document."""
        document = self._create_document(db_session, test_org, test_user)

        # Create first split.
        document_split_service.create_split(
            document_id=document.id,
            owner_id=test_org.id,
            created_by=test_user.id,
            justification="First split",
            db=db_session,
        )

        # Second split should fail.
        with pytest.raises(ValueError, match="already has a split"):
            document_split_service.create_split(
                document_id=document.id,
                owner_id=test_org.id,
                created_by=test_user.id,
                justification="Second split",
                db=db_session,
            )

    def test_add_expense_to_split(self, db_session: DbSession, test_org, test_user):
        """Should link an expense to a split."""
        document = self._create_document(db_session, test_org, test_user)

        split = document_split_service.create_split(
            document_id=document.id,
            owner_id=test_org.id,
            created_by=test_user.id,
            justification="Test split",
            db=db_session,
        )

        expense = Expense(
            id=uuid.uuid4(),
            owner_id=test_org.id,
            document_id=document.id,
            supplier_id=uuid.uuid4(),
            currency="EUR",
            total=Decimal("100.00"),
            state="draft",
        )
        db_session.add(expense)
        db_session.commit()

        link = document_split_service.add_expense_to_split(
            split_id=split.id,
            expense_id=expense.id,
            owner_id=test_org.id,
            db=db_session,
        )
        assert link.split_id == split.id
        assert link.expense_id == expense.id

    def test_add_expense_to_split_duplicate(self, db_session: DbSession, test_org, test_user):
        """Should reject duplicate expense links."""
        document = self._create_document(db_session, test_org, test_user)

        split = document_split_service.create_split(
            document_id=document.id,
            owner_id=test_org.id,
            created_by=test_user.id,
            justification="Test split",
            db=db_session,
        )

        expense = Expense(
            id=uuid.uuid4(),
            owner_id=test_org.id,
            document_id=document.id,
            supplier_id=uuid.uuid4(),
            currency="EUR",
            total=Decimal("100.00"),
            state="draft",
        )
        db_session.add(expense)
        db_session.commit()

        # First link.
        document_split_service.add_expense_to_split(
            split_id=split.id,
            expense_id=expense.id,
            owner_id=test_org.id,
            db=db_session,
        )

        # Second link should fail.
        with pytest.raises(ValueError, match="already linked"):
            document_split_service.add_expense_to_split(
                split_id=split.id,
                expense_id=expense.id,
                owner_id=test_org.id,
                db=db_session,
            )

    def test_get_split(self, db_session: DbSession, test_org, test_user):
        """Should get a split with its expenses."""
        document = self._create_document(db_session, test_org, test_user)

        split = document_split_service.create_split(
            document_id=document.id,
            owner_id=test_org.id,
            created_by=test_user.id,
            justification="Test split",
            db=db_session,
        )

        expense = Expense(
            id=uuid.uuid4(),
            owner_id=test_org.id,
            document_id=document.id,
            supplier_id=uuid.uuid4(),
            currency="EUR",
            total=Decimal("100.00"),
            state="draft",
        )
        db_session.add(expense)
        db_session.commit()

        document_split_service.add_expense_to_split(
            split_id=split.id,
            expense_id=expense.id,
            owner_id=test_org.id,
            db=db_session,
        )

        split_data = document_split_service.get_split(
            split_id=split.id,
            owner_id=test_org.id,
            db=db_session,
        )
        assert split_data is not None
        assert split_data["id"] == str(split.id)
        assert len(split_data["expenses"]) == 1
        assert split_data["expenses"][0]["id"] == str(expense.id)

    def test_list_splits(self, db_session: DbSession, test_org, test_user):
        """Should list splits for a document."""
        document = self._create_document(db_session, test_org, test_user)

        split = document_split_service.create_split(
            document_id=document.id,
            owner_id=test_org.id,
            created_by=test_user.id,
            justification="Test split",
            db=db_session,
        )

        splits = document_split_service.list_splits(
            document_id=document.id,
            owner_id=test_org.id,
            db=db_session,
        )
        assert len(splits) == 1
        assert splits[0]["id"] == str(split.id)

    def test_get_split_isolated_by_org(self, db_session: DbSession, test_org, test_user):
        """Splits should be isolated by organization."""
        from backend.models.organization import Organization
        other_org = Organization(id=uuid.uuid4(), name="Other Org", state="active")
        db_session.add(other_org)
        db_session.commit()

        document = self._create_document(db_session, test_org, test_user)

        split = document_split_service.create_split(
            document_id=document.id,
            owner_id=test_org.id,
            created_by=test_user.id,
            justification="Test split",
            db=db_session,
        )

        # Query with other org should return None.
        split_data = document_split_service.get_split(
            split_id=split.id,
            owner_id=other_org.id,
            db=db_session,
        )
        assert split_data is None


class TestDocumentSplitAPI:
    """Integration tests for document splits API."""

    @pytest.fixture()
    def reviewer_headers(self, client: TestClient, db_session: DbSession, test_org, test_user) -> dict:
        """Get auth headers for a user with reviewer role."""
        test_user.role = "reviewer"
        db_session.commit()

        response = client.post(
            "/api/v1/auth/login",
            json={"username": "testuser", "password": "testpass123"},
        )
        assert response.status_code == 200
        token = response.json()["token"]
        return {"Authorization": f"Bearer {token}"}

    def _create_document(self, db_session: DbSession, test_org, test_user) -> SourceDocument:
        """Helper to create a test document."""
        document = SourceDocument(
            id=uuid.uuid4(),
            owner_id=test_org.id,
            safe_name="test.pdf",
            original_filename="test.pdf",
            fingerprint_sha256="abc123" * 8,  # 64 chars
            doc_type="invoice",
            format_detected="pdf",
            size_bytes=1024,
            uploaded_by=test_user.id,
            state="uploaded",
        )
        db_session.add(document)
        db_session.commit()
        return document

    def test_create_split_endpoint(self, client: TestClient, reviewer_headers, db_session, test_org, test_user):
        """POST /api/v1/documents/{id}/splits should create a split."""
        document = self._create_document(db_session, test_org, test_user)

        resp = client.post(
            f"/api/v1/documents/{document.id}/splits",
            json={"justification": "Multiple expenses"},
            headers=reviewer_headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["document_id"] == str(document.id)
        assert data["justification"] == "Multiple expenses"

    def test_get_split_endpoint(self, client: TestClient, auth_headers, db_session, test_org, test_user):
        """GET /api/v1/splits/{id} should return a split."""
        document = self._create_document(db_session, test_org, test_user)

        split = document_split_service.create_split(
            document_id=document.id,
            owner_id=test_org.id,
            created_by=test_user.id,
            justification="Test split",
            db=db_session,
        )

        resp = client.get(
            f"/api/v1/splits/{split.id}",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == str(split.id)

    def test_list_splits_endpoint(self, client: TestClient, auth_headers, db_session, test_org, test_user):
        """GET /api/v1/documents/{id}/splits should list splits."""
        document = self._create_document(db_session, test_org, test_user)

        document_split_service.create_split(
            document_id=document.id,
            owner_id=test_org.id,
            created_by=test_user.id,
            justification="Test split",
            db=db_session,
        )

        resp = client.get(
            f"/api/v1/documents/{document.id}/splits",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
