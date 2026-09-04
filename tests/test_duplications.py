"""Tests for V5-S1 (duplication detection) and V5-S2 (duplication resolution).

Covers:
- build_dup_key: key construction and normalization.
- detect_logical_duplicates: detection at extraction completion.
- GET /duplications: list with filter.
- GET /duplications/{id}: detail with document info.
- POST /duplications/{id}/resolve: confirmed, not_duplicate, invalid.
- Isolation: another org cannot see/resolve.
"""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.database import Base, get_db
from backend.models import (
    Organization,
    User,
    Session as SessionModel,
    SourceDocument,
    Extraction,
    ExtractedValue,
    NormalizedValue,
    ValidatedValue,
    Expense,
    TaxRate,
    Supplier,
    Duplication,
    AuditEvent,
)
from backend.main import create_app
from backend.services.duplication_service import build_dup_key
from backend.utils import uuid7
import bcrypt


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


@pytest.fixture(autouse=True)
def _isolate_storage(tmp_path, monkeypatch):
    storage = tmp_path / "documents"
    storage.mkdir()
    monkeypatch.setenv("GASTOSE_DOCUMENT_STORAGE_PATH", str(storage))
    yield


@pytest.fixture()
def db_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture()
def db_session(db_engine) -> Generator[DbSession, None, None]:
    TestingSessionLocal = sessionmaker(bind=db_engine, autoflush=False)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def test_org(db_session: DbSession) -> Organization:
    org = Organization(id=uuid.uuid4(), name="Test Org", state="active")
    db_session.add(org)
    db_session.commit()
    db_session.refresh(org)
    return org


@pytest.fixture()
def other_org(db_session: DbSession) -> Organization:
    org = Organization(id=uuid.uuid4(), name="Other Org", state="active")
    db_session.add(org)
    db_session.commit()
    db_session.refresh(org)
    return org


@pytest.fixture()
def test_user(db_session: DbSession, test_org: Organization) -> User:
    user = User(
        id=uuid.uuid4(),
        organization_id=test_org.id,
        username="testuser",
        email="test@example.com",
        password_hash=_hash_password("testpass123"),
        role="approver",
        state="active",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture()
def test_session(db_session: DbSession, test_user: User, test_org: Organization) -> SessionModel:
    token = "test-worker-token"
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    session = SessionModel(
        id=token_hash,
        user_id=test_user.id,
        organization_id=test_org.id,
        role="approver",
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        revoked_at=None,
    )
    db_session.add(session)
    db_session.commit()
    db_session.refresh(session)
    return session


@pytest.fixture()
def client(
    db_engine,
    test_org: Organization,
    test_user: User,
    test_session: SessionModel,
) -> Generator[TestClient, None, None]:
    TestingSessionLocal = sessionmaker(bind=db_engine, autoflush=False)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    app.state.session_factory = TestingSessionLocal

    with TestClient(app) as c:
        yield c


@pytest.fixture()
def auth_headers(client: TestClient, test_user: User, test_org: Organization) -> dict:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "testuser", "password": "testpass123"},
    )
    assert response.status_code == 200
    token = response.json()["token"]
    return {"Authorization": f"Bearer {token}"}


def _create_document_with_extraction(
    db: DbSession,
    org: Organization,
    user: User,
    supplier: str = "Acme Corp SL",
    doc_number: str = "INV-001",
    date_str: str = "2024-01-15",
    total: str = "121.00",
    base: str = "100.00",
    vat: str = "21.00",
    content: bytes = b"test document content",
    doc_state: str = "extracted",
) -> tuple:
    """Create a document with a completed extraction.

    Returns (doc_id, extraction_id).
    """
    from datetime import date as date_type

    # Tax rate.
    existing_tr = (
        db.execute(select(TaxRate).where(TaxRate.owner_id == org.id))
        .scalars()
        .first()
    )
    if existing_tr is None:
        tr = TaxRate(
            id=uuid7(),
            owner_id=org.id,
            code="VAT21",
            description="IVA 21%",
            tax_type="vat",
            percentage=Decimal("21.00"),
            valid_from=date_type(2020, 1, 1),
        )
        db.add(tr)
        db.flush()

    fingerprint = hashlib.sha256(content).hexdigest()
    safe_name = f"{uuid7()}.xml"

    doc = SourceDocument(
        id=uuid7(),
        owner_id=org.id,
        safe_name=safe_name,
        original_filename="test.xml",
        fingerprint_sha256=fingerprint,
        doc_type="received_invoice",
        format_detected="xml",
        size_bytes=len(content),
        uploaded_by=user.id,
        state=doc_state,
    )
    db.add(doc)
    db.flush()

    extraction = Extraction(
        id=uuid7(),
        owner_id=org.id,
        document_id=doc.id,
        method="xml_schema",
        state="completed",
        started_at=datetime.now(timezone.utc),
        finished_at=datetime.now(timezone.utc),
    )
    db.add(extraction)
    db.flush()

    values = [
        {"field": "supplier_name", "raw": supplier},
        {"field": "invoice_number", "raw": doc_number},
        {"field": "invoice_date", "raw": date_str},
        {"field": "total_amount", "raw": total},
        {"field": "base_amount", "raw": base},
        {"field": "vat_amount", "raw": vat},
        {"field": "currency", "raw": "EUR"},
        {"field": "vat_rate", "raw": "21"},
    ]
    for v in values:
        ev = ExtractedValue(
            id=uuid7(),
            owner_id=org.id,
            extraction_id=extraction.id,
            field=v["field"],
            raw_value=v["raw"],
            confidence=0.95,
            provenance={"method": "xml_schema", "rule": f"xml:{v['field']}"},
        )
        db.add(ev)
        db.flush()

    # Store file.
    from backend.config import get_settings
    settings = get_settings()
    directory = os.path.join(settings.DOCUMENT_STORAGE_PATH, str(org.id))
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, fingerprint)
    with open(path, "wb") as fh:
        fh.write(content)

    db.commit()
    return str(doc.id), str(extraction.id)


# --- build_dup_key tests ---


class TestBuildDupKey:
    def test_basic_key(self):
        key = build_dup_key("Acme Corp", "INV-001", "2024-01-15", "121.00")
        assert key == "acme corp|inv-001|2024-01-15|121.00"

    def test_normalization(self):
        key1 = build_dup_key("  Acme Corp  ", " INV-001 ", "2024-01-15", "121.00")
        key2 = build_dup_key("acme corp", "inv-001", "2024-01-15", "121.00")
        assert key1 == key2

    def test_no_document_number(self):
        key = build_dup_key("Acme Corp", None, "2024-01-15", "121.00")
        assert key == "acme corp||2024-01-15|121.00"

    def test_missing_fields(self):
        key = build_dup_key("Acme Corp", "", "", "")
        assert key == "acme corp|||"


# --- detect_logical_duplicates tests ---


class TestDetectLogicalDuplicates:
    def test_detect_duplicate(self, db_session, test_org, test_user):
        """Two documents with same supplier, number, date, total -> duplication."""
        doc1_id, ext1_id = _create_document_with_extraction(
            db_session, test_org, test_user,
            supplier="Acme Corp", doc_number="INV-001",
            date_str="2024-01-15", total="121.00",
            content=b"first doc",
        )

        # Create second document with same key.
        doc2_id, ext2_id = _create_document_with_extraction(
            db_session, test_org, test_user,
            supplier="Acme Corp", doc_number="INV-001",
            date_str="2024-01-15", total="121.00",
            content=b"second doc",
        )

        # Set dup_key on first doc (simulating detection at first extraction).
        doc1 = db_session.get(SourceDocument, uuid.UUID(doc1_id))
        doc1.dup_key = build_dup_key("Acme Corp", "INV-001", "2024-01-15", "121.00")
        db_session.commit()

        # Run detection on second extraction.
        from backend.services.duplication_service import detect_logical_duplicates
        created = detect_logical_duplicates(
            extraction_id=uuid.UUID(ext2_id),
            owner_id=test_org.id,
            db=db_session,
        )

        assert len(created) == 1
        dup = created[0]
        assert dup.state == "probable"
        assert dup.dup_type == "logical"

    def test_no_duplicate_different_supplier(self, db_session, test_org, test_user):
        """Different supplier -> no duplication."""
        _create_document_with_extraction(
            db_session, test_org, test_user,
            supplier="Acme Corp", doc_number="INV-001",
            date_str="2024-01-15", total="121.00",
            content=b"first doc",
        )
        doc2_id, ext2_id = _create_document_with_extraction(
            db_session, test_org, test_user,
            supplier="Beta Corp", doc_number="INV-001",
            date_str="2024-01-15", total="121.00",
            content=b"second doc",
        )

        # Set dup_key on first doc.
        doc1 = db_session.execute(
            select(SourceDocument).where(
                SourceDocument.owner_id == test_org.id
            ).order_by(SourceDocument.created_at.asc())
        ).scalars().first()
        doc1.dup_key = build_dup_key("Acme Corp", "INV-001", "2024-01-15", "121.00")
        db_session.commit()

        from backend.services.duplication_service import detect_logical_duplicates
        created = detect_logical_duplicates(
            extraction_id=uuid.UUID(ext2_id),
            owner_id=test_org.id,
            db=db_session,
        )
        assert len(created) == 0

    def test_idempotency(self, db_session, test_org, test_user):
        """Running detection twice doesn't create duplicate records."""
        _create_document_with_extraction(
            db_session, test_org, test_user,
            supplier="Acme Corp", doc_number="INV-001",
            date_str="2024-01-15", total="121.00",
            content=b"first doc",
        )
        doc2_id, ext2_id = _create_document_with_extraction(
            db_session, test_org, test_user,
            supplier="Acme Corp", doc_number="INV-001",
            date_str="2024-01-15", total="121.00",
            content=b"second doc",
        )

        doc1 = db_session.execute(
            select(SourceDocument).where(
                SourceDocument.owner_id == test_org.id
            ).order_by(SourceDocument.created_at.asc())
        ).scalars().first()
        doc1.dup_key = build_dup_key("Acme Corp", "INV-001", "2024-01-15", "121.00")
        db_session.commit()

        from backend.services.duplication_service import detect_logical_duplicates
        created1 = detect_logical_duplicates(
            extraction_id=uuid.UUID(ext2_id),
            owner_id=test_org.id,
            db=db_session,
        )
        created2 = detect_logical_duplicates(
            extraction_id=uuid.UUID(ext2_id),
            owner_id=test_org.id,
            db=db_session,
        )

        assert len(created1) == 1
        assert len(created2) == 0  # Idempotent: no new records.


# --- GET /duplications tests ---


class TestListDuplications:
    def test_list_empty(self, client, auth_headers):
        """Empty list."""
        response = client.get(
            "/api/v1/duplications",
            headers=auth_headers,
        )
        assert response.status_code == 200
        body = response.json()
        assert body["count"] == 0
        assert body["duplications"] == []

    def test_list_with_items(self, client, auth_headers, db_session, test_org, test_user):
        """List shows duplications."""
        _create_document_with_extraction(
            db_session, test_org, test_user,
            supplier="Acme Corp", doc_number="INV-001",
            date_str="2024-01-15", total="121.00",
            content=b"first doc",
        )
        doc2_id, ext2_id = _create_document_with_extraction(
            db_session, test_org, test_user,
            supplier="Acme Corp", doc_number="INV-001",
            date_str="2024-01-15", total="121.00",
            content=b"second doc",
        )

        doc1 = db_session.execute(
            select(SourceDocument).where(
                SourceDocument.owner_id == test_org.id
            ).order_by(SourceDocument.created_at.asc())
        ).scalars().first()
        doc1.dup_key = build_dup_key("Acme Corp", "INV-001", "2024-01-15", "121.00")
        db_session.commit()

        from backend.services.duplication_service import detect_logical_duplicates
        detect_logical_duplicates(
            extraction_id=uuid.UUID(ext2_id),
            owner_id=test_org.id,
            db=db_session,
        )

        response = client.get(
            "/api/v1/duplications",
            headers=auth_headers,
        )
        assert response.status_code == 200
        body = response.json()
        assert body["count"] == 1
        assert body["duplications"][0]["state"] == "probable"

    def test_list_filter_by_state(self, client, auth_headers, db_session, test_org, test_user):
        """Filter by state."""
        _create_document_with_extraction(
            db_session, test_org, test_user,
            supplier="Acme Corp", doc_number="INV-001",
            date_str="2024-01-15", total="121.00",
            content=b"first doc",
        )
        doc2_id, ext2_id = _create_document_with_extraction(
            db_session, test_org, test_user,
            supplier="Acme Corp", doc_number="INV-001",
            date_str="2024-01-15", total="121.00",
            content=b"second doc",
        )

        doc1 = db_session.execute(
            select(SourceDocument).where(
                SourceDocument.owner_id == test_org.id
            ).order_by(SourceDocument.created_at.asc())
        ).scalars().first()
        doc1.dup_key = build_dup_key("Acme Corp", "INV-001", "2024-01-15", "121.00")
        db_session.commit()

        from backend.services.duplication_service import detect_logical_duplicates
        detect_logical_duplicates(
            extraction_id=uuid.UUID(ext2_id),
            owner_id=test_org.id,
            db=db_session,
        )

        # Filter by probable.
        response = client.get(
            "/api/v1/duplications?state=probable",
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["count"] == 1

        # Filter by confirmed (none).
        response = client.get(
            "/api/v1/duplications?state=confirmed",
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["count"] == 0


# --- GET /duplications/{id} tests ---


class TestGetDuplication:
    def test_get_detail(self, client, auth_headers, db_session, test_org, test_user):
        """Get duplication detail with document info."""
        doc1_id, _ = _create_document_with_extraction(
            db_session, test_org, test_user,
            supplier="Acme Corp", doc_number="INV-001",
            date_str="2024-01-15", total="121.00",
            content=b"first doc",
        )
        doc2_id, ext2_id = _create_document_with_extraction(
            db_session, test_org, test_user,
            supplier="Acme Corp", doc_number="INV-001",
            date_str="2024-01-15", total="121.00",
            content=b"second doc",
        )

        doc1 = db_session.get(SourceDocument, uuid.UUID(doc1_id))
        doc1.dup_key = build_dup_key("Acme Corp", "INV-001", "2024-01-15", "121.00")
        db_session.commit()

        from backend.services.duplication_service import detect_logical_duplicates
        created = detect_logical_duplicates(
            extraction_id=uuid.UUID(ext2_id),
            owner_id=test_org.id,
            db=db_session,
        )
        assert len(created) == 1
        dup_id = str(created[0].id)

        response = client.get(
            f"/api/v1/duplications/{dup_id}",
            headers=auth_headers,
        )
        assert response.status_code == 200
        body = response.json()
        assert body["id"] == dup_id
        assert body["state"] == "probable"
        assert body["document_a"]["id"] is not None
        assert body["document_b"]["id"] is not None

    def test_get_not_found(self, client, auth_headers):
        """Non-existent duplication -> 404."""
        fake_id = uuid.uuid4()
        response = client.get(
            f"/api/v1/duplications/{fake_id}",
            headers=auth_headers,
        )
        assert response.status_code == 404

    def test_get_isolation(self, client, db_session, test_org, other_org, test_user):
        """Another org cannot see this duplication -> 404."""
        doc1_id, _ = _create_document_with_extraction(
            db_session, test_org, test_user,
            supplier="Acme Corp", doc_number="INV-001",
            date_str="2024-01-15", total="121.00",
            content=b"first doc",
        )
        doc2_id, ext2_id = _create_document_with_extraction(
            db_session, test_org, test_user,
            supplier="Acme Corp", doc_number="INV-001",
            date_str="2024-01-15", total="121.00",
            content=b"second doc",
        )

        doc1 = db_session.get(SourceDocument, uuid.UUID(doc1_id))
        doc1.dup_key = build_dup_key("Acme Corp", "INV-001", "2024-01-15", "121.00")
        db_session.commit()

        from backend.services.duplication_service import detect_logical_duplicates
        created = detect_logical_duplicates(
            extraction_id=uuid.UUID(ext2_id),
            owner_id=test_org.id,
            db=db_session,
        )
        dup_id = str(created[0].id)

        other_user = User(
            id=uuid.uuid4(),
            organization_id=other_org.id,
            username="otheruser",
            email="other@example.com",
            password_hash=_hash_password("otherpass123"),
            role="approver",
            state="active",
        )
        db_session.add(other_user)
        db_session.commit()
        db_session.refresh(other_user)

        response = client.post(
            "/api/v1/auth/login",
            json={"username": "otheruser", "password": "otherpass123"},
        )
        other_token = response.json()["token"]
        other_headers = {"Authorization": f"Bearer {other_token}"}

        response = client.get(
            f"/api/v1/duplications/{dup_id}",
            headers=other_headers,
        )
        assert response.status_code == 404


# --- POST /duplications/{id}/resolve tests ---


class TestResolveDuplication:
    def _setup_duplication(self, db_session, test_org, test_user) -> str:
        """Create a probable duplication and return its ID."""
        doc1_id, _ = _create_document_with_extraction(
            db_session, test_org, test_user,
            supplier="Acme Corp", doc_number="INV-001",
            date_str="2024-01-15", total="121.00",
            content=b"first doc",
        )
        doc2_id, ext2_id = _create_document_with_extraction(
            db_session, test_org, test_user,
            supplier="Acme Corp", doc_number="INV-001",
            date_str="2024-01-15", total="121.00",
            content=b"second doc",
        )

        doc1 = db_session.get(SourceDocument, uuid.UUID(doc1_id))
        doc1.dup_key = build_dup_key("Acme Corp", "INV-001", "2024-01-15", "121.00")
        db_session.commit()

        from backend.services.duplication_service import detect_logical_duplicates
        created = detect_logical_duplicates(
            extraction_id=uuid.UUID(ext2_id),
            owner_id=test_org.id,
            db=db_session,
        )
        assert len(created) == 1
        return str(created[0].id)

    def test_resolve_confirmed(self, client, auth_headers, db_session, test_org, test_user):
        """Resolve as confirmed duplicate."""
        dup_id = self._setup_duplication(db_session, test_org, test_user)

        response = client.post(
            f"/api/v1/duplications/{dup_id}/resolve",
            json={"resolution": "confirmed", "reason": "Same invoice uploaded twice"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        body = response.json()
        assert body["state"] == "confirmed"
        assert body["resolution_reason"] == "Same invoice uploaded twice"

    def test_resolve_not_duplicate(self, client, auth_headers, db_session, test_org, test_user):
        """Resolve as not a duplicate."""
        dup_id = self._setup_duplication(db_session, test_org, test_user)

        response = client.post(
            f"/api/v1/duplications/{dup_id}/resolve",
            json={"resolution": "not_duplicate", "reason": "Two separate purchases"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        body = response.json()
        assert body["state"] == "not_duplicate"

    def test_resolve_already_resolved(self, client, auth_headers, db_session, test_org, test_user):
        """Cannot resolve an already resolved duplication."""
        dup_id = self._setup_duplication(db_session, test_org, test_user)

        client.post(
            f"/api/v1/duplications/{dup_id}/resolve",
            json={"resolution": "confirmed", "reason": "First"},
            headers=auth_headers,
        )

        response = client.post(
            f"/api/v1/duplications/{dup_id}/resolve",
            json={"resolution": "not_duplicate", "reason": "Second"},
            headers=auth_headers,
        )
        assert response.status_code == 409

    def test_resolve_invalid_resolution(self, client, auth_headers, db_session, test_org, test_user):
        """Invalid resolution type -> 409."""
        dup_id = self._setup_duplication(db_session, test_org, test_user)

        response = client.post(
            f"/api/v1/duplications/{dup_id}/resolve",
            json={"resolution": "invalid", "reason": "Test"},
            headers=auth_headers,
        )
        assert response.status_code == 409

    def test_resolve_missing_reason(self, client, auth_headers, db_session, test_org, test_user):
        """Missing reason -> 409."""
        dup_id = self._setup_duplication(db_session, test_org, test_user)

        response = client.post(
            f"/api/v1/duplications/{dup_id}/resolve",
            json={"resolution": "confirmed", "reason": ""},
            headers=auth_headers,
        )
        assert response.status_code == 409

    def test_resolve_not_found(self, client, auth_headers):
        """Non-existent duplication -> 409."""
        fake_id = uuid.uuid4()
        response = client.post(
            f"/api/v1/duplications/{fake_id}/resolve",
            json={"resolution": "confirmed", "reason": "Test"},
            headers=auth_headers,
        )
        assert response.status_code == 409
