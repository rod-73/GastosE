# STATE — GastosE

- **Phase**: 1 — Requirements and Domain Discovery
- **Milestone**: M1 — Baseline funcional, de arquitectura, de persistencia
  conceptual, de API y de seguridad (sin implementación)
- **Updated**: 2026-08-31 (por director, al cerrar Phase 1 — PHASE1-006 ACCEPTED)

## Current architecture

- OpenCode 1.18.20. Agente primario por defecto: `director`.
- 10 subagentes: domain, architect, database, backend, extraction, frontend,
  qa, security (read-only), reviewer (read-only), devops.
- 10 skills en `.opencode/skills/` (conocimiento bajo demanda).
- 6 custom tools vía plugin `.opencode/plugin/tools.js`: run-tests, lint,
  migration-check, openapi-check, docker-health, scope-check.
- Permisos least-privilege por agente (ver `.opencode/agent/*.md` y
  `opencode.json`).
- Estado persistente: `docs/project/` (este archivo, TASKS, DECISIONS,
  CONTRACTS). ADRs en `docs/adr/`.

## Current implementation state

- Sin código de aplicación: no backend, no frontend, no workers,
  no schema productivo, sin OCR/LLM, sin stack productivo.
- Phase 1 es SOLO documentación: requisitos, arquitectura, modelo de
  persistencia conceptual, contratos de API, threat review, backlog de
  vertical slices. Prohibido introducir código de aplicación.
- Modelo de persistencia conceptual completado en `docs/persistence/`
  (PHASE1-003, agente database): 7 archivos (README + 6 secciones). Sin DDL,
  sin ORM, sin migraciones.
- Threat review temprano completado (PHASE1-004, agente security, read-only):
  informe con 10 amenazas (T1..T10), 22 gaps (G1..G22) y 8 decisiones
  (D1..D8). D1/OQ-9 (tenancy) resuelta por ADR-0008 (organización
  multi-usuario); pendientes D2..D8.
- Runtime del servidor: podman 5.8.2 (docker CLI lo emula). Python 3.9
  (pytest, alembic, PyYAML, jsonschema disponibles). Sin Node.js.

## Blockers

- Ninguno para Phase 1 (documentación). Para Phase 2, las decisiones D2..D8
  del threat review son pendientes (D1/OQ-9 tenancy resuelta por ADR-0008).

## Decisiones pendientes (del threat review PHASE1-004)

| # | Decisión | Severidad |
|---|----------|-----------|
| D1 | OQ-9: modelo de tenancy — **RESUELTA (ADR-0008)**: organización multi-usuario | HIGH → resuelta |
| D2 | OQ-1: umbral de confidence (y si varía por método) | MEDIUM |
| D3 | OQ-10: retención de documentos y auditoría | MEDIUM |
| D4 | Mecanismo de autenticación (JWT vs cookie) y política de revocación | MEDIUM |
| D5 | Si se usa LLM externo (API) o local | MEDIUM |
| D6 | Mecanismo de sandbox del worker (contenedor, límites) | MEDIUM |
| D7 | Mecanismo de inmutabilidad del registro de auditoría | LOW |
| D8 | Política de recursos compartidos (catálogos) por tenant — **RESUELTA (ADR-0008)**: por organización | LOW → resuelta |

## Condiciones de la revisión (PHASE1-005) — estado

| # | Condición | Estado |
|---|-----------|--------|
| C1 | Resolver OQ-9 (tenancy) antes de Phase 2 | HECHO (ADR-0008: organización multi-usuario) |
| C2 | Materializar threat review como artefacto versionado | HECHO (docs/security/threat-review.md) |
| C3 | Definir esquema estricto para accepted_snapshot | HECHO (ExpenseSnapshot en openapi.yaml) |
| C4 | Aclarar ciclo de vida A (estados derivados del gasto) | HECHO (docs/requirements/04-lifecycle.md) |
| C5 | Corregir enum ValidationOutcome (añadir failed/warning) | HECHO (openapi.yaml) |

## Next gate

- Phase 1 COMPLETADA (M1 cerrado). Orden de orquestación del director:
  1. DOMAIN -> baseline funcional (docs/requirements/). [ACCEPTED]
  2. ARCHITECT -> arquitectura + contratos API + ADRs (docs/architecture/,
     docs/api/, docs/adr/). [ACCEPTED]
  3. DATABASE (modelo conceptual) + SECURITY (threat review) en paralelo.
     [ACCEPTED]
  4. REVIEWER -> revisión independiente de la propuesta completa.
     [ACCEPTED — APROBADO CON CONDICIONES]
  5. DIRECTOR -> consolidación, backlog de vertical slices, quality gate.
     [ACCEPTED — PHASE1-006]
- Condiciones C1..C5 aplicadas (C1: ADR-0008, tenancy por organización).
- Aceptación final de Phase 1 por el usuario: commit pendiente de
  aprobación explícita (sin push ni remotos).
- Tras la aprobación: decisiones D2..D8 (D1/OQ-9 resuelta por ADR-0008) y
  arranque de Phase 2 (implementación por vertical slices, ver
  docs/project/VERTICAL-SLICES.md).
