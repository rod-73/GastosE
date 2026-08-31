# 04 — Cola de trabajo de extracción (ADR-0005)

Modelo conceptual de la tabla de trabajo para la cola de extracción
(ADR-0005). La cola vive en PostgreSQL (no se introduce un broker externo).
Cada tarea de extracción es una fila en la tabla `extraction_jobs`.

**Nota**: esta tabla es **distinta** de `extractions` (E2). `extractions`
registra el resultado de la extracción (valores extraídos, método, estado del
ciclo B). `extraction_jobs` es la **cola de trabajo**: la tarea que el worker
debe procesar. Una tarea de cola puede producir una extracción (si se
completa) o quedar `failed` (si falla).

## 1. Tabla `extraction_jobs`

| Columna | Tipo | Notas |
|---|---|---|
| `id` | UUID (PK) | UUIDv7. |
| `owner_id` | UUID (FK) | Propietario. |
| `document_id` | UUID (FK) | Documento fuente a procesar. |
| `document_fingerprint` | CHAR(64) | Fingerprint SHA-256 del documento (referencia rápida). |
| `format_detected` | TEXT | Formato detectado (`xml` \| `pdf_text` \| `pdf_scanned` \| `image`). |
| `state` | TEXT | `pending` \| `running` \| `completed` \| `failed`. |
| `claimed_by` | UUID (nullable) | Worker que reclamó la tarea (para lease/timeout). |
| `claimed_at` | TIMESTAMPTZ (nullable) | Fecha/hora del claim. |
| `lease_expires_at` | TIMESTAMPTZ (nullable) | Fecha/hora de expiración del lease. |
| `attempts` | INT | Número de intentos (reintentos con backoff). |
| `max_attempts` | INT | Máximo de intentos (configurable, NFR-9). |
| `next_retry_at` | TIMESTAMPTZ (nullable) | Fecha/hora del próximo reintento (backoff exponencial). |
| `failure_reason` | TEXT (nullable) | Motivo de fallo si `failed` (INV-15). |
| `failure_code` | TEXT (nullable) | Código de error estable (p. e.g. `file_corrupt`, `schema_violation`, `ocr_unavailable`). |
| `extraction_id` | UUID (FK, nullable) | Extracción resultante (si `completed`). |
| `created_at` | TIMESTAMPTZ | |
| `updated_at` | TIMESTAMPTZ | |

- **PK**: `id`.
- **FK**: `document_id` → `source_documents.id`; `owner_id` → `users.id`;
  `extraction_id` → `extractions.id`.
- **Sub-contexto**: Document Ingestion (crea la tarea) / Extraction (worker la
  procesa).

## 2. Estados de la tarea

```
[*] --> pending : se crea la tarea (misma transacción que el registro del documento)
pending --> running : el worker reclama la tarea (claim atómico)
running --> completed : la extracción se completa (se crea la extracción E2)
running --> pending : el lease expira (worker muerto); la tarea vuelve a pending
running --> failed : fallo agotando intentos (max_attempts alcanzado)
pending --> failed : fallo agotando intentos (si no se puede reintentar)
completed --> [*] : terminal
failed --> [*] : terminal (permite crear una NUEVA tarea si el fallo es recuperable)
```

**Notas**:

- `pending`: tarea creada, no reclamada. El worker puede reclamarla.
- `running`: en curso. El worker tiene un lease (timeout) para completarla.
- `completed`: completada. Se crea la extracción (E2) con los valores
  extraídos.
- `failed`: terminal. Con motivo (INV-15). Permite crear una **nueva** tarea
  (reintento manual) si el fallo es recuperable (FR-FST-2). No se revierte
  esta tarea.
- **Lease/timeout**: si el worker muere a mitad de tarea, el lease expira y la
  tarea vuelve a `pending` (otro worker la reclama). Esto evita que una tarea
  quede bloqueada para siempre.

## 3. Claim atómico

El worker reclama tareas con una operación atómica de modo que dos workers no
procesan la misma tarea:

```
-- Conceptual (no es DDL):
UPDATE extraction_jobs
SET state = 'running',
    claimed_by = :worker_id,
    claimed_at = NOW(),
    lease_expires_at = NOW() + :lease_duration,
    attempts = attempts + 1
WHERE state = 'pending'
  AND (next_retry_at IS NULL OR next_retry_at <= NOW())
ORDER BY created_at ASC
LIMIT :batch_size
RETURNING id, document_id, document_fingerprint, format_detected;
```

**Propiedades**:

- **Atómico**: la operación UPDATE...RETURNING es atómica en PostgreSQL. Dos
  workers no pueden reclamar la misma tarea.
- **FIFO**: `ORDER BY created_at ASC` garantiza que las tareas más antiguas se
  procesan primero.
- **Lote**: `LIMIT :batch_size` permite que el worker reclame varias tareas a
  la vez (eficiencia).
- **Lease**: `lease_expires_at` permite recuperar tareas de workers muertos.
  Un task periódico (o el propio worker al arrancar) recupera tareas con
  `state = 'running' AND lease_expires_at < NOW()` y las vuelve a `pending`.

## 4. Reintentos con backoff

- **Backoff exponencial**: si una tarea falla, se programa un reintento con
  `next_retry_at = NOW() + backoff(attempts)`. El backoff es exponencial
  (p. e.g. 1s, 2s, 4s, 8s, ...).
- **Máximo de intentos**: `max_attempts` es configurable (NFR-9). Si
  `attempts >= max_attempts`, la tarea queda `failed` con motivo (FR-FST-1).
- **Reintento manual**: si el fallo es recuperable (FR-FST-2), se puede crear
  una **nueva** tarea (no se revierte la `failed`). La nueva tarea referencia
  el mismo documento fuente.

## 5. Idempotencia

- **Re-procesamiento**: re-procesar el mismo documento no duplica valores
  (FR-EXT-5, NFR-4). El worker reemplaza atómicamente los valores de la
  extracción (estado `reprocessed` en E2).
- **Claim atómico**: una tarea no se procesa dos veces a la vez (claim
  atómico).
- **Fingerprint**: el `document_fingerprint` en la tarea permite verificar la
  integridad del documento antes de procesar (NFR-3).

## 6. Transaccionalidad

- **Creación atómica**: la creación de la tarea de extracción y el registro
  del documento fuente pueden estar en la **misma transacción** (atomo
  "documento registrado + tarea en cola"). Esto garantiza que no hay
  documento sin tarea ni tarea sin documento.
- **Completado atómico**: el worker persiste los valores extraídos y actualiza
  la tarea en transacciones acotadas. Si la transacción falla, la tarea no
  queda a medio completar.

## 7. Relación con `extractions` (E2)

- Una tarea `completed` produce una extracción (E2). La FK
  `extraction_jobs.extraction_id` → `extractions.id` registra la relación.
- Una tarea `failed` NO produce extracción. `extraction_id` es NULL.
- El re-procesamiento (`reprocessed` en E2) corresponde a una **nueva** tarea
  de cola (no se revierte la tarea anterior).

## 8. Escalabilidad

- **N workers**: múltiples workers consumen la cola (claim atómico). El
  `batch_size` y el `lease_duration` son configurables.
- **Volumen bajo**: Phase 2 es ~1.000 documentos/mes (NFR-6). La cola en BD
  es más que suficiente.
- **Migración futura**: si el volumen exige un broker (RabbitMQ/Redis), el
  contrato de cola (estado de tarea, claim, reintentos) permite migrar sin
  cambiar el dominio (ADR-0005).
