# Modelo de API / recursos — GastosE (PHASE1-002)

Contrato de API de GastosE. Fuente de verdad: [`openapi.yaml`](openapi.yaml)
(spec OpenAPI 3.0). Este documento describe el modelo de recursos y las
convenciones; el spec es el contrato ejecutable.

- **Tarea**: PHASE1-002. **Autor**: subagente `architect`. **Fecha**: 2026-08-31.
- **Fase**: Phase 1 — documentación de contrato, no implementación.
- **Skills aplicadas**: `api-design` (versionado, identidad, schemas, errores,
  idempotencia, asíncrono, compatibilidad).

## 1. Versionado

- **URL versionada**: `/api/v1/...`. Breaking change => `v2` (o campo opt-in
  documentado).
- Añadir campos a responses es compatible; quitar/renombrar no.
- El spec OpenAPI es la fuente de verdad; se valida con la tool
  `openapi-check`.
- Deprecación: header `Deprecation` + ventana documentada.

## 2. Recursos

| Recurso | Ruta base | Entidad (baseline) | Operaciones |
|---|---|---|---|
| Proveedor | `/suppliers` | E9 | CRUD + búsqueda (NIF/nombre) + activar/inactivar. |
| Documento fuente | `/documents` | E1 | Subida (asíncrona), consulta, estado, verificación de fingerprint, descarga. |
| Extracción | `/documents/{id}/extractions` | E2, E3 | Listado, consulta (valores extraídos, método, estado). |
| Gasto | `/expenses` | E6 | CRUD + transiciones (accept, reject, void) + revalidación. |
| Línea de gasto | `/expenses/{id}/lines` | E7 | CRUD. |
| Línea fiscal | `/expenses/{id}/lines/{lineId}/tax-lines` | E8 | CRUD. |
| Categoría | `/categories` | E10 | CRUD + activar/inactivar. |
| Método de pago | `/payment-methods` | E11 | CRUD + activar/inactivar. |
| Pago | `/expenses/{id}/payments` | E12 | CRUD. |
| Revisión | `/expenses/{id}/review` | E13, E14 | Vista de revisión, decisiones por campo (confirmar/corregir/rechazar). |
| Duplicación | `/duplications` | E15 | Listado, consulta, resolución (confirmar duplicado / no-duplicado). |
| Tipo impositivo | `/tax-rates` | E18 | CRUD (catálogo). |
| Moneda | `/currencies` | E17 | Listado (catálogo ISO-4217). |
| Auditoría | `/audit-events` | E16 | Listado/consulta (solo lectura, append-only). |
| Split de documento | `/expenses/{id}/splits` | E19 | Crear split (operación explícita). |

## 3. Operaciones de transición de estado

Las transiciones de estado son operaciones explícitas (no `PATCH` genérico),
lo que hace la máquina de estados auditable e idempotente:

| Operación | Ruta | Efecto | Rol mínimo |
|---|---|---|---|
| Aceptar gasto | `POST /expenses/{id}/accept` | `ready_for_acceptance -> accepted` (IRREV) + snapshot. Revalidación definitiva. | `approver` |
| Rechazar gasto | `POST /expenses/{id}/reject` | cualquier estado no terminal -> `rejected` (IRREV), motivo obligatorio. | `reviewer` |
| Anular gasto | `POST /expenses/{id}/void` | `accepted -> voided` (IRREV), motivo obligatorio. | `approver` (OQ-13) |
| Enviar a revisión | `POST /expenses/{id}/submit-review` | `draft -> under_review`. | `reviewer` |
| Decidir revisión | `POST /expenses/{id}/review/decisions` | confirmar/corregir/rechazar campos (E13/E14). | `reviewer` |
| Resolver duplicado | `POST /duplications/{id}/resolve` | `probable -> confirmed` / `resolved_not_duplicate` (IRREV), motivo. | `reviewer` |
| Corregir valor | (dentro de `review/decisions`) | corrección manual auditada (E14, INV-7). | `reviewer` |
| Reintentar extracción | `POST /documents/{id}/extractions/retry` | nueva extracción si el fallo es recuperable (FR-FST-2). | `reader` (propietario) |

**Reglas**:

- Una transición inválida (p. e.g. aceptar un `rejected`) devuelve `409` con
  el estado actual y la transición esperada.
- La aceptación verifica todas las reglas BLOCK (INV-5, INV-6, INV-8); si
  alguna falla, `409` con las reglas fallidas.
- Las transiciones son idempotentes por diseño (estado actual + transición
  esperada): repetir la misma operación no produce efectos secundarios.

## 4. Convenciones de schema

- **Dinero**: `string` con formato decimal exacto (p. e.g. `"1234.56"`),
  NUNCA float (INV-2, NFR-2). Moneda ISO-4217 obligatoria cuando hay importe
  (campo `currency` adyacente o en el recurso).
- **Fechas**: ISO-8601. Fecha del documento = `YYYY-MM-DD` (OQ-15); eventos
  (subida, revisión, aceptación) = `YYYY-MM-DDTHH:MM:SSZ`.
- **Identificadores**: UUIDv7 (identidad estable, ordenable por tiempo).
- **Estados**: enums canónicos de los ciclos A/B/C/D (04-lifecycle.md).
- **Campos desconocidos en requests**: rechazados (validación estricta).
- **Confidence**: número 0..1. **Provenance**: objeto (método, página, bbox,
  regla).

## 5. Errores

Formato único RFC 7807 (`application/problem+json`):

```json
{
  "type": "https://gastos.example/errors/validation",
  "title": "Validation error",
  "status": 422,
  "detail": "Line 2: total does not match base + VAT",
  "errors": [{"field": "lines[1].total", "issue": "arithmetic_mismatch"}]
}
```

| Código | Uso |
|---|---|
| 400 | Mala sintaxis / parámetros inválidos. |
| 401 | No autenticado. |
| 403 | No autorizado (rol insuficiente). |
| 404 | Recurso no existe (o no es del usuario: aislamiento, NFR-7). |
| 409 | Conflicto: estado inválido, duplicado, transición no permitida. |
| 422 | Validación de negocio fallida (reglas VR, tamaño, formato). |
| 423 | Recurso bloqueado (p. e.g. en revisión, duplicación probable). |
| 429 | Rate limit. |
| 500 | Error inesperado (nunca expone stack traces). |

Nunca se exponen stack traces ni información interna.

## 6. Operaciones asíncronas

- `POST /api/v1/documents` => `202 Accepted` con `Location:
  /api/v1/documents/{id}`; estado consultable (`uploaded|processing|
  extracted|failed|...`). El cliente consulta el estado; no asume duración.
- El resto de operaciones son síncronas (ver
  `docs/architecture/04-async-boundaries.md`).

## 7. Idempotencia

- `POST` de mutación soporta header `Idempotency-Key`: repetir la misma key
  devuelve la misma respuesta sin re-ejecutar.
- Operaciones de aceptación/corrección: idempotentes por diseño (estado
  actual + transición esperada).
- Subida con fingerprint ya existente: no crea un segundo documento idéntico;
  se detecta como duplicación (DUP-1, NFR-4).

## 8. Autenticación (esquema)

- Esquema: `http` bearer (token) o cookie de sesión (el mecanismo exacto es
  de Phase 2; el contrato usa el security scheme `bearerAuth`).
- Autenticación obligatoria en todos los endpoints (salvo `/healthz`).
- Autorización por rol (NFR-7): `reader`, `reviewer`, `approver`, `admin`
  (ver `docs/architecture/07-security-boundaries.md`, sección 2).
- Aislamiento por usuario: el propietario se deriva de la sesión; las
  queries filtran por organización (`owner_id` = `organization_id`, ADR-0008).

## 9. Paginación y filtros

- **Paginación por cursor** en colecciones: parámetros `cursor` (opcional) y
  `limit` (por defecto 50, máx. 200). Response incluye `next_cursor` (null si
  no hay más). Orden determinístico (p. e.g. por `created_at` + `id`).
- **Filtros básicos** (query params): por estado, proveedor, fecha
  (`date_from`/`date_to`), categoría, moneda. Filtros limitados y documentados
  por recurso.
- **Ordenación**: parámetro `sort` con campos permitidos (p. e.g.
  `-created_at`, `total`).

## 10. Compatibilidad y evolución

- Cambios de contrato => actualizar OpenAPI + ADR si es significativo.
- Breaking change => nueva versión (`/api/v2/`).
- Los contratos internos (cola de extracción, esquema de output de
  extracción) se versionan igual y se registran en
  `docs/project/CONTRACTS.md`.
