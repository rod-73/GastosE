# 03 — Aplicación de invariantes a nivel de persistencia (GastosE)

Cómo se aplica cada invariante (INV-1..15, `docs/requirements/05-invariants.md`)
a nivel de persistencia: restricciones, índices únicos, NOT NULL, check
constraints, append-only. La aplicación completa de los invariantes es
responsabilidad del dominio (C2) y de los servicios de aplicación (C3); el
modelo de persistencia proporciona las **garantías estructurales** que hacen
posible (y en algunos casos obligan) el cumplimiento.

**Nota**: las restricciones de transición de estado (máquina de estados de los
ciclos A/B/C/D) se aplican en el dominio, no en la BD. La BD garantiza
integridad referencial, tipos exactos y append-only; el dominio garantiza las
transiciones legales.

---

## INV-1 — Identidad aritmética del total

`total == sum(bases de líneas) + sum(cuotas IVA) − sum(cuotas retención)`,
con tolerancia de redondeo ≤ 0,01 por línea.

**Aplicación en persistencia**:

- **Tipos exactos**: `expenses.total`, `expense_lines.amount`,
  `tax_lines.taxable_base`, `tax_lines.tax_amount` son `NUMERIC` (decimal
  exacto). Nunca float.
- **Check constraints**: `tax_lines.taxable_base >= 0`,
  `tax_lines.tax_amount >= 0`, `expense_lines.amount >= 0` (VR-ARITH-4).
- **Validación en dominio**: la identidad aritmética se verifica en el dominio
  (VR-ARITH-1, VR-ARITH-2, VR-ARITH-3) antes de aceptar. La BD no puede
  expresar la identidad aritmética como constraint (requiere agregación); es
  responsabilidad del dominio.
- **Tolerancia**: la tolerancia de redondeo (≤ 0,01) se aplica en el dominio,
  no en la BD.

**Garantía estructural**: los tipos NUMERIC evitan errores de redondeo de
punto flotante (INV-2). La identidad aritmética se verifica en el dominio
antes de la aceptación.

---

## INV-2 — Exactitud numérica

Todo valor monetario se almacena y manipula como decimal exacto (nunca
float). Las fechas se almacenan en formato canónico (ISO-8601).

**Aplicación en persistencia**:

- **Tipos monetarios**: todos los valores monetarios (`expenses.total`,
  `expense_lines.amount`, `tax_lines.taxable_base`, `tax_lines.tax_amount`,
  `payments.amount_paid`, `extracted_values.confidence`) son `NUMERIC`.
  **Nunca** `FLOAT`, `REAL`, `DOUBLE PRECISION`.
- **Tipos de fecha**: `document_date`, `payment_date`, `valid_from`,
  `valid_until` son `DATE` (ISO-8601, YYYY-MM-DD). `uploaded_at`,
  `registered_at`, `accepted_at`, `occurred_at`, `created_at`, `updated_at`
  son `TIMESTAMPTZ` (ISO-8601 con hora).
- **Moneda**: `expenses.currency` es `CHAR(3)` ISO-4217. `currencies.code`
  es `CHAR(3)` PK.
- **Decimales de moneda**: el número de decimales del importe coincide con el
  de la moneda (VR-NORM-6). Se verifica en el dominio; la BD almacena
  `NUMERIC` sin escala fija (para soportar distintas monedas).

**Garantía estructural**: el uso de `NUMERIC` y `DATE`/`TIMESTAMPTZ` hace
imposible el almacenamiento de float para dinero o de fechas no canónicas.

---

## INV-3 — Un gasto, un documento fuente

Todo gasto aceptado referencia exactamente un documento fuente válido.

**Aplicación en persistencia**:

- **NOT NULL**: `expenses.document_id` es NOT NULL. Un gasto sin documento
  fuente no se puede crear.
- **FK**: `expenses.document_id` → `source_documents.id` (integridad
  referencial).
- **Check en dominio**: la aceptación verifica que el documento fuente existe,
  está íntegro (fingerprint OK) y es de un tipo compatible (VR-REF-4).

**Garantía estructural**: la FK NOT NULL garantiza que todo gasto tiene un
documento fuente. La validez del documento se verifica en el dominio.

---

## INV-4 — Un documento, un gasto (salvo split)

Un documento fuente no puede aceptar dos gastos distintos salvo split
explícito y documentado (E19).

**Aplicación en persistencia**:

- **No hay constraint de unicidad directo**: la BD permite varios gastos por
  documento (para soportar split). La restricción se aplica en el dominio.
- **Split documentado**: si hay más de un gasto por documento, debe existir un
  `document_splits` que lo justifique (VR-REF-5). El dominio verifica esta
  condición antes de aceptar.
- **Check en dominio**: la aceptación verifica que no hay dos gastos aceptados
  por el mismo documento sin split.

**Garantía estructural**: la tabla `document_splits` proporciona la evidencia
del split. El dominio verifica la condición antes de aceptar.

---

## INV-5 — Proveedor válido antes de aceptar

Los datos fiscales del proveedor (mínimo NIF/CIF válido) deben existir antes
de aceptar el gasto.

**Aplicación en persistencia**:

- **NOT NULL**: `suppliers.nif_cif` es NOT NULL. Un proveedor sin NIF/CIF no
  se puede registrar.
- **FK**: `expenses.supplier_id` → `suppliers.id` (integridad referencial).
- **Check en dominio**: la aceptación verifica que el proveedor existe, está
  `active` (o se permite `inactive` con advertencia — OQ-14) y tiene NIF/CIF
  válido (VR-REF-1, VR-BIZ-1, VR-NORM-3).

**Garantía estructural**: la FK NOT NULL garantiza que todo gasto tiene un
proveedor. La validez del NIF/CIF se verifica en el dominio.

---

## INV-6 — Duplicado probable bloquea aceptación

Mismo (proveedor, número de documento, fecha, importe) => duplicación
`probable` => bloqueo de aceptación hasta resolución humana.

**Aplicación en persistencia**:

- **Tabla `duplications`**: registra la relación de duplicado con estado
  `probable` \| `confirmed` \| `resolved_not_duplicate`.
- **Check en dominio**: la aceptación verifica que no hay duplicación
  `probable` pendiente sobre el gasto (VR-BIZ-2). Si la hay, la aceptación se
  bloquea (409).
- **Clave de duplicación**: `source_documents.dup_key` almacena la clave
  (proveedor, nº documento, fecha, importe) para la detección por clave
  lógica (DUP-2).

**Garantía estructural**: la tabla `duplications` con estado `probable`
proporciona la evidencia del bloqueo. El dominio verifica la condición antes
de aceptar.

---

## INV-7 — Auditoría de correcciones manuales

Toda corrección manual queda auditada: usuario, fecha/hora, valor anterior,
valor posterior.

**Aplicación en persistencia**:

- **Tabla `manual_corrections`**: registra `field`, `old_value`, `new_value`,
  `corrected_by`, `corrected_at`, `reason`.
- **NOT NULL**: `old_value`, `new_value`, `corrected_by`, `corrected_at` son
  NOT NULL. Una corrección sin estos datos no se puede registrar.
- **FK**: `manual_corrections.review_id` → `reviews.id`;
  `validated_values.manual_correction_id` → `manual_corrections.id`.
- **Append-only**: `manual_corrections` no se modifica ni se elimina (solo se
  añade). Ver sección "Auditoría append-only" abajo.

**Garantía estructural**: la tabla `manual_corrections` con NOT NULL en los
campos de auditoría garantiza que toda corrección queda auditada.

---

## INV-8 — Solo se acepta lo validado

Un valor solo puede ser `accepted` si es `validated`; un gasto solo puede
aceptarse si todos sus valores obligatorios están validados.

**Aplicación en persistencia**:

- **Referencias obligatorias**: `validated_values.normalized_value_id` NOT
  NULL; `normalized_values.extracted_value_id` NOT NULL. Un valor validado sin
  origen normalizado no es válido.
- **Check en dominio**: la aceptación verifica que todos los valores
  obligatorios están validados (VR-BIZ-3). Si no, la aceptación se bloquea
  (409).
- **Snapshot**: al aceptar, se registra `expenses.accepted_snapshot` (JSONB)
  con los valores validados aceptados. El snapshot es inmutable (INV-14).

**Garantía estructural**: las referencias obligatorias (E3→E4→E5) hacen
imposible aceptar un valor que no ha pasado por normalización y validación.

---

## INV-9 — Inmutabilidad del documento fuente

El contenido del documento fuente no se modifica tras la subida; su
fingerprint SHA-256 es estable y verificable.

**Aplicación en persistencia**:

- **Fingerprint**: `source_documents.fingerprint_sha256` es NOT NULL y
  `CHAR(64)`. Se calcula al subir y se verifica bajo demanda (NFR-3).
- **Inmutabilidad en filesystem**: el contenido se escribe una única vez en el
  filesystem (ADR-0006); después es solo de lectura. La BD no almacena el
  contenido.
- **Check en dominio**: la verificación de integridad recalcula el SHA-256 y
  compara con el registrado. Si no coincide, se alerta (NFR-3).
- **No hay operación de "reemplazar contenido"**: la única vía es subir un
  documento nuevo (FR-DOC-3).

**Garantía estructural**: el fingerprint SHA-256 en la BD + la inmutabilidad
del filesystem garantizan la integridad del documento.

---

## INV-10 — Trazabilidad completa

Para todo gasto aceptado, debe poder reconstruirse la cadena completa:
documento fuente → extracción (método) → valores extraídos (confidence,
provenance) → valores normalizados → valores validados (reglas aplicadas) →
revisión (si hubo) → aceptación (usuario, fecha, snapshot).

**Aplicación en persistencia**:

- **Referencias obligatorias**: la cadena E1→E2→E3→E4→E5→E13→E6 está
  garantizada por FK NOT NULL en cada eslabón:
  - `extractions.document_id` → `source_documents.id` (NOT NULL)
  - `extracted_values.extraction_id` → `extractions.id` (NOT NULL)
  - `normalized_values.extracted_value_id` → `extracted_values.id` (NOT NULL)
  - `validated_values.normalized_value_id` → `normalized_values.id` (NOT NULL)
  - `reviews.expense_id` → `expenses.id` (NOT NULL)
  - `expenses.document_id` → `source_documents.id` (NOT NULL)
- **Snapshot**: `expenses.accepted_snapshot` (JSONB) registra los valores
  aceptados en el momento de la aceptación.
- **Auditoría**: `audit_events` registra todas las transiciones (NFR-1).
- **Reconstrucción**: la cadena se reconstruye recorriendo las FK desde el
  gasto aceptado hacia atrás (E6→E5→E4→E3→E2→E1) y hacia adelante (E6→E13).

**Garantía estructural**: las FK NOT NULL en cada eslabón de la cadena hacen
posible la reconstrucción completa de la trazabilidad. Sin referencia no hay
valor válido en el nivel superior.

---

## INV-11 — Confianza y provenance obligatorias

Todo valor extraído lleva confidence (0..1) y provenance (método, página,
coordenadas, regla). Un valor sin provenance no es un valor extraído válido.

**Aplicación en persistencia**:

- **NOT NULL**: `extracted_values.confidence` y
  `extracted_values.provenance` son NOT NULL.
- **Check constraint**: `extracted_values.confidence >= 0 AND
  extracted_values.confidence <= 1`.
- **Provenance**: `extracted_values.provenance` es `JSONB` con método,
  página, coordenadas/bbox, regla.

**Garantía estructural**: los NOT NULL y el check constraint garantizan que
todo valor extraído tiene confidence y provenance.

---

## INV-12 — Normalización determinística

La normalización es determinística: el mismo valor extraído produce siempre
el mismo valor normalizado.

**Aplicación en persistencia**:

- **Referencia obligatoria**: `normalized_values.extracted_value_id` NOT
  NULL. La normalización solo opera sobre valores extraídos persistidos.
- **Regla de normalización**: `normalized_values.normalization_rule` registra
  la regla aplicada.
- **Determinismo**: la determinística es responsabilidad del dominio (la
  normalización es una función pura). La BD no puede garantizar el
  determinismo; lo garantiza el dominio.

**Garantía estructural**: la referencia obligatoria garantiza que la
normalización opera sobre un valor extraído concreto. El determinismo se
garantiza en el dominio.

---

## INV-13 — Moneda única por gasto

Un gasto está denominado en una única moneda ISO-4217; no se mezclan monedas
en sus líneas sin conversión explícita y registrada.

**Aplicación en persistencia**:

- **Moneda en gasto**: `expenses.currency` es `CHAR(3)` NOT NULL. Un gasto
  tiene una única moneda.
- **No hay moneda en líneas**: `expense_lines` y `tax_lines` NO tienen
  columna `currency`. Heredan la moneda del gasto. Esto hace imposible
  mezclar monedas en las líneas.
- **Check en dominio**: la validación verifica que el gasto usa una única
  moneda (VR-BIZ-5). Si se intenta añadir una línea en otra moneda, se
  bloquea (o se exige conversión explícita con tipo de cambio registrado,
  según OQ-4).

**Garantía estructural**: la ausencia de columna `currency` en las líneas
hace imposible mezclar monedas a nivel de persistencia. La moneda es
propiedad del gasto, no de las líneas.

---

## INV-14 — Aceptación irreversible

Una vez aceptado, un gasto no cambia de estado ni de valores; la única salida
es la anulación (registro separado, FR-EXP-5).

**Aplicación en persistencia**:

- **Snapshot inmutable**: `expenses.accepted_snapshot` (JSONB) se registra en
  el momento de la aceptación. Una vez `state = accepted`, el snapshot no se
  modifica.
- **No hay UPDATE sobre gastos aceptados**: el dominio bloquea cualquier
  modificación de un gasto `accepted` (FR-EXP-3). La BD no tiene un
  constraint directo para esto (sería un trigger), pero el dominio garantiza
  la inmutabilidad.
- **Anulación**: la anulación crea un registro separado (`expenses.voided_by`,
  `expenses.voided_at`, `expenses.voided_reason`) y transita el gasto a
  `voided`. El gasto original conserva su estado `accepted` y su snapshot.
- **Check en dominio**: la transición a `accepted` es irreversible (máquina
  de estados del dominio). Una vez `accepted`, no se puede volver a
  `draft`/`under_review`.

**Garantía estructural**: el snapshot JSONB + la transición irreversible en el
dominio garantizan la inmutabilidad del gasto aceptado.

---

## INV-15 — Fallo con motivo

Todo objeto en estado de fallo (`failed`, `validation_error`) lleva motivo
registrado.

**Aplicación en persistencia**:

- **Columnas de motivo**: `source_documents.failure_reason`,
  `extractions.failure_reason`, `expenses.failure_reason`,
  `expenses.rejection_reason` son `TEXT` (nullable).
- **Check en dominio**: al transitar a un estado de fallo, el dominio exige un
  motivo (FR-FST-1). Si no hay motivo, la transición se bloquea.
- **Check constraint (opcional)**: se puede añadir un check constraint que
  verifique que `failure_reason IS NOT NULL` cuando `state = 'failed'`. Esto
  es una garantía estructural adicional.

**Garantía estructural**: las columnas de motivo + el check en dominio
garantizan que todo fallo tiene motivo registrado.

---

## Auditoría append-only (NFR-1)

El registro de auditoría (`audit_events`) no se modifica ni se elimina; solo
se añade.

**Aplicación en persistencia**:

- **Append-only**: `audit_events` no tiene operaciones de UPDATE ni DELETE.
  Solo INSERT.
- **Implementación**: en Phase 2, se puede implementar como:
  - Una tabla sin triggers de UPDATE/DELETE.
  - Un trigger que bloquea UPDATE y DELETE.
  - Una vista de solo lectura.
  - Permisos de BD: el usuario de aplicación tiene solo INSERT/SELECT sobre
    `audit_events`.
- **Inmutabilidad**: los datos `before_data` y `after_data` (JSONB) no se
  modifican una vez insertados.

**Garantía estructural**: la ausencia de UPDATE/DELETE en `audit_events`
garantiza la inmutabilidad del registro de auditoría.

---

## Resumen de garantías estructurales

| INV | Garantía estructural en BD | Garantía en dominio |
|---|---|---|
| INV-1 | Tipos NUMERIC, check ≥ 0 | Identidad aritmética (VR-ARITH-1/2/3) |
| INV-2 | NUMERIC para dinero, DATE/TIMESTAMPTZ para fechas | Redondeo documentado |
| INV-3 | `expenses.document_id` NOT NULL + FK | VR-REF-4 (documento válido) |
| INV-4 | Tabla `document_splits` | Verificación de split antes de aceptar |
| INV-5 | `suppliers.nif_cif` NOT NULL + FK | VR-REF-1, VR-BIZ-1, VR-NORM-3 |
| INV-6 | Tabla `duplications` con estado | VR-BIZ-2 (bloqueo si `probable`) |
| INV-7 | `manual_corrections` NOT NULL + append-only | Registro obligatorio de correcciones |
| INV-8 | FK NOT NULL en cadena E3→E4→E5 | VR-BIZ-3 (valores validados) |
| INV-9 | `fingerprint_sha256` NOT NULL + inmutabilidad filesystem | Verificación de integridad |
| INV-10 | FK NOT NULL en cada eslabón de la cadena | Reconstrucción de trazabilidad |
| INV-11 | `confidence` y `provenance` NOT NULL + check 0..1 | — |
| INV-12 | `extracted_value_id` NOT NULL | Normalización determinística (función pura) |
| INV-13 | Sin columna `currency` en líneas | VR-BIZ-5 (moneda única) |
| INV-14 | Snapshot JSONB + transición irreversible | Bloqueo de UPDATE sobre `accepted` |
| INV-15 | Columnas de motivo + check (opcional) | Motivo obligatorio al transitar a fallo |
| NFR-1 | `audit_events` append-only (sin UPDATE/DELETE) | — |
