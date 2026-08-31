# Arquitectura baseline — GastosE (PHASE1-002)

Arquitectura de referencia de GastosE: gestión automatizada de gastos,
facturas recibidas, tickets y documentos asociados.

- **Tarea**: PHASE1-002 (estado: DESIGNING; solo el director transita estados).
- **Autor**: subagente `architect`.
- **Fecha**: 2026-08-31.
- **Fase**: Phase 1 — solo documentación y diseño. Prohibido implementar
  código de aplicación, backend, frontend, workers, schema productivo, OCR/LLM.
- **Entrada consumida**: baseline funcional completo en `docs/requirements/`
  (terminología canónica, entidades E1..E19, FR-xxx, ciclos de vida,
  INV-1..15, VR/DUP, NFR-1..10, OQ-1..18). Este documento consume ese
  baseline; no lo redefine ni lo contradice.
- **Skills aplicadas**: `architecture`, `api-design`, `security` (checklists).

## Regla fundamental (heredada del baseline)

```
SOURCE DOCUMENT != EXTRACTED VALUES != NORMALIZED VALUES != VALIDATED VALUES != ACCEPTED EXPENSE
```

Nunca: `LLM OUTPUT == ACCOUNTING FACT`. La arquitectura hace imposible
saltar los cinco niveles de valor (ver
[05-failure-semantics.md](05-failure-semantics.md), sección 5).

## Índice

| Archivo | Contenido |
|---|---|
| [01-bounded-contexts.md](01-bounded-contexts.md) | Confines de los bounded contexts internos, context map, qué vive fuera (FacturaE, contabilidad general, conciliación bancaria). |
| [02-components.md](02-components.md) | Componentes principales, responsabilidades, límites de servicio y dirección de dependencias. |
| [03-flows.md](03-flows.md) | Flujos: ingesta de documentos, extracción (cascada determinística), revisión/aceptación; dónde ocurre normalización y validación. |
| [04-async-boundaries.md](04-async-boundaries.md) | Límites asíncronos: qué es asíncrono, mecanismo, justificación. |
| [05-failure-semantics.md](05-failure-semantics.md) | Semántica de fallos por componente, reintentos, idempotencia, imposibilidad de saltar niveles de valor. |
| [06-facturae-isolation.md](06-facturae-isolation.md) | Garantías arquitectónicas de ADR-0001 (aislamiento FacturaE). |
| [07-security-boundaries.md](07-security-boundaries.md) | AuthN/AuthZ, aislamiento por usuario, uploads, trust boundaries OCR/LLM, secrets, logs. |
| [08-performance-notes.md](08-performance-notes.md) | Notas de rendimiento orientativas (NFR-6). |

## Contratos

- Modelo de API/recursos: [`docs/api/README.md`](../api/README.md).
- Spec OpenAPI v1: [`docs/api/openapi.yaml`](../api/openapi.yaml).
- ADRs de esta tarea: ADR-0004..ADR-0007 en [`docs/adr/`](../adr/).

## Resumen ejecutivo

- **Monolito modular** (API + dominio) con **workers de extracción
  separados** (ADR-0004).
- Procesamiento asíncrono de extracción mediante **cola en base de datos +
  worker** (ADR-0005).
- Documentos fuente en **filesystem local en volumen dedicado, inmutable,
  identificado por fingerprint SHA-256** (ADR-0006).
- **Sin eventos internos** en Phase 1/2: acoplamiento directo por servicios
  de aplicación; los eventos se introducen solo si un ADR futuro lo justifica
  (ADR-0007).
- API versionada `/api/v1/`, errores RFC 7807, idempotencia por
  `Idempotency-Key` y por diseño de transiciones de estado.
- Aislamiento total de FacturaE (ADR-0001): sin dependencias, sin DB
  compartida, sin almacenamiento compartido.
