# Modelo de persistencia CONCEPTUAL (GastosE)

Este documento es el **modelo de persistencia conceptual** de GastosE
(tarea PHASE1-003). Es un diseño de datos a nivel conceptual: define tablas,
columnas, tipos, claves y relaciones, pero **no** prescribe DDL ejecutable,
ORM ni migraciones (eso es Phase 2).

## Qué es y qué no es

- **Es**: un mapa conceptual de tablas y relaciones, trazable al baseline de
  entidades (E1..E19, `docs/requirements/02-entities.md`) y a los invariantes
  (INV-1..15, `docs/requirements/05-invariants.md`).
- **No es**: DDL, Alembic migrations, código ORM, ni decisiones de indexación
  exacta (Phase 2). Los nombres de columna y tipos son orientativos.

## Convenciones de tipos

| Concepto | Tipo conceptual | Justificación |
|---|---|---|
| Identificadores | `UUID` (UUIDv7) | Orden temporal + unicidad global (ADR de diseño). |
| Valores monetarios | `NUMERIC` (decimal exacto) | INV-2, NFR-2: nunca float. |
| Moneda | `CHAR(3)` ISO-4217 | INV-13, FR-CUR-1. |
| Fechas | `DATE` (ISO-8601) | OQ-15: fecha del documento = YYYY-MM-DD. |
| Fechas/hora de eventos | `TIMESTAMPTZ` (ISO-8601) | OQ-15: eventos con hora. |
| Confidence | `NUMERIC(4,3)` (0..1) | INV-11. |
| Provenance | `JSONB` | INV-11: método, página, bbox, regla. |
| Snapshot de aceptación | `JSONB` | INV-14, FR-ACC-4. |
| Estado | `TEXT` (enum lógico) | Ciclos A/B/C/D. |
| Fingerprint | `CHAR(64)` SHA-256 | INV-9, NFR-3. |

## Relación con el baseline de entidades

Cada tabla conceptual corresponde a una entidad del baseline (E1..E19). La
correspondencia se detalla en [01-entities-and-tables.md](01-entities-and-tables.md).
Los invariantes (INV-1..15) se aplican a nivel de persistencia como
restricciones, índices únicos, NOT NULL y check constraints; ver
[03-invariants-enforcement.md](03-invariants-enforcement.md).

## Qué vive en la BD y qué vive en el filesystem

- **En la BD**: metadatos de documento (fingerprint, nombre seguro, estado,
  propietario), valores extraídos/normalizados/validados, gastos, líneas,
  proveedores, catálogos, revisiones, auditoría, cola de trabajo.
- **En el filesystem** (ADR-0006): el **contenido** del documento fuente.
  Solo se referencia por fingerprint SHA-256. La BD NO almacena el contenido
  del documento (ni BLOB).

## Aislamiento de FacturaE (ADR-0001)

GastosE tiene su propia base de datos y su propio volumen de documentos. No
se comparte ninguna tabla, schema, migración ni almacenamiento con FacturaE.
Integración futura solo vía API versionada o contrato de eventos versionado.

## Índice del modelo

| Archivo | Contenido |
|---|---|
| [01-entities-and-tables.md](01-entities-and-tables.md) | Tablas conceptuales por entidad E1..E19. |
| [02-relations.md](02-relations.md) | Relaciones entre tablas (1:1, 1:N, M:N) y cadena de niveles de valor. |
| [03-invariants-enforcement.md](03-invariants-enforcement.md) | Cómo se aplica cada INV-1..15 a nivel de persistencia. |
| [04-work-queue.md](04-work-queue.md) | Cola de trabajo de extracción (ADR-0005). |
| [05-indexes-and-performance.md](05-indexes-and-performance.md) | Índices conceptuales (NFR-6). |
| [06-isolation-and-tenancy.md](06-isolation-and-tenancy.md) | Aislamiento por propietario/tenant (OQ-9, NFR-7). |
| [07-open-questions.md](07-open-questions.md) | Preguntas abiertas de persistencia para el director. |
