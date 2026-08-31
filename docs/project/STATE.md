# STATE — GastosE

- **Phase**: 0 — Agentic Development Environment
- **Milestone**: M0 — Multi-agent governance bootstrap
- **Updated**: 2026-08-31 (por director, al completar bootstrap)

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

- Sin código de aplicación (Phase 0): no backend, no frontend, no workers,
  no schema productivo, sin OCR/LLM, sin stack productivo.
- Runtime del servidor: podman 5.8.2 (docker CLI lo emula). Python 3.9
  (pytest, alembic, PyYAML, jsonschema disponibles). Sin Node.js.

## Blockers

- Ninguno.

## Next gate

- Aceptación del usuario de Phase 0 (M0).
- Tras la aceptación: PHASE 1 — Requirements and Domain Discovery
  (DOMAIN -> requirements baseline -> domain model -> ARCHITECT ->
  architecture baseline + persistence conceptual + API contracts + ADRs ->
  DIRECTOR -> vertical-slice backlog).
