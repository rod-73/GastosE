# 02 — Estrategia de migraciones Alembic (GastosE Phase 2)

Estrategia de migraciones para el esquema de GastosE. Define cómo se
materializa el diseño de `01-schema-design.md` como migraciones Alembic
ejecutables, con upgrade y downgrade completos.

## Principios

1. **Una migración por vertical slice**: cada slice (V1-S1, V1-S2, …) tiene
   una o pocas migraciones que crean/modifican las tablas que ese slice
   necesita. No se crea el esquema completo de golpe.
2. **Upgrade y downgrade completos**: toda migración tiene `upgrade()` y
   `downgrade()` que se anulan exactamente. El downgrade destruye lo que el
   upgrade creó (tablas, índices, constraints, triggers, permisos).
3. **Idempotencia de migraciones**: Alembic gestiona la versión en
   `alembic_version`. No se ejecutan dos veces la misma migración.
4. **Orden determinista**: las migraciones se encadenan por `down_revision`.
   No hay branches en V1.
5. **Sin datos de producción en migraciones**: las migraciones de datos
   (seed) son separadas de las de esquema. Los datos de referencia
   (`currencies`, `tax_rates` iniciales) se insertan en migraciones de seed
   con `downgrade` que los elimina.
6. **Triggers y permisos en la misma migración**: si una migración crea una
   tabla con trigger o restringe permisos, el downgrade debe revertirlos.

## Estructura del proyecto

```
gastose/
  alembic/
    env.py              # Configuración de Alembic (conexión, target_metadata)
    script.py.mako      # Plantilla de migración
    versions/
      0001_initial_foundation.py
      0002_v1_s1_document_ingestion.py
      0003_v1_s2_extraction.py
      ...
  alembic.ini           # Configuración de Alembic
```

- `env.py` configura `target_metadata` desde el modelo SQLAlchemy para
  autogenerar migraciones cuando sea posible.
- `script.py.mako` incluye el template estándar con `upgrade()` y
  `downgrade()`.

## Naming convention

```
NNNN_<descripción_corto>.py
```

- `NNNN`: número de 4 dígitos, secuencial.
- `<descripción_corto>`: snake_case, describe el cambio.

Ejemplos:
- `0001_initial_foundation.py`
- `0002_v1_s1_document_ingestion.py`
- `0003_v1_s2_extraction.py`
- `0004_v1_s3_expense_core.py`
- `0005_v1_s4_review_acceptance.py`

## Migración inicial (0001)

La migración `0001_initial_foundation.py` crea las tablas de tenencia y
catálogos que son prerequisito de todos los slices:

### Tablas creadas en 0001

| Tabla | Justificación |
|---|---|
| `organizations` | Prerequisito de tenencia (ADR-0008). |
| `users` | Prerequisito de autenticación (ADR-0009). |
| `sessions` | Prerequisito de autenticación (ADR-0009). |
| `currencies` | Catálogo global, prerequisito de `expenses`. |
| `tax_rates` | Catálogo, prerequisito de `expense_lines` y `tax_lines`. |
| `categories` | Catálogo, prerequisito de `expenses`. |
| `payment_methods` | Catálogo, prerequisito de `payments`. |
| `suppliers` | Prerequisito de `expenses` (INV-5). |

### Seed en 0001

- `currencies`: insertar EUR, USD, GBP (mínimo). El `downgrade` los elimina.
- `tax_rates`: NO se siembran en 0001 (dependen de la organización; se
  crean por la API de administración).

### DDL ilustrativo (upgrade)

```python
def upgrade():
    # organizations
    op.create_table(
        "organizations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("state IN ('active', 'inactive')", name="chk_org_state"),
    )
    # ... (resto de tablas)

def downgrade():
    # Inverso: DROP en orden inverso a las dependencias
    op.drop_table("suppliers")
    op.drop_table("payment_methods")
    op.drop_table("categories")
    op.drop_table("tax_rates")
    op.drop_table("currencies")
    op.drop_table("sessions")
    op.drop_table("users")
    op.drop_table("organizations")
```

## Migraciones por slice

### 0002 — V1-S1: Document Ingestion

Crea las tablas necesarias para el slice V1-S1 (upload de documentos):

| Tabla | Justificación |
|---|---|
| `source_documents` | E1: documento fuente. |
| `extraction_jobs` | Cola de trabajo (ADR-0005). |
| `idempotency_keys` | NFR-4: idempotencia. |
| `audit_events` | E16: auditoría (necesaria desde el primer slice). |

**Índices** (ver `05-indexes-and-performance.md`):
- `idx_source_documents_owner` ON `(owner_id)`
- `idx_source_documents_fingerprint` ON `(owner_id, fingerprint_sha256)` UNIQUE
- `idx_extraction_jobs_claim` ON `(state, next_retry_at)` WHERE `state = 'pending'`
- `idx_audit_events_entity` ON `(owner_id, entity_type, entity_id)`

**Triggers** (ver `07-audit-and-retention.md`):
- Trigger de append-only en `audit_events` (prohíbe UPDATE/DELETE).
- Trigger de append-only en `manual_corrections` (si se crea en este slice).

**Permisos** (ver `07-audit-and-retention.md`):
- `REVOKE UPDATE, DELETE ON audit_events FROM app_user;`

### 0003 — V1-S2: Extraction

Crea las tablas de extracción:

| Tabla | Justificación |
|---|---|
| `extractions` | E2: proceso de extracción. |
| `extracted_values` | E3: valores extraídos. |

**Índices**:
- `idx_extractions_document` ON `(document_id)`
- `idx_extracted_values_extraction` ON `(extraction_id)`

### 0004 — V1-S3: Expense Core

Crea las tablas de gasto:

| Tabla | Justificación |
|---|---|
| `normalized_values` | E4: valores normalizados. |
| `validated_values` | E5: valores validados. |
| `expenses` | E6: gasto. |
| `expense_lines` | E7: líneas de gasto. |
| `tax_lines` | E8: líneas de impuesto. |
| `payments` | E12: pagos. |
| `duplications` | E15: detección de duplicados. |
| `document_splits` | E19: splits de documento. |
| `split_expenses` | Tabla de asociación split→gasto. |

**Índices**:
- `idx_expenses_owner_state` ON `(owner_id, state)`
- `idx_expenses_document` ON `(document_id)`
- `idx_expenses_supplier` ON `(supplier_id)`
- `idx_expense_lines_expense` ON `(expense_id)`
- `idx_tax_lines_expense` ON `(expense_id)`
- `idx_duplications_owner` ON `(owner_id, state)`

### 0005 — V1-S4: Review & Acceptance

Crea las tablas de revisión:

| Tabla | Justificación |
|---|---|
| `reviews` | E13: revisión. |
| `review_field_results` | Resultados por campo. |
| `manual_corrections` | E14: correcciones manuales. |

**Triggers**:
- Trigger de append-only en `manual_corrections` (prohíbe UPDATE/DELETE).

**Permisos**:
- `REVOKE UPDATE, DELETE ON manual_corrections FROM app_user;`

## Plantilla de migración

```python
"""<descripción>

Revision ID: <alembic revision id>
Revises: <down_revision>
Create Date: <fecha>
"""
from alembic import op
import sqlalchemy as sa

revision = "<alembic revision id>"
down_revision = "<down_revision>"
branch_labels = None
depends_on = None


def upgrade():
    # 1. Crear tablas (en orden de dependencias)
    # 2. Crear índices
    # 3. Crear triggers
    # 4. Aplicar permisos
    # 5. Seed (si aplica)
    pass


def downgrade():
    # Inverso exacto:
    # 1. Eliminar seed
    # 2. Revocar permisos / restaurar permisos
    # 3. Eliminar triggers
    # 4. Eliminar índices
    # 5. Eliminar tablas (en orden inverso a las dependencias)
    pass
```

## Reglas de migración

1. **No modificar migraciones ya aplicadas**: una migración en producción no
   se edita. Si hay un error, se crea una nueva migración que lo corrige.
2. **No romper la cadena**: `down_revision` debe apuntar a la migración
   inmediatamente anterior. No hay branches.
3. **Triggers y permisos en el downgrade**: si el upgrade crea un trigger o
   revoca un permiso, el downgrade debe eliminar el trigger o restaurar el
   permiso.
4. **Seed reversible**: los datos sembrados en una migración deben poder
   eliminarse en el downgrade (por `id` o por `code`).
5. **Testing**: cada migración se testa en un entorno limpio (upgrade +
   downgrade + upgrade). Ver skill `testing`.

## Herramientas

- `migration-check` (custom tool): comprueba heads, branches, grafo de
  migraciones. Se ejecuta tras cada migración.
- `alembic upgrade head`: aplica todas las migraciones.
- `alembic downgrade -1`: revierte la última migración.
- `alembic history`: muestra el grafo de migraciones.

## Riesgos

| Riesgo | Mitigación |
|---|---|
| Migración que no tiene downgrade correcto | Test de upgrade+downgrade+upgrade en CI. |
| Migración que rompe datos existentes | No modificar migraciones aplicadas; nueva migración para correcciones. |
| Branching accidental | `migration-check` detecta branches. |
| Seed no reversible | El downgrade elimina los datos sembrados por `id`/`code`. |
