# Diseño de implementación API Phase 2 — GastosE

Diseño de implementación de la API HTTP de GastosE para Phase 2. Es la
materialización operativa del contrato OpenAPI (`docs/api/openapi.yaml`).

## Qué es y qué no es

- **Es**: diseño de implementación de la API: estructura de handlers,
  validación de requests, manejo de errores, idempotencia, autenticación,
  autorización.
- **No es**: código de aplicación, ni el contrato OpenAPI (eso es
  `docs/api/openapi.yaml`).

## Relación con el contrato OpenAPI

| OpenAPI (contrato) | Phase 2 (este diseño) |
|---|---|
| `docs/api/openapi.yaml` | `01-api-implementation.md` |
| Paths (36) | Handlers y servicios de aplicación |
| Schemas (51) | Validación de requests/responses |
| Security schemes (bearerAuth) | Middleware de autenticación |
| Error responses | Manejo de errores |

## Índice del diseño

| Archivo | Contenido |
|---|---|
| [01-api-implementation.md](01-api-implementation.md) | Estructura de handlers, validación, errores, idempotencia, autenticación, autorización. |

## Convenciones

- **Framework**: FastAPI (Python).
- **Validación**: Pydantic (schemas de `docs/api/openapi.yaml`).
- **Autenticación**: middleware de autenticación (token opaco, ADR-0009).
- **Autorización**: filtro por `owner_id` + verificación de rol (ADR-0008).
- **Idempotencia**: `Idempotency-Key` header (NFR-4).
- **Errores**: formato estandarizado (code, message, details).

## Reglas duras

1. **Autenticación obligatoria**: todos los endpoints requieren autenticación
   (salvo `/healthz`).
2. **Aislamiento por organización**: todas las queries filtran por `owner_id`
   (= `organization_id`, ADR-0008; NFR-7).
3. **Idempotencia**: todas las operaciones de mutación son idempotentes
   (NFR-4).
4. **Errores estandarizados**: formato `{error: {code, message, details}}`.
5. **No stack traces**: los errores no incluyen stack traces al cliente.
6. **Deterministic first**: la extracción usa cascada determinística; el LLM
   es último recurso.

## Dependencias

- **Entrada**: contrato OpenAPI (`docs/api/openapi.yaml`), diseño de
  seguridad (`docs/design/security/`), diseño de persistencia
  (`docs/design/persistence/`).
- **Salida**: este diseño es la entrada para el agente `backend` (implementar
  handlers, servicios de aplicación).
- **No bloquea**: no requiere infraestructura (PostgreSQL no está desplegado
  aún; eso es devops).
