# TASKS — GastosE

Estados: PROPOSED -> DESIGNING -> READY -> IMPLEMENTING -> TESTING -> REVIEW
-> ACCEPTED -> MERGED -> DONE (BLOCKED en cualquier punto).
Solo el director transita estados y declara ACCEPTED/MERGED/DONE.

| ID | Tarea | Agente | Estado | Rama | Actualizado | Notas |
|----|-------|--------|--------|------|-------------|-------|
| INFRA-001 | Bootstrap infraestructura multiagente (agentes, skills, tools, permisos, estado persistente, ADRs) | director | ACCEPTED | main | 2026-08-31 | Pendiente de validación final del usuario; commit pendiente de aprobación |
| PHASE1-001 | Requirements baseline del dominio de gastos (terminología, entidades, invariantes, ciclo de vida, reglas, duplicados, criterios de aceptación) | domain | ACCEPTED | - | 2026-08-31 | Baseline completo en docs/requirements/ (11 archivos); revisado y aceptado por el director |
| PHASE1-002 | Arquitectura baseline + contratos API + ADRs | architect | ACCEPTED | - | 2026-08-31 | Baseline completo en docs/architecture/ (9 archivos) + docs/api/ (openapi.yaml + README) + ADR-0004..0007; revisado y aceptado por el director (openapi-check OK, 36 paths) |
| PHASE1-003 | Modelo de persistencia CONCEPTUAL (sin ORM, sin migraciones) | database | ACCEPTED | - | 2026-08-31 | Baseline completo en docs/persistence/ (7 archivos); revisado y aceptado por el director (cadena E3->E4->E5, NUMERIC, aislamiento owner) |
| PHASE1-004 | Threat review temprano (uploads, parsers, OCR/LLM, auth, aislamiento, secrets, FacturaE) | security | ACCEPTED | - | 2026-08-31 | Read-only; threat review completado (informe del subagente); revisado y aceptado por el director; 8 decisiones D1..D8 pendientes (ver docs/project/STATE.md) |
| PHASE1-005 | Revisión independiente de la propuesta Phase 1 | reviewer | ACCEPTED | - | 2026-08-31 | Read-only; veredicto APROBADO CON CONDICIONES (5 condiciones C1..C5); revisado y aceptado por el director |
| PHASE1-006 | Consolidación Phase 1 + backlog de vertical slices + quality gate | director | ACCEPTED | - | 2026-08-31 | Consolidación completada: threat review materializado (C2), C3/C4/C5 aplicados, backlog de vertical slices en docs/project/VERTICAL-SLICES.md, quality gate superado. C1 (OQ-9) resuelta: ADR-0008 (organización multi-usuario). Commit pendiente de aprobación explícita |

## Historial

- 2026-08-31 — director: INFRA-001 creada (PROPOSED) -> IMPLEMENTING ->
  TESTING -> REVIEW -> ACCEPTED. Prueba real de orquestación DOMAIN+ARCHITECT
  superada. Commit final pendiente de aprobación del usuario.
- 2026-08-31 — director: Phase 1 iniciada. PHASE1-001 -> DESIGNING;
  creadas PHASE1-002..006 (PROPOSED).
- 2026-08-31 — domain: PHASE1-001 baseline funcional completado en
  docs/requirements/ (README + 10 archivos: terminología, entidades,
  requisitos funcionales, ciclo de vida, invariantes, validación,
  duplicados, semántica de valores, NFR, preguntas abiertas). Estado
  DESIGNING -> READY (pendiente de dirección del director).
- 2026-08-31 — director: PHASE1-001 revisado y -> ACCEPTED. PHASE1-002 ->
  DESIGNING (delegada a architect).
- 2026-08-31 — director: PHASE1-002 revisado y -> ACCEPTED. openapi-check
  OK (36 paths, 51 schemas, sin float para dinero). ADR-0004..0007
  registrados. PHASE1-003 y PHASE1-004 -> DESIGNING (delegadas a database y
  security en paralelo).
- 2026-08-31 — database: PHASE1-003 modelo de persistencia conceptual
  completado en docs/persistence/ (README + 6 archivos: entidades y tablas,
  relaciones, aplicación de invariantes, cola de trabajo, índices y
  rendimiento, aislamiento y tenencia, preguntas abiertas). Sin código de
  aplicación, sin ORM, sin migraciones. Estado DESIGNING -> READY (pendiente
  de dirección del director).
- 2026-08-31 — director: PHASE1-003 revisado y -> ACCEPTED (cadena E3->E4->E5
  forzada por FK NOT NULL, dinero NUMERIC, aislamiento por owner_id, contenido
  en filesystem no BD). PHASE1-004 (security) -> ACCEPTED: threat review
  completado (informe read-only); 8 decisiones D1..D8 pendientes para Phase 2
  (OQ-9 tenancy HIGH, OQ-1 confidence, OQ-10 retención, auth, LLM, sandbox,
  inmutabilidad auditoría, catálogos por tenant). PHASE1-005 -> DESIGNING
  (delegada a reviewer).
- 2026-08-31 — director: PHASE1-005 (reviewer) -> ACCEPTED. Veredicto:
  APROBADO CON CONDICIONES. 5 condiciones C1..C5: (C1) resolver OQ-9 tenancy
  antes de Phase 2 [bloqueante], (C2) materializar threat review como
  artefacto versionado, (C3) definir esquema estricto para accepted_snapshot,
  (C4) aclarar ciclo de vida A (estados derivados del gasto), (C5) corregir
  enum ValidationOutcome (añadir failed/warning). PHASE1-006 -> DESIGNING
  (consolidación: aplicar C2..C5, definir backlog de vertical slices).
- 2026-08-31 — director: PHASE1-006 -> ACCEPTED. Consolidación completada:
  (C2) threat review materializado en docs/security/threat-review.md; (C3)
  esquema ExpenseSnapshot añadido a openapi.yaml (accepted_snapshot lo
  referencia); (C4) ciclo de vida A aclarado en docs/requirements/04-lifecycle.md;
  (C5) enum ValidationOutcome corregido a [passed, failed, warning, corrected].
  Backlog de vertical slices definido en docs/project/VERTICAL-SLICES.md
  (8 verticales priorizadas). Quality gate de Phase 1 superado. C1 (OQ-9
  tenancy) resuelta por el usuario: ADR-0008 (organización multi-usuario,
  `owner_id` = `organization_id`); actualizados docs/requirements (OQ-9,
  NFR-7), docs/persistence (01, 06, 07) y DECISIONS.md. Commit de Phase 1
  pendiente de aprobación explícita del usuario.
