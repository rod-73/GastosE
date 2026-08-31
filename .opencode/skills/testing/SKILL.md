---
name: testing
description: Use when writing or reviewing GastosE tests: unit, integration, database, API, worker, extraction, frontend, E2E, regression, quality gates, deriving tests from requirements and contracts.
---

# Testing — GastosE

Estrategia de pruebas para GastosE.

## Capas

| Capa | Qué | Dónde |
|---|---|---|
| Unit | Lógica pura: validaciones, aritmética fiscal, normalización, reglas de duplicados. | `tests/unit/` |
| Integration | Servicios + persistencia (DB real o testcontainer). | `tests/integration/` |
| Database | Migraciones (upgrade/downgrade), constraints, integridad. | `tests/database/` |
| API | Endpoints: schemas, errores, idempotencia, estados HTTP. | `tests/api/` |
| Worker | Pipeline de extracción con fixtures de documentos. | `tests/workers/` |
| Extraction | Fixtures PDF/XML/OCR; outputs contra schema estricto; confidence. | `tests/extraction/` |
| Frontend | Componentes: estados del ciclo de vida, revisión, errores. | `tests/frontend/` |
| E2E | Flujos completos: subir -> extraer -> revisar -> aceptar. | `tests/e2e/` |
| Regression | Suite estable que corre en cada gate. | toda la suite |

## Derivar pruebas

1. De `docs/requirements/`: cada criterio de aceptación => al menos un test.
2. De `docs/api/` (OpenAPI): cada endpoint => happy path + errores +
   idempotencia.
3. De invariantes del dominio (skill `expense-domain`): cada invariante =>
   test que la viola y espera rechazo.
4. De ADRs: las consecuencias medibles => tests.

## Reglas

- Tests determinísticos: sin red, sin reloj real (freeze), sin aleatoriedad
  sin seed.
- Fixtures de documentos versionados en el repo (pequeños, representativos).
- Un test = una comportamiento; nombres `test_<comportamiento>_<caso>`.
- NO modificar código productivo para pasar tests (solo QA lo ejecuta; si
  falla, se reporta al Director).
- Coverage: umbral mínimo definido por Director (p. ej. 80% en dominio).

## Quality gates

- Gate de tarea: tests del scope pasan + lint.
- Gate de feature: suite completa (unit+integration+api+workers) + E2E del
  slice + security (si aplica) + review.
- Gate de merge: regression completa en `main`.

## Herramientas

- Backend/workers: `pytest` (tool `run-tests` scopes `backend`/`workers`).
- Frontend: runner del stack elegido (tool `run-tests` scope `frontend`).
- `migration-check` para grafo de migraciones; `openapi-check` para contrato.

## Checklist de suite

- [ ] ¿Cada criterio de aceptación tiene test?
- [ ] ¿Cada invariante tiene test de violación?
- [ ] ¿Errores de API cubiertos (400/404/409/422)?
- [ ] ¿Idempotencia probada?
- [ ] ¿Fixtures de extracción con schema estricto?
- [ ] ¿E2E del slice principal?
