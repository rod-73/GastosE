# 07 — Preguntas abiertas de persistencia (GastosE)

Preguntas de persistencia que requieren decisión del director. Se refieren a
las preguntas abiertas del baseline (OQ-1..OQ-18,
`docs/requirements/10-open-questions.md`) y añaden preguntas específicas de
persistencia.

## PQ-1 — OQ-9: Modelo de multi-tenancy / aislamiento por usuario

- **RESUELTA (2026-08-31, ADR-0008)**: aislamiento por **organización
  (multi-usuario)**. `owner_id` = `organization_id`. Se añade tabla
  `organizations` y `users.organization_id` (FK NOT NULL). El filtro de
  aislamiento se aplica sobre `owner_id` (= organización). La atribución de
  auditoría sigue siendo por usuario (`audit_events.actor`).
- **Urgencia**: resuelta; ya no bloquea Phase 2.

## PQ-2 — OQ-10: Retención de documentos y auditoría

- **RESUELTA (2026-09-01, D3)**: sin purga automática en V1 / Phase 2. Los
  documentos se conservan mientras no exista una política explícita de
  eliminación. La arquitectura debe permitir políticas configurables de
  retención por organización, tipo documental, estado y requisitos legales.
  Los `audit_events` no tendrán eliminación automática en V1. No se
  hardcodean plazos legales concretos.
- **Impacto en persistencia**: no hay purga en V1 → no se necesita
  particionamiento por fecha para purga (PQ-8 sigue abierto para rendimiento).
  El diseño debe soportar futuras políticas de purga sin romper invariantes
  (INV-10, NFR-1, INV-9).
- **Decisión pendiente**: definir la política concreta de retención por
  organización/tipo documental (tarea de configuración en Phase 2, no
  bloqueante).

## PQ-3 — OQ-15: Formato de fecha canónico

- **Pregunta**: ¿la fecha canónica es solo la fecha (YYYY-MM-DD) o incluye
  hora (YYYY-MM-DDTHH:MM:SS)?
- **Impacto en persistencia**: determina si `document_date` es `DATE` o
  `TIMESTAMPTZ`. El baseline asume `DATE` para la fecha del documento y
  `TIMESTAMPTZ` para los eventos.
- **Por defecto en el baseline**: fecha del documento = YYYY-MM-DD; eventos =
  con hora.
- **Decisión pendiente**: confirmar.

## PQ-4 — OQ-6: Pagos parciales

- **Pregunta**: ¿se permiten pagos parciales (varios pagos que suman el
  total)?
- **Impacto en persistencia**: si se permiten, `payments` ya soporta varios
  pagos por gasto (1:N). Si no, se puede añadir un check constraint de que
  solo hay un pago por gasto.
- **Por defecto en el baseline**: no se prescribe (FR-PAY-3 opcional).
- **Decisión pendiente**: si se soportan pagos parciales y cómo se valida la
  suma.

## PQ-5 — OQ-17: Jerarquía de categorías

- **Pregunta**: ¿las categorías son planas o jerárquicas?
- **Impacto en persistencia**: si son jerárquicas, `categories.parent_id` se
  usa. Si son planas, `parent_id` es siempre NULL.
- **Por defecto en el baseline**: se permite jerarquía (E10) pero no se
  prescribe.
- **Decisión pendiente**: si se usa jerarquía y a cuántos niveles.

## PQ-6 — OQ-4: Multimoneda

- **Pregunta**: ¿se soporta multimoneda (gastos en distintas monedas con
  conversión)?
- **Impacto en persistencia**: el modelo actual asume una única moneda por
  gasto (INV-13). Si se soporta conversión, se necesita una tabla
  `exchange_rates` (tipo de cambio, fecha de referencia, origen) y una
  referencia en `expenses` o `expense_lines`.
- **Por defecto en el baseline**: cada gasto en una única moneda (INV-13); la
  conversión es explícita y registrada (FR-CUR-3) pero no se prescribe fuente.
- **Decisión pendiente**: si se soporta conversión automática, qué fuente de
  tipos de cambio y con qué fecha de referencia.

## PQ-7 — OQ-13: Anulación de gastos aceptados: permisos

- **Pregunta**: ¿quiénes pueden anular un gasto aceptado? ¿Requiere motivo
  obligatorio?
- **Impacto en persistencia**: `expenses.voided_by`, `expenses.voided_at`,
  `expenses.voided_reason` ya están en el modelo. La decisión afecta a la
  autorización (rol), no a la persistencia.
- **Por defecto en el baseline**: usuario autorizado con permiso de anulación;
  motivo obligatorio (FR-EXP-5).
- **Decisión pendiente**: definir el rol exacto y si la anulación requiere
  doble aprobación.

## PQ-8 — Particionamiento de auditoría

- **Pregunta**: ¿se particiona `audit_events` por fecha desde Phase 2?
- **Impacto en persistencia**: el particionamiento por fecha mejora el
  rendimiento de las queries de auditoría y facilita la retención. Con volumen
  bajo (~1.000 documentos/mes), no es necesario en Phase 2.
- **Por defecto**: no particionar en Phase 2. Revisar si el volumen lo exige.
- **Decisión pendiente**: decidir en Phase 2 según el volumen real.

## PQ-9 — Snapshot de aceptación: JSONB vs tablas

- **Pregunta**: ¿el snapshot de aceptación (`expenses.accepted_snapshot`) es
  JSONB o se modela con tablas separadas?
- **Impacto en persistencia**: JSONB es más flexible pero no permite queries
  SQL sobre los valores del snapshot. Tablas separadas permiten queries pero
  añaden complejidad.
- **Por defecto**: JSONB (flexibilidad + inmutabilidad). El snapshot es
  inmutable (INV-14) y no se consulta con queries SQL complejas.
- **Decisión pendiente**: confirmar JSONB o tablas separadas.

## PQ-10 — Provenance: JSONB vs tablas

- **Pregunta**: ¿la provenance (`extracted_values.provenance`) es JSONB o se
  modela con columnas separadas?
- **Impacto en persistencia**: JSONB es más flexible (método, página, bbox,
  regla pueden variar). Columnas separadas permiten queries SQL pero son más
  rígidas.
- **Por defecto**: JSONB (flexibilidad). La provenance no se consulta con
  queries SQL complejas; se muestra en la UI.
- **Decisión pendiente**: confirmar JSONB o columnas separadas.

## PQ-11 — Clave de duplicación: columna TEXT vs tablas

- **Pregunta**: ¿la clave de duplicación (`source_documents.dup_key`) es una
  columna TEXT (concatenada) o se modela con columnas separadas?
- **Impacto en persistencia**: TEXT es más simple pero no permite queries SQL
  sobre los componentes individuales. Columnas separadas permiten queries pero
  añaden complejidad.
- **Por defecto**: TEXT (simple). La detección de duplicado por clave lógica
  (DUP-2) se hace en el dominio, no con queries SQL.
- **Decisión pendiente**: confirmar TEXT o columnas separadas.

## PQ-12 — Tabla `users`: ¿en scope de GastosE?

- **RESUELTA (2026-09-01, ADR-0009)**: la autenticación es **nativa de
  GastosE** (token opaco + sesión server-side en BD). La tabla `users` es
  parte del modelo de persistencia de GastosE. Se añade la tabla `sessions`
  (token opaco, user_id, organization_id, role, expiración, revocación).
- **Impacto en persistencia**: `users` y `sessions` son tablas de GastosE.
  El `organization_id` se deriva de la sesión (nunca de un parámetro del
  cliente).
- **Decisión pendiente**: ninguna (resuelta por ADR-0009).
