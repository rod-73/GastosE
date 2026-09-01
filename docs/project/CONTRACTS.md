# CONTRACTS — Registro de contratos (GastosE)

Contratos entre componentes de GastosE y con sistemas externos.
Fuente de verdad: `docs/api/` (spec OpenAPI en `docs/api/openapi.yaml`).

## Externos

| Contrato | Sistema | Versión | Estado | Notas |
|----------|---------|---------|--------|-------|
| (ninguno) | FacturaE | - | no aprobado | Integración futura SOLO vía API versionada o contrato de eventos versionado (ADR-0001). Pendiente de decisión explícita. |

## Internos

| Contrato | Proveedor | Consumidor | Versión | Estado |
|----------|-----------|------------|---------|--------|
| API pública GastosE (OpenAPI, `docs/api/openapi.yaml`) | GastosE (API) | Frontend / clientes | v1 | propuesto (PHASE1-002) |
| Cola de trabajo de extracción (tabla de trabajo + claim atómico, ADR-0005) | Document Ingestion (API) | Worker de extracción | v1 | propuesto (PHASE1-002) |
| Output de extracción (esquema estricto JSON, VR-SCHEMA-1; docs/architecture/03-flows.md §2) | Worker de extracción | Expense Core | v1 | propuesto (PHASE1-002) |
| Valores extraídos (E3: confidence + provenance, INV-11) | Worker de extracción | Expense Core | v1 | propuesto (PHASE1-002) |
| Documento fuente íntegro (fingerprint SHA-256 verificado) | Document store (C6) | Worker de extracción | v1 | propuesto (PHASE1-002) |
| Modelo de persistencia conceptual (tablas, relaciones, invariantes, cola de trabajo) | GastosE (persistencia) | Todos los sub-contextos | v1 | propuesto (PHASE1-003) |
| ExtractionLLM (abstracción provider-neutral: endpoint, model, auth, timeout, structured output, errores/reintentos, provenance; ADR-0010) | Worker de extracción | Servicio LLM (local o externo, compatible con OpenAI) | v1 | propuesto (D5, 2026-09-01) |
| Sesiones de autenticación (tabla `sessions`: token opaco, user_id, organization_id, role, expiración, revocación; ADR-0009) | GastosE (API) | Clientes / frontend | v1 | propuesto (D4, 2026-09-01) |

## Reglas

- Todo contrato se versiona desde el primer diseño.
- Breaking change => nueva versión + ADR si es significativo.
- El director registra aquí cada contrato nuevo o modificado.
