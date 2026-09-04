# 05 — Índices y rendimiento (GastosE Phase 2)

Definiciones concretas de índices para PostgreSQL. Cada índice incluye: tipo,
columnas, justificación, y DDL ilustrativo.

**Nota**: el DDL es **esquemático** (referencia de diseño). No es el artefacto
final que se ejecuta; el agente `backend` lo materializará como migraciones
Alembic.

## Convenciones

- **B-tree**: índice por defecto para columnas de ordenación y búsqueda
  exacta/rango.
- **Parcial**: `WHERE` clause para índices que solo cubren un subconjunto de
  filas (p. e.g. `state = 'pending'`). Reduce tamaño y mejora rendimiento.
- **Unique**: constraint de unicidad que también crea un índice implícito.
- **GIN**: solo para JSONB si se requiere búsqueda por contenido (no en V1).
- **Covering**: `INCLUDE` para evitar heap fetch en queries frecuentes (no en
  V1, considerar en Phase 3).

## 1. Índices por tabla

### 1.1 `organizations`

| Índice | Tipo | Columnas | Justificación |
|--------|------|----------|---------------|
| PK | B-tree | `id` | Búsqueda por ID. |

```sql
-- PK implícita
```

### 1.2 `users`

| Índice | Tipo | Columnas | Justificación |
|--------|------|----------|---------------|
| PK | B-tree | `id` | Búsqueda por ID. |
| `idx_users_org` | B-tree | `organization_id` | Listado de usuarios por organización. |
| `uq_users_username` | Unique | `username` | Unicidad de username (constraint). |
| `uq_users_email` | Unique | `email` | Unicidad de email (constraint). |

```sql
CREATE INDEX idx_users_org ON users (organization_id);
-- uq_users_username y uq_users_email son constraints UNIQUE implícitas
```

### 1.3 `sessions` (ADR-0009)

| Índice | Tipo | Columnas | Justificación |
|--------|------|----------|---------------|
| PK | B-tree | `id` | Búsqueda por token (autenticación). |
| `idx_sessions_user` | B-tree | `user_id` | Listado de sesiones por usuario (revocación). |
| `idx_sessions_org` | B-tree | `organization_id` | Revocación por organización. |
| `idx_sessions_expires` | B-tree | `expires_at` | Limpieza de sesiones expiradas. |

```sql
CREATE INDEX idx_sessions_user ON sessions (user_id);
CREATE INDEX idx_sessions_org ON sessions (organization_id);
CREATE INDEX idx_sessions_expires ON sessions (expires_at);
```

### 1.4 `source_documents` (E1)

| Índice | Tipo | Columnas | Justificación |
|--------|------|----------|---------------|
| PK | B-tree | `id` | Búsqueda por ID. |
| `idx_docs_owner` | B-tree | `owner_id` | Aislamiento por organización (NFR-7). Toda query filtra por owner. |
| `idx_docs_owner_state` | B-tree | `owner_id, state` | Listado de documentos por estado (p. e.g. "mis documentos en `extracted`"). |
| `idx_docs_owner_date` | B-tree | `owner_id, uploaded_at DESC` | Búsqueda por fecha (NFR-6). |
| `uq_docs_owner_fingerprint` | Unique | `owner_id, fingerprint_sha256` | Detección de duplicado por fingerprint (DUP-1). Red de seguridad para idempotencia (NFR-4). |
| `idx_docs_dup_key` | B-tree | `owner_id, dup_key` | Detección de duplicado por clave lógica (DUP-2). |

```sql
CREATE INDEX idx_docs_owner ON source_documents (owner_id);
CREATE INDEX idx_docs_owner_state ON source_documents (owner_id, state);
CREATE INDEX idx_docs_owner_date ON source_documents (owner_id, uploaded_at DESC);
CREATE UNIQUE INDEX uq_docs_owner_fingerprint ON source_documents (owner_id, fingerprint_sha256);
CREATE INDEX idx_docs_dup_key ON source_documents (owner_id, dup_key);
```

### 1.5 `extractions` (E2)

| Índice | Tipo | Columnas | Justificación |
|--------|------|----------|---------------|
| PK | B-tree | `id` | Búsqueda por ID. |
| `idx_ext_document` | B-tree | `document_id` | Búsqueda de extracciones por documento. |
| `idx_ext_owner_state` | B-tree | `owner_id, state` | Listado de extracciones por estado. |

```sql
CREATE INDEX idx_ext_document ON extractions (document_id);
CREATE INDEX idx_ext_owner_state ON extractions (owner_id, state);
```

### 1.6 `extracted_values` (E3)

| Índice | Tipo | Columnas | Justificación |
|--------|------|----------|---------------|
| PK | B-tree | `id` | Búsqueda por ID. |
| `idx_ev_extraction` | B-tree | `extraction_id` | Búsqueda de valores por extracción. |
| `idx_ev_field` | B-tree | `extraction_id, field` | Búsqueda de valores por campo dentro de una extracción. |

```sql
CREATE INDEX idx_ev_extraction ON extracted_values (extraction_id);
CREATE INDEX idx_ev_field ON extracted_values (extraction_id, field);
```

### 1.7 `normalized_values` (E4)

| Índice | Tipo | Columnas | Justificación |
|--------|------|----------|---------------|
| PK | B-tree | `id` | Búsqueda por ID. |
| `idx_nv_extracted` | B-tree | `extracted_value_id` | Búsqueda de valor normalizado por origen (cadena E3→E4). |

```sql
CREATE INDEX idx_nv_extracted ON normalized_values (extracted_value_id);
```

### 1.8 `validated_values` (E5)

| Índice | Tipo | Columnas | Justificación |
|--------|------|----------|---------------|
| PK | B-tree | `id` | Búsqueda por ID. |
| `idx_vv_normalized` | B-tree | `normalized_value_id` | Búsqueda de valor validado por origen (cadena E4→E5). |
| `idx_vv_field` | B-tree | `normalized_value_id, field` | Búsqueda de valores validados por campo. |

```sql
CREATE INDEX idx_vv_normalized ON validated_values (normalized_value_id);
CREATE INDEX idx_vv_field ON validated_values (normalized_value_id, field);
```

### 1.9 `expenses` (E6)

| Índice | Tipo | Columnas | Justificación |
|--------|------|----------|---------------|
| PK | B-tree | `id` | Búsqueda por ID. |
| `idx_exp_owner` | B-tree | `owner_id` | Aislamiento por organización. |
| `idx_exp_owner_state` | B-tree | `owner_id, state` | Listado de gastos por estado (p. e.g. "mis gastos en `under_review`"). |
| `idx_exp_owner_date` | B-tree | `owner_id, document_date DESC` | Búsqueda por fecha (NFR-6). |
| `idx_exp_owner_supplier` | B-tree | `owner_id, supplier_id` | Búsqueda por proveedor (NFR-6). |
| `idx_exp_owner_supplier_date` | B-tree | `owner_id, supplier_id, document_date DESC` | Búsqueda por proveedor + fecha (NFR-6: < 2s para 100.000 gastos). |
| `idx_exp_owner_category` | B-tree | `owner_id, category_id` | Listado por categoría (FR-CAT-3). |
| `idx_exp_document` | B-tree | `document_id` | Búsqueda de gastos por documento (INV-3/INV-4). |
| `idx_exp_accepted` | Parcial | `owner_id, accepted_at DESC` WHERE `state = 'accepted'` | Listado de gastos aceptados (hechos contables). |

```sql
CREATE INDEX idx_exp_owner ON expenses (owner_id);
CREATE INDEX idx_exp_owner_state ON expenses (owner_id, state);
CREATE INDEX idx_exp_owner_date ON expenses (owner_id, document_date DESC);
CREATE INDEX idx_exp_owner_supplier ON expenses (owner_id, supplier_id);
CREATE INDEX idx_exp_owner_supplier_date ON expenses (owner_id, supplier_id, document_date DESC);
CREATE INDEX idx_exp_owner_category ON expenses (owner_id, category_id);
CREATE INDEX idx_exp_document ON expenses (document_id);
CREATE INDEX idx_exp_accepted ON expenses (owner_id, accepted_at DESC) WHERE state = 'accepted';
```

### 1.10 `expense_lines` (E7)

| Índice | Tipo | Columnas | Justificación |
|--------|------|----------|---------------|
| PK | B-tree | `id` | Búsqueda por ID. |
| `idx_el_expense` | B-tree | `expense_id` | Búsqueda de líneas por gasto. |

```sql
CREATE INDEX idx_el_expense ON expense_lines (expense_id);
```

### 1.11 `tax_lines` (E8)

| Índice | Tipo | Columnas | Justificación |
|--------|------|----------|---------------|
| PK | B-tree | `id` | Búsqueda por ID. |
| `idx_tl_line` | B-tree | `expense_line_id` | Búsqueda de líneas fiscales por línea de gasto. |
| `idx_tl_expense` | B-tree | `expense_id` | Búsqueda de líneas fiscales por gasto (totales). |

```sql
CREATE INDEX idx_tl_line ON tax_lines (expense_line_id);
CREATE INDEX idx_tl_expense ON tax_lines (expense_id);
```

### 1.12 `suppliers`

| Índice | Tipo | Columnas | Justificación |
|--------|------|----------|---------------|
| PK | B-tree | `id` | Búsqueda por ID. |
| `idx_sup_owner_nif` | B-tree | `owner_id, nif_cif` | Búsqueda por NIF/CIF (FR-SUP-3). |
| `idx_sup_owner_name` | B-tree | `owner_id, legal_name` | Búsqueda por nombre (FR-SUP-3). |

```sql
CREATE INDEX idx_sup_owner_nif ON suppliers (owner_id, nif_cif);
CREATE INDEX idx_sup_owner_name ON suppliers (owner_id, legal_name);
```

### 1.13 `payments`

| Índice | Tipo | Columnas | Justificación |
|--------|------|----------|---------------|
| PK | B-tree | `id` | Búsqueda por ID. |
| `idx_pay_expense` | B-tree | `expense_id` | Búsqueda de pagos por gasto. |

```sql
CREATE INDEX idx_pay_expense ON payments (expense_id);
```

### 1.14 `reviews`

| Índice | Tipo | Columnas | Justificación |
|--------|------|----------|---------------|
| PK | B-tree | `id` | Búsqueda por ID. |
| `idx_rev_expense` | B-tree | `expense_id` | Búsqueda de revisiones por gasto. |

```sql
CREATE INDEX idx_rev_expense ON reviews (expense_id);
```

### 1.15 `duplications`

| Índice | Tipo | Columnas | Justificación |
|--------|------|----------|---------------|
| PK | B-tree | `id` | Búsqueda por ID. |
| `idx_dup_doc_a` | B-tree | `document_a_id` | Búsqueda de duplicaciones por documento A. |
| `idx_dup_doc_b` | B-tree | `document_b_id` | Búsqueda de duplicaciones por documento B. |
| `idx_dup_owner_state` | B-tree | `owner_id, state` | Listado de duplicaciones por estado (p. e.g. "duplicaciones `probable` pendientes"). |

```sql
CREATE INDEX idx_dup_doc_a ON duplications (document_a_id);
CREATE INDEX idx_dup_doc_b ON duplications (document_b_id);
CREATE INDEX idx_dup_owner_state ON duplications (owner_id, state);
```

### 1.16 `audit_events`

| Índice | Tipo | Columnas | Justificación |
|--------|------|----------|---------------|
| PK | B-tree | `id` | Búsqueda por ID. |
| `idx_audit_entity` | B-tree | `entity_type, entity_id` | Búsqueda de eventos por entidad (trazabilidad, INV-10). |
| `idx_audit_owner_date` | B-tree | `owner_id, occurred_at DESC` | Listado de eventos por fecha (auditoría). |
| `idx_audit_action` | B-tree | `action` | Búsqueda de eventos por acción. |

```sql
CREATE INDEX idx_audit_entity ON audit_events (entity_type, entity_id);
CREATE INDEX idx_audit_owner_date ON audit_events (owner_id, occurred_at DESC);
CREATE INDEX idx_audit_action ON audit_events (action);
```

### 1.17 `extraction_jobs`

| Índice | Tipo | Columnas | Justificación |
|--------|------|----------|---------------|
| PK | B-tree | `id` | Búsqueda por ID. |
| `idx_jobs_pending` | Parcial | `state, created_at` WHERE `state = 'pending'` | Claim atómico: búsqueda de tareas pendientes en orden FIFO. |
| `idx_jobs_lease` | Parcial | `state, lease_expires_at` WHERE `state = 'running'` | Recuperación de tareas de workers muertos (lease expirado). |
| `idx_jobs_document` | B-tree | `document_id` | Búsqueda de tareas por documento. |

```sql
CREATE INDEX idx_jobs_pending ON extraction_jobs (state, created_at) WHERE state = 'pending';
CREATE INDEX idx_jobs_lease ON extraction_jobs (state, lease_expires_at) WHERE state = 'running';
CREATE INDEX idx_jobs_document ON extraction_jobs (document_id);
```

### 1.18 `currencies`, `tax_rates`, `categories`, `payment_methods`

| Índice | Tipo | Columnas | Justificación |
|--------|------|----------|---------------|
| PK | B-tree | `code` / `id` | Búsqueda por ID/código. |
| `idx_*_owner` | B-tree | `owner_id` | Aislamiento por organización (para catálogos con owner). |

```sql
-- Para catálogos con owner_id (tax_rates, categories, payment_methods):
CREATE INDEX idx_tax_rates_owner ON tax_rates (owner_id);
CREATE INDEX idx_categories_owner ON categories (owner_id);
CREATE INDEX idx_payment_methods_owner ON payment_methods (owner_id);
-- currencies: catálogo global, sin owner_id
```

## 2. Paginación por cursor (NFR-6)

Los listados de gastos y documentos usan **paginación por cursor** (no
OFFSET/LIMIT) para rendimiento estable en datasets grandes.

- **Cursor**: el cursor es el valor de la columna de ordenación de la última
  fila de la página anterior (p. e.g. `document_date` + `id` para
  desempatar).
- **Query**: `WHERE (document_date, id) < (:cursor_date, :cursor_id) ORDER BY
  document_date DESC, id DESC LIMIT :page_size`.
- **Índice**: `idx_exp_owner_supplier_date` soporta la paginación por cursor
  en búsquedas por proveedor + fecha.
- **Ventaja**: la paginación por cursor es estable (no se saltan filas si se
  insertan nuevas entre páginas) y tiene rendimiento constante (no depende del
  offset).

## 3. Particionamiento de auditoría (NFR-1)

El registro de auditoría (`audit_events`) crece de forma continua y es
append-only. Para mantener el rendimiento de las queries de auditoría y
facilitar la retención (OQ-10), se considera **particionamiento por fecha**.

- **Partición**: por `occurred_at` (mes o trimestre, según volumen).
- **Ventaja**: las queries de auditoría por rango de fecha solo escanean las
  particiones relevantes. La retención (purga) se hace eliminando
  particiones completas (aunque la auditoría es append-only, la purga de
  particiones antiguas es una operación de retención, no de modificación).
- **Nota**: el particionamiento es una decisión de Phase 2. En Phase 1/2 con
  volumen bajo (~1.000 documentos/mes), no es necesario. Se documenta aquí
  como preparación para escalado.

## 4. Rendimiento orientativo (NFR-6)

| Operación | Objetivo | Índice que lo soporta |
|-----------|----------|----------------------|
| Búsqueda de gastos por proveedor/fecha | < 2s para 100.000 gastos | `idx_exp_owner_supplier_date` |
| Listado de documentos por estado | < 2s | `idx_docs_owner_state` |
| Búsqueda de duplicaciones `probable` | < 2s | `idx_dup_owner_state` |
| Claim atómico de cola | < 100ms | `idx_jobs_pending` (parcial) |
| Reconstrucción de trazabilidad (INV-10) | < 1 min | FK + índices en cadena E3→E4→E5 |
| Auditoría por entidad | < 2s | `idx_audit_entity` |
| Autenticación (búsqueda por token) | < 50ms | PK `sessions.id` |
| Revocación de sesión por usuario | < 100ms | `idx_sessions_user` |

## 5. Notas

- **Índices parciales**: los índices parciales (WHERE) se usan para la cola de
  trabajo (`extraction_jobs`) y para los gastos aceptados (`expenses`).
  Reducen el tamaño del índice y mejoran el rendimiento.
- **Índices covering**: en Phase 2, se pueden considerar índices covering
  (INCLUDE) para las queries más frecuentes (p. e.g. listado de gastos por
  proveedor/fecha incluyendo `total`, `state`). No se prescriben en V1.
- **VACUUM/ANALYZE**: el mantenimiento de la BD (VACUUM, ANALYZE) es
  responsabilidad de Phase 2/devops. No se prescribe aquí.
- **GIN para JSONB**: no se usan índices GIN en V1. La búsqueda por contenido
  de JSONB (provenance, snapshot) no es un caso de uso frecuente. Si se
  necesita en Phase 3, se añadirá un índice GIN específico.
