# Backlog de vertical slices — GastosE (PHASE1-006)

- **Tarea**: PHASE1-006 (estado: DESIGNING).
- **Autor**: director.
- **Fecha**: 2026-08-31.
- **Fase**: Phase 1 — solo documentación y diseño. Prohibido implementar
  código de aplicación.
- **Entrada consumida**: baseline funcional (`docs/requirements/`),
  arquitectura (`docs/architecture/`), contrato API (`docs/api/`), modelo de
  persistencia (`docs/persistence/`), threat review
  (`docs/security/threat-review.md`), ADR-0001..0007.

## Qué es una vertical slice

Una vertical slice es una unidad de trabajo que atraviesa TODAS las capas
(API → servicios de aplicación → dominio → persistencia → UI) para entregar
un incremento de valor funcional completo y testeable. No se trabaja por
capas (no "primero toda la persistencia, luego toda la API"). Cada slice:

- Es **independiente** (no depende de otros slices para ser funcional).
- Es **testeable** (tiene criterios de aceptación verificables).
- Es **pequeña** (1-3 días de trabajo estimado).
- Cubre un **flujo end-to-end** o una **operación de negocio** completa.

## Orden de slices (priorizado)

El orden sigue el flujo de valor N1→N2→N3→N4→N5 y las dependencias entre
sub-contextos. Los slices se agrupan en **verticales** (incrementos de valor
completos).

### Vertical 1 — Ingesta de documentos (N1)

| Slice | Descripción | Sub-contexto | Depende de | Criterios de aceptación |
|-------|-------------|--------------|------------|------------------------|
| V1-S1 | Subir documento (multipart) con validación de tamaño/formato (magic bytes), fingerprint SHA-256, nombre seguro (UUID), almacenamiento inmutable en filesystem, registro en BD (estado `uploaded`), creación de tarea de extracción en cola. Responde `202 Accepted` con `Location`. | Document Ingestion | - | FR-DOC-1..5, INV-9, NFR-6 (< 5 s para 20 MB). Detección de duplicado por fingerprint (DUP-1) crea duplicación `probable`. Idempotencia por `Idempotency-Key`. |
| V1-S2 | Consultar estado de documento (`GET /documents/{id}`) con estados del ciclo A. Verificación de fingerprint bajo demanda (`POST /documents/{id}/verify-fingerprint`). Descarga de documento (`GET /documents/{id}/content`). | Document Ingestion | V1-S1 | NFR-3 (verificación de integridad). Estados del ciclo A visibles. ETag para caché. |

### Vertical 2 — Extracción (N2)

| Slice | Descripción | Sub-contexto | Depende de | Criterios de aceptación |
|-------|-------------|--------------|------------|------------------------|
| V2-S1 | Worker de extracción: claim atómico de tarea (cola en BD, ADR-0005), lectura de documento por fingerprint (verificar integridad), selección de método por cascada determinística (XML → PDF texto → OCR → LLM), ejecución con timeouts/límites de memoria, validación del output contra esquema estricto (VR-SCHEMA-1), persistencia de valores extraídos (E3: confidence + provenance, INV-11), estado `completed`/`failed`. | Extraction | V1-S1 | FR-EXT-1..5, INV-11, NFR-4 (idempotencia). Output no conforme al esquema → `failed` sin valores parciales. Reintentos con backoff. |
| V2-S2 | Reintento de extracción (`POST /documents/{id}/extractions/retry`): nueva extracción si el fallo es recuperable (FR-FST-2). Listado y consulta de extracciones (`GET /documents/{id}/extractions`, `GET /extractions/{id}`). | Extraction | V2-S1 | FR-FST-1..2, NFR-4. Re-procesamiento idempotente (estado `reprocessed`). |

### Vertical 3 — Normalización y validación (N3, N4)

| Slice | Descripción | Sub-contexto | Depende de | Criterios de aceptación |
|-------|-------------|--------------|------------|------------------------|
| V3-S1 | Normalización determinística (N3): moneda ISO-4217 decimal exacto, fecha ISO-8601, NIF/CIF validado, tipo impositivo conocido. Creación de valores normalizados (E4) con referencia a E3 (INV-10). | Expense Core | V2-S1 | FR-NOR-1..3, INV-10, INV-12. Valor no normalizable → `uncertain`. |
| V3-S2 | Validación determinística (N4): reglas VR-xxx (aritméticas, esquema, normalización, referencias, negocio). Creación de valores validados (E5) con referencia a E4 (INV-10). Resultados `passed`/`failed`/`warning`/`corrected`. | Expense Core | V3-S1 | FR-VAL-1..4, INV-8, INV-10. Regla BLOCK falla → `validation_error`. Regla WARN → advertencia. |
| V3-S3 | Creación de gasto (E6) a partir de valores validados: líneas de gasto (E7), líneas fiscales (E8), totales e identidad aritmética (INV-1), moneda única (INV-13). Estado `draft`. | Expense Core | V3-S2 | FR-TOT-1..2, INV-1, INV-13. Gasto referencia documento fuente (INV-3). |

### Vertical 4 — Revisión y aceptación (N5)

| Slice | Descripción | Sub-contexto | Depende de | Criterios de aceptación |
|-------|-------------|--------------|------------|------------------------|
| V4-S1 | Vista de revisión (`GET /expenses/{id}/review`): pantalla por campo con valor extraído (N2), normalizado (N3), validado (N4), confidence, provenance, documento fuente para contraste. | Review & Acceptance | V3-S3 | FR-REV-1. Cinco niveles visibles. |
| V4-S2 | Decisiones de revisión (`POST /expenses/{id}/review/decisions`): confirmar/corregir/rechazar por campo. Corrección manual auditada (E14, INV-7). Revalidación determinística de campos afectados. | Review & Acceptance | V4-S1 | FR-REV-2, INV-7. Corrección auditada (antes/después). |
| V4-S3 | Aceptación (`POST /expenses/{id}/accept`): revalidación definitiva (VR-xxx), comprobación de invariantes (INV-5, INV-6, INV-8), transición a `accepted` (IRREV), snapshot inmutable (INV-14), auditoría. Transacción acotada. | Review & Acceptance | V4-S2 | FR-ACC-1..4, INV-5, INV-6, INV-8, INV-14. Regla BLOCK falla → 409. Duplicación `probable` → 409. |
| V4-S4 | Rechazo (`POST /expenses/{id}/reject`): terminal, motivo obligatorio. Anulación (`POST /expenses/{id}/void`): solo de gastos `accepted`, motivo obligatorio, registro de anulación. | Review & Acceptance | V4-S3 | FR-REJ-1..3, FR-EXP-5. Rechazo terminal. Anulación crea registro `voided`. |

### Vertical 5 — Duplicaciones

| Slice | Descripción | Sub-contexto | Depende de | Criterios de aceptación |
|-------|-------------|--------------|------------|------------------------|
| V5-S1 | Detección de duplicado por clave lógica (DUP-2/3) al completar extracción. Listado y consulta de duplicaciones (`GET /duplications`, `GET /duplications/{id}`). | Document Ingestion / Expense Core | V2-S1 | DUP-1..3. Duplicación `probable` bloquea aceptación (INV-6). |
| V5-S2 | Resolución de duplicado (`POST /duplications/{id}/resolve`): confirmar duplicado / confirmar no-duplicado, humana, auditada. | Review & Acceptance | V5-S1 | DUP-4..10. Resolución terminal (IRREV). Motivo obligatorio. |

### Vertical 6 — Catálogos y proveedores

| Slice | Descripción | Sub-contexto | Depende de | Criterios de aceptación |
|-------|-------------|--------------|------------|------------------------|
| V6-S1 | CRUD de proveedores (`/suppliers`): nombre legal, NIF/CIF validado (VR-NORM-3), dirección fiscal, estado `active`/`inactive`. Búsqueda por NIF/nombre. | Supplier | - | FR-SUP-1..5, INV-5. Con gastos aceptados no se elimina, solo `inactive`. |
| V6-S2 | CRUD de catálogos: categorías (`/categories`), métodos de pago (`/payment-methods`), tipos impositivos (`/tax-rates`), monedas (`/currencies`). | Expense Core | - | FR-CAT-1..4. Catálogos administrables (rol `admin`). |

### Vertical 7 — Auditoría

| Slice | Descripción | Sub-contexto | Depende de | Criterios de aceptación |
|-------|-------------|--------------|------------|------------------------|
| V7-S1 | Registro de auditoría append-only (E16): todo evento de dominio (subida, extracción, normalización, validación, revisión, aceptación, rechazo, anulación, resolución de duplicado) se registra con actor, timestamp, antes/después. Listado y consulta (`GET /audit-events`, `GET /audit-events/{id}`). | Transversal | V1-S1 | NFR-1, INV-10. Append-only (sin UPDATE/DELETE). |

### Vertical 8 — Autenticación y autorización

| Slice | Descripción | Sub-contexto | Depende de | Criterios de aceptación |
|-------|-------------|--------------|------------|------------------------|
| V8-S1 | Autenticación: login/logout, sesiones/tokens con expiración y revocación. Esquema `bearerAuth`. | Transversal | - | NFR-7. Autenticación obligatoria (salvo `/healthz`). |
| V8-S2 | Autorización por rol: `reader`, `reviewer`, `approver`, `admin`. Object-level authorization: filtro por `owner_id` en todas las queries (derivado de sesión). | Transversal | V8-S1 | NFR-7. Test de aislamiento: usuario A no ve recurso de B (404). |

## Dependencias entre verticales

```
V8 (Auth) ──────────────────────────────────────────────────┐
V1 (Ingesta) ──> V2 (Extracción) ──> V3 (Norm/Val) ──> V4 (Revisión/Aceptación)
                          │                    │                    │
                          └──> V5 (Duplicaciones) <─────────────────┘
V6 (Catálogos) ──> V3 (referencias a catálogos)
V7 (Auditoría) ──> todas las verticales (transversal)
```

## Reglas de implementación (Phase 2)

1. **Deterministic first**: la extracción usa cascada determinística; el LLM
   es último recurso. Nunca `LLM OUTPUT == ACCOUNTING FACT`.
2. **Cinco niveles de valor**: cada slice respeta la frontera N1→N2→N3→N4→N5.
   No se salta nivel.
3. **Idempotencia**: todas las operaciones de mutación son idempotentes
   (NFR-4).
4. **Transacciones acotadas**: una operación de negocio = una transacción.
5. **Aislamiento por organización**: todas las queries filtran por `owner_id`
   (= `organization_id`, ADR-0008; NFR-7).
6. **Dinero NUMERIC**: nunca float (INV-2).
7. **FacturaE isolation**: no compartir código, DB, almacenamiento (ADR-0001).

## Preguntas abiertas que afectan a los slices

- **OQ-9 (D1)**: modelo de tenancy — **RESUELTA (ADR-0008)**: organización
  multi-usuario. Afecta a V8-S2 (authZ: usuario→organización, roles) y a
  todas las queries de aislamiento (`owner_id` = `organization_id`).
- **OQ-1 (D2)**: umbral de confidence — afecta a V2-S1 (extracción) y V3-S2
  (validación).
- **OQ-10 (D3)**: retención — afecta a V7-S1 (auditoría) y V1-S1
  (documentos).

**Fin del backlog de vertical slices (PHASE1-006).**
