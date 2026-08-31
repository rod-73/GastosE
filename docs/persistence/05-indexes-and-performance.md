# 05 — Índices y rendimiento (GastosE)

Índices conceptuales que soportan los requisitos de rendimiento (NFR-6) y las
consultas frecuentes. **Nota**: las definiciones exactas de índices (tipo,
columnas, parciales, covering) son de Phase 2. Aquí se indican los índices
conceptuales y su justificación.

## 1. Índices por tabla

### 1.1 `source_documents`

| Índice conceptual | Columnas | Justificación |
|---|---|---|
| PK | `id` | Búsqueda por ID. |
| `idx_docs_owner` | `owner_id` | Aislamiento por propietario (OQ-9, NFR-7). Toda query filtra por owner. |
| `idx_docs_owner_state` | `owner_id, state` | Listado de documentos por estado (p. e.g. "mis documentos en `extracted`"). |
| `idx_docs_fingerprint` | `fingerprint_sha256` | Detección de duplicado por fingerprint (DUP-1). Búsqueda por fingerprint. |
| `idx_docs_owner_date` | `owner_id, uploaded_at DESC` | Búsqueda por fecha (NFR-6: búsqueda por proveedor/fecha). |
| `idx_docs_dup_key` | `owner_id, dup_key` | Detección de duplicado por clave lógica (DUP-2). |

### 1.2 `extractions`

| Índice conceptual | Columnas | Justificación |
|---|---|---|
| PK | `id` | Búsqueda por ID. |
| `idx_ext_document` | `document_id` | Búsqueda de extracciones por documento. |
| `idx_ext_owner_state` | `owner_id, state` | Listado de extracciones por estado. |

### 1.3 `extracted_values`

| Índice conceptual | Columnas | Justificación |
|---|---|---|
| PK | `id` | Búsqueda por ID. |
| `idx_ev_extraction` | `extraction_id` | Búsqueda de valores por extracción. |
| `idx_ev_field` | `extraction_id, field` | Búsqueda de valores por campo dentro de una extracción. |

### 1.4 `normalized_values`

| Índice conceptual | Columnas | Justificación |
|---|---|---|
| PK | `id` | Búsqueda por ID. |
| `idx_nv_extracted` | `extracted_value_id` | Búsqueda de valor normalizado por origen (cadena E3→E4). |

### 1.5 `validated_values`

| Índice conceptual | Columnas | Justificación |
|---|---|---|
| PK | `id` | Búsqueda por ID. |
| `idx_vv_normalized` | `normalized_value_id` | Búsqueda de valor validado por origen (cadena E4→E5). |
| `idx_vv_field` | `normalized_value_id, field` | Búsqueda de valores validados por campo. |

### 1.6 `expenses`

| Índice conceptual | Columnas | Justificación |
|---|---|---|
| PK | `id` | Búsqueda por ID. |
| `idx_exp_owner` | `owner_id` | Aislamiento por propietario. |
| `idx_exp_owner_state` | `owner_id, state` | Listado de gastos por estado (p. e.g. "mis gastos en `under_review`"). |
| `idx_exp_owner_date` | `owner_id, document_date DESC` | Búsqueda por fecha (NFR-6). |
| `idx_exp_owner_supplier` | `owner_id, supplier_id` | Búsqueda por proveedor (NFR-6). |
| `idx_exp_owner_supplier_date` | `owner_id, supplier_id, document_date DESC` | Búsqueda por proveedor + fecha (NFR-6: búsqueda por proveedor/fecha < 2s para 100.000 gastos). |
| `idx_exp_owner_category` | `owner_id, category_id` | Listado por categoría (FR-CAT-3). |
| `idx_exp_document` | `document_id` | Búsqueda de gastos por documento (INV-3/INV-4). |
| `idx_exp_accepted` | `owner_id, accepted_at DESC` WHERE `state = 'accepted'` | Listado de gastos aceptados (hechos contables). Índice parcial. |

### 1.7 `expense_lines`

| Índice conceptual | Columnas | Justificación |
|---|---|---|
| PK | `id` | Búsqueda por ID. |
| `idx_el_expense` | `expense_id` | Búsqueda de líneas por gasto. |

### 1.8 `tax_lines`

| Índice conceptual | Columnas | Justificación |
|---|---|---|
| PK | `id` | Búsqueda por ID. |
| `idx_tl_line` | `expense_line_id` | Búsqueda de líneas fiscales por línea de gasto. |
| `idx_tl_expense` | `expense_id` | Búsqueda de líneas fiscales por gasto (totales). |

### 1.9 `suppliers`

| Índice conceptual | Columnas | Justificación |
|---|---|---|
| PK | `id` | Búsqueda por ID. |
| `idx_sup_owner_nif` | `owner_id, nif_cif` | Búsqueda por NIF/CIF (FR-SUP-3). |
| `idx_sup_owner_name` | `owner_id, legal_name` | Búsqueda por nombre (FR-SUP-3). |

### 1.10 `payments`

| Índice conceptual | Columnas | Justificación |
|---|---|---|
| PK | `id` | Búsqueda por ID. |
| `idx_pay_expense` | `expense_id` | Búsqueda de pagos por gasto. |

### 1.11 `reviews`

| Índice conceptual | Columnas | Justificación |
|---|---|---|
| PK | `id` | Búsqueda por ID. |
| `idx_rev_expense` | `expense_id` | Búsqueda de revisiones por gasto. |

### 1.12 `duplications`

| Índice conceptual | Columnas | Justificación |
|---|---|---|
| PK | `id` | Búsqueda por ID. |
| `idx_dup_doc_a` | `document_a_id` | Búsqueda de duplicaciones por documento A. |
| `idx_dup_doc_b` | `document_b_id` | Búsqueda de duplicaciones por documento B. |
| `idx_dup_owner_state` | `owner_id, state` | Listado de duplicaciones por estado (p. e.g. "duplicaciones `probable` pendientes"). |

### 1.13 `audit_events`

| Índice conceptual | Columnas | Justificación |
|---|---|---|
| PK | `id` | Búsqueda por ID. |
| `idx_audit_entity` | `entity_type, entity_id` | Búsqueda de eventos por entidad (trazabilidad, INV-10). |
| `idx_audit_owner_date` | `owner_id, occurred_at DESC` | Listado de eventos por fecha (auditoría). |
| `idx_audit_action` | `action` | Búsqueda de eventos por acción. |

### 1.14 `extraction_jobs`

| Índice conceptual | Columnas | Justificación |
|---|---|---|
| PK | `id` | Búsqueda por ID. |
| `idx_jobs_pending` | `state, created_at` WHERE `state = 'pending'` | Claim atómico: búsqueda de tareas pendientes en orden FIFO. Índice parcial. |
| `idx_jobs_lease` | `state, lease_expires_at` WHERE `state = 'running'` | Recuperación de tareas de workers muertos (lease expirado). Índice parcial. |
| `idx_jobs_document` | `document_id` | Búsqueda de tareas por documento. |

### 1.15 `currencies`, `tax_rates`, `categories`, `payment_methods`

| Índice conceptual | Columnas | Justificación |
|---|---|---|
| PK | `code` / `id` | Búsqueda por ID/código. |
| `idx_*_owner` | `owner_id` | Aislamiento por propietario (para catálogos con owner). |

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
  volumen bajo (~1.000 documentos/mes), no es necesario.

## 4. Rendimiento orientativo (NFR-6)

| Operación | Objetivo | Índice que lo soporta |
|---|---|---|
| Búsqueda de gastos por proveedor/fecha | < 2s para 100.000 gastos | `idx_exp_owner_supplier_date` |
| Listado de documentos por estado | < 2s | `idx_docs_owner_state` |
| Búsqueda de duplicaciones `probable` | < 2s | `idx_dup_owner_state` |
| Claim atómico de cola | < 100ms | `idx_jobs_pending` (parcial) |
| Reconstrucción de trazabilidad (INV-10) | < 1 min | FK + índices en cadena E3→E4→E5 |
| Auditoría por entidad | < 2s | `idx_audit_entity` |

## 5. Notas

- **Índices parciales**: los índices parciales (WHERE) se usan para la cola de
  trabajo (`extraction_jobs`) y para los gastos aceptados (`expenses`).
  Reducen el tamaño del índice y mejoran el rendimiento.
- **Índices covering**: en Phase 2, se pueden considerar índices covering
  (INCLUIDE) para las queries más frecuentes (p. e.g. listado de gastos por
  proveedor/fecha incluyendo `total`, `state`).
- **VACUUM/ANALYZE**: el mantenimiento de la BD (VACUUM, ANALYZE) es
  responsabilidad de Phase 2/devops. No se prescribe aquí.
