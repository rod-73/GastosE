---
name: api-design
description: Use when designing or reviewing GastosE HTTP APIs or OpenAPI contracts: versioning, request/response schemas, validation, errors, idempotency, compatibility, asynchronous operations, resource identity.
---

# API Design — GastosE

Reglas de diseño de API para GastosE.

## Versioning

- URL versionada: `/api/v1/...`. Breaking change => `v2` (o campo opt-in
  documentado).
- Añadir campos a responses es compatible; quitar/renombrar no.
- El contrato OpenAPI (`docs/api/openapi.yaml`) es la fuente de verdad;
  validarlo con el tool `openapi-check`.

## Identidad de recursos

- Recursos con identidad estable: `GET /api/v1/expenses/{id}` (UUIDv7).
- Colecciones: paginación (`cursor` o `page`+`size`), orden determinístico.
- ETags para caché de recursos inmutables (documentos fuente).

## Schemas

- Request/response documentados en OpenAPI con ejemplos.
- Validación estricta en el servidor: schema completo, campos desconocidos
  rechazados o ignorados de forma documentada (elegir y documentar).
- Importes monetarios: string decimal o number con precisión documentada;
  moneda ISO-4217 obligatoria.
- Fechas: ISO-8601.

## Errores

Formato de error único (RFC 7807 problem+json recomendado):

```json
{
  "type": "https://gastos.example/errors/validation",
  "title": "Validation error",
  "status": 422,
  "detail": "Line 2: total does not match base + VAT",
  "errors": [{"field": "lines[1].total", "issue": "arithmetic_mismatch"}]
}
```

- 400 mala sintaxis; 404 no existe; 409 conflicto (duplicado, estado inválido);
  422 validación; 423 recurso bloqueado (p. ej. en revisión); 500 solo
  inesperado.
- Nunca exponer stack traces ni información interna.

## Idempotencia

- `POST` de mutación soporta header `Idempotency-Key`: repetir la misma key
  devuelve la misma respuesta sin re-ejecutar.
- Operaciones de aceptación/corrección: idempotentes por diseño (estado
  actual + transición esperada).

## Operaciones asíncronas

- Extracción de documentos: `POST /api/v1/documents` => `202 Accepted` con
  `Location: /api/v1/documents/{id}` y estado consultable
  (`uploaded|processing|extracted|failed|...`).
- El cliente consulta el estado; no asume duración.

## Compatibilidad

- Cambios de contrato => actualizar OpenAPI + ADR si es significativo.
- Deprecación: header `Deprecation` + ventana documentada.

## Checklist

- [ ] ¿Versionado en URL?
- [ ] ¿OpenAPI actualizado y validado (openapi-check)?
- [ ] ¿Formato de error único y sin leaks?
- [ ] ¿Idempotency-Key en mutaciones?
- [ ] ¿Operaciones largas asíncronas con estado?
- [ ] ¿Paginación en colecciones?
