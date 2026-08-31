# ADR-0007: Sin eventos internos en Phase 1/2 (acoplamiento directo por servicios de aplicación)

Status: proposed
Date: 2026-08-31

## Context

La skill `architecture` establece: "Eventos internos: solo si un ADR lo
justifica; schema versionado". Hay que decidir si GastosE introduce un
mecanismo de eventos internos (p. e.g. un bus de eventos dentro del sistema)
para desacoplar los sub-contextos, o si se mantiene el acoplamiento directo.

Los sub-contextos (Document Ingestion, Extraction, Expense Core, Supplier,
Review & Acceptance) comparten la misma base de datos (ADR-0004) y se
comunican a través de servicios de aplicación y de la cola de trabajo
(ADR-0005). La comunicación actual es:

- API → servicios de aplicación → dominio → persistencia (síncrono).
- API → cola → worker (asíncrono, ADR-0005).
- Worker → persistencia (valores extraídos, estados).

No hay un bus de eventos interno.

## Decision

GastosE **no introduce eventos internos** en Phase 1/2. El acoplamiento entre
sub-contextos es **directo** (servicios de aplicación + cola de trabajo). Los
eventos internos se introducirán solo si un ADR futuro lo justifica (p. e.g.
necesidad de auditoría distribuida, integración con otros sistemas, o
desacoplamiento por crecimiento del sistema).

- La **auditoría** (E16, NFR-1) es un registro append-only en la base de
  datos, no un bus de eventos: los sub-contextos escriben eventos de auditoría
  directamente en la tabla de auditoría dentro de su transacción.
- La **cola de trabajo** (ADR-0005) es el único mecanismo asíncrono interno;
  no es un bus de eventos genérico, sino una cola de tareas de extracción.
- Si en el futuro se aprueba una integración con FacturaE o con contabilidad
  general, se usará un **contrato de eventos versionado** (externo), no un bus
  interno.

## Alternatives considered

1. **Bus de eventos interno** (p. e.g. tabla de eventos + consumidores, o un
   broker): ofrece desacoplamiento temporal y auditoría distribuida. Rechazado
   para Phase 1/2: los sub-contextos comparten base de datos y el acoplamiento
   directo es suficiente; un bus interno añade complejidad (orden de eventos,
   reintentos, idempotencia de consumidores) sin beneficio claro a este escala.
2. **Acoplamiento directo (elegido)**: los sub-contextos se comunican por
   servicios de aplicación (síncrono) y por la cola de trabajo (asíncrono). La
   auditoría es append-only en la BD. Simplicidad: sin mecanismo extra.

## Consequences

- **Positivas**:
  - Simplicidad: sin mecanismo de eventos que gestionar.
  - Transaccionalidad: la auditoría se escribe en la misma transacción que la
    operación (consistencia).
  - Menos componentes y menos superficie de fallo.
- **Negativas / riesgos**:
  - Acoplamiento más fuerte entre sub-contextos (comparten BD y servicios).
  - Si el sistema crece o se necesita auditoría distribuida, habrá que
    introducir eventos (cambio de diseño).
- **Reversibilidad**: introducir eventos internos en el futuro es un cambio de
  diseño incremental (los contratos de sub-contexto ya están versionados); no
  es irreversible, pero requiere un ADR nuevo.
