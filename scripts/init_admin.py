#!/usr/bin/env python3
"""
Script de inicialización: crea organización y usuario admin.

Uso:
    docker exec gastose-backend python /app/scripts/init_admin.py

O desde el host:
    python scripts/init_admin.py
"""

import os
import sys
import uuid
from datetime import datetime, timezone

import bcrypt
import sqlalchemy
from sqlalchemy import text


def get_database_url() -> str:
    """Obtiene DATABASE_URL del entorno o por defecto."""
    return os.environ.get(
        "GASTOSE_DATABASE_URL",
        "postgresql://gastose:gastose@localhost:5432/gastose",
    )


def hash_password(password: str) -> str:
    """Hashea la contraseña con bcrypt."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def main() -> int:
    db_url = get_database_url()
    print(f"Conectando a: {db_url.split('@')[-1]}")  # Oculta password

    engine = sqlalchemy.create_engine(db_url)

    with engine.connect() as conn:
        # Verificar si ya existe organización
        result = conn.execute(
            text("SELECT id, name FROM organizations WHERE name = :name"),
            {"name": "Test Org"},
        )
        row = result.fetchone()

        if row:
            org_id = row[0]
            print(f"Organización existente: {row[1]} ({org_id})")
        else:
            org_id = str(uuid.uuid4())
            conn.execute(
                text(
                    "INSERT INTO organizations (id, name, state, created_at, updated_at) "
                    "VALUES (:id, :name, 'active', NOW(), NOW())"
                ),
                {"id": org_id, "name": "Test Org"},
            )
            conn.commit()
            print(f"Organización creada: Test Org ({org_id})")

        # Verificar si ya existe usuario admin
        result = conn.execute(
            text("SELECT id, username FROM users WHERE username = :username"),
            {"username": "admin"},
        )
        row = result.fetchone()

        if row:
            print(f"Usuario existente: {row[1]} ({row[0]})")
            # Actualizar contraseña
            password_hash = hash_password("admin123")
            conn.execute(
                text("UPDATE users SET password_hash = :hash WHERE id = :id"),
                {"hash": password_hash, "id": row[0]},
            )
            conn.commit()
            print("Contraseña actualizada a: admin123")
        else:
            user_id = str(uuid.uuid4())
            password_hash = hash_password("admin123")
            conn.execute(
                text(
                    "INSERT INTO users (id, username, email, password_hash, organization_id, "
                    "role, state, created_at, updated_at) "
                    "VALUES (:id, 'admin', 'admin@example.com', :hash, :org_id, 'admin', 'active', NOW(), NOW())"
                ),
                {"id": user_id, "hash": password_hash, "org_id": org_id},
            )
            conn.commit()
            print(f"Usuario admin creado ({user_id})")

        # Verificar si ya existe tasa de IVA 21%
        result = conn.execute(
            text("SELECT id FROM tax_rates WHERE owner_id = :org_id AND code = :code"),
            {"org_id": org_id, "code": "VAT-21"},
        )
        row = result.fetchone()

        if row:
            print(f"Tasa de IVA existente: VAT-21 ({row[0]})")
        else:
            rate_id = str(uuid.uuid4())
            conn.execute(
                text(
                    "INSERT INTO tax_rates (id, owner_id, code, description, tax_type, "
                    "percentage, valid_from, valid_until, jurisdiction, created_at, updated_at) "
                    "VALUES (:id, :org_id, 'VAT-21', 'IVA 21%', 'vat', 21.00, "
                    "'2020-01-01', NULL, 'ES', NOW(), NOW())"
                ),
                {"id": rate_id, "org_id": org_id},
            )
            conn.commit()
            print(f"Tasa de IVA creada: VAT-21 (21%)")

    print("\n✓ Inicialización completada")
    print("  Usuario: admin")
    print("  Password: admin123")
    print("  Tasa de IVA: VAT-21 (21%)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
