# 01 — Implementación API (GastosE Phase 2)

Diseño de implementación de la API HTTP de GastosE. Cubre: estructura de
handlers, validación de requests, manejo de errores, idempotencia,
autenticación, autorización.

**Nota**: este documento es la materialización operativa del contrato
OpenAPI (`docs/api/openapi.yaml`). No redefine el contrato, solo describe
cómo se implementa.

## 1. Estructura de la aplicación

### 1.1 Framework: FastAPI

- **Framework**: FastAPI (Python).
- **Validación**: Pydantic (schemas derivados de `docs/api/openapi.yaml`).
- **Autenticación**: middleware de autenticación.
- **Autorización**: dependencias de FastAPI (`Depends`).

### 1.2 Estructura de directorios

```
backend/
    ├── main.py              # Punto de entrada (FastAPI app)
    ├── config.py            # Configuración (env vars)
    ├── database.py          # Conexión a BD (SQLAlchemy)
    ├── models/              # Modelos ORM (SQLAlchemy)
    │   ├── __init__.py
    │   ├── organization.py
    │   ├── user.py
    │   ├── session.py
    │   ├── document.py
    │   ├── expense.py
    │   └── ...
    ├── schemas/             # Schemas Pydantic (requests/responses)
    │   ├── __init__.py
    │   ├── auth.py
    │   ├── document.py
    │   ├── expense.py
    │   └── ...
    ├── services/            # Servicios de aplicación
    │   ├── __init__.py
    │   ├── auth_service.py
    │   ├── document_service.py
    │   ├── expense_service.py
    │   └── ...
    ├── routers/             # Routers (handlers HTTP)
    │   ├── __init__.py
    │   ├── auth.py
    │   ├── documents.py
    │   ├── expenses.py
    │   └── ...
    ├── middleware/          # Middleware
    │   ├── __init__.py
    │   ├── auth.py
    │   └── rate_limit.py
    └── exceptions.py        # Excepciones personalizadas
```

### 1.3 Flujo de request

```
Request HTTP
    │
    ▼
Middleware de autenticación
    │
    ├── Token válido? ──No──► 401 Unauthorized
    │
    Sí
    ▼
Middleware de rate limiting
    │
    ├── Excede límite? ──Sí──► 429 Too Many Requests
    │
    No
    ▼
Router (handler HTTP)
    │
    ├── Validación de request (Pydantic)
    │   ├── Válida? ──No──► 422 Unprocessable Entity
    │
    Sí
    ▼
Servicio de aplicación
    │
    ├── Lógica de negocio
    ├── Query a BD (filtro por owner_id)
    │
    ▼
Response HTTP
```

## 2. Autenticación (middleware)

### 2.1 Middleware de autenticación

```python
from fastapi import Request, HTTPException
from backend.services.auth_service import verify_session

async def auth_middleware(request: Request, call_next):
    # Excepción: /healthz no requiere autenticación
    if request.url.path == "/healthz":
        return await call_next(request)
    
    # Obtener token del header Authorization
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(401, "Authentication required")
    token = auth_header.removeprefix("Bearer ")
    
    # Verificar sesión
    session = verify_session(token)
    if session is None:
        raise HTTPException(401, "Invalid or expired token")
    
    # Almacenar sesión en el request
    request.state.session = session
    
    return await call_next(request)
```

### 2.2 Dependencia de sesión

```python
from fastapi import Request

def get_session(request: Request):
    session = request.state.session
    if session is None:
        raise HTTPException(401, "Authentication required")
    return session
```

### 2.3 Dependencia de rol

```python
from fastapi import HTTPException

ROLE_ORDER = {'reader': 0, 'reviewer': 1, 'approver': 2, 'admin': 3}

def require_role(min_role: str):
    def dependency(session: Session = Depends(get_session)):
        if ROLE_ORDER[session.role] < ROLE_ORDER[min_role]:
            raise HTTPException(403, "Insufficient permissions")
        return session
    return dependency
```

## 3. Validación de requests

### 3.1 Schemas Pydantic

- **Fuente**: `docs/api/openapi.yaml` (schemas).
- **Generación**: los schemas Pydantic se derivan del contrato OpenAPI.
- **Validación**: FastAPI valida automáticamente los requests contra los
  schemas.

### 3.2 Ejemplo: upload de documento

```python
from pydantic import BaseModel, Field
from typing import Optional

class DocumentUploadResponse(BaseModel):
    id: UUID
    state: str
    fingerprint_sha256: str
    safe_name: str
    uploaded_at: datetime
```

### 3.3 Validación de multipart

- **Multipart**: `POST /documents` usa `multipart/form-data`.
- **Validación**:
  - Tamaño: ≤ 20 MB (NFR-6).
  - Formato: magic bytes (PDF, XML, JPEG, PNG).
  - Nombre: se genera UUID (no se usa el nombre original).

## 4. Manejo de errores

### 4.1 Formato de error

```json
{
  "error": {
    "code": "document.too_large",
    "message": "The document exceeds the maximum size of 20 MB.",
    "details": {}
  }
}
```

### 4.2 Códigos de error

| Code | HTTP Status | Descripción |
|------|-------------|-------------|
| `auth.unauthorized` | 401 | Autenticación requerida. |
| `auth.forbidden` | 403 | Permisos insuficientes. |
| `resource.not_found` | 404 | Recurso no encontrado. |
| `validation.error` | 422 | Error de validación. |
| `document.too_large` | 413 | Documento demasiado grande. |
| `document.unsupported_format` | 415 | Formato no soportado. |
| `conflict.duplicate` | 409 | Duplicado detectado. |
| `conflict.state` | 409 | Estado inválido. |
| `rate_limit.exceeded` | 429 | Límite de requests excedido. |
| `internal.error` | 500 | Error interno. |

### 4.3 Excepciones personalizadas

```python
class GastosEException(Exception):
    def __init__(self, code: str, message: str, status_code: int, details: dict = None):
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}

class UnauthorizedException(GastosEException):
    def __init__(self):
        super().__init__("auth.unauthorized", "Authentication required", 401)

class ForbiddenException(GastosEException):
    def __init__(self):
        super().__init__("auth.forbidden", "Insufficient permissions", 403)

class NotFoundException(GastosEException):
    def __init__(self, resource: str = "Resource"):
        super().__init__("resource.not_found", f"{resource} not found", 404)

class DocumentTooLargeException(GastosEException):
    def __init__(self):
        super().__init__("document.too_large", 
                         "The document exceeds the maximum size of 20 MB.", 413)
```

### 4.4 Handler de excepciones

```python
from fastapi import Request
from fastapi.responses import JSONResponse

@app.exception_handler(GastosEException)
async def gastosE_exception_handler(request: Request, exc: GastosEException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message, 
                           "details": exc.details}}
    )
```

## 5. Idempotencia (NFR-4)

### 5.1 Idempotency-Key

- **Header**: `Idempotency-Key` en peticiones de mutación.
- **Almacenamiento**: no se almacena en la BD en V1 (se usa el fingerprint
  como clave de idempotencia para documentos).
- **Comportamiento**: si se recibe la misma `Idempotency-Key` con la misma
  operación, se devuelve el resultado existente (200 OK) en lugar de crear
  uno nuevo.

### 5.2 Implementación

```python
from fastapi import Header

@router.post("/documents", status_code=202)
async def upload_document(
    file: UploadFile,
    idempotency_key: str = Header(None),
    session: Session = Depends(get_session),
):
    # Verificar idempotencia
    if idempotency_key:
        existing = await document_service.find_by_idempotency_key(
            session.organization_id, idempotency_key
        )
        if existing:
            return JSONResponse(
                status_code=200,
                content={"id": existing.id, "state": existing.state}
            )
    
    # Procesar upload
    document = await document_service.upload(file, session)
    
    return JSONResponse(
        status_code=202,
        headers={"Location": f"/api/v1/documents/{document.id}"},
        content={"id": document.id, "state": document.state}
    )
```

## 6. Endpoints principales

### 6.1 Auth

| Endpoint | Método | Rol | Descripción |
|----------|--------|-----|-------------|
| `/auth/login` | POST | - | Login (username + password). |
| `/auth/logout` | POST | reader | Logout (revocar sesión). |
| `/auth/password` | POST | reader | Cambiar password. |
| `/auth/sessions` | DELETE | reader | Revocar todas las sesiones del usuario. |

### 6.2 Documents

| Endpoint | Método | Rol | Descripción |
|----------|--------|-----|-------------|
| `/documents` | POST | reader | Subir documento (multipart). |
| `/documents` | GET | reader | Listar documentos. |
| `/documents/{id}` | GET | reader | Ver documento. |
| `/documents/{id}/content` | GET | reader | Descargar documento. |
| `/documents/{id}/verify-fingerprint` | POST | reader | Verificar fingerprint. |
| `/documents/{id}/extractions` | GET | reader | Listar extracciones. |
| `/documents/{id}/extractions/retry` | POST | reviewer | Reintentar extracción. |

### 6.3 Expenses

| Endpoint | Método | Rol | Descripción |
|----------|--------|-----|-------------|
| `/expenses` | GET | reader | Listar gastos. |
| `/expenses/{id}` | GET | reader | Ver gasto. |
| `/expenses/{id}/review` | GET | reviewer | Vista de revisión. |
| `/expenses/{id}/review/decisions` | POST | reviewer | Decisiones de revisión. |
| `/expenses/{id}/accept` | POST | approver | Aceptar gasto. |
| `/expenses/{id}/reject` | POST | approver | Rechazar gasto. |
| `/expenses/{id}/void` | POST | approver | Anular gasto. |

### 6.4 Suppliers

| Endpoint | Método | Rol | Descripción |
|----------|--------|-----|-------------|
| `/suppliers` | GET | reader | Listar proveedores. |
| `/suppliers` | POST | admin | Crear proveedor. |
| `/suppliers/{id}` | GET | reader | Ver proveedor. |
| `/suppliers/{id}` | PUT | admin | Actualizar proveedor. |
| `/suppliers/{id}` | DELETE | admin | Eliminar proveedor. |

### 6.5 Duplications

| Endpoint | Método | Rol | Descripción |
|----------|--------|-----|-------------|
| `/duplications` | GET | reader | Listar duplicaciones. |
| `/duplications/{id}` | GET | reader | Ver duplicación. |
| `/duplications/{id}/resolve` | POST | reviewer | Resolver duplicación. |

### 6.6 Audit

| Endpoint | Método | Rol | Descripción |
|----------|--------|-----|-------------|
| `/audit-events` | GET | reader | Listar eventos de auditoría. |
| `/audit-events/{id}` | GET | reader | Ver evento de auditoría. |

### 6.7 Admin

| Endpoint | Método | Rol | Descripción |
|----------|--------|-----|-------------|
| `/admin/users` | GET | admin | Listar usuarios. |
| `/admin/users` | POST | admin | Crear usuario. |
| `/admin/users/{id}/role` | PUT | admin | Cambiar rol. |
| `/admin/sessions` | DELETE | admin | Revocar sesiones de la org. |

## 7. Notas

- **FastAPI**: framework de elección (asíncrono, validación automática).
- **Pydantic**: schemas derivados del contrato OpenAPI.
- **Autenticación**: middleware de autenticación (token opaco).
- **Autorización**: dependencias de FastAPI (filtro por `owner_id` + rol).
- **Idempotencia**: `Idempotency-Key` header.
- **Errores**: formato estandarizado (code, message, details).
