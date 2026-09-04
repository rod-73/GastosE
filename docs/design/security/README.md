# Diseño de seguridad Phase 2 — GastosE

Este directorio contiene el **diseño de implementación de seguridad** de
GastosE para Phase 2. Es la materialización operativa del threat review de
Phase 1 (`docs/security/threat-review.md`) y de las decisiones D1..D8
(ADR-0008..0012).

## Qué es y qué no es

- **Es**: diseño de seguridad a nivel de implementación: autenticación,
  autorización, tenencia, uploads, parsers, sandbox del worker, auditoría,
  secrets y logging. Incluye referencias a tablas, endpoints, ADRs y
  amenazas específicas.
- **No es**: código de aplicación, scripts ejecutables, ni decisiones de
  infraestructura (eso es devops). Los diseños aquí son de referencia, no
  artefactos finales.

## Relación con el threat review (Phase 1)

| Threat review (Phase 1) | Phase 2 (este diseño) |
|---|---|
| T1 (autenticación) | `01-authentication.md` |
| T2 (autorización) | `02-authorization-tenancy.md` |
| T3 (documentos maliciosos) | `03-uploads-and-parsers.md` |
| T4 (compromiso del worker) | `04-worker-sandbox.md` |
| T5 (tampereamiento de auditoría) | `05-audit-and-retention.md` |
| T6 (fuga de secrets) | `06-secrets-and-logging.md` |
| G1..G22 (gaps) | Cubiertos en los archivos correspondientes |
| D1..D8 (decisiones) | Resueltas por ADR-0008..0012 |

## Índice del diseño

| Archivo | Contenido |
|---|---|
| [01-authentication.md](01-authentication.md) | Autenticación: token opaco, sesiones, revocación, password hashing, rate limiting. |
| [02-authorization-tenancy.md](02-authorization-tenancy.md) | Autorización: roles, object-level authorization, aislamiento por organización. |
| [03-uploads-and-parsers.md](03-uploads-and-parsers.md) | Uploads: validación MIME, tamaño, nombre seguro, path traversal, parser security. |
| [04-worker-sandbox.md](04-worker-sandbox.md) | Sandbox del worker: contenedor, cgroup, no-root, seccomp, network egress. |
| [05-audit-and-retention.md](05-audit-and-retention.md) | Auditoría: append-only, permisos, trigger, retención. |
| [06-secrets-and-logging.md](06-secrets-and-logging.md) | Secrets y logging: gestión de secrets, redacción de logs, error messages. |

## Convenciones

- **Referencias**: cada control de seguridad referencia la amenaza (T#), el
  gap (G#), la decisión (D#), el ADR, y la NFR correspondiente.
- **Tablas**: las referencias a tablas usan los nombres definidos en
  `docs/design/persistence/01-schema-design.md`.
- **Endpoints**: las referencias a endpoints usan los nombres definidos en
  `docs/api/openapi.yaml`.
- **ADR**: las referencias a ADR usan el formato ADR-XXXX.

## Reglas duras de seguridad

1. **Aislamiento por organización**: todas las queries filtran por `owner_id`
   (= `organization_id`, ADR-0008; NFR-7).
2. **Token opaco**: el token de sesión es opaco (no JWT). Se almacena hasheado
   en la BD (ADR-0009).
3. **Append-only**: la auditoría es append-only (permisos + trigger,
   ADR-0012).
4. **Sandbox del worker**: el worker de extracción se ejecuta en un
   contenedor con límites (ADR-0011).
5. **Deterministic first**: el LLM es último recurso. Nunca `LLM OUTPUT ==
   ACCOUNTING FACT`.
6. **No secrets en logs**: nunca loguear tokens, passwords, datos financieros
   completos.
7. **FacturaE isolation**: no compartir código, DB, almacenamiento (ADR-0001).

## Dependencias

- **Entrada**: threat review (`docs/security/threat-review.md`), ADRs
  (ADR-0008..0012), NFRs (`docs/requirements/09-non-functional-requirements.md`),
  API contract (`docs/api/openapi.yaml`), diseño de persistencia
  (`docs/design/persistence/`).
- **Salida**: este diseño es la entrada para el agente `backend` (implementar
  autenticación, autorización, uploads) y para el agente `devops` (sandbox
  del worker, secrets management).
- **No bloquea**: no requiere infraestructura (PostgreSQL no está desplegado
  aún; eso es devops).
