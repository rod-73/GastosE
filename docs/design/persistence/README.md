# Diseño de persistencia Phase 2 — GastosE

Este directorio contiene el **diseño detallado de persistencia** de GastosE
para Phase 2 (tarea PHASE2-002). Es la materialización operativa del modelo
conceptual de Phase 1 (`docs/persistence/`): define el esquema relacional
concreto, la estrategia de migraciones, la aplicación de invariantes a nivel
de BD, el diseño de la cola de trabajo, los índices, el modelo de tenencia,
la auditoría append-only y el diseño de datos específico de V1-S1.

## Qué es y qué no es

- **Es**: diseño de datos a nivel lógico-físico (tablas, columnas, tipos
  PostgreSQL, PK/FK, constraints, índices, migraciones Alembic, triggers,
  permisos). Incluye DDL **ilustrativo/esquemático** como referencia de
  diseño.
- **No es**: código de aplicación, migraciones Alembic ejecutables, DDL
  listo para producción, ni decisiones de infraestructura (eso es devops).
  Los DDL aquí son **esquemáticos**: muestran la intención de diseño, no son
  el artefacto final que se ejecuta.

## Relación con el baseline conceptual (Phase 1)

| Phase 1 (conceptual) | Phase 2 (este diseño) |
|---|---|
| `docs/persistence/01-entities-and-tables.md` | `01-schema-design.md` |
| `docs/persistence/02-relations.md` | `01-schema-design.md` (FKs) + `03-invariants-enforcement.md` |
| `docs/persistence/03-invariants-enforcement.md` | `03-invariants-enforcement.md` |
| `docs/persistence/04-work-queue.md` | `04-work-queue-design.md` |
| `docs/persistence/05-indexes-and-performance.md` | `05-indexes-and-performance.md` |
| `docs/persistence/06-isolation-and-tenancy.md` | `06-tenancy-and-isolation.md` |
| `docs/persistence/07-open-questions.md` | Resueltas en este diseño (ver cada doc) |
| — (no existía) | `02-migration-strategy.md` |
| — (no existía) | `07-audit-and-retention.md` |
| — (no existía) | `08-v1-s1-data-design.md` |

## Convenciones de tipos (PostgreSQL)

| Concepto | Tipo PostgreSQL | Justificación |
|---|---|---|
| Identificadores | `UUID` (UUIDv7) | Orden temporal + unicidad global. |
| Valores monetarios | `NUMERIC(14,2)` | INV-2, NFR-2: nunca float. |
| Importes unitarios | `NUMERIC(14,4)` | Redondeo posterior a 2 decimales. |
| Moneda | `CHAR(3)` ISO-4217 | INV-13, FR-CUR-1. |
| Fechas | `DATE` | OQ-15: fecha del documento = YYYY-MM-DD. |
| Fechas/hora de eventos | `TIMESTAMPTZ` | OQ-15: eventos con hora. |
| Confidence | `NUMERIC(4,3)` (0..1) | INV-11. |
| Provenance | `JSONB` | INV-11: método, página, bbox, regla. |
| Snapshot de aceptación | `JSONB` | INV-14, FR-ACC-4. |
| Estado | `TEXT` + `CHECK` | Ciclos A/B/C/D. No enums nativos. |
| Fingerprint | `CHAR(64)` SHA-256 | INV-9, NFR-3. |
| Tasa impositiva | `NUMERIC(5,2)` | Porcentaje (p. e.g. 21.00). |

## Reglas duras de diseño

1. **PostgreSQL** para producción. SQLite solo para pruebas concretas
   aprobadas por Director+Architect.
2. **Dinero NUMERIC**: nunca `FLOAT`, `REAL`, `DOUBLE PRECISION`.
3. **UUIDv7** para PKs de recursos públicos.
4. **Estados como `TEXT`** con `CHECK` constraints (no enums nativos).
5. **FK explícitas** con `ON DELETE` declarado (`RESTRICT` para datos
   contables).
6. **Tenencia**: `owner_id` = `organization_id` (ADR-0008) en todas las
   tablas de negocio.
7. **Aislamiento FacturaE** (ADR-0001): BD propia, sin tablas compartidas.
8. **Append-only** para `audit_events` y `manual_corrections` (ADR-0012).
9. **Cadena E3→E4→E5** forzada por FK NOT NULL (INV-10).
10. **Idempotencia**: unique constraints como red de seguridad (NFR-4).

## Índice del diseño

| Archivo | Contenido |
|---|---|
| [01-schema-design.md](01-schema-design.md) | Esquema relacional completo: tablas, columnas, tipos, PKs, FKs, constraints, DDL ilustrativo. |
| [02-migration-strategy.md](02-migration-strategy.md) | Estrategia de migraciones Alembic: una migración por vertical slice, upgrade/downgrade, orden, naming. |
| [03-invariants-enforcement.md](03-invariants-enforcement.md) | Cómo INV-1..INV-15 se aplican a nivel de BD: constraints, triggers, NOT NULL FKs. |
| [04-work-queue-design.md](04-work-queue-design.md) | Tabla `extraction_jobs`, claim atómico, estados, reintentos con backoff, idempotencia. |
| [05-indexes-and-performance.md](05-indexes-and-performance.md) | Definiciones concretas de índices con justificación. |
| [06-tenancy-and-isolation.md](06-tenancy-and-isolation.md) | `owner_id` = `organization_id`, filtro en queries, RLS opcional, permisos. |
| [07-audit-and-retention.md](07-audit-and-retention.md) | `audit_events` append-only, permisos + trigger, sin purga en V1, retención configurable. |
| [08-v1-s1-data-design.md](08-v1-s1-data-design.md) | V1-S1: `source_documents`, fingerprint, estado `uploaded`, creación de job, DUP-1, idempotencia. |

## Decisiones resueltas en este diseño

| PQ (Phase 1) | Decisión | Justificación |
|---|---|---|
| PQ-1 (OQ-9) | **RESUELTA**: `owner_id` = `organization_id` (ADR-0008). | Ya resuelta en Phase 1. |
| PQ-2 (OQ-10) | **RESUELTA**: sin purga automática en V1 (D3). | Ya resuelta en Phase 1. |
| PQ-3 (OQ-15) | **RESUELTA**: `DATE` para fechas de documento, `TIMESTAMPTZ` para eventos. | Baseline Phase 1. |
| PQ-4 (OQ-6) | **RESUELTA**: pagos parciales soportados (1:N `payments`). | FR-PAY-3. |
| PQ-5 (OQ-17) | **RESUELTA**: categorías jerárquicas (`parent_id`). | E10 baseline. |
| PQ-6 (OQ-4) | **RESUELTA**: una moneda por gasto (INV-13); sin conversión en V1. | INV-13. |
| PQ-7 (OQ-13) | **RESUELTA**: anulación por rol `approver`/`admin`, motivo obligatorio. | FR-EXP-5. |
| PQ-8 | **RESUELTA**: sin particionamiento en V1 (volumen bajo). | NFR-6. |
| PQ-9 | **RESUELTA**: `accepted_snapshot` como JSONB. | INV-14, flexibilidad. |
| PQ-10 | **RESUELTA**: `provenance` como JSONB. | INV-11, flexibilidad. |
| PQ-11 | **RESUELTA**: `dup_key` como TEXT concatenado. | Simplicidad; detección en dominio. |
| PQ-12 (OQ-13) | **RESUELTA**: `users` + `sessions` en GastosE (ADR-0009). | Autenticación nativa. |

## Dependencias

- **Entrada**: baseline Phase 1 (`docs/persistence/`, `docs/requirements/`,
  `docs/adr/`, `docs/api/openapi.yaml`).
- **Salida**: este diseño es la entrada para el agente `backend` (implementar
  migraciones Alembic + ORM) y para el agente `qa` (tests de BD).
- **No bloquea**: no requiere infraestructura (PostgreSQL no está desplegado
  aún; eso es devops).
