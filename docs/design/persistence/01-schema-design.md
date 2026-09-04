# 01 — Diseño de esquema relacional (GastosE Phase 2)

Esquema relacional completo de GastosE para PostgreSQL. Cada tabla incluye:
columnas con tipo PostgreSQL, PK, FKs, constraints, y DDL ilustrativo.

**Nota**: el DDL es **esquemático** (referencia de diseño). No es el artefacto
final que se ejecuta; el agente `backend` lo materializará como migraciones
Alembic.

## Convenciones

- PK: `UUID` (UUIDv7) para recursos públicos; `CHAR(3)` para `currencies`.
- FK: `UUID` con `REFERENCES ... ON DELETE RESTRICT` (datos contables).
- Estados: `TEXT` + `CHECK` (no enums nativos).
- Dinero: `NUMERIC(14,2)`. Nunca `FLOAT`.
- Fechas: `DATE` para fechas de documento; `TIMESTAMPTZ` para eventos.
- `owner_id`: `UUID` NOT NULL FK → `organizations.id` en todas las tablas de
  negocio (ADR-0008).
- Timestamps: `created_at`, `updated_at` en todas las tablas de negocio.

---

## 1. Tablas de tenencia (ADR-0008)

### 1.1 `organizations`

```sql
CREATE TABLE organizations (
    id          UUID PRIMARY KEY,
    name        TEXT NOT NULL,
    state       TEXT NOT NULL DEFAULT 'active'
                CHECK (state IN ('active', 'inactive')),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### 1.2 `users`

```sql
CREATE TABLE users (
    id               UUID PRIMARY KEY,
    organization_id  UUID NOT NULL REFERENCES organizations(id) ON DELETE RESTRICT,
    username         TEXT NOT NULL UNIQUE,
    email            TEXT NOT NULL UNIQUE,
    password_hash    TEXT NOT NULL,
    role             TEXT NOT NULL DEFAULT 'reader'
                     CHECK (role IN ('reader', 'reviewer', 'approver', 'admin')),
    state            TEXT NOT NULL DEFAULT 'active'
                     CHECK (state IN ('active', 'inactive')),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### 1.3 `sessions` (ADR-0009)

```sql
CREATE TABLE sessions (
    id               TEXT PRIMARY KEY,  -- token opaco (UUID aleatorio)
    user_id          UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    organization_id  UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    role             TEXT NOT NULL,
    expires_at       TIMESTAMPTZ NOT NULL,
    last_seen_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    revoked_at       TIMESTAMPTZ,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

- **PK**: `id` (token opaco).
- **FK**: `user_id` → `users.id` (CASCADE: al eliminar usuario, se eliminan
  sus sesiones); `organization_id` → `organizations.id` (CASCADE).
- **Nota**: `revoked_at` NULL = sesión activa. La expiración se verifica en la
  aplicación (comparar `expires_at` y `last_seen_at` con NOW()).

---

## 2. Tablas de negocio

### 2.1 `source_documents` (E1)

```sql
CREATE TABLE source_documents (
    id                  UUID PRIMARY KEY,
    owner_id            UUID NOT NULL REFERENCES organizations(id) ON DELETE RESTRICT,
    safe_name           TEXT NOT NULL,
    original_filename   TEXT,
    fingerprint_sha256  CHAR(64) NOT NULL,
    doc_type            TEXT NOT NULL
                        CHECK (doc_type IN ('received_invoice', 'ticket', 'other')),
    format_detected     TEXT NOT NULL
                        CHECK (format_detected IN ('xml', 'pdf_text', 'pdf_scanned', 'image')),
    size_bytes          BIGINT NOT NULL CHECK (size_bytes >= 0),
    page_count          INTEGER,
    uploaded_by         UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    uploaded_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    state               TEXT NOT NULL DEFAULT 'uploaded'
                        CHECK (state IN (
                            'uploaded', 'processing', 'extracted', 'uncertain',
                            'validation_error', 'duplicate', 'manually_corrected',
                            'validated', 'accepted', 'rejected',
                            'confirmed_duplicate', 'failed'
                        )),
    failure_reason      TEXT,
    dup_key             TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- INV-15: motivo obligatorio en estado de fallo
    CONSTRAINT chk_docs_failure_reason
        CHECK (state != 'failed' OR failure_reason IS NOT NULL)
);
```

- **PK**: `id`.
- **FK**: `owner_id` → `organizations.id`; `uploaded_by` → `users.id`.
- **Unique**: `(owner_id, fingerprint_sha256)` — red de seguridad para DUP-1
  (idempotencia, NFR-4). Ver `08-v1-s1-data-design.md`.
- **Nota**: el contenido NO está en la BD (ADR-0006). Se recupera por
  `fingerprint_sha256` / `safe_name` en el filesystem.

### 2.2 `extractions` (E2)

```sql
CREATE TABLE extractions (
    id              UUID PRIMARY KEY,
    owner_id        UUID NOT NULL REFERENCES organizations(id) ON DELETE RESTRICT,
    document_id     UUID NOT NULL REFERENCES source_documents(id) ON DELETE RESTRICT,
    method          TEXT NOT NULL
                    CHECK (method IN ('xml_schema', 'pdf_text_rules', 'ocr', 'vision_llm')),
    state           TEXT NOT NULL DEFAULT 'pending'
                    CHECK (state IN ('pending', 'running', 'completed', 'failed', 'reprocessed')),
    started_at      TIMESTAMPTZ,
    finished_at     TIMESTAMPTZ,
    failure_reason  TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT chk_ext_failure_reason
        CHECK (state != 'failed' OR failure_reason IS NOT NULL)
);
```

- **PK**: `id`.
- **FK**: `document_id` → `source_documents.id`; `owner_id` → `organizations.id`.
- **Nota**: una extracción produce uno o más valores extraídos (E3).

### 2.3 `extracted_values` (E3)

```sql
CREATE TABLE extracted_values (
    id              UUID PRIMARY KEY,
    owner_id        UUID NOT NULL REFERENCES organizations(id) ON DELETE RESTRICT,
    extraction_id   UUID NOT NULL REFERENCES extractions(id) ON DELETE RESTRICT,
    field           TEXT NOT NULL,
    raw_value       TEXT NOT NULL,
    confidence      NUMERIC(4,3) NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    provenance      JSONB NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

- **PK**: `id`.
- **FK**: `extraction_id` → `extractions.id`; `owner_id` → `organizations.id`.
- **INV-11**: `confidence` y `provenance` NOT NULL. `provenance` es JSONB con
  `{method, page?, bbox?, rule?}`.

### 2.4 `normalized_values` (E4)

```sql
CREATE TABLE normalized_values (
    id                  UUID PRIMARY KEY,
    owner_id            UUID NOT NULL REFERENCES organizations(id) ON DELETE RESTRICT,
    extracted_value_id  UUID NOT NULL REFERENCES extracted_values(id) ON DELETE RESTRICT,
    field               TEXT NOT NULL,
    normalized_value    TEXT NOT NULL,
    normalization_rule  TEXT NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

- **PK**: `id`.
- **FK**: `extracted_value_id` → `extracted_values.id` (NOT NULL, INV-10);
  `owner_id` → `organizations.id`.
- **Nota**: no hay camino para normalizar un valor que no tiene origen E3.

### 2.5 `validated_values` (E5)

```sql
CREATE TABLE validated_values (
    id                   UUID PRIMARY KEY,
    owner_id            UUID NOT NULL REFERENCES organizations(id) ON DELETE RESTRICT,
    normalized_value_id  UUID NOT NULL REFERENCES normalized_values(id) ON DELETE RESTRICT,
    field               TEXT NOT NULL,
    validated_value     TEXT NOT NULL,
    validation_result   TEXT NOT NULL
                        CHECK (validation_result IN ('passed', 'corrected')),
    rules_applied       JSONB NOT NULL,
    manual_correction_id UUID REFERENCES manual_corrections(id) ON DELETE SET NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

- **PK**: `id`.
- **FK**: `normalized_value_id` → `normalized_values.id` (NOT NULL, INV-10);
  `manual_correction_id` → `manual_corrections.id` (nullable);
  `owner_id` → `organizations.id`.
- **Nota**: `normalized_value_id` NOT NULL garantiza que un valor no
  normalizado no puede marcarse validado (INV-8).

### 2.6 `expenses` (E6)

```sql
CREATE TABLE expenses (
    id                  UUID PRIMARY KEY,
    owner_id            UUID NOT NULL REFERENCES organizations(id) ON DELETE RESTRICT,
    document_id         UUID NOT NULL REFERENCES source_documents(id) ON DELETE RESTRICT,
    supplier_id         UUID NOT NULL REFERENCES suppliers(id) ON DELETE RESTRICT,
    document_number     TEXT,
    document_date       DATE,
    registered_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    currency            CHAR(3) NOT NULL REFERENCES currencies(code) ON DELETE RESTRICT,
    base_total          NUMERIC(14,2),
    vat_total           NUMERIC(14,2),
    withholding_total   NUMERIC(14,2),
    total               NUMERIC(14,2) NOT NULL CHECK (total >= 0),
    category_id         UUID REFERENCES categories(id) ON DELETE SET NULL,
    payment_method_id   UUID REFERENCES payment_methods(id) ON DELETE SET NULL,
    state               TEXT NOT NULL DEFAULT 'draft'
                        CHECK (state IN (
                            'draft', 'under_review', 'validation_error', 'duplicate',
                            'ready_for_acceptance', 'accepted', 'voided', 'rejected',
                            'confirmed_duplicate', 'failed'
                        )),
    rejection_reason    TEXT,
    failure_reason      TEXT,
    accepted_by         UUID REFERENCES users(id) ON DELETE SET NULL,
    accepted_at         TIMESTAMPTZ,
    accepted_snapshot   JSONB,
    voided_by           UUID REFERENCES users(id) ON DELETE SET NULL,
    voided_at           TIMESTAMPTZ,
    voided_reason       TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- INV-15
    CONSTRAINT chk_exp_failure_reason
        CHECK (state != 'failed' OR failure_reason IS NOT NULL),
    -- INV-14: snapshot inmutable una vez aceptado
    CONSTRAINT chk_exp_accepted_snapshot
        CHECK (state != 'accepted' OR accepted_snapshot IS NOT NULL)
);
```

- **PK**: `id`.
- **FK**: `document_id` → `source_documents.id` (NOT NULL, INV-3);
  `supplier_id` → `suppliers.id` (NOT NULL, INV-5);
  `category_id` → `categories.id` (nullable);
  `payment_method_id` → `payment_methods.id` (nullable);
  `currency` → `currencies.code` (NOT NULL, INV-13);
  `owner_id` → `organizations.id`.
- **Nota**: `document_id` NOT NULL (INV-3). `accepted_snapshot` es inmutable
  una vez `state = accepted` (INV-14).

### 2.7 `expense_lines` (E7)

```sql
CREATE TABLE expense_lines (
    id              UUID PRIMARY KEY,
    owner_id        UUID NOT NULL REFERENCES organizations(id) ON DELETE RESTRICT,
    expense_id      UUID NOT NULL REFERENCES expenses(id) ON DELETE RESTRICT,
    description     TEXT NOT NULL,
    quantity        NUMERIC(14,4),
    amount          NUMERIC(14,2) NOT NULL CHECK (amount >= 0),
    tax_rate_id     UUID NOT NULL REFERENCES tax_rates(id) ON DELETE RESTRICT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

- **PK**: `id`.
- **FK**: `expense_id` → `expenses.id`; `tax_rate_id` → `tax_rates.id`;
  `owner_id` → `organizations.id`.
- **Nota**: `amount` NOT NULL y ≥ 0 (VR-ARITH-4). La suma de `amount` debe
  coincidir con `base_total` del gasto (INV-1, verificado en dominio).

### 2.8 `tax_lines` (E8)

```sql
CREATE TABLE tax_lines (
    id              UUID PRIMARY KEY,
    owner_id        UUID NOT NULL REFERENCES organizations(id) ON DELETE RESTRICT,
    expense_line_id UUID REFERENCES expense_lines(id) ON DELETE RESTRICT,
    expense_id      UUID REFERENCES expenses(id) ON DELETE RESTRICT,
    tax_type        TEXT NOT NULL CHECK (tax_type IN ('vat', 'withholding')),
    tax_rate_id     UUID NOT NULL REFERENCES tax_rates(id) ON DELETE RESTRICT,
    taxable_base    NUMERIC(14,2) NOT NULL CHECK (taxable_base >= 0),
    tax_amount      NUMERIC(14,2) NOT NULL CHECK (tax_amount >= 0),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Debe pertenecer a una línea de gasto O a un gasto (para totales)
    CONSTRAINT chk_tax_line_parent
        CHECK (expense_line_id IS NOT NULL OR expense_id IS NOT NULL)
);
```

- **PK**: `id`.
- **FK**: `expense_line_id` → `expense_lines.id` (nullable);
  `expense_id` → `expenses.id` (nullable);
  `tax_rate_id` → `tax_rates.id`; `owner_id` → `organizations.id`.
- **Nota**: `taxable_base` y `tax_amount` NOT NULL y ≥ 0 (VR-ARITH-4).

### 2.9 `suppliers` (E9)

```sql
CREATE TABLE suppliers (
    id              UUID PRIMARY KEY,
    owner_id        UUID NOT NULL REFERENCES organizations(id) ON DELETE RESTRICT,
    legal_name      TEXT NOT NULL,
    nif_cif         TEXT NOT NULL,
    tax_address     TEXT,
    contact_data    JSONB,
    state           TEXT NOT NULL DEFAULT 'active'
                    CHECK (state IN ('active', 'inactive')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

- **PK**: `id`.
- **FK**: `owner_id` → `organizations.id`.
- **Nota**: `nif_cif` NOT NULL (INV-5). Un proveedor con gastos aceptados no
  se elimina, solo `inactive` (FR-SUP-4).

### 2.10 `categories` (E10)

```sql
CREATE TABLE categories (
    id              UUID PRIMARY KEY,
    owner_id        UUID NOT NULL REFERENCES organizations(id) ON DELETE RESTRICT,
    name            TEXT NOT NULL,
    description     TEXT,
    parent_id       UUID REFERENCES categories(id) ON DELETE SET NULL,
    state           TEXT NOT NULL DEFAULT 'active'
                    CHECK (state IN ('active', 'inactive')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

- **PK**: `id`.
- **FK**: `parent_id` → `categories.id` (nullable, jerarquía);
  `owner_id` → `organizations.id`.

### 2.11 `payment_methods` (E11)

```sql
CREATE TABLE payment_methods (
    id              UUID PRIMARY KEY,
    owner_id        UUID NOT NULL REFERENCES organizations(id) ON DELETE RESTRICT,
    name            TEXT NOT NULL,
    state           TEXT NOT NULL DEFAULT 'active'
                    CHECK (state IN ('active', 'inactive')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### 2.12 `payments` (E12)

```sql
CREATE TABLE payments (
    id                  UUID PRIMARY KEY,
    owner_id            UUID NOT NULL REFERENCES organizations(id) ON DELETE RESTRICT,
    expense_id          UUID NOT NULL REFERENCES expenses(id) ON DELETE RESTRICT,
    payment_method_id   UUID NOT NULL REFERENCES payment_methods(id) ON DELETE RESTRICT,
    payment_date        DATE NOT NULL,
    reference           TEXT,
    amount_paid         NUMERIC(14,2) NOT NULL CHECK (amount_paid >= 0),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

- **PK**: `id`.
- **FK**: `expense_id` → `expenses.id`; `payment_method_id` →
  `payment_methods.id`; `owner_id` → `organizations.id`.
- **Nota**: un gasto puede tener varios pagos (pago parcial, PQ-4 resuelta).

### 2.13 `reviews` (E13)

```sql
CREATE TABLE reviews (
    id              UUID PRIMARY KEY,
    owner_id        UUID NOT NULL REFERENCES organizations(id) ON DELETE RESTRICT,
    expense_id      UUID NOT NULL REFERENCES expenses(id) ON DELETE RESTRICT,
    reviewed_by     UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    reviewed_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    state           TEXT NOT NULL DEFAULT 'in_progress'
                    CHECK (state IN ('in_progress', 'completed', 'aborted')),
    comment         TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### 2.14 `review_field_results`

```sql
CREATE TABLE review_field_results (
    id              UUID PRIMARY KEY,
    review_id       UUID NOT NULL REFERENCES reviews(id) ON DELETE CASCADE,
    field           TEXT NOT NULL,
    result          TEXT NOT NULL
                    CHECK (result IN ('confirmed', 'corrected', 'rejected')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### 2.15 `manual_corrections` (E14)

```sql
CREATE TABLE manual_corrections (
    id              UUID PRIMARY KEY,
    owner_id        UUID NOT NULL REFERENCES organizations(id) ON DELETE RESTRICT,
    review_id       UUID NOT NULL REFERENCES reviews(id) ON DELETE RESTRICT,
    field           TEXT NOT NULL,
    old_value       TEXT NOT NULL,
    new_value       TEXT NOT NULL,
    corrected_by    UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    corrected_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    reason          TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

- **PK**: `id`.
- **FK**: `review_id` → `reviews.id`; `corrected_by` → `users.id`;
  `owner_id` → `organizations.id`.
- **INV-7**: `old_value`, `new_value`, `corrected_by`, `corrected_at` NOT NULL.
- **Append-only**: no UPDATE/DELETE (ver `07-audit-and-retention.md`).

### 2.16 `duplications` (E15)

```sql
CREATE TABLE duplications (
    id              UUID PRIMARY KEY,
    owner_id        UUID NOT NULL REFERENCES organizations(id) ON DELETE RESTRICT,
    document_a_id   UUID NOT NULL REFERENCES source_documents(id) ON DELETE RESTRICT,
    document_b_id   UUID NOT NULL REFERENCES source_documents(id) ON DELETE RESTRICT,
    expense_a_id    UUID REFERENCES expenses(id) ON DELETE SET NULL,
    expense_b_id    UUID REFERENCES expenses(id) ON DELETE SET NULL,
    dup_type        TEXT NOT NULL CHECK (dup_type IN ('fingerprint', 'logical')),
    state           TEXT NOT NULL DEFAULT 'probable'
                    CHECK (state IN ('probable', 'confirmed', 'resolved_not_duplicate')),
    resolved_by     UUID REFERENCES users(id) ON DELETE SET NULL,
    resolved_at     TIMESTAMPTZ,
    resolution_reason TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- No duplicación de un documento consigo mismo
    CONSTRAINT chk_dup_different_docs
        CHECK (document_a_id != document_b_id)
);
```

- **PK**: `id`.
- **FK**: `document_a_id`, `document_b_id` → `source_documents.id`;
  `expense_a_id`, `expense_b_id` → `expenses.id` (nullable);
  `resolved_by` → `users.id` (nullable); `owner_id` → `organizations.id`.
- **Nota**: `probable` bloquea la aceptación (INV-6, DUP-6).

### 2.17 `audit_events` (E16)

Ver `07-audit-and-retention.md` para el diseño completo.

```sql
CREATE TABLE audit_events (
    id              UUID PRIMARY KEY,
    owner_id        UUID NOT NULL REFERENCES organizations(id) ON DELETE RESTRICT,
    entity_type     TEXT NOT NULL,
    entity_id       UUID NOT NULL,
    action          TEXT NOT NULL,
    actor           UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    occurred_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    before_data     JSONB,
    after_data      JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

- **PK**: `id`.
- **FK**: `owner_id` → `organizations.id`; `actor` → `users.id`.
- **Append-only**: sin UPDATE/DELETE (ADR-0012). Ver `07-audit-and-retention.md`.

### 2.18 `currencies` (E17)

```sql
CREATE TABLE currencies (
    code        CHAR(3) PRIMARY KEY,
    name        TEXT NOT NULL,
    decimals    INTEGER NOT NULL DEFAULT 2 CHECK (decimals >= 0 AND decimals <= 4)
);
```

- **PK**: `code` (CHAR(3) ISO-4217).
- **Nota**: tabla de referencia global; no lleva `owner_id`.

### 2.19 `tax_rates` (E18)

```sql
CREATE TABLE tax_rates (
    id              UUID PRIMARY KEY,
    owner_id        UUID NOT NULL REFERENCES organizations(id) ON DELETE RESTRICT,
    code            TEXT NOT NULL,
    description     TEXT,
    tax_type        TEXT NOT NULL CHECK (tax_type IN ('vat', 'withholding')),
    percentage      NUMERIC(5,2) NOT NULL CHECK (percentage >= 0 AND percentage <= 100),
    valid_from      DATE NOT NULL,
    valid_until     DATE,
    jurisdiction    TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Vigencia coherente
    CONSTRAINT chk_tax_rate_validity
        CHECK (valid_until IS NULL OR valid_until >= valid_from)
);
```

### 2.20 `document_splits` (E19)

```sql
CREATE TABLE document_splits (
    id              UUID PRIMARY KEY,
    owner_id        UUID NOT NULL REFERENCES organizations(id) ON DELETE RESTRICT,
    document_id     UUID NOT NULL REFERENCES source_documents(id) ON DELETE RESTRICT,
    created_by      UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    justification  TEXT NOT NULL
);
```

### 2.21 `split_expenses`

```sql
CREATE TABLE split_expenses (
    split_id      UUID NOT NULL REFERENCES document_splits(id) ON DELETE CASCADE,
    expense_id    UUID NOT NULL REFERENCES expenses(id) ON DELETE RESTRICT,
    PRIMARY KEY (split_id, expense_id)
);
```

### 2.22 `extraction_jobs` (cola de trabajo, ADR-0005)

Ver `04-work-queue-design.md` para el diseño completo.

```sql
CREATE TABLE extraction_jobs (
    id                  UUID PRIMARY KEY,
    owner_id            UUID NOT NULL REFERENCES organizations(id) ON DELETE RESTRICT,
    document_id         UUID NOT NULL REFERENCES source_documents(id) ON DELETE RESTRICT,
    document_fingerprint CHAR(64) NOT NULL,
    format_detected     TEXT NOT NULL
                        CHECK (format_detected IN ('xml', 'pdf_text', 'pdf_scanned', 'image')),
    state               TEXT NOT NULL DEFAULT 'pending'
                        CHECK (state IN ('pending', 'running', 'completed', 'failed')),
    claimed_by          UUID,
    claimed_at          TIMESTAMPTZ,
    lease_expires_at    TIMESTAMPTZ,
    attempts            INTEGER NOT NULL DEFAULT 0,
    max_attempts        INTEGER NOT NULL DEFAULT 3,
    next_retry_at       TIMESTAMPTZ,
    failure_reason      TEXT,
    failure_code        TEXT,
    extraction_id       UUID REFERENCES extractions(id) ON DELETE SET NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT chk_job_failure_reason
        CHECK (state != 'failed' OR failure_reason IS NOT NULL)
);
```

### 2.23 `idempotency_keys` (NFR-4)

```sql
CREATE TABLE idempotency_keys (
    key             TEXT PRIMARY KEY,
    owner_id        UUID NOT NULL REFERENCES organizations(id) ON DELETE RESTRICT,
    endpoint        TEXT NOT NULL,
    request_hash    TEXT NOT NULL,
    response_status INTEGER NOT NULL,
    response_body   JSONB NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

- **PK**: `key` (la `Idempotency-Key` del header).
- **FK**: `owner_id` → `organizations.id`.
- **Nota**: permite devolver la misma respuesta a una petición repetida con la
  misma key (NFR-4). El `request_hash` permite detectar si la petición es
  realmente idéntica.

---

## 3. Resumen de tablas

| # | Tabla | Entidad | Sub-contexto |
|---|---|---|---|
| 1 | `organizations` | — | Tenencia (ADR-0008) |
| 2 | `users` | — | Tenencia / Auth |
| 3 | `sessions` | — | Auth (ADR-0009) |
| 4 | `source_documents` | E1 | Document Ingestion |
| 5 | `extractions` | E2 | Extraction |
| 6 | `extracted_values` | E3 | Extraction |
| 7 | `normalized_values` | E4 | Expense Core |
| 8 | `validated_values` | E5 | Expense Core |
| 9 | `expenses` | E6 | Expense Core |
| 10 | `expense_lines` | E7 | Expense Core |
| 11 | `tax_lines` | E8 | Expense Core |
| 12 | `suppliers` | E9 | Supplier |
| 13 | `categories` | E10 | Expense Core (catálogos) |
| 14 | `payment_methods` | E11 | Expense Core (catálogos) |
| 15 | `payments` | E12 | Expense Core |
| 16 | `reviews` | E13 | Review & Acceptance |
| 17 | `review_field_results` | — | Review & Acceptance |
| 18 | `manual_corrections` | E14 | Review & Acceptance |
| 19 | `duplications` | E15 | Expense Core / Review |
| 20 | `audit_events` | E16 | Transversal |
| 21 | `currencies` | E17 | Expense Core (catálogos) |
| 22 | `tax_rates` | E18 | Expense Core (catálogos) |
| 23 | `document_splits` | E19 | Expense Core |
| 24 | `split_expenses` | — | Expense Core |
| 25 | `extraction_jobs` | — | Document Ingestion / Extraction |
| 26 | `idempotency_keys` | — | Transversal (NFR-4) |

**Total: 26 tablas.**
