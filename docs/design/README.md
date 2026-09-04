# Diseño Phase 2 — GastosE

Este directorio contiene el **diseño detallado de Phase 2** de GastosE. Es
la materialización operativa del baseline de Phase 1 (`docs/requirements/`,
`docs/architecture/`, `docs/persistence/`, `docs/api/`, `docs/security/`).

## Qué es y qué no es

- **Es**: diseño detallado de implementación: persistencia, seguridad,
  testing, API, y slices verticales. Incluye DDL ilustrativo, esquemas de
  tablas, y referencias a ADRs, NFRs, y requisitos.
- **No es**: código de aplicación, migraciones ejecutables, ni decisiones de
  infraestructura (eso es devops). Los diseños aquí son de referencia, no
  artefactos finales.

## Índice del diseño

| Directorio | Contenido |
|------------|-----------|
| [persistence/](persistence/) | Diseño de persistencia: esquema, migraciones, invariantes, cola de trabajo, índices, tenencia, auditoría, V1-S1. |
| [security/](security/) | Diseño de seguridad: autenticación, autorización, uploads, sandbox, auditoría, secrets. |
| [testing/](testing/) | Estrategia de testing: tipos de tests, cobertura, herramientas, quality gates. |
| [api/](api/) | Diseño de implementación API: estructura de handlers, validación, errores, idempotencia. |

## Relación con el baseline de Phase 1

| Phase 1 (baseline) | Phase 2 (este diseño) |
|---|---|
| `docs/requirements/` | Entrada (requisitos, invariantes, NFRs). |
| `docs/architecture/` | Entrada (bounded contexts, componentes, flujos). |
| `docs/persistence/` | `persistence/` (materialización operativa). |
| `docs/api/openapi.yaml` | `api/` (implementación del contrato). |
| `docs/security/threat-review.md` | `security/` (materialización operativa). |
| `docs/project/VERTICAL-SLICES.md` | `persistence/08-v1-s1-data-design.md` (V1-S1 detallado). |

## Convenciones

- **Referencias**: cada diseño referencia los ADRs, NFRs, FRs, INVs, y VRs
  correspondientes.
- **Tablas**: las referencias a tablas usan los nombres definidos en
  `persistence/01-schema-design.md`.
- **Endpoints**: las referencias a endpoints usan los nombres definidos en
  `docs/api/openapi.yaml`.
- **ADR**: las referencias a ADR usan el formato ADR-XXXX.

## Reglas duras

1. **PostgreSQL** para producción. SQLite solo para pruebas concretas.
2. **Dinero NUMERIC**: nunca `FLOAT`, `REAL`, `DOUBLE PRECISION`.
3. **UUIDv7** para PKs de recursos públicos.
4. **Estados como `TEXT`** con `CHECK` constraints (no enums nativos).
5. **Tenencia**: `owner_id` = `organization_id` (ADR-0008) en todas las
   tablas de negocio.
6. **Aislamiento FacturaE** (ADR-0001): BD propia, sin tablas compartidas.
7. **Append-only** para `audit_events` y `manual_corrections` (ADR-0012).
8. **Cadena E3→E4→E5** forzada por FK NOT NULL (INV-10).
9. **Idempotencia**: unique constraints como red de seguridad (NFR-4).
10. **Deterministic first**: la extracción usa cascada determinística; el LLM
    es último recurso.

## Dependencias

- **Entrada**: baseline Phase 1 (`docs/requirements/`, `docs/architecture/`,
  `docs/persistence/`, `docs/api/`, `docs/security/`, `docs/adr/`).
- **Salida**: este diseño es la entrada para los agentes `backend`,
  `database`, `extraction`, `frontend`, `qa`, y `devops`.
- **No bloquea**: no requiere infraestructura (PostgreSQL no está desplegado
  aún; eso es devops).

## Estado

- **persistence/**: COMPLETADO (8 archivos).
- **security/**: COMPLETADO (7 archivos).
- **testing/**: COMPLETADO (1 archivo).
- **api/**: COMPLETADO (2 archivos).

## Revisiones aplicadas

Tras la revisión independiente (security + reviewer), se aplicaron las
siguientes correcciones:

| # | Severidad | Archivo | Corrección |
|---|-----------|---------|------------|
| 1 | MEDIUM | `security/03-uploads-and-parsers.md` | Reemplazado `signal.SIGALRM` por timeout a nivel de worker (cgroup). El parser no usa señales (no thread-safe en workers asíncronos). |
| 2 | MEDIUM | `security/04-worker-sandbox.md` | Reemplazado `network_mode: "none"` por red dedicada `worker_net` con firewall. `none` bloqueaba el acceso al LLM (contradicción con la excepción declarada). |
| 3 | MEDIUM | `security/02-authorization-tenancy.md` | `GET /audit-events` cambiado de `reader` a `approver` (ADR-0012). |
| 4 | MEDIUM | `security/01-authentication.md` | Añadida sección §7 "Propagación de cambios de rol (G14)": al cambiar el rol, se revocan las sesiones del usuario. |
| 5 | LOW | `security/01-authentication.md` | Añadida nota sobre rate limiting: en V1 se usa BD, Redis es opción para Phase 3. |
