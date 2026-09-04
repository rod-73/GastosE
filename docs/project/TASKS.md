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
| PHASE2-000 | Cierre de decisiones D2..D7 (pre-Phase 2) | director | ACCEPTED | - | 2026-09-01 | D2/D3: política configurable (OQ-1/OQ-10 actualizadas). D4: ADR-0009 (token opaco + sesión BD). D5: ADR-0010 (ExtractionLLM provider-neutral, local por defecto). D6: ADR-0011 (sandbox contenedor + cgroup + network egress restringido). D7: ADR-0012 (append-only BD, hash-chain no es requisito V1). Consistencia transversal verificada. Commit pendiente de aprobación explícita |
| M1.2-001 | Endurecer infraestructura multiagente (delegación exclusiva del Director, steps=25, fail-fast, handoff, concurrencia máx. 2) | director | ACCEPTED | main | 2026-09-03 | ADR-0013. Cambios: opencode.json (agent.*.steps=25 + task: deny en 10 especialistas), .opencode/agent/*.md (frontmatter steps/task:deny + secciones fail-fast y handoff en 10 agentes), director.md (salvaguardas M1.2 + concurrencia 2 + domain no disponible), AGENTS.md, STATE/TASKS/DECISIONS. Validado: JSON válido, subagent_depth=1, especialistas sin delegación, steps efectivo, git diff --check limpio. Commit M1.2 creado (sin push). **M1.2 = baseline operativo vigente** |
| M1.3-001 | Circuit breaker determinista de tool-loops (experimento) | director | DESCARTADO | main | 2026-09-04 | **Experimento NO OPERATIVO, descartado para uso.** Commit 22bf730. Los tests internos pasaban, pero la validación end-to-end real con Shell FALLÓ (#1/#2/#3 EXECUTED): el hook permission.ask no intercepta la ejecución de Shell en runtime => NO proporciona protección runtime efectiva. Desactivado en opencode.json (no registrado en el array plugin); código conservado como historial. Causa: limitación de la API de hooks de OpenCode. No se continuará su investigación ni desarrollo. Riesgo residual: un agente puede entrar en loop hasta steps=25 (mitigado por M1.2) |
| M1.3-002 | Cierre de investigación de runtime multiagente: consolidar M1.2 como baseline y registrar M1.3 como no operativo | director | ACCEPTED | main | 2026-09-04 | Cambios: opencode.json (plugin circuit-breaker desactivado), comentarios de estado en circuit-breaker.js y tools.js, STATE/TASKS/DECISIONS/ADR-0013 actualizados. Validado: opencode.json JSON válido, M1.2 sigue efectiva (subagent_depth=1, task: deny, steps=25), M1.3 no se presenta como protección operativa, docs/design/ intacto, git diff --check limpio. docs/design/ NO incluido en el commit (trabajo de Phase 2 pendiente de continuar) |
| PHASE2-001 | Diseño detallado Phase 2: persistencia, seguridad, testing, API | director | ACCEPTED | main | 2026-09-04 | 18 archivos en docs/design/ (~4600 líneas). Áreas: persistence/ (8), security/ (7), testing/ (1), api/ (2). Revisiones aplicadas: 5 findings corregidos (3 MEDIUM, 1 MEDIUM, 1 LOW). Permisos de agentes actualizados (.opencode/agent/*.md) para permitir escritura en docs/design/** |
| V1S1-001 | Implementar V1-S1: ingesta de documentos (upload, auth, tenancy, fingerprint, duplicate detection, idempotency) | director | ACCEPTED | main | 2026-09-04 | Backend FastAPI + SQLAlchemy + Alembic. Migraciones 0001+0002. Security invariants verificados. Quality gate superado. Decisiones: SQLAlchemy sync, engine lazy, filesystem storage, magic bytes, SHA-256, bcrypt directo, settings sin cache |
| V1S2-001 | Implementar V1-S2: consultar estado, verify-fingerprint, descarga de contenido | director | ACCEPTED | main | 2026-09-04 | 2 endpoints nuevos: POST /documents/{id}/verify-fingerprint (NFR-3), GET /documents/{id}/content (descarga binaria con ETag). 47 tests passing. Aislamiento por org verificado. Quality gate superado |
| V2S1-001 | Implementar V2-S1: worker de extracción (claim, cascada determinística, validación schema, persistencia E2/E3, retry, lease) | director | ACCEPTED | main | 2026-09-04 | 3 endpoints worker: POST /worker/claim, POST /worker/process, POST /worker/reap. Migración 0003 (extractions + extracted_values). Cascada XML/PDF text (OCR/LLM stubs). Validación schema estricto (VR-SCHEMA-1). Confidence + provenance (INV-11). Retry con backoff. Lease reaping. Idempotencia. 77 tests passing. Quality gate superado |

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
- 2026-09-01 — director: PHASE2-000 (cierre D2..D7) -> ACCEPTED. Decisiones
  D2..D7 resueltas: D2 (OQ-1) y D3 (OQ-10) por política configurable
  (actualizadas en docs/requirements/10-open-questions.md); D4 por ADR-0009
  (token opaco + sesión server-side en BD, revocación por usuario y
  organización); D5 por ADR-0010 (abstracción ExtractionLLM provider-neutral,
  backend por defecto local); D6 por ADR-0011 (worker en contenedor con
  límites cgroup, no-root, seccomp, network egress restringido); D7 por
  ADR-0012 (append-only BD con permisos + trigger, hash-chain no es requisito
  de V1). Actualizados: DECISIONS.md (ADR-0009..0012), CONTRACTS.md
  (ExtractionLLM, sesiones), STATE.md (D2..D7 resueltas), TASKS.md.
   Consistencia transversal verificada. Sin código de aplicación. Phase 2 no
   iniciada. Commit pendiente de aprobación explícita del usuario.
- 2026-09-03 — director: M1.2-001 (endurecimiento del runtime multiagente)
  -> ACCEPTED. ADR-0013 registrado. Salvaguardas aplicadas: (1) delegación
  exclusiva del Director: subagent_depth=1 + task: deny en los 10
  especialistas (frontmatter + opencode.json); (2) límite duro de pasos
  steps: 25 por especialista (mecanismo nativo; valor documentado en
  ADR-0013); (3) política fail-fast común (prompts de los 10 especialistas +
  director); (4) handoff estructurado (STATUS/ENTREGABLES/VALIDACION/
  RIESGOS/AL_DIRECTOR); (5) concurrencia máxima 2 especialistas (política
  del director); (6) domain NO DISPONIBLE temporalmente (no invocarlo).
   Validación: opencode.json JSON válido, subagent_depth=1, especialistas sin
   delegación, steps efectivo, git diff --check limpio. Commit M1.2 creado
   (sin push). Phase 2 NO reanudada.
- 2026-09-04 — director: M1.3-001 (circuit breaker de tool-loops) ->
   DESCARTADO. Experimento NO OPERATIVO: la validación end-to-end real con
   Shell FALLÓ (3 ejecuciones consecutivas idénticas no interceptadas:
   #1/#2/#3 EXECUTED); el hook permission.ask no intercepta la ejecución de
   Shell en runtime, por lo que el breaker no proporciona protección
   runtime efectiva. Desactivado en opencode.json (no registrado en el
   array plugin); código conservado como historial (commit 22bf730). No se
   continuará su investigación ni desarrollo. Riesgo residual documentado:
   un agente puede entrar en loop hasta steps=25 (mitigado por M1.2).
- 2026-09-04 — director: M1.3-002 (cierre de investigación de runtime) ->
   ACCEPTED. M1.2 consolidado como baseline operativo vigente (ADR-0013
   actualizado). M1.3 registrado como experimento no operativo / descartado
   para uso. docs/design/ (trabajo previo de Phase 2) preservado intacto y
   NO incluido en el commit de cierre. GastosE preparado para reanudar
   Phase 2 (pendiente de instrucción del usuario).
- 2026-09-04 — director: PHASE2-001 (diseño detallado Phase 2) -> ACCEPTED.
   Diseño completado en docs/design/ (18 archivos, ~4600 líneas). Áreas:
   persistence/ (8 archivos: esquema, migraciones, invariantes, cola de
   trabajo, índices, tenencia, auditoría, V1-S1), security/ (7 archivos:
   autenticación, autorización, uploads, sandbox, auditoría, secrets),
   testing/ (1 archivo: estrategia), api/ (2 archivos: implementación).
   Revisiones aplicadas: 5 findings corregidos (SIGALRM -> cgroup timeout,
   network_mode none -> red dedicada con firewall, audit-events reader ->
   approver, propagación de rol G14, rate limiting nota). Permisos de
   agentes actualizados (.opencode/agent/*.md). Checkpoint commit pendiente.
