# CONTRACTS — Registro de contratos (GastosE)

Contratos entre componentes de GastosE y con sistemas externos.
Fuente de verdad: `docs/api/` (aún vacío hasta Phase 1).

## Externos

| Contrato | Sistema | Versión | Estado | Notas |
|----------|---------|---------|--------|-------|
| (ninguno) | FacturaE | - | no aprobado | Integración futura SOLO vía API versionada o contrato de eventos versionado (ADR-0001). Pendiente de decisión explícita. |

## Internos

| Contrato | Proveedor | Consumidor | Versión | Estado |
|----------|-----------|------------|---------|--------|
| (ninguno definido) | - | - | - | Se definirán en Phase 1 (architecture baseline) |

## Reglas

- Todo contrato se versiona desde el primer diseño.
- Breaking change => nueva versión + ADR si es significativo.
- El director registra aquí cada contrato nuevo o modificado.
