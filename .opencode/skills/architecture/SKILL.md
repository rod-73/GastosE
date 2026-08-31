---
name: architecture
description: Use when designing or reviewing GastosE architecture: bounded contexts, service boundaries, dependency direction, APIs, events, contracts, ADRs, failure semantics, vertical slices, or FacturaE/GastosE isolation.
---

# Architecture — GastosE

Patrones de arquitectura para GastosE.

## Bounded contexts

GastosE es UN bounded context independiente: "Gestión de gastos y documentos
recibidos". Contextos internos sugeridos (refinar en Phase 1):

- **Document Ingestion**: subida, validación de archivo, fingerprint,
  almacenamiento inmutable.
- **Extraction**: pipeline determinístico-first hacia valores extraídos.
- **Expense Core**: gastos, líneas, impuestos, validación, aceptación.
- **Supplier**: proveedores y datos fiscales.
- **Review & Acceptance**: revisión humana, correcciones, aceptación.

## Separación FacturaE / GastosE (no negociable)

```
FACTURAE (externo, solo lectura)
   |
   |   API / EVENT CONTRACT — únicamente si se aprueba en el futuro
   |
GASTOSE
```

- Prohibido: compartir código, modelos ORM, base de datos, tablas,
  migraciones, almacenamiento o directorios internos.
- Integración futura SOLO mediante: API explícitamente versionada
  (`/api/v1/...`) o contrato de eventos versionado (schema + versión).
- FacturaE vive en `/workspace/facturaE`: SOLO LECTURA, nunca modificar.

## Dirección de dependencias

- `frontend -> API -> application services -> domain -> persistence`.
- `workers (extraction) -> API interna / colas -> persistence`.
- El dominio NO depende de HTTP, DB ni UI.
- Los contratos (`docs/api/`) son la única fuente de verdad entre componentes.

## APIs y eventos

- API versionada desde el día 1 (`v1`); breaking changes => nueva versión.
- Operaciones largas (extracción) => operación asíncrona con estado
  consultable (ver skill `api-design`).
- Eventos internos: solo si un ADR lo justifica; schema versionado.

## Failure semantics

- Toda operación tiene estado de fallo explícito y recuperable.
- Extracción fallida => documento en `failed` con motivo; nunca datos parciales
  aceptados.
- Idempotencia en endpoints de mutación (ver skill `api-design`).
- Transacciones acotadas: una unidad de trabajo = una operación de negocio.

## ADRs

Formato obligatorio en `docs/adr/ADR-NNNN-titulo.md`:

```
# ADR-NNNN: Título
Status: proposed | accepted | deprecated | superseded by ADR-XXXX
Date: YYYY-MM-DD

## Context
## Decision
## Alternatives considered
## Consequences
```

Un ADR por decisión importante. No inventar decisiones técnicas sin análisis.

## Vertical slices

Desarrollar por slices end-to-end (UI -> API -> dominio -> DB), no por capas:

1. Proveedor mínimo end-to-end.
2. Subida segura de documento.
3. Extracción + almacenamiento.
4. Review/correction.
5. Clasificación.
6. Búsqueda/listados/dashboard.
7. Exportación/integración.

(Backlog conceptual; el Director define el backlog real tras Phase 1.)
