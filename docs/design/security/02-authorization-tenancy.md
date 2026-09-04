# 02 — Autorización y tenencia (GastosE Phase 2)

Diseño de implementación de la autorización y el aislamiento por
organización (ADR-0008 + ADR-0009). Cubre: roles, object-level
authorization, aislamiento por organización.

**Amenazas cubiertas**: T2 (autorización), G6..G10.
**ADR**: ADR-0008 (tenencia por organización), ADR-0009 (sesiones).
**NFR**: NFR-7 (aislamiento por organización, roles).

## 1. Modelo de roles

### 1.1 Roles disponibles

| Rol | Descripción | Permisos |
|-----|-------------|----------|
| `reader` | Lectura solo. | Ver documentos, gastos, proveedores, auditoría. |
| `reviewer` | Lectura + revisión. | Todo lo de `reader` + revisar gastos, corregir campos. |
| `approver` | Lectura + revisión + aceptación. | Todo lo de `reviewer` + aceptar/rechazar gastos, anular. |
| `admin` | Administración. | Todo lo de `approver` + gestionar usuarios, catálogos, proveedores. |

### 1.2 Jerarquía de roles

```
admin > approver > reviewer > reader
```

- Un rol superior incluye todos los permisos del rol inferior.
- La verificación de rol es por jerarquía: si se requiere `reviewer`, un
  `approver` o `admin` también puede.

### 1.3 Asignación de roles

- **Al crear usuario**: se asigna un rol (por defecto `reader`).
- **Cambio de rol**: solo un `admin` puede cambiar el rol de otro usuario.
- **Endpoint**: `PUT /api/v1/admin/users/{id}/role` (rol `admin`).

## 2. Object-level authorization

### 2.1 Regla fundamental

**Todas las queries filtran por `owner_id` (= `organization_id`) derivado de
la sesión.**

- El `owner_id` **nunca** viene de un parámetro de la petición.
- El `owner_id` se deriva de la sesión autenticada:
  `session.organization_id` → `owner_id`.
- Si un recurso no pertenece a la organización del usuario, se devuelve
  **404** (no 403, para no revelar la existencia del recurso).

### 2.2 Patrón de implementación

```python
# Middleware de autenticación:
def authenticate(request) -> Session:
    token = request.headers.get("Authorization", "").removeprefix("Bearer ")
    session = verify_session(token)
    if session is None:
        raise HTTPException(401, "Unauthorized")
    request.state.session = session
    return session

# Servicio de aplicación:
def get_expense(expense_id: UUID, session: Session) -> Expense:
    expense = db.query(Expense).filter_by(
        id=expense_id,
        owner_id=session.organization_id  # <-- filtro por owner_id
    ).first()
    if expense is None:
        raise HTTPException(404, "Not Found")
    return expense
```

### 2.3 Verificación de rol

```python
def require_role(min_role: str):
    role_order = {'reader': 0, 'reviewer': 1, 'approver': 2, 'admin': 3}
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            session = current_session()
            if role_order[session.role] < role_order[min_role]:
                raise HTTPException(403, "Forbidden")
            return func(*args, **kwargs)
        return wrapper
    return decorator

# Uso:
@require_role('approver')
def accept_expense(expense_id: UUID, session: Session):
    ...
```

### 2.4 Endpoints por rol

| Endpoint | Rol mínimo | Descripción |
|----------|------------|-------------|
| `GET /documents` | `reader` | Listar documentos. |
| `GET /documents/{id}` | `reader` | Ver documento. |
| `POST /documents` | `reader` | Subir documento. |
| `GET /expenses` | `reader` | Listar gastos. |
| `GET /expenses/{id}` | `reader` | Ver gasto. |
| `GET /expenses/{id}/review` | `reviewer` | Vista de revisión. |
| `POST /expenses/{id}/review/decisions` | `reviewer` | Decisiones de revisión. |
| `POST /expenses/{id}/accept` | `approver` | Aceptar gasto. |
| `POST /expenses/{id}/reject` | `approver` | Rechazar gasto. |
| `POST /expenses/{id}/void` | `approver` | Anular gasto. |
| `GET /suppliers` | `reader` | Listar proveedores. |
| `POST /suppliers` | `admin` | Crear proveedor. |
| `PUT /suppliers/{id}` | `admin` | Actualizar proveedor. |
| `DELETE /suppliers/{id}` | `admin` | Eliminar proveedor (solo si no tiene gastos aceptados). |
| `GET /categories` | `reader` | Listar categorías. |
| `POST /categories` | `admin` | Crear categoría. |
| `GET /audit-events` | `approver` | Listar auditoría (ADR-0012). |
| `GET /admin/users` | `admin` | Listar usuarios. |
| `POST /admin/users` | `admin` | Crear usuario. |
| `PUT /admin/users/{id}/role` | `admin` | Cambiar rol. |
| `DELETE /admin/sessions` | `admin` | Revocar sesiones de la org. |

## 3. Aislamiento por organización

### 3.1 Filtro en todas las queries

Ver `docs/design/persistence/06-tenancy-and-isolation.md` §2 para el diseño
completo.

**Resumen**:
- Todas las queries filtran por `owner_id = :session_owner_id`.
- El `owner_id` se deriva de la sesión (nunca de la petición).
- Acceso directo por ID: si el recurso no pertenece a la org, se devuelve
  404.

### 3.2 Test de aislamiento (NFR-7)

Ver `docs/design/persistence/06-tenancy-and-isolation.md` §5 para los tests
completos.

**Resumen**:
- Usuario A (org X) no ve gastos de org Y → 404.
- Usuario A (org X) no ve documentos de org Y → 404.
- Usuario A (org X) no ve proveedores de org Y → 404.
- Usuario A (org X) no ve auditoría de org Y → 404 o lista vacía.

## 4. Seguridad adicional

### 4.1 No revelar existencia de recursos

- Si un recurso no pertenece a la organización del usuario, se devuelve
  **404** (no 403).
- Esto evita que un atacante pueda enumerar recursos de otras organizaciones.

### 4.2 Consistencia de errores

- Los errores de autorización (403) solo se devuelven cuando el usuario
  pertenece a la organización pero no tiene el rol suficiente.
- Los errores de aislamiento (404) se devuelven cuando el recurso no
  pertenece a la organización.

### 4.3 Logging de acceso denegado

- Cada acceso denegado (403/404) se registra en `audit_events`:
  - `action`: `access.denied`
  - `entity_type`: tipo de recurso
  - `entity_id`: ID del recurso
  - `after`: `{reason: 'insufficient_role' | 'cross_tenant'}`

## 5. Notas

- **Roles**: 4 roles (reader, reviewer, approver, admin). La jerarquía es
  lineal.
- **Object-level authorization**: el filtro por `owner_id` es la línea
  principal de defensa. RLS es una segunda línea (opcional en V1).
- **404 vs 403**: 404 para cross-tenant (no revelar existencia), 403 para
  insuficiente rol (dentro de la misma org).
- **Logging**: los accesos denegados se registran en auditoría.
