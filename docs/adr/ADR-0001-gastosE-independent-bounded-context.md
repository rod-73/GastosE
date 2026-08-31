# ADR-0001: GastosE es un bounded context independiente de FacturaE

Status: accepted
Date: 2026-08-31

## Context

Existe un sistema estable de facturación, FacturaE (`/workspace/facturaE`),
junto con backups históricos (`facturaE.orig`, `facturaE.despuesdeBorrado`,
`facturaE-before-cleanup-20260831.bundle`). GastosE es un nuevo proyecto para
la gestión automatizada de gastos, facturas recibidas, tickets y documentos
asociados. Ambos sistemas comparten vocabulario (proveedores, impuestos,
documentos) pero tienen propósitos, ciclos de vida y equipos de desarrollo
distintos. Acoplarlos desde el diseño (código, ORM, base de datos,
migraciones, almacenamiento) impediría evolucionar GastosE de forma
independiente y pondría en riesgo la estabilidad de FacturaE.

## Decision

GastosE se construye DESDE CERO como un bounded context independiente:

- Propia base de datos (PostgreSQL), propias tablas, propias migraciones
  (Alembic), propio almacenamiento de documentos, propias credenciales.
- Prohibido: copiar código de FacturaE, importar sus módulos, usar sus
  modelos ORM, acceder a su base de datos, compartir tablas/migraciones o
  almacenamiento, o crear dependencias internas (Python/JS) entre ambos.
- `/workspace/facturaE` y sus backups son SOLO LECTURA; nunca se modifican.
- Cualquier integración futura se realizará exclusivamente mediante:
  (a) API explícitamente versionada, o (b) contrato de eventos
  explícitamente versionado. Dicha integración NO se implementa ahora y
  requerirá aprobación explícita (nuevo ADR + contrato registrado en
  `docs/project/CONTRACTS.md`).

## Alternatives considered

1. **Extender FacturaE con el módulo de gastos**: rechazado — acoplamiento
   fuerte, riesgo sobre un sistema estable, imposibilidad de evolucionar
   GastosE por separado.
2. **Compartir base de datos/esquema con límites lógicos**: rechazado —
   acoplamiento en el nivel más rígido (schema), migraciones cruzadas,
   riesgo de integridad mutua.
3. **Monolito con shared library**: rechazado — dependencia interna
   implícita, versiones acopladas.

## Consequences

- Duplicación controlada de conceptos (proveedores, impuestos) en cada
  contexto; se aceptan a cambio de independencia total.
- Eventual integración requiere diseño de contrato versionado (trabajo
  futuro, Phase 1+).
- La infraestructura (containers, volumes, credentials) debe ser
  independiente (skill `docker`).
- Regla de aislamiento verificable: cualquier cambio que toque
  `/workspace/facturaE*` es una violación de scope (scope-check).
