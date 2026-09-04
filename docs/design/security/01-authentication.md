# 01 — Autenticación (GastosE Phase 2)

Diseño de implementación de la autenticación (ADR-0009). Cubre: token opaco,
sesiones server-side en BD, revocación, password hashing, rate limiting.

**Amenazas cubiertas**: T1 (autenticación), G1..G5.
**ADR**: ADR-0009 (token opaco + sesión server-side en BD).
**NFR**: NFR-7 (autenticación obligatoria, salvo `/healthz`).

## 1. Token opaco (ADR-0009)

### 1.1 Generación del token

- **Algoritmo**: `secrets.token_urlsafe(32)` (Python) o equivalente
  criptográficamente seguro.
- **Longitud**: 256 bits (32 bytes) → 43 caracteres en URL-safe base64.
- **Formato**: string opaco (no JWT, no decodificable).
- **Momento**: se genera al hacer login (creación de sesión).

### 1.2 Almacenamiento del token

- **En la BD**: se almacena el **hash** del token (SHA-256), nunca el token
  en claro.
- **En el cliente**: el token se almacena en un cookie `HttpOnly` (no
  accesible desde JavaScript) o en el header `Authorization: Bearer <token>`.
- **Prohibido**: almacenar el token en claro en la BD, en logs, o en el
  frontend (localStorage).

### 1.3 Tabla `sessions`

```sql
CREATE TABLE sessions (
    id               TEXT PRIMARY KEY,  -- hash SHA-256 del token (64 chars)
    user_id          UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    organization_id  UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    role             TEXT NOT NULL,
    expires_at       TIMESTAMPTZ NOT NULL,
    last_seen_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    revoked_at       TIMESTAMPTZ,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

- **PK**: `id` (hash SHA-256 del token).
- **FK**: `user_id` → `users.id` (CASCADE); `organization_id` →
  `organizations.id` (CASCADE).
- **`revoked_at`**: NULL = sesión activa. Si no es NULL, la sesión está
  revocada.
- **`expires_at`**: timestamp de expiración. La aplicación verifica que
  `NOW() < expires_at`.

### 1.4 Verificación de sesión

```python
def verify_session(token: str) -> Session | None:
    token_hash = sha256(token).hexdigest()
    session = db.query(Sessions).filter_by(id=token_hash).first()
    if session is None:
        return None
    if session.revoked_at is not None:
        return None
    if session.expires_at < now():
        return None
    # Actualizar last_seen_at
    session.last_seen_at = now()
    db.commit()
    return session
```

- **Cada request**: se verifica la sesión (token → hash → BD).
- **`last_seen_at`**: se actualiza en cada request (para detectar sesiones
  inactivas).
- **Caché**: opcionalmente, se puede cachear la sesión en memoria (TTL corto)
  para reducir queries a la BD. No es obligatorio en V1.

## 2. Login y logout

### 2.1 Login (`POST /api/v1/auth/login`)

```
Request:
  {
    "username": "user@example.com",
    "password": "secret"
  }

Response (200 OK):
  {
    "token": "abc123...",  // token opaco
    "expires_at": "2026-09-05T12:00:00Z"
  }
```

**Flujo**:
1. Validar username y password (argon2id).
2. Verificar que el usuario está `active`.
3. Generar token opaco (256 bits).
4. Calcular hash SHA-256 del token.
5. Insertar en `sessions` (id=hash, user_id, organization_id, role,
   expires_at=NOW()+30d).
6. Devolver el token (no el hash) al cliente.

### 2.2 Logout (`POST /api/v1/auth/logout`)

```
Request:
  Authorization: Bearer <token>

Response (204 No Content)
```

**Flujo**:
1. Verificar la sesión (token → hash → BD).
2. Marcar `revoked_at = NOW()`.
3. El token deja de ser válido (la siguiente verificación fallará).

### 2.3 Expiración de sesión

- **Duración**: 30 días por defecto (configurable).
- **Expiración**: al hacer un request con un token expirado, se devuelve
  `401 Unauthorized`.
- **Limpieza**: un job periódico (opcional) elimina sesiones expiradas de la
  BD. No es obligatorio en V1.

## 3. Revocación de sesiones (ADR-0009)

### 3.1 Revocación por usuario

- **Endpoint**: `DELETE /api/v1/auth/sessions` (revocar todas las sesiones
  del usuario actual).
- **Flujo**:
  1. Verificar la sesión actual.
  2. `UPDATE sessions SET revoked_at = NOW() WHERE user_id = :user_id AND
     revoked_at IS NULL`.
  3. Todas las sesiones del usuario dejan de ser válidas.

### 3.2 Revocación por organización

- **Endpoint**: `DELETE /api/v1/admin/sessions` (revocar todas las sesiones
  de la organización, rol `admin`).
- **Flujo**:
  1. Verificar la sesión actual (rol `admin`).
  2. `UPDATE sessions SET revoked_at = NOW() WHERE organization_id =
     :org_id AND revoked_at IS NULL`.
  3. Todas las sesiones de la organización dejan de ser válidas.

### 3.3 Revocación por password reset

- Al cambiar la password, se revocan todas las sesiones del usuario (excepto
  la actual).
- **Flujo**:
  1. Verificar la sesión actual.
  2. Verificar la password actual.
  3. Hashar la nueva password (argon2id).
  4. `UPDATE sessions SET revoked_at = NOW() WHERE user_id = :user_id AND
     id != :current_session_id AND revoked_at IS NULL`.

## 4. Password hashing

### 4.1 Algoritmo: argon2id

- **Algoritmo**: argon2id (recomendado por OWASP).
- **Parámetros**:
  - `time_cost`: 3 (iteraciones).
  - `memory_cost`: 65536 (64 MB).
  - `parallelism`: 4.
  - `salt_length`: 16 bytes.
  - `hash_length`: 32 bytes.
- **Implementación**: `argon2-cffi` (Python) o equivalente.

### 4.2 Verificación de password

```python
def verify_password(password: str, password_hash: str) -> bool:
    return argon2.verify(password_hash, password.encode())
```

- **Timing-safe**: argon2id es timing-safe (no revela información por
  timing).
- **No reversible**: el hash no se puede invertir.

### 4.3 Cambio de password

- **Endpoint**: `POST /api/v1/auth/password` (cambiar password).
- **Flujo**:
  1. Verificar la sesión actual.
  2. Verificar la password actual.
  3. Hashar la nueva password (argon2id).
  4. `UPDATE users SET password_hash = :new_hash WHERE id = :user_id`.
  5. Revocar todas las sesiones excepto la actual.

## 5. Rate limiting

### 5.1 Login rate limiting

- **Límite**: 5 intentos de login por minuto por IP.
- **Implementación**: Redis (o BD) con contador por IP.
- **Exceso**: `429 Too Many Requests` con header `Retry-After`.

### 5.2 API rate limiting

- **Límite**: 100 requests por minuto por usuario (configurable).
- **Implementación**: middleware de rate limiting.
- **Exceso**: `429 Too Many Requests`.

## 6. Seguridad adicional

### 6.1 Cookie HttpOnly

- El token se almacena en una cookie `HttpOnly` (no accesible desde
  JavaScript).
- **Flags**: `HttpOnly`, `Secure` (solo HTTPS), `SameSite=Strict`.

### 6.2 CSRF

- **Protección**: el token en header `Authorization` no está sujeto a CSRF
  (el navegador no lo añade automáticamente).
- **Si se usa cookie**: se añade un token CSRF en el header
  `X-CSRF-Token` (generado al login, verificado en cada request).

### 6.3 HTTPS

- **Obligatorio**: toda la comunicación es HTTPS (TLS 1.2+).
- **HSTS**: header `Strict-Transport-Security` para forzar HTTPS.

## 7. Propagación de cambios de rol (G14)

### 7.1 Problema

El `role` se almacena en la tabla `sessions`. Si un admin cambia el rol de un
usuario, las sesiones existentes del usuario conservan el rol antiguo hasta
que se revocan o expiran.

### 7.2 Solución

- **Al cambiar el rol**: se revocan todas las sesiones del usuario (excepto
  la actual del admin). El usuario debe hacer login de nuevo para obtener una
  sesión con el nuevo rol.
- **Implementación**:
  ```python
  def change_user_role(user_id: UUID, new_role: str, admin_session: Session):
      # Verificar que el admin tiene permiso
      # Cambiar el rol en users
      db.execute(update(User).where(User.id == user_id).values(role=new_role))
      # Revocar todas las sesiones del usuario (excepto la del admin)
      db.execute(
          update(Session)
          .where(Session.user_id == user_id, Session.id != admin_session.id)
          .values(revoked_at=now())
      )
      db.commit()
  ```
- **Alternativa**: en lugar de revocar, se puede actualizar el `role` en las
  sesiones existentes:
  ```python
  db.execute(
      update(Session)
      .where(Session.user_id == user_id, Session.revoked_at.is_(None))
      .values(role=new_role)
  )
  ```
  Esta alternativa es más simple pero menos segura (el usuario no tiene que
  hacer login de nuevo). En V1, se usa la primera opción (revocar).

## 8. Notas

- **Token opaco**: no es JWT. No contiene información (no se puede
  decodificar). La información se obtiene de la BD.
- **Hash del token**: se almacena el hash SHA-256 del token, no el token en
  claro. Si la BD se fuga, los tokens no son utilizables.
- **Revocación**: la revocación es inmediata (marcar `revoked_at`). No hay
  que esperar a la expiración.
- **Caché**: opcional. No es obligatorio en V1. Si se usa, el TTL debe ser
  corto (< 1 min) para que la revocación sea efectiva.
- **Rate limiting**: el rate limiting depende de Redis (o BD). En V1, se usa
  BD (tabla `rate_limits` o contador en `sessions`). Redis es una opción para
  Phase 3.
