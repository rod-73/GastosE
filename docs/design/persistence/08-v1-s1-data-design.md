# 08 — Diseño de datos V1-S1 (GastosE Phase 2)

Diseño de datos específico para el slice V1-S1 (ingesta de documentos). Este
documento detalla cómo se implementa la ingesta de documentos a nivel de
persistencia.

**Nota**: este documento es la materialización operativa del diseño general
de `01-schema-design.md` para el slice V1-S1.

## 1. Flujo de ingesta (V1-S1)

```
Cliente
    │
    ▼
POST /api/v1/documents (multipart)
    │
    ├── Validación de tamaño (≤ 20 MB, NFR-6)
    ├── Validación de formato (magic bytes)
    ├── Cálculo de fingerprint SHA-256
    ├── Generación de nombre seguro (UUID)
    ├── Almacenamiento en filesystem (inmutable, ADR-0006)
    ├── Registro en BD (source_documents, state='uploaded')
    ├── Detección de duplicado por fingerprint (DUP-1)
    ├── Creación de tarea de extracción (extraction_jobs)
    └── Respuesta 202 Accepted + Location
```

## 2. Tabla `source_documents` (E1)

### 2.1 Columnas relevantes para V1-S1

| Columna | Tipo | Descripción |
|---------|------|-------------|
| `id` | UUID | PK (UUIDv7). |
| `owner_id` | UUID | Organización propietaria (ADR-0008). |
| `safe_name` | TEXT | Nombre seguro (UUID + extensión). Nunca el nombre original. |
| `original_filename` | TEXT | Nombre original del archivo (nullable, solo para referencia). |
| `fingerprint_sha256` | CHAR(64) | Fingerprint SHA-256 del contenido (INV-9). |
| `doc_type` | TEXT | Tipo de documento: `received_invoice`, `ticket`, `other`. |
| `format_detected` | TEXT | Formato detectado: `xml`, `pdf_text`, `pdf_scanned`, `image`. |
| `size_bytes` | BIGINT | Tamaño en bytes (≥ 0). |
| `page_count` | INTEGER | Número de páginas (nullable, se rellena en extracción). |
| `uploaded_by` | UUID | Usuario que subió el documento (FK → users.id). |
| `uploaded_at` | TIMESTAMPTZ | Timestamp de la subida. |
| `state` | TEXT | Estado inicial: `uploaded`. |
| `failure_reason` | TEXT | Motivo de fallo (NULL en `uploaded`). |
| `dup_key` | TEXT | Clave lógica para duplicados (DUP-2, nullable en V1-S1). |
| `created_at` | TIMESTAMPTZ | Timestamp de creación. |
| `updated_at` | TIMESTAMPTZ | Timestamp de última modificación. |

### 2.2 Constraints

```sql
-- INV-15: motivo obligatorio en estado de fallo
CONSTRAINT chk_docs_failure_reason
    CHECK (state != 'failed' OR failure_reason IS NOT NULL)

-- Unicidad de fingerprint por organización (DUP-1, NFR-4):
CREATE UNIQUE INDEX uq_docs_owner_fingerprint
    ON source_documents (owner_id, fingerprint_sha256);
```

### 2.3 DDL ilustrativo

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

    CONSTRAINT chk_docs_failure_reason
        CHECK (state != 'failed' OR failure_reason IS NOT NULL)
);

CREATE UNIQUE INDEX uq_docs_owner_fingerprint
    ON source_documents (owner_id, fingerprint_sha256);
```

## 3. Fingerprint y detección de duplicados (DUP-1)

### 3.1 Cálculo del fingerprint

- **Algoritmo**: SHA-256 del contenido del archivo.
- **Formato**: 64 caracteres hexadecimales (`CHAR(64)`).
- **Momento**: se calcula durante la subida (antes de almacenar).
- **Propósito**: detección de duplicados (DUP-1) e integridad (INV-9).

### 3.2 Detección de duplicado por fingerprint

```sql
-- Al subir un documento, se comprueba si ya existe:
SELECT id, state FROM source_documents
WHERE owner_id = :session_owner_id
  AND fingerprint_sha256 = :fingerprint
LIMIT 1;
```

- **Si existe**: se crea una duplicación `probable` (tabla `duplications`).
  El documento nuevo se registra con `state = 'duplicate'` y referencia al
  documento original.
- **Si no existe**: se registra el documento con `state = 'uploaded'`.

### 3.3 Tabla `duplications`

```sql
CREATE TABLE duplications (
    id              UUID PRIMARY KEY,
    owner_id        UUID NOT NULL REFERENCES organizations(id) ON DELETE RESTRICT,
    document_a_id   UUID NOT NULL REFERENCES source_documents(id) ON DELETE RESTRICT,
    document_b_id   UUID NOT NULL REFERENCES source_documents(id) ON DELETE RESTRICT,
    dup_type        TEXT NOT NULL
                    CHECK (dup_type IN ('fingerprint', 'logical')),
    state           TEXT NOT NULL DEFAULT 'probable'
                    CHECK (state IN ('probable', 'confirmed', 'resolved')),
    resolved_by     UUID REFERENCES users(id) ON DELETE SET NULL,
    resolved_at     TIMESTAMPTZ,
    resolution      TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

- **`dup_type`**: `fingerprint` (DUP-1) o `logical` (DUP-2/3).
- **`state`**: `probable` (detectado), `confirmed` (confirmado duplicado),
  `resolved` (resuelto: confirmado o no-duplicado).
- **INV-6**: una duplicación `probable` bloquea la aceptación del gasto.

## 4. Almacenamiento en filesystem (ADR-0006)

### 4.1 Estructura de directorios

```
/var/gastosE/documents/
    └── {owner_id}/
        └── {fingerprint_sha256}
```

- **`owner_id`**: subdirectorio por organización (aislamiento).
- **`fingerprint_sha256`**: nombre del archivo (el fingerprint es único por
  organización).
- **Inmutable**: una vez escrito, el archivo no se modifica. Si se necesita
  re-procesar, se lee el mismo archivo.

### 4.2 Nombre seguro

- **`safe_name`**: `{uuid}.{ext}` (p. e.g. `a1b2c3d4-....pdf`).
- **UUID**: UUIDv7 generado por el sistema (no el nombre original).
- **Extensión**: derivada del formato detectado (`.pdf`, `.xml`, `.jpg`, etc.).
- **Prohibido**: usar el nombre original del archivo (path traversal).

### 4.3 Verificación de integridad (NFR-3)

```sql
-- Al verificar el fingerprint bajo demanda:
SELECT fingerprint_sha256 FROM source_documents
WHERE id = :document_id
  AND owner_id = :session_owner_id;
```

- La aplicación lee el archivo del filesystem, calcula SHA-256, y compara con
  el `fingerprint_sha256` almacenado.
- Si no coincide: error de integridad (INV-9).

## 5. Creación de tarea de extracción

### 5.1 Tabla `extraction_jobs`

```sql
CREATE TABLE extraction_jobs (
    id              UUID PRIMARY KEY,
    owner_id        UUID NOT NULL REFERENCES organizations(id) ON DELETE RESTRICT,
    document_id     UUID NOT NULL REFERENCES source_documents(id) ON DELETE RESTRICT,
    state           TEXT NOT NULL DEFAULT 'pending'
                    CHECK (state IN ('pending', 'running', 'completed', 'failed', 'cancelled')),
    priority        INTEGER NOT NULL DEFAULT 0,
    attempts        INTEGER NOT NULL DEFAULT 0,
    max_attempts    INTEGER NOT NULL DEFAULT 3,
    lease_expires_at TIMESTAMPTZ,
    worker_id       TEXT,
    failure_reason  TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT chk_jobs_failure_reason
        CHECK (state != 'failed' OR failure_reason IS NOT NULL)
);
```

### 5.2 Creación del job

```sql
-- Al subir un documento (state='uploaded'), se crea un job:
INSERT INTO extraction_jobs (id, owner_id, document_id, state, priority, attempts, max_attempts)
VALUES (:job_id, :session_owner_id, :document_id, 'pending', 0, 0, 3);
```

- **`state`**: `pending` (esperando a ser claimado por un worker).
- **`priority`**: 0 por defecto (FIFO).
- **`attempts`**: 0 (primer intento).
- **`max_attempts`**: 3 (reintentos con backoff).

### 5.3 Claim atómico

Ver `04-work-queue-design.md` para el diseño completo del claim atómico.

## 6. Idempotencia (NFR-4)

### 6.1 Idempotency-Key

- **Header**: `Idempotency-Key` en la petición `POST /api/v1/documents`.
- **Almacenamiento**: no se almacena en la BD en V1-S1 (se usa el fingerprint
  como clave de idempotencia).
- **Comportamiento**: si se recibe la misma `Idempotency-Key` con el mismo
  fingerprint, se devuelve el documento existente (200 OK) en lugar de crear
  uno nuevo.

### 6.2 Red de seguridad: unique constraint

- **`uq_docs_owner_fingerprint`**: `(owner_id, fingerprint_sha256)`.
- Si se intenta insertar un documento con el mismo fingerprint y la misma
  organización, la BD lo rechaza (violación de unicidad).
- La aplicación captura el error y devuelve el documento existente.

## 7. Estados del documento (ciclo A)

### 7.1 Estados en V1-S1

| Estado | Descripción |
|--------|-------------|
| `uploaded` | Documento subido y registrado. |
| `duplicate` | Documento duplicado (fingerprint existente). |
| `failed` | Fallo en la subida (validación, almacenamiento). |

### 7.2 Transiciones en V1-S1

```
uploaded ──► duplicate (si fingerprint existe)
uploaded ──► failed (si fallo en subida)
```

- Las transiciones a `processing`, `extracted`, etc. ocurren en V2-S1
  (extracción).

## 8. Criterios de aceptación (V1-S1)

| Criterio | Requisito | Verificación |
|----------|-----------|--------------|
| FR-DOC-1 | Subir documento multipart | Test: POST /documents con archivo válido → 202 |
| FR-DOC-2 | Validación de tamaño (≤ 20 MB) | Test: POST con archivo > 20 MB → 413 |
| FR-DOC-3 | Validación de formato (magic bytes) | Test: POST con archivo no soportado → 415 |
| FR-DOC-4 | Fingerprint SHA-256 | Test: verificar fingerprint en BD |
| FR-DOC-5 | Nombre seguro (UUID) | Test: verificar safe_name en BD |
| INV-9 | Integridad del documento | Test: verificar fingerprint bajo demanda |
| NFR-6 | < 5s para 20 MB | Test: timing de subida |
| DUP-1 | Detección de duplicado | Test: subir mismo documento 2 veces → duplicación `probable` |
| NFR-4 | Idempotencia | Test: misma Idempotency-Key → mismo documento |

## 9. Notas

- **V1-S1 no incluye extracción**: el documento se registra con `state =
  'uploaded'` y se crea un job de extracción, pero la extracción ocurre en
  V2-S1.
- **V1-S1 no incluye normalización/validación**: esos slices son V3-S1/S2.
- **V1-S1 no incluye revisión/aceptación**: esos slices son V4-S1..S4.
- **Almacenamiento**: el contenido del documento NO está en la BD
  (ADR-0006). Solo la metadata.
