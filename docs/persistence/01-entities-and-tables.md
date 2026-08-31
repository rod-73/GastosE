# 01 — Entidades y tablas conceptuales (GastosE)

Correspondencia entre las entidades del baseline (E1..E19,
`docs/requirements/02-entities.md`) y las tablas conceptuales del modelo de
persistencia. Cada tabla indica: nombre, columnas clave (con tipo), clave
primaria, claves foráneas y sub-contexto propietario.

**Nota importante (ADR-0006)**: el **contenido** del documento fuente vive en
el filesystem (volumen dedicado, inmutable). En la BD solo se almacenan los
**metadatos** del documento: fingerprint SHA-256, nombre seguro, estado,
propietario, formato detectado, tamaño, páginas. La BD NO almacena el
contenido (ni BLOB).

**Convención de propietario**: todas las tablas de negocio llevan una columna
`owner_id` (UUID) que identifica a la **organización propietaria**
(`owner_id` = `organization_id`; OQ-9 resuelta por ADR-0008). Ver
[06-isolation-and-tenancy.md](06-isolation-and-tenancy.md).

**Tablas de tenencia** (ADR-0008):

- `organizations` (id UUID PK, name TEXT, state TEXT, created_at, updated_at).
- `users` (id UUID PK, organization_id UUID FK NOT NULL → `organizations.id`,
  email, role, state, timestamps). Un usuario pertenece a una organización.

---

## E1 — Documento fuente → tabla `source_documents`

| Columna | Tipo | Notas |
|---|---|---|
| `id` | UUID (PK) | UUIDv7. |
| `owner_id` | UUID (FK) | Organización propietaria (ADR-0008). |
| `safe_name` | TEXT | Nombre seguro generado por el sistema (UUID). Nunca el original en rutas. |
| `original_filename` | TEXT | Nombre original, solo como dato descriptivo (FR-DOC-4). |
| `fingerprint_sha256` | CHAR(64) | Fingerprint SHA-256 del contenido (INV-9, NFR-3). |
| `doc_type` | TEXT | `received_invoice` \| `ticket` \| `other`. |
| `format_detected` | TEXT | `xml` \| `pdf_text` \| `pdf_scanned` \| `image` (detectado, no declarado; FR-DOC-5). |
| `size_bytes` | BIGINT | Tamaño del archivo. |
| `page_count` | INT | Número de páginas. |
| `uploaded_by` | UUID | Usuario que subió. |
| `uploaded_at` | TIMESTAMPTZ | Fecha/hora de subida. |
| `state` | TEXT | Ciclo A: `uploaded` \| `processing` \| `extracted` \| `uncertain` \| `validation_error` \| `duplicate` \| `manually_corrected` \| `validated` \| `accepted` \| `rejected` \| `confirmed_duplicate` \| `failed`. |
| `failure_reason` | TEXT | Motivo de fallo si `failed` (INV-15). |
| `dup_key` | TEXT | Clave de duplicación (si aplica): (proveedor, nº documento, fecha, importe). |
| `created_at` | TIMESTAMPTZ | |
| `updated_at` | TIMESTAMPTZ | |

- **PK**: `id`.
- **FK**: `owner_id` → `organizations.id`; `uploaded_by` → `users.id`.
- **Sub-contexto**: Document Ingestion.
- **Nota**: el contenido NO está en la BD (ADR-0006). Se recupera por
  `fingerprint_sha256` / `safe_name` en el filesystem.

---

## E2 — Extracción → tabla `extractions`

| Columna | Tipo | Notas |
|---|---|---|
| `id` | UUID (PK) | UUIDv7. |
| `owner_id` | UUID (FK) | Propietario. |
| `document_id` | UUID (FK) | Documento fuente al que pertenece. |
| `method` | TEXT | `xml_schema` \| `pdf_text_rules` \| `ocr` \| `vision_llm` (nivel alcanzado en la cascada). |
| `state` | TEXT | Ciclo B: `pending` \| `running` \| `completed` \| `failed` \| `reprocessed`. |
| `started_at` | TIMESTAMPTZ | Fecha/hora de inicio. |
| `finished_at` | TIMESTAMPTZ | Fecha/hora de fin. |
| `failure_reason` | TEXT | Motivo de fallo si `failed` (INV-15). |
| `created_at` | TIMESTAMPTZ | |
| `updated_at` | TIMESTAMPTZ | |

- **PK**: `id`.
- **FK**: `document_id` → `source_documents.id`; `owner_id` → `organizations.id`.
- **Sub-contexto**: Extraction.
- **Nota**: una extracción produce uno o más valores extraídos (E3). El
  re-procesamiento (`reprocessed`) reemplaza atómicamente los valores de la
  extracción (idempotencia, FR-EXT-5, NFR-4).

---

## E3 — Valor extraído → tabla `extracted_values`

| Columna | Tipo | Notas |
|---|---|---|
| `id` | UUID (PK) | UUIDv7. |
| `owner_id` | UUID (FK) | Propietario. |
| `extraction_id` | UUID (FK) | Extracción a la que pertenece. |
| `field` | TEXT | Campo al que corresponde (p. e.g. `supplier.nif`, `invoice.number`, `line[0].amount`, `total`). |
| `raw_value` | TEXT | Valor crudo (tal como se leyó). |
| `confidence` | NUMERIC(4,3) | 0..1 (INV-11). |
| `provenance` | JSONB | Método, página, coordenadas/bbox, patrón o regla aplicada (INV-11). |
| `created_at` | TIMESTAMPTZ | |

- **PK**: `id`.
- **FK**: `extraction_id` → `extractions.id`; `owner_id` → `organizations.id`.
- **Sub-contexto**: Extraction.
- **Nota**: `confidence` y `provenance` son NOT NULL (INV-11). Un valor sin
  provenance no es un valor extraído válido.

---

## E4 — Valor normalizado → tabla `normalized_values`

| Columna | Tipo | Notas |
|---|---|---|
| `id` | UUID (PK) | UUIDv7. |
| `owner_id` | UUID (FK) | Propietario. |
| `extracted_value_id` | UUID (FK) | Valor extraído de origen (referencia obligatoria, INV-10). |
| `field` | TEXT | Campo. |
| `normalized_value` | TEXT | Valor normalizado (moneda ISO-4217 decimal exacto, fecha ISO-8601, NIF/CIF validado, tipo impositivo conocido). |
| `normalization_rule` | TEXT | Regla de normalización aplicada. |
| `created_at` | TIMESTAMPTZ | |

- **PK**: `id`.
- **FK**: `extracted_value_id` → `extracted_values.id`; `owner_id` → `organizations.id`.
- **Sub-contexto**: Expense Core.
- **Nota**: `extracted_value_id` es NOT NULL (INV-10, INV-12). No hay camino
  para normalizar un valor que no tiene origen E3.

---

## E5 — Valor validado → tabla `validated_values`

| Columna | Tipo | Notas |
|---|---|---|
| `id` | UUID (PK) | UUIDv7. |
| `owner_id` | UUID (FK) | Propietario. |
| `normalized_value_id` | UUID (FK) | Valor normalizado de origen (referencia obligatoria, INV-10). |
| `field` | TEXT | Campo. |
| `validated_value` | TEXT | Valor validado. |
| `validation_result` | TEXT | `passed` \| `corrected` (por revisión humana). |
| `rules_applied` | JSONB | Reglas de validación aplicadas y su resultado (VR-xxx). |
| `manual_correction_id` | UUID (FK, nullable) | Referencia a la corrección manual (E14) si `corrected`. |
| `created_at` | TIMESTAMPTZ | |

- **PK**: `id`.
- **FK**: `normalized_value_id` → `normalized_values.id`;
  `manual_correction_id` → `manual_corrections.id`; `owner_id` → `organizations.id`.
- **Sub-contexto**: Expense Core.
- **Nota**: `normalized_value_id` es NOT NULL (INV-10, INV-8). Un valor no
  normalizado no puede marcarse validado.

---

## E6 — Gasto → tabla `expenses`

| Columna | Tipo | Notas |
|---|---|---|
| `id` | UUID (PK) | UUIDv7. |
| `owner_id` | UUID (FK) | Propietario. |
| `document_id` | UUID (FK) | Documento fuente al que referencia (exactamente uno; salvo split, E19). |
| `supplier_id` | UUID (FK) | Proveedor (E9). |
| `document_number` | TEXT | Número de documento (nº de factura / nº de ticket). |
| `document_date` | DATE | Fecha del documento (ISO-8601, OQ-15). |
| `registered_at` | TIMESTAMPTZ | Fecha de registro. |
| `currency` | CHAR(3) | Moneda ISO-4217 (E17). |
| `total` | NUMERIC | Total (base + IVA − retenciones; decimal exacto, INV-2). |
| `category_id` | UUID (FK, nullable) | Categoría (E10). |
| `payment_method_id` | UUID (FK, nullable) | Método de pago (E11). |
| `state` | TEXT | Ciclo C: `draft` \| `under_review` \| `validation_error` \| `duplicate` \| `ready_for_acceptance` \| `accepted` \| `voided` \| `rejected` \| `confirmed_duplicate` \| `failed`. |
| `rejection_reason` | TEXT | Motivo de rechazo si `rejected`. |
| `failure_reason` | TEXT | Motivo de fallo si `failed` (INV-15). |
| `accepted_by` | UUID (nullable) | Usuario que aceptó. |
| `accepted_at` | TIMESTAMPTZ (nullable) | Fecha/hora de aceptación. |
| `accepted_snapshot` | JSONB (nullable) | Snapshot inmutable de valores aceptados (INV-14, FR-ACC-4). |
| `voided_by` | UUID (nullable) | Usuario que anuló. |
| `voided_at` | TIMESTAMPTZ (nullable) | Fecha/hora de anulación. |
| `voided_reason` | TEXT (nullable) | Motivo de anulación. |
| `created_at` | TIMESTAMPTZ | |
| `updated_at` | TIMESTAMPTZ | |

- **PK**: `id`.
- **FK**: `document_id` → `source_documents.id`; `supplier_id` →
  `suppliers.id`; `category_id` → `categories.id`; `payment_method_id` →
  `payment_methods.id`; `owner_id` → `organizations.id`.
- **Sub-contexto**: Expense Core.
- **Nota**: `document_id` es NOT NULL (INV-3). Un gasto aceptado referencia
  exactamente un documento fuente. `accepted_snapshot` es inmutable una vez
  `state = accepted` (INV-14).

---

## E7 — Línea de gasto → tabla `expense_lines`

| Columna | Tipo | Notas |
|---|---|---|
| `id` | UUID (PK) | UUIDv7. |
| `owner_id` | UUID (FK) | Propietario. |
| `expense_id` | UUID (FK) | Gasto al que pertenece. |
| `description` | TEXT | Descripción / concepto. |
| `quantity` | NUMERIC | Cantidad (decimal exacto; puede ser no monetaria, p. e.g. unidades). |
| `amount` | NUMERIC | Importe (base imponible de la línea; decimal exacto, INV-2). |
| `tax_rate_id` | UUID (FK) | Tipo impositivo aplicado (E18). |
| `created_at` | TIMESTAMPTZ | |

- **PK**: `id`.
- **FK**: `expense_id` → `expenses.id`; `tax_rate_id` → `tax_rates.id`;
  `owner_id` → `organizations.id`.
- **Sub-contexto**: Expense Core.
- **Nota**: `amount` es NOT NULL y ≥ 0 (VR-ARITH-4). La suma de `amount` de
  las líneas debe coincidir con la base total del gasto (INV-1, VR-ARITH-3).

---

## E8 — Línea fiscal → tabla `tax_lines`

| Columna | Tipo | Notas |
|---|---|---|
| `id` | UUID (PK) | UUIDv7. |
| `owner_id` | UUID (FK) | Propietario. |
| `expense_line_id` | UUID (FK, nullable) | Línea de gasto a la que pertenece. |
| `expense_id` | UUID (FK, nullable) | Gasto (para totales). |
| `tax_type` | TEXT | `vat` \| `withholding`. |
| `tax_rate_id` | UUID (FK) | Tipo impositivo (E18). |
| `taxable_base` | NUMERIC | Base imponible (decimal exacto, INV-2). |
| `tax_amount` | NUMERIC | Cuota (decimal exacto, INV-2). |
| `created_at` | TIMESTAMPTZ | |

- **PK**: `id`.
- **FK**: `expense_line_id` → `expense_lines.id`; `expense_id` →
  `expenses.id`; `tax_rate_id` → `tax_rates.id`; `owner_id` → `organizations.id`.
- **Sub-contexto**: Expense Core.
- **Nota**: `taxable_base` y `tax_amount` son NOT NULL y ≥ 0 (VR-ARITH-4).
  `cuota == round(base × tipo impositivo, 2)` con tolerancia ≤ 0,01
  (VR-ARITH-2).

---

## E9 — Proveedor → tabla `suppliers`

| Columna | Tipo | Notas |
|---|---|---|
| `id` | UUID (PK) | UUIDv7. |
| `owner_id` | UUID (FK) | Propietario. |
| `legal_name` | TEXT | Nombre legal. |
| `nif_cif` | TEXT | NIF/CIF (con dígito de control validado, VR-NORM-3). |
| `tax_address` | TEXT | Dirección fiscal. |
| `contact_data` | JSONB | Datos de contacto (opcionales). |
| `state` | TEXT | `active` \| `inactive`. |
| `created_at` | TIMESTAMPTZ | |
| `updated_at` | TIMESTAMPTZ | |

- **PK**: `id`.
- **FK**: `owner_id` → `organizations.id`.
- **Sub-contexto**: Supplier.
- **Nota**: `nif_cif` es NOT NULL para gastos aceptados (INV-5). Un proveedor
  con gastos aceptados no se elimina, solo `inactive` (FR-SUP-4).

---

## E10 — Categoría → tabla `categories`

| Columna | Tipo | Notas |
|---|---|---|
| `id` | UUID (PK) | UUIDv7. |
| `owner_id` | UUID (FK) | Propietario. |
| `name` | TEXT | Nombre. |
| `description` | TEXT | Descripción. |
| `parent_id` | UUID (FK, nullable) | Jerarquía (padre, si se decide jerárquica — OQ-17). |
| `state` | TEXT | `active` \| `inactive`. |
| `created_at` | TIMESTAMPTZ | |
| `updated_at` | TIMESTAMPTZ | |

- **PK**: `id`.
- **FK**: `parent_id` → `categories.id`; `owner_id` → `organizations.id`.
- **Sub-contexto**: Expense Core (catálogos).

---

## E11 — Método de pago → tabla `payment_methods`

| Columna | Tipo | Notas |
|---|---|---|
| `id` | UUID (PK) | UUIDv7. |
| `owner_id` | UUID (FK) | Propietario. |
| `name` | TEXT | Nombre (efectivo, tarjeta, transferencia, cheque, otro). |
| `state` | TEXT | `active` \| `inactive`. |
| `created_at` | TIMESTAMPTZ | |
| `updated_at` | TIMESTAMPTZ | |

- **PK**: `id`.
- **FK**: `owner_id` → `organizations.id`.
- **Sub-contexto**: Expense Core (catálogos).

---

## E12 — Pago → tabla `payments`

| Columna | Tipo | Notas |
|---|---|---|
| `id` | UUID (PK) | UUIDv7. |
| `owner_id` | UUID (FK) | Propietario. |
| `expense_id` | UUID (FK) | Gasto al que pertenece. |
| `payment_method_id` | UUID (FK) | Método de pago (E11). |
| `payment_date` | DATE | Fecha de pago (ISO-8601). |
| `reference` | TEXT | Referencia (nº de operación, etc., opcional). |
| `amount_paid` | NUMERIC | Importe pagado (decimal exacto; normalmente igual al total del gasto). |
| `created_at` | TIMESTAMPTZ | |

- **PK**: `id`.
- **FK**: `expense_id` → `expenses.id`; `payment_method_id` →
  `payment_methods.id`; `owner_id` → `organizations.id`.
- **Sub-contexto**: Expense Core.
- **Nota**: un gasto puede tener varios pagos (pago parcial, OQ-6). En pago
  único, `amount_paid == total` con tolerancia ≤ 0,01 (VR-ARITH-5).

---

## E13 — Revisión → tabla `reviews`

| Columna | Tipo | Notas |
|---|---|---|
| `id` | UUID (PK) | UUIDv7. |
| `owner_id` | UUID (FK) | Propietario. |
| `expense_id` | UUID (FK) | Gasto al que pertenece. |
| `reviewed_by` | UUID | Usuario. |
| `reviewed_at` | TIMESTAMPTZ | Fecha/hora. |
| `state` | TEXT | Ciclo D: `in_progress` \| `completed` \| `aborted`. |
| `comment` | TEXT | Comentario (opcional). |
| `created_at` | TIMESTAMPTZ | |
| `updated_at` | TIMESTAMPTZ | |

- **PK**: `id`.
- **FK**: `expense_id` → `expenses.id`; `reviewed_by` → `users.id`;
  `owner_id` → `organizations.id`.
- **Sub-contexto**: Review & Acceptance.
- **Nota**: los resultados por campo se registran en `review_field_results`
  (ver abajo) o en `validated_values.validation_result`.

### Tabla auxiliar: `review_field_results`

| Columna | Tipo | Notas |
|---|---|---|
| `id` | UUID (PK) | UUIDv7. |
| `review_id` | UUID (FK) | Revisión a la que pertenece. |
| `field` | TEXT | Campo revisado. |
| `result` | TEXT | `confirmed` \| `corrected` \| `rejected`. |
| `created_at` | TIMESTAMPTZ | |

- **PK**: `id`.
- **FK**: `review_id` → `reviews.id`.
- **Sub-contexto**: Review & Acceptance.

---

## E14 — Corrección manual → tabla `manual_corrections`

| Columna | Tipo | Notas |
|---|---|---|
| `id` | UUID (PK) | UUIDv7. |
| `owner_id` | UUID (FK) | Propietario. |
| `review_id` | UUID (FK) | Revisión a la que pertenece. |
| `field` | TEXT | Campo. |
| `old_value` | TEXT | Valor anterior. |
| `new_value` | TEXT | Valor posterior. |
| `corrected_by` | UUID | Usuario. |
| `corrected_at` | TIMESTAMPTZ | Fecha/hora. |
| `reason` | TEXT | Motivo (opcional). |
| `created_at` | TIMESTAMPTZ | |

- **PK**: `id`.
- **FK**: `review_id` → `reviews.id`; `corrected_by` → `users.id`;
  `owner_id` → `organizations.id`.
- **Sub-contexto**: Review & Acceptance.
- **Nota**: `old_value` y `new_value` son NOT NULL (INV-7). Toda corrección
  manual queda auditada.

---

## E15 — Duplicación → tabla `duplications`

| Columna | Tipo | Notas |
|---|---|---|
| `id` | UUID (PK) | UUIDv7. |
| `owner_id` | UUID (FK) | Propietario. |
| `document_a_id` | UUID (FK) | Documento fuente A. |
| `document_b_id` | UUID (FK) | Documento fuente B. |
| `expense_a_id` | UUID (FK, nullable) | Gasto A (si aplica). |
| `expense_b_id` | UUID (FK, nullable) | Gasto B (si aplica). |
| `dup_type` | TEXT | `fingerprint` (mismo archivo) \| `logical` (misma clave de duplicación). |
| `state` | TEXT | `probable` \| `confirmed` \| `resolved_not_duplicate`. |
| `resolved_by` | UUID (nullable) | Usuario que resolvió. |
| `resolved_at` | TIMESTAMPTZ (nullable) | Fecha/hora de resolución. |
| `resolution_reason` | TEXT (nullable) | Motivo de resolución. |
| `created_at` | TIMESTAMPTZ | |
| `updated_at` | TIMESTAMPTZ | |

- **PK**: `id`.
- **FK**: `document_a_id` → `source_documents.id`; `document_b_id` →
  `source_documents.id`; `expense_a_id` → `expenses.id`; `expense_b_id` →
  `expenses.id`; `resolved_by` → `users.id`; `owner_id` → `organizations.id`.
- **Sub-contexto**: Expense Core (estado) / Review & Acceptance (resolución).
- **Nota**: `probable` bloquea la aceptación (INV-6, DUP-6). La resolución es
  humana (DUP-4).

---

## E16 — Evento de auditoría → tabla `audit_events`

| Columna | Tipo | Notas |
|---|---|---|
| `id` | UUID (PK) | UUIDv7. |
| `owner_id` | UUID (FK) | Propietario. |
| `entity_type` | TEXT | Tipo de entidad afectada (p. e.g. `source_document`, `expense`, `validated_value`). |
| `entity_id` | UUID | Identificador de la entidad afectada. |
| `action` | TEXT | Acción (p. e.g. `document.uploaded`, `value.corrected`, `expense.accepted`). |
| `actor` | UUID | Usuario (o sistema). |
| `occurred_at` | TIMESTAMPTZ | Fecha/hora. |
| `before_data` | JSONB | Datos antes (según acción). |
| `after_data` | JSONB | Datos después (según acción). |
| `created_at` | TIMESTAMPTZ | |

- **PK**: `id`.
- **FK**: `owner_id` → `organizations.id`; `actor` → `users.id`.
- **Sub-contexto**: Transversal (todos los sub-contextos alimentan la
  auditoría).
- **Nota**: **append-only** (NFR-1). No se modifica ni se elimina; solo se
  añade. Ver [03-invariants-enforcement.md](03-invariants-enforcement.md).

---

## E17 — Moneda → tabla `currencies`

| Columna | Tipo | Notas |
|---|---|---|
| `code` | CHAR(3) (PK) | Código ISO-4217. |
| `name` | TEXT | Nombre. |
| `decimals` | INT | Número de decimales (p. e.g. EUR: 2). |

- **PK**: `code`.
- **FK**: ninguna.
- **Sub-contexto**: Expense Core (catálogos).
- **Nota**: tabla de referencia; no lleva `owner_id` (es un catálogo global
  ISO-4217).

---

## E18 — Tipo impositivo → tabla `tax_rates`

| Columna | Tipo | Notas |
|---|---|---|
| `id` | UUID (PK) | UUIDv7. |
| `owner_id` | UUID (FK) | Propietario. |
| `code` | TEXT | Código. |
| `description` | TEXT | Descripción. |
| `tax_type` | TEXT | `vat` \| `withholding`. |
| `percentage` | NUMERIC | Porcentaje. |
| `valid_from` | DATE | Período de vigencia (desde). |
| `valid_until` | DATE (nullable) | Período de vigencia (hasta). |
| `jurisdiction` | TEXT | Jurisdicción. |
| `created_at` | TIMESTAMPTZ | |
| `updated_at` | TIMESTAMPTZ | |

- **PK**: `id`.
- **FK**: `owner_id` → `organizations.id`.
- **Sub-contexto**: Expense Core (catálogos).
- **Nota**: el tipo impositivo usado debe existir en el catálogo (VR-NORM-4)
  y estar vigente en la fecha del documento (VR-NORM-5).

---

## E19 — Split de documento → tabla `document_splits`

| Columna | Tipo | Notas |
|---|---|---|
| `id` | UUID (PK) | UUIDv7. |
| `owner_id` | UUID (FK) | Propietario. |
| `document_id` | UUID (FK) | Documento fuente. |
| `created_by` | UUID | Usuario que lo creó. |
| `created_at` | TIMESTAMPTZ | Fecha/hora. |
| `justification` | TEXT | Justificación. |

- **PK**: `id`.
- **FK**: `document_id` → `source_documents.id`; `created_by` → `users.id`;
  `owner_id` → `organizations.id`.
- **Sub-contexto**: Expense Core.
- **Nota**: un split permite que un documento fuente alimente varios gastos
  (INV-4, VR-REF-5). La relación split → gastos se modela como una tabla
  intermedia `split_expenses` (ver [02-relations.md](02-relations.md)).

### Tabla auxiliar: `split_expenses`

| Columna | Tipo | Notas |
|---|---|---|
| `split_id` | UUID (FK) | Split. |
| `expense_id` | UUID (FK) | Gasto resultante. |

- **PK**: (`split_id`, `expense_id`).
- **FK**: `split_id` → `document_splits.id`; `expense_id` → `expenses.id`.

---

## Tabla auxiliar: `users`

| Columna | Tipo | Notas |
|---|---|---|
| `id` | UUID (PK) | UUIDv7. |
| `username` | TEXT | Nombre de usuario único. |
| `email` | TEXT | Correo electrónico. |
| `role` | TEXT | `reader` \| `reviewer` \| `approver` \| `admin`. |
| `created_at` | TIMESTAMPTZ | |
| `updated_at` | TIMESTAMPTZ | |

- **PK**: `id`.
- **Sub-contexto**: Transversal (autenticación/autorización, NFR-7).
- **Nota**: si OQ-9 decide multi-tenancy por organización, se añade una tabla
  `tenants` y `users.tenant_id`. Ver [06-isolation-and-tenancy.md](06-isolation-and-tenancy.md).
