# ADR-0005: Cola en base de datos + worker para el procesamiento asíncrono de extracción

Status: proposed
Date: 2026-08-31

## Context

La extracción de documentos es asíncrona (docs/architecture/
04-async-boundaries.md): puede tardar hasta 60 s (NFR-6) y no debe bloquear la
petición de subida. Hay que elegir el mecanismo de cola/tareas que conecte la
API (que crea la tarea) con el worker (que la procesa).

Restricciones del runtime: podman 5.8.2 + Python 3.9 (pytest, alembic, PyYAML,
jsonschema disponibles), sin Node.js. PostgreSQL es la base de datos de
producción (regla dura). El volumen de Phase 2 es bajo (~1.000 documentos/mes).
Se valora la simplicidad operativa y el número de componentes nuevos.

## Decision

Se usa una **cola en base de datos** (tabla de trabajo en PostgreSQL) +
**worker** (proceso separado, ADR-0004). No se introduce un broker de mensajes
externo (RabbitMQ, Redis, Kafka) en Phase 1/2.

- Cada tarea de extracción es una fila en una tabla de trabajo (no se
  prescriben columnas; PHASE1-003). Referencia: documento fuente (fingerprint),
  formato detectado, estado (`pending`/`running`/`completed`/`failed`),
  intentos, motivo de fallo, timestamps.
- **Claim atómico**: el worker reclama tareas con una operación atómica
  (p. e.g. `UPDATE ... WHERE estado='pending' ... RETURNING`), de modo que dos
  workers no procesan la misma tarea.
- **Reintentos**: backoff exponencial con máximo de intentos (configurable,
  NFR-9); agotados → `failed` con motivo (FR-FST-1).
- **Idempotencia**: re-procesar el mismo documento no duplica valores
  (FR-EXT-5, NFR-4): reemplazo atómico de los valores de la extracción.
- La creación de la tarea y el registro del documento fuente pueden estar en
  la **misma transacción** (atomo "documento registrado + tarea en cola").

## Alternatives considered

1. **Broker de mensajes externo** (RabbitMQ/Redis/Kafka): ofrece mayor
   throughput y características (DLQ, priorización). Rechazado para Phase 1/2:
   añade un componente nuevo (y un nuevo sistema de fallo), complejidad
   operativa (despliegue, monitorización, credenciales) y una dependencia
   extra que el runtime no necesita para ~1.000 documentos/mes. Se revisará si
   el volumen o las necesidades (DLQ, priorización) lo exigen.
2. **Cola en memoria / tareas en proceso** (p. e.g. thread pool en la API):
   rechazado: no es duradero (se pierde al reiniciar), no escala a múltiples
   réplicas de worker, y acopla el procesamiento costoso al proceso de la API.
3. **Cola en base de datos + worker (elegido)**: sin componente nuevo;
   transaccional (la tarea y el documento se crean juntos); duradera; el claim
   atómico evita duplicación de trabajo; el volumen es bajo.

## Consequences

- **Positivas**:
  - Un solo sistema de persistencia (PostgreSQL) para datos y cola: menos
    componentes, menos credenciales, menos superficie de fallo.
  - Transaccionalidad: "documento registrado + tarea en cola" es atómico.
  - Durabilidad: las tareas no se pierden al reiniciar.
  - Escalado: N workers consumen la cola (claim atómico).
  - Simplicidad: no se introduce tecnología nueva.
- **Negativas / riesgos**:
  - La cola en BD puede ser un cuello de botella a muy alto volumen (no es el
    caso de Phase 1/2).
  - El claim atómico requiere cuidado en la implementación (lease/timeout para
    recuperar tareas de workers muertos).
- **Reversibilidad**: el contrato de cola (estado de tarea, claim, reintentos)
  es estable; migrar a un broker externo en el futuro no cambia el dominio ni
  la API, solo la capa de cola.
