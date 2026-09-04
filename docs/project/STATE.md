# STATE — GastosE

- **Phase**: 2 — Implementation (V1-S1 + V1-S2 + V2-S1 + V2-S2 + V3-S1 completadas; V3-S2 pendiente)
- **Milestone**: M1.2 — Baseline operativo vigente del runtime multiagente (ADR-0013). M1.3 (circuit breaker) = experimento NO OPERATIVO, descartado para uso (2026-09-04)
- **Updated**: 2026-09-04 (por director: V3-S1 implementada. Normalización determinística (currency, amount, date, NIF/CIF, VAT). 138 tests passing. Quality gate superado.)

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

- **V1-S1 + V1-S2 + V2-S1 IMPLEMENTADAS** (2026-09-04, por director):
   - `backend/`: FastAPI app con auth (login/logout), documents (upload/get/
     verify-fingerprint/content), worker (claim/process/reap), middleware de
     autenticación (Bearer token opaco), exception handlers (RFC 7807),
     services (auth, document, extraction), models (ORM SQLAlchemy),
     schemas (Pydantic), config (pydantic-settings), utils (uuid7 fallback).
   - `alembic/`: 3 migraciones (0001 foundation, 0002 V1-S1 document
     ingestion, 0003 V2-S1 extraction). Chain: base -> 0001 -> 0002 -> 0003 (head).
   - `tests/`: 77 tests passing (health, auth, documents, models, security,
     extraction). 2 skipped (PostgreSQL CHECK constraints no aplicables en SQLite).
   - `requirements.txt`: fastapi, uvicorn, sqlalchemy, alembic, bcrypt,
     pydantic-settings, python-multipart.
   - V1-S2 endpoints:
     - `POST /api/v1/documents/{id}/verify-fingerprint`: verifica integridad
       (NFR-3). Re-lee el archivo, calcula SHA-256, compara con BD.
     - `GET /api/v1/documents/{id}/content`: descarga binaria con
       Content-Disposition, ETag (fingerprint), Content-Type por formato.
   - V2-S1 endpoints:
     - `POST /api/v1/worker/claim`: claim atómico de job pendiente (FIFO,
       scoped por org). 404 si no hay jobs pendientes.
     - `POST /api/v1/worker/process?job_id={id}`: procesa un job claimado
       (extracción + validación schema + persistencia E2/E3). 409 si el job
       no está en 'running' o no pertenece al worker.
     - `POST /api/v1/worker/reap`: reap de jobs con lease expirado.
   - V2-S1 extracción:
     - Cascada determinística: XML (xml_schema) -> PDF text (pdf_text_rules)
       -> OCR (stub) -> LLM (stub).
     - Validación schema estricto (VR-SCHEMA-1): campos requeridos,
       confidence [0,1], provenance con method.
     - Persistencia: Extraction (E2) + ExtractedValue (E3) con confidence
       NUMERIC(4,3) + provenance JSON (INV-11).
     - Retry con backoff exponencial (1min, 5min, 30min).
     - Lease expiry + reaping (5min lease).
     - Idempotencia: si existe extracción completed, se reutiliza.
   - Decisiones de implementación:
     - SQLAlchemy síncrono (sin driver async disponible).
     - Engine lazy (`get_engine()`, `get_session_local()`) para evitar
       import-time failures sin DB.
     - Filesystem storage para documentos (immutable, ADR-0006).
     - Magic bytes validation para detección de formato.
     - SHA-256 fingerprinting para integridad y detección de duplicados.
     - Token opaco (SHA-256 hash en BD, ADR-0009).
     - bcrypt directo (passlib incompatible con bcrypt 5.0).
     - Settings sin cache (re-reads env vars; overhead negligible en prod).
     - StreamingResponse para descarga (chunked, 64KB).
     - JSON (no JSONB) en modelos ORM para compatibilidad SQLite/PostgreSQL.
     - OCR/LLM como stubs (fallo controlado, no bloquean la cascada).
- Modelo de persistencia conceptual completado en `docs/persistence/`
  (PHASE1-003, agente database): 7 archivos (README + 6 secciones).
- Threat review temprano completado (PHASE1-004, agente security, read-only):
  informe con 10 amenazas (T1..T10), 22 gaps (G1..G22) y 8 decisiones
  (D1..D8). Todas resueltas.
- **Diseño Phase 2 completado en `docs/design/`** (por director, 2026-09-04):
  18 archivos (~4600 líneas) en 4 áreas. Revisiones aplicadas.
- Runtime del servidor: podman 5.8.2 (docker CLI lo emula). Python 3.9
  (pytest, alembic, PyYAML, jsonschema disponibles). Sin Node.js.
  Sin PostgreSQL driver (psycopg2) en runtime; tests usan SQLite in-memory.

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
- **M1.3 = experimento NO OPERATIVO / descartado para uso** (2026-09-04).
- **V1-S1 COMPLETADA** (2026-09-04): implementación, tests, migraciones,
  security invariants verificados. Quality gate superado.
- **V1-S2 COMPLETADA** (2026-09-04): verify-fingerprint + content download.
  47 tests passing. Quality gate superado.
- **V2-S1 COMPLETADA** (2026-09-04): worker de extracción (claim, process,
  reap). Cascada determinística XML/PDF text. Validación schema estricto.
  Persistencia E2+E3. Retry con backoff. Lease reaping. 77 tests passing.
  Quality gate superado.
- **V2-S2 COMPLETADA** (2026-09-04): retry de extracción
  (POST /documents/{id}/extractions/retry), listado
  (GET /documents/{id}/extractions), detalle
  (GET /extractions/{id}). 90 tests passing. Quality gate superado.
- **V3-S1 COMPLETADA** (2026-09-04): normalización determinística
  (POST /extractions/{id}/normalize, GET /extractions/{id}/normalized-values).
  Migración 0004 (normalized_values E4). Normalización: currency (ISO-4217),
  amount (decimal exacto), date (ISO-8601), NIF/CIF (check digit), VAT rate
  (0/4/10/21). Provenance INV-10. Idempotencia. Aislamiento por org.
  138 tests passing. Quality gate superado.
- **Próximo paso**: V3-S2 (validación determinística VR rules).
- Phase 1 COMPLETADA (M1 cerrado).
- Phase 2 en curso: V1-S1 + V1-S2 + V2-S1 + V2-S2 + V3-S1 ACCEPTED.
