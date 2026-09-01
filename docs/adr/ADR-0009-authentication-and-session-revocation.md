# ADR-0009: Authentication and session revocation

Status: accepted
Date: 2026-09-01
Resuelve: D4 del threat review (docs/security/threat-review.md), G10/G11/G12.

## Context

El threat review (PHASE1-004) identificó que el mecanismo de autenticación
(JWT vs cookie opaca) no estaba decidido (G10, MEDIUM), ni la política de
revocación de tokens/sesiones (G11, LOW), ni la política de contraseñas (G12,
LOW). La tenancy por organización (ADR-0008) exige que la autorización sea
por organización (filtro por `owner_id` = `organization_id`) y que los roles
sean por organización (G14). El contrato OpenAPI ya define `bearerAuth` con
`bearerFormat: opaque`.

## Decision

GastosE usa **token opaco + sesión server-side persistida en BD**:

- **Token opaco**: el cliente recibe un token aleatorio (no JWT) que es un
  puntero a una fila de sesión en la base de datos. El token no contiene
  claims; toda la información (usuario, organización, rol, expiración) se
  consulta en la BD en cada petición.
- **Tabla `sessions`**: `id` (token), `user_id` (FK), `organization_id`
  (FK, derivado del usuario), `role` (rol del usuario en la organización),
  `expires_at` (expiración absoluta), `last_seen_at` (última actividad),
  `revoked_at` (timestamp de revocación, NULL si activa), `created_at`.
- **Expiración doble**:
  - Por inactividad: si no hay actividad en X minutos (default 30,
    configurable), la sesión se expira.
  - Absoluta: la sesión expira a las Y horas desde la creación (default 12 h,
    configurable).
  - Los valores son **defaults configurables** (NFR-9), no constantes
    arquitectónicas.
- **Revocación inmediata**:
  - Cierre de sesión: `revoked_at` se setea.
  - Cambio de contraseña: todas las sesiones del usuario se revocan.
  - Desactivación de usuario: todas las sesiones del usuario se revocan.
  - Desactivación de organización: todas las sesiones de la organización se
    revocan.
- **`organization_id` derivado de la sesión**: el `owner_id` de las queries
  se deriva de la sesión autenticada (nunca de un parámetro proporcionado por
  el cliente). El filtro por `owner_id` se aplica en la capa de persistencia
  (NFR-7, V8-S2).
- **Roles por organización**: el rol es un atributo del usuario en su
  organización (G14, ADR-0008). El rol se almacena en la sesión y se
  actualiza si cambia (la siguiente petición refleja el nuevo rol).
- **Política de contraseñas** (G12): hash con algoritmo adaptativo (argon2id
  o bcrypt), longitud mínima configurable. Recuperación de cuenta: fuera de
  scope de Phase 2 v1 (1 org + 1 usuario, ADR-0008).
- **Contrato OpenAPI**: `bearerAuth` se mantiene (`type: http`, `scheme:
  bearer`, `bearerFormat: opaque`). La descripción se actualiza para
  reflejar que el token es opaco y la sesión es server-side.

## Alternatives considered

1. **JWT sin estado** (HS256/RS256): el token contiene claims y no requiere
   consulta a BD. Rechazado: no permite revocación inmediata (crítico para
   datos financieros, NFR-7). Con tenancy por organización + roles por org
   (G14), el estado cambia a menudo (cambio de rol, desactivación de
   organización) y el JWT no puede reflejarlo hasta expirar.
2. **Cookie de sesión** (server-side session, cookie `HttpOnly`/`Secure`/
   `SameSite`): permite revocación inmediata. Rechazado: desvía el contrato
   `bearerAuth` existente (es cookie, no bearer). Sería válida si el Director
   prefiere UX web pura, pero requeriría versionar el contrato.
3. **Token opaco + sesión en BD (elegido)**: permite revocación inmediata,
   respeta `bearerAuth`, no añade componente nuevo (la BD ya existe,
   ADR-0004/0005), y el volumen bajo (~1.000 docs/mes) hace trivial la tabla
   de sesiones.

## Consequences

- **Positivas**:
  - Revocación inmediata (G11): cierre de sesión, cambio de contraseña,
    desactivación de usuario/organización.
  - Coherencia con tenancy por organización (ADR-0008): `organization_id`
    derivado de la sesión, roles por org (G14).
  - Contrato `bearerAuth` respetado (openapi.yaml).
  - Sin componente nuevo: la tabla `sessions` vive en la BD existente.
- **Negativas / riesgos**:
  - Cada petición requiere una consulta a BD para validar la sesión (coste
    trivial para el volumen de Phase 2).
  - La tabla `sessions` requiere limpieza periódica (sesiones expiradas).
- **Reversibilidad**: migrar de token opaco a JWT sin estado es posible pero
  **pierde la revocación inmediata** (regresión de seguridad). Migrar a cookie
  requiere versionar el contrato. La tabla `sessions` es fácil de eliminar si
  se cambia de mecanismo.

## Implicaciones

- **Slices**: V8-S1 (login/logout, sesiones, expiración/revocación), V8-S2
  (authZ por rol + filtro `owner_id`).
- **Contratos**: openapi.yaml (refinar descripción de `bearerAuth`).
  `docs/project/CONTRACTS.md`.
- **Persistencia**: nueva tabla `sessions` (conceptual, para el agente
  database).
- **Seguridad**: cierra G10, G11, G12 (parcial — G12: recuperación de cuenta
  fuera de scope v1).
