# STATE — GastosE

- **Phase**: 1 — Requirements and Domain Discovery (cierre M1; Phase 2 NO iniciada)
- **Milestone**: M1.2 — Baseline operativo vigente del runtime multiagente (ADR-0013). M1.3 (circuit breaker) = experimento NO OPERATIVO, descartado para uso (2026-09-04)
- **Updated**: 2026-09-04 (por director: cierre de investigación de runtime — M1.3 descartado, M1.2 consolidado como baseline; preparación para reanudar Phase 2)

## Current architecture

- OpenCode 1.18.20. Agente primario por defecto: `director`.
- 10 subagentes: domain, architect, database, backend, extraction, frontend,
  qa, security (read-only), reviewer (read-only), devops.
- 10 skills en `.opencode/skills/` (conocimiento bajo demanda).
- 6 custom tools vía plugin `.opencode/plugin/tools.js`: run-tests, lint,
  migration-check, openapi-check, docker-health, scope-check.
- Permisos least-privilege por agente (ver `.opencode/agent/*.md` y
  `opencode.json`).
- Salvaguardas de ejecución (M1.2, ADR-0013) — **baseline operativo
  vigente**: `subagent_depth=1` + `task: deny` en los 10 especialistas
  (solo el Director delega); `steps: 25` por especialista (límite duro
  nativo); política fail-fast y handoff estructurado
  (STATUS/ENTREGABLES/VALIDACION/RIESGOS/AL_DIRECTOR); máximo 2
  especialistas concurrentes; tareas acotadas.
- M1.3 (circuit breaker de tool-loops, commit 22bf730): **experimento NO
  OPERATIVO, descartado para uso** (2026-09-04). La validación end-to-end
  real con Shell FALLÓ (3 ejecuciones consecutivas idénticas no
  interceptadas): el hook `permission.ask` no intercepta la ejecución de
  Shell en runtime. No proporciona protección runtime efectiva. Desactivado
  en `opencode.json` (no registrado en el array `plugin`); el código se
  conserva como historial. No se continuará su investigación ni desarrollo.
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

- Ninguno para Phase 2. Todas las decisiones D1..D8 del threat review están
  resueltas (D1/D8 por ADR-0008; D2/D3 por política configurable; D4..D7 por
  ADR-0009..0012).

## Riesgos operativos pendientes

- **Riesgo residual de loops (post-M1.3, 2026-09-04)**: un agente puede
  entrar en loop hasta alcanzar `steps: 25` (límite duro nativo). Sin
  detección de loops por contenido en runtime (M1.3 descartado).
  Mitigaciones vigentes (M1.2, ADR-0013): `subagent_depth=1`,
  `task: deny` en especialistas, `steps=25`, máximo 2 especialistas
  concurrentes, tareas acotadas, fail-fast y handoffs estructurados.
- **Subagente `domain` NO DISPONIBLE temporalmente** (2026-09-01): el
  subagente `domain` produce respuestas vacías o degenerativas
  (repetitivas/incoherentes) al ejecutarse como child session en OpenCode.
  El fallo persiste incluso utilizando temporalmente la configuración
  completa de `architect.md`, lo que descarta la causa en las instrucciones
  de `domain.md`. La causa raíz está asociada al agente/session/plumbing de
  OpenCode y todavía no está determinada.

  **Workaround operativo (no es una decisión arquitectónica permanente):**
  las responsabilidades de análisis de dominio (requisitos, invariantes,
  reglas, criterios de aceptación) serán asumidas temporalmente por
  `architect` y/o `director` hasta que el subagente `domain` se resuelva.
  No se cambia la arquitectura conceptual ni el ownership definitivo.
  No se modifica ningún contrato funcional de GastosE.

## Decisiones del threat review (PHASE1-004) — estado

| # | Decisión | Severidad | Estado |
|---|----------|-----------|--------|
| D1 | OQ-9: modelo de tenancy | HIGH | **RESUELTA (ADR-0008)**: organización multi-usuario |
| D2 | OQ-1: umbral de confidence | MEDIUM | **RESUELTA (2026-09-01)**: política configurable, no thresholds fijos; confidence ≠ aceptación automática; calibración con corpus en Phase 2 |
| D3 | OQ-10: retención de documentos y auditoría | MEDIUM | **RESUELTA (2026-09-01)**: sin purga automática en V1; políticas configurables por org/tipo/estado; sin plazos legales hardcoded |
| D4 | Mecanismo de autenticación y revocación | MEDIUM | **RESUELTA (ADR-0009)**: token opaco + sesión server-side en BD; revocación por usuario y organización |
| D5 | LLM externo vs local | MEDIUM | **RESUELTA (ADR-0010)**: abstracción `ExtractionLLM` provider-neutral; backend por defecto local (endpoint compatible con OpenAI) |
| D6 | Sandbox del worker | MEDIUM | **RESUELTA (ADR-0011)**: contenedor podman + límites cgroup + no-root + seccomp + network egress restringido |
| D7 | Inmutabilidad del registro de auditoría | LOW | **RESUELTA (ADR-0012)**: append-only BD (permisos + trigger); hash-chain no es requisito de V1 |
| D8 | Catálogos por tenant | LOW | **RESUELTA (ADR-0008)**: por organización |

## Condiciones de la revisión (PHASE1-005) — estado

| # | Condición | Estado |
|---|-----------|--------|
| C1 | Resolver OQ-9 (tenancy) antes de Phase 2 | HECHO (ADR-0008: organización multi-usuario) |
| C2 | Materializar threat review como artefacto versionado | HECHO (docs/security/threat-review.md) |
| C3 | Definir esquema estricto para accepted_snapshot | HECHO (ExpenseSnapshot en openapi.yaml) |
| C4 | Aclarar ciclo de vida A (estados derivados del gasto) | HECHO (docs/requirements/04-lifecycle.md) |
| C5 | Corregir enum ValidationOutcome (añadir failed/warning) | HECHO (openapi.yaml) |

## Next gate

- **M1.2 = baseline operativo vigente** (2026-09-03, ADR-0013).
- **M1.3 = experimento NO OPERATIVO / descartado para uso** (2026-09-04):
  el circuit breaker no intercepta realmente Shell en runtime (validación
  end-to-end real falló: #1 EXECUTED, #2 EXECUTED, #3 EXECUTED). No se
  continuará su investigación. Riesgo residual: loops hasta `steps: 25`
  (mitigado por las salvaguardas M1.2).
- **Preparado para reanudar Phase 2** (pendiente de instrucción del
  usuario): trabajo previo de Phase 2 en `docs/design/` preservado intacto.
  Phase 2 NO reanudada hasta nuevo aviso del usuario.
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
- Decisiones D2..D7 resueltas (2026-09-01): D2/D3 por política configurable
  (OQ-1/OQ-10 actualizadas); D4..D7 por ADR-0009..0012.
- Aceptación final de Phase 1 + cierre D2..D7 por el usuario: commit
  pendiente de aprobación explícita (sin push ni remotos).
- Tras la aprobación: arranque de Phase 2 (implementación por vertical
  slices, ver docs/project/VERTICAL-SLICES.md). Primer slice: V1-S1
  (ingesta de documentos).
