# ADR-0004: Monolito modular con workers de extracción separados

Status: proposed
Date: 2026-08-31

## Context

GastosE necesita una arquitectura de despliegue. El dominio tiene una parte
síncrona e interactiva (API: subida, revisión, aceptación, catálogos) y una
parte asíncrona y costosa (extracción de documentos: XML/PDF/OCR/LLM, hasta
60 s por documento, NFR-6). El runtime disponible es podman 5.8.2 + Python
3.9, sin Node.js. El volumen de Phase 2 es bajo (~1.000 documentos/mes,
NFR-6). La regla dura ADR-0001 exige aislamiento total de FacturaE (sin
compartir código, DB ni almacenamiento).

Hay que decidir la granularidad de los componentes: ¿un solo monolito, un
monolito con workers separados, o microservicios?

## Decision

GastosE se implementa como **monolito modular** (API + dominio + servicios de
aplicación + persistencia en un solo despliegue) con **workers de extracción
separados** (proceso independiente que consume una cola y ejecuta la cascada
determinística). No se usan microservicios.

- Un único esquema de base de datos PostgreSQL (propio, ADR-0001) compartido
  por la API y el worker.
- Un único document store (volumen) compartido por la API y el worker
  (ADR-0006).
- Los sub-contextos (Document Ingestion, Extraction, Expense Core, Supplier,
  Review & Acceptance) son **módulos** dentro del monolito con límites de
  código claros (docs/architecture/01-bounded-contexts.md), no servicios
  independientes.
- El worker es el único proceso que ejecuta parsers/OCR/LLM (aísla la
  superficie de ataque de documentos no fiables).

## Alternatives considered

1. **Monolito puro (sin worker separado)**: la extracción se ejecutaría en el
   proceso de la API. Rechazado: las operaciones de extracción son largas
   (hasta 60 s) y consumen CPU (OCR); ejecutarlas en la API degradaría la
   latencia de las operaciones interactivas (NFR-6) y acoplaría la superficie
   de ataque de parsers maliciosos al proceso de la API.
2. **Microservicios** (un servicio por sub-contexto): rechazado para Phase
   1/2. El volumen es bajo; los microservicios añaden complejidad operativa
   (redes, despliegues, transacciones distribuidas, versionado de contratos
   entre servicios) sin beneficio a este escala. La regla de transaccionalidad
   (una unidad de trabajo = una operación de negocio) se complica con
   servicios distribuidos. Se revisará si el volumen o el equipo lo exigen.
3. **Monolito modular con worker separado (elegido)**: equilibrio. La parte
   interactiva escala de forma stateless; la parte costosa se aísla en un
   proceso escalable; se mantiene un solo esquema y un solo document store
   (transacciones acotadas, sin transacciones distribuidas).

## Consequences

- **Positivas**:
  - Transacciones acotadas (una operación de negocio = una transacción) sin
    complejidad distribuida.
  - Aislamiento de la superficie de ataque de parsers (worker).
  - Escalado independiente de API (stateless) y worker (N réplicas).
  - Simplicidad operativa: pocos componentes, un esquema, un volumen.
  - Cumple ADR-0001 (esquema y almacenamiento propios).
- **Negativas / riesgos**:
  - El monolito de API crece; se mitiga con límites de módulo (sub-contextos)
    y dirección de dependencias acíclica (docs/architecture/02-components.md).
  - El worker y la API comparten esquema: un cambio de esquema afecta a ambos
    (se gestiona con migraciones versionadas, PHASE1-003).
- **Reversibilidad**: migrar de monolito modular a microservicios es posible
  pero costoso (repartir esquema, introducir transacciones distribuidas). La
  decisión de worker separado es de baja reversibilidad (aísla un proceso);
  se justifica por el aislamiento de parsers y la latencia.
