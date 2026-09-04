# 04 — Diseño de la cola de trabajo (GastosE Phase 2)

Diseño de la cola de trabajo basada en PostgreSQL (ADR-0005) para el
proceso de extracción documental. La cola es la tabla `extraction_jobs`
definida en `01-schema-design.md` §2.22.

## Principios

1. **PostgreSQL como broker**: no se usa un broker externo (RabbitMQ,
   Redis, etc.). La cola es una tabla en la misma BD.
2. **Claim atómico**: un worker reclama un job con una operación atómica
   (`UPDATE ... WHERE ... RETURNING` o `SELECT ... FOR UPDATE SKIP LOCKED`).
   No hay race conditions.
3. **Estados**: `pending` → `running` → `completed` | `failed`.
4. **Reintentos con backoff exponencial**: si un job falla, se reintenta con
   espera creciente. Máximo `max_attempts` reintentos.
5. **Lease**: un job en `running` tiene un `lease_expires_at`. Si el worker
   muere sin completar, el lease expira y el job vuelve a `pending`.
6. **Idempotencia**: el proceso de extracción es idempotente. Si un job se
   ejecuta dos veces (por lease expiry + re-claim), el resultado es el mismo.

## Tabla `extraction_jobs`

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

### Columnas

| Columna | Tipo | Descripción |
|---|---|---|
| `id` | UUID | PK. |
| `owner_id` | UUID | Tenencia (ADR-0008). |
| `document_id` | UUID | FK → `source_documents.id`. |
| `document_fingerprint` | CHAR(64) | Copia del fingerprint para idempotencia. |
| `format_detected` | TEXT | Formato detectado (determina el método de extracción). |
| `state` | TEXT | `pending` / `running` / `completed` / `failed`. |
| `claimed_by` | UUID | Worker que reclama el job (nullable). |
| `claimed_at` | TIMESTAMPTZ | Momento del claim. |
| `lease_expires_at` | TIMESTAMPTZ | Expiración del lease. |
| `attempts` | INTEGER | Número de intentos realizados. |
| `max_attempts` | INTEGER | Máximo de intentos (default 3). |
| `next_retry_at` | TIMESTAMPTZ | Próximo reintento (backoff). |
| `failure_reason` | TEXT | Motivo del fallo (obligatorio si `state = 'failed'`). |
| `failure_code` | TEXT | Código de fallo (para clasificación). |
| `extraction_id` | UUID | FK → `extractions.id` (resultado del job). |
| `created_at` | TIMESTAMPTZ | Creación. |
| `updated_at` | TIMESTAMPTZ | Última actualización. |

## Ciclo de vida de un job

```
                    ┌─────────────────────────────────────────────────┐
                    │                                                 │
                    ▼                                                 │
              ┌──────────┐    claim     ┌──────────┐   complete   ┌───────────┐
              │ pending  │─────────────▶│ running  │─────────────▶│ completed │
              └──────────┘              └──────────┘              └───────────┘
                    ▲                      │
                    │                      │ fail (attempts < max)
                    │                      ▼
                    │                 ┌──────────┐
                    └─────────────────│ failed   │
                      (retry)         └──────────┘
```

### Transiciones

| De | A | Condición |
|---|---|---|
| — | `pending` | Creación del job (upload de documento). |
| `pending` | `running` | Claim atómico por un worker. |
| `running` | `completed` | Extracción exitosa. |
| `running` | `failed` | Extracción fallida. |
| `failed` | `pending` | Reintento (si `attempts < max_attempts` y `next_retry_at` ha pasado). |
| `failed` | `failed` | Sin más reintentos (`attempts >= max_attempts`). El job queda en `failed` permanente. |

## Claim atómico

### Opción A: `UPDATE ... WHERE ... RETURNING`

```sql
UPDATE extraction_jobs
SET state = 'running',
    claimed_by = :worker_id,
    claimed_at = NOW(),
    lease_expires_at = NOW() + INTERVAL '5 minutes',
    attempts = attempts + 1,
    updated_at = NOW()
WHERE id = (
    SELECT id FROM extraction_jobs
    WHERE state = 'pending'
      AND (next_retry_at IS NULL OR next_retry_at <= NOW())
    ORDER BY created_at ASC
    LIMIT 1
    FOR UPDATE SKIP LOCKED
)
RETURNING *;
```

- `FOR UPDATE SKIP LOCKED`: si otro worker está reclamando la misma fila,
  se salta (no bloquea).
- `ORDER BY created_at ASC`: FIFO (first-in, first-out).
- `LIMIT 1`: un job por claim.
- Si no hay jobs pendientes, `RETURNING` no devuelve nada.

### Opción B: `SELECT ... FOR UPDATE SKIP LOCKED` + `UPDATE`

```sql
-- Paso 1: seleccionar
SELECT id FROM extraction_jobs
WHERE state = 'pending'
  AND (next_retry_at IS NULL OR next_retry_at <= NOW())
ORDER BY created_at ASC
LIMIT 1
FOR UPDATE SKIP LOCKED;

-- Paso 2: actualizar (en la misma transacción)
UPDATE extraction_jobs
SET state = 'running',
    claimed_by = :worker_id,
    claimed_at = NOW(),
    lease_expires_at = NOW() + INTERVAL '5 minutes',
    attempts = attempts + 1,
    updated_at = NOW()
WHERE id = :claimed_id;
```

**Decisión**: se usa la **Opción A** (una sola sentencia) por simplicidad y
atomoicidad.

## Reintentos con backoff exponencial

Cuando un job falla:

```
attempts=1 → next_retry_at = NOW() + 1 minute
attempts=2 → next_retry_at = NOW() + 5 minutes
attempts=3 → next_retry_at = NOW() + 30 minutes
attempts>=max_attempts → state = 'failed' permanente
```

### Cálculo del backoff

```python
def compute_backoff(attempts: int) -> timedelta:
    """Backoff exponencial: 1min, 5min, 30min, ..."""
    if attempts <= 1:
        return timedelta(minutes=1)
    elif attempts == 2:
        return timedelta(minutes=5)
    else:
        return timedelta(minutes=30)
```

### Transición a reintento

```sql
UPDATE extraction_jobs
SET state = 'pending',
    claimed_by = NULL,
    claimed_at = NULL,
    lease_expires_at = NULL,
    next_retry_at = NOW() + :backoff_interval,
    updated_at = NOW()
WHERE id = :job_id
  AND state = 'failed'
  AND attempts < max_attempts;
```

### Transición a fallo permanente

```sql
UPDATE extraction_jobs
SET state = 'failed',
    claimed_by = NULL,
    claimed_at = NULL,
    lease_expires_at = NULL,
    next_retry_at = NULL,
    updated_at = NOW()
WHERE id = :job_id
  AND state = 'failed'
  AND attempts >= max_attempts;
```

## Lease expiry

Si un worker muere mientras tiene un job en `running`, el lease expira.
Un **reaper** (tarea periódica) detecta los jobs con lease expirado y los
vuelve a `pending`:

```sql
UPDATE extraction_jobs
SET state = 'pending',
    claimed_by = NULL,
    claimed_at = NULL,
    lease_expires_at = NULL,
    updated_at = NOW()
WHERE state = 'running'
  AND lease_expires_at < NOW();
```

- **Frecuencia del reaper**: cada 30 segundos (configurable).
- **Lease duration**: 5 minutos (configurable). Debe ser mayor que el tiempo
  máximo de extracción.

## Idempotencia

El proceso de extracción debe ser **idempotente**: si un job se ejecuta dos
veces (por lease expiry + re-claim), el resultado es el mismo.

- El `document_fingerprint` en el job permite verificar que el documento no
  ha cambiado.
- La extracción crea una fila en `extractions` y filas en
  `extracted_values`. Si ya existe una extracción completada para el mismo
  documento, se reutiliza (no se crea otra).

```python
# Pseudocódigo en el worker
def process_job(job):
    # Verificar idempotencia: ¿ya hay una extracción completada?
    existing = db.query(Extraction).filter(
        Extraction.document_id == job.document_id,
        Extraction.state == 'completed'
    ).first()
    if existing:
        mark_job_completed(job, existing.id)
        return

    # Ejecutar extracción
    extraction = perform_extraction(job)
    mark_job_completed(job, extraction.id)
```

## Índices

| Índice | Definición | Justificación |
|---|---|---|
| `idx_jobs_claim` | `ON (state, next_retry_at) WHERE state = 'pending'` | Claim atómico: buscar jobs pendientes. |
| `idx_jobs_owner` | `ON (owner_id)` | Filtrado por organización. |
| `idx_jobs_document` | `ON (document_id)` | Buscar jobs por documento. |
| `idx_jobs_lease` | `ON (lease_expires_at) WHERE state = 'running'` | Reaper: buscar jobs con lease expirado. |

Ver `05-indexes-and-performance.md` para el detalle.

## Configuración

| Parámetro | Default | Descripción |
|---|---|---|
| `lease_duration` | 5 minutes | Duración del lease de un job en `running`. |
| `max_attempts` | 3 | Máximo de intentos por job. |
| `reaper_interval` | 30 seconds | Frecuencia del reaper. |
| `backoff_intervals` | [1min, 5min, 30min] | Backoff exponencial. |

Estos parámetros se configuran en la aplicación (no en la BD). La BD solo
almacena los valores por job.

## Riesgos

| Riesgo | Mitigación |
|---|---|
| Worker muere y no libera el job | Lease expiry + reaper. |
| Job se ejecuta dos veces | Idempotencia del proceso de extracción. |
| Backoff insuficiente | Backoff exponencial configurable. |
| Cola crece sin procesar | Monitorización: alertar si hay jobs `pending` con `created_at` antiguo. |
| `FOR UPDATE SKIP LOCKED` no soportado | PostgreSQL 9.5+ lo soporta. GastosE requiere PostgreSQL 14+. |
