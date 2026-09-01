# ADR-0012: Append-only audit log

Status: accepted
Date: 2026-09-01
Resuelve: D7 del threat review (docs/security/threat-review.md), G20/G22.

## Context

El baseline de persistencia (docs/persistence/03-invariants.md) prescribe que
`audit_events` es append-only (sin `UPDATE`/`DELETE`). NFR-1 exige que todo
evento relevante quede registrado en un registro de auditoría inmutable con
trazabilidad completa (INV-10). El threat review (PHASE1-004) identificó que
el mecanismo de inmutabilidad no estaba prescrito (G20, LOW) y que el acceso
al registro debe ser restringido (G22, LOW).

## Decision

El registro de auditoría (`audit_events`, E16) es **append-only protegido a
nivel de persistencia**:

### Mecanismo base (V1)

- **INSERT permitido**: la aplicación inserta eventos de auditoría.
- **SELECT permitido según autorización**: las queries de consulta
  (`GET /audit-events`, `GET /audit-events/{id}`) están restringidas a roles
  autorizados (recomendado: `admin`/`approver`).
- **UPDATE prohibido**: no se permite modificar eventos de auditoría.
- **DELETE prohibido**: no se permite eliminar eventos de auditoría.

El mecanismo se aplica mediante **permisos de BD** (el usuario de aplicación
tiene solo `INSERT` y `SELECT` sobre `audit_events`; no tiene `UPDATE` ni
`DELETE`) y/o **mecanismos equivalentes** (trigger `BEFORE UPDATE OR DELETE`
que lanza una excepción, roles de BD, etc.). La implementación concreta la
define el agente `database` en Phase 2.

### Contenido de cada evento

Cada evento de auditoría debe permitir mantener trazabilidad suficiente de:

- **Actor**: usuario concreto (o sistema) que ejecutó la acción.
- **Organization**: organización a la que pertenece el actor (ADR-0008).
- **Timestamp**: fecha/hora de la acción (ISO-8601).
- **Acción**: tipo de acción (subida, extracción, normalización, validación,
  corrección manual, revisión, aceptación, rechazo, anulación, resolución de
  duplicado, cambio de configuración, etc.).
- **Entidad afectada**: tipo de entidad (documento, gasto, proveedor, etc.) e
  identificador.
- **Identificadores relevantes**: IDs de las entidades relacionadas
  (documento, extracción, valores, revisión, etc.).
- **Metadata/provenance necesaria**: datos antes/después cuando aplique
  (p. e.g. corrección manual: valor anterior y posterior, INV-7), motivo de
  la acción cuando aplique (p. e.g. rechazo, anulación).

### Hash-chain: NO es requisito de V1

- **No se implementa hash-chain como requisito obligatorio de V1**.
- Se documenta únicamente como **posible hardening futuro** para eventos de
  alto valor (aceptación, anulación, corrección manual) si resulta útil.
- La justificación: el mecanismo base (permisos + trigger) ya previene
  modificaciones/destrucción ordinaria. La hash-chain añade detección de
  alteración (no solo prevención) pero con complejidad adicional (verificación
  de la cadena, gestión de la raíz de confianza) que no es necesaria para V1.

### Retención

- **No hay eliminación automática de `audit_events` en V1** (D3, OQ-10
  resuelta).
- La retención de auditoría es indefinida en V1 (NFR-1, no repudio).
- Una futura política/job de purga (si se implementa) deberá respetar
  invariantes de trazabilidad, auditoría e integridad (INV-10, NFR-1).

### Acceso

- `GET /audit-events` y `GET /audit-events/{id}`: solo para roles
  `admin`/`approver` (recomendado). El acceso es solo lectura.
- El contrato OpenAPI ya define estos endpoints como solo lectura.

## Alternatives considered

1. **Hash chain como mecanismo base**: cada evento lleva el hash del evento
   anterior (cadena inmutable). Rechazado como mecanismo base: añade
   complejidad (verificación de la cadena, gestión de la raíz de confianza)
   que no es necesaria para V1. Se recomienda como hardening futuro para
   eventos de alto valor.
2. **WORM storage**: almacenamiento write-once-read-many. Rechazado: requiere
   infraestructura nueva (fuera de scope para Phase 2), no es nativo a la BD
   (ADR-0004), y el coste es desproporcionado para el volumen bajo.
3. **Append-only BD (permisos + trigger) (elegido)**: el baseline de
   persistencia ya prescribe append-only → D7 lo concreta sin añadir
   complejidad. El mecanismo es nativo a la BD (ADR-0004). El coste es muy
   bajo y el volumen es bajo (~1.000 docs/mes).

## Consequences

- **Positivas**:
  - Inmutabilidad garantizada a nivel de BD (permisos + trigger).
  - Trazabilidad completa (INV-10, NFR-1).
  - No repudio (NFR-7): la atribución por usuario no puede alterarse.
  - Sin componente nuevo: el mecanismo es nativo a la BD (ADR-0004).
  - Coste muy bajo.
- **Negativas / riesgos**:
  - No detecta alteraciones (solo previene). Si un administrador de BD
    modifica el registro directamente (bypass de permisos), no se detecta.
    Se mitiga con la hash-chain como hardening futuro.
  - El registro crece indefinidamente (sin purga en V1). Para el volumen de
    Phase 2 (~1.000 docs/mes), el crecimiento es manejable.
- **Reversibilidad**: **Alta**. Añadir/quitar la hash-chain no cambia el
  dominio ni la API. Los permisos y el trigger son fáciles de modificar.

## Implicaciones

- **Slices**: V7-S1 (registro de auditoría append-only).
- **Persistencia**: `audit_events` (conceptual, para el agente database):
  permisos, trigger, (opcional) columnas de hash-chain para hardening futuro.
- **Seguridad**: cierra G20, G22; condiciona G21 (la retención es D3/OQ-10).
- **Contratos**: openapi.yaml no cambia (`GET /audit-events` ya es solo
  lectura). `docs/project/CONTRACTS.md` (si se añade hash-chain en el futuro,
  se documenta el esquema).
