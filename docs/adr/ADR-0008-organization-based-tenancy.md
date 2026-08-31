# ADR-0008: Modelo de tenancy por organización (multi-usuario)

Status: accepted
Date: 2026-08-31
Resuelve: OQ-9 (docs/requirements/10-open-questions.md), D1 del threat review
(docs/security/threat-review.md), condición C1 de la revisión Phase 1.

## Context

OQ-9 dejaba pendiente el modelo de aislamiento de datos: por usuario
individual, por organización/empresa, o multi-tenant. El baseline de
persistencia (docs/persistence/06-isolation-and-tenancy.md) documentaba ambos
caminos y señalaba que la arquitectura soporta ambos sin cambios
estructurales: solo cambia la interpretación de `owner_id`.

El threat review (PHASE1-004) clasificó esta decisión como D1, severidad HIGH,
bloqueante para Phase 2: afecta a la semántica de `owner_id`, al
autorizamiento (authZ), a las queries de aislamiento y a la atribución de
auditoría.

## Decision

GastosE usa **aislamiento por organización (multi-usuario)**:

- Una **organización** (empresa) es la unidad de tenencia. Varios usuarios
  pertenecen a una organización y comparten sus datos.
- **`owner_id` = `organization_id`** en todas las tablas de negocio. El
  filtro de aislamiento se aplica sobre `owner_id` (= organización), no sobre
  `user_id`.
- Se añade una tabla `organizations` (id, name, state, timestamps) y
  `users.organization_id` (FK, NOT NULL). Un usuario pertenece a una
  organización.
- **Acceso dentro de la organización**: todos los usuarios de la misma
  organización ven los mismos documentos, gastos, proveedores y catálogos.
  El aislamiento es entre organizaciones, no entre usuarios.
- **Atribución (no repudio)**: la auditoría (`audit_events`) sigue
  registrando el `actor` (usuario concreto) de cada acción. La tenencia es
  por organización; la atribución es por usuario.
- **Roles** (NFR-7): los roles (lectura, revisión, aceptación,
  administración) se aplican **dentro de la organización**. El rol es un
  atributo del usuario en su organización (p. e.g. `users.role` o tabla
  `organization_members` con rol; se decide en Phase 2).
- **Catálogos**: `categories`, `payment_methods`, `tax_rates` y `suppliers`
  son por organización (llevan `owner_id` = organización). `currencies`
  sigue siendo global (ISO-4217).
- **Un usuario por organización** en Phase 2 (v1): la estructura soporta
  multi-usuario, pero la onboarding inicial es 1 organización + 1 usuario.
  La multi-usuario real (invitaciones, roles) se implementa en una vertical
  posterior (ver docs/project/VERTICAL-SLICES.md).

## Alternatives considered

1. **Aislamiento por usuario individual** (default del baseline): cada
   usuario tiene sus propios datos. Rechazado: no encaja con el caso de uso
   real (una empresa con varios empleados que registran gastos).
2. **Multi-tenant (SaaS multi-empresa con aislamiento estricto)**: cada
   tenant con schema/BD separada o RLS por tenant. Rechazado para Phase 2:
   GastosE es una aplicación de empresa propia (no SaaS multi-tenant); el
   aislamiento por organización es suficiente y más simple. Si en el futuro
   se ofrece como SaaS, se revisa con ADR nuevo.

## Consequences

- **Positivas**:
  - Encaja con el caso de uso: varios usuarios de una empresa comparten
    gastos, proveedores y catálogos.
  - Aislamiento claro entre organizaciones (NFR-7, T1 del threat review).
  - Atribución por usuario preservada en auditoría.
- **Negativas / riesgos**:
  - Complejidad de authZ: hay que resolver "usuario pertenece a organización"
    y "rol dentro de la organización" (D4 del threat review, pendiente).
  - Si un usuario cambia de organización, los datos quedan en la anterior
    (no se migran).
- **Reversibilidad**: cambiar de tenencia por organización a multi-tenant
  estricto requiere cambios de esquema (RLS, schema por tenant) y un ADR
  nuevo. Cambiar a tenencia por usuario es más simple (reinterpretar
  `owner_id`), pero pierde el caso multi-usuario.

## Implicaciones en el baseline (aplicadas)

- `docs/requirements/10-open-questions.md`: OQ-9 resuelta.
- `docs/requirements/09-non-functional-requirements.md`: NFR-7 actualizado.
- `docs/persistence/06-isolation-and-tenancy.md`: modelo por organización
  como decisión (ya no pendiente).
- `docs/persistence/01-entities-and-tables.md`: `owner_id` = `organization_id`;
  tablas `organizations` y `users.organization_id`.
- `docs/project/STATE.md`: D1 resuelto; C1 cerrada.
