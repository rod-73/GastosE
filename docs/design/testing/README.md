# Estrategia de testing Phase 2 — GastosE

Estrategia de testing para GastosE Phase 2. Define los tipos de tests, su
cobertura, y cómo se derivan de los requirements, contratos e invariantes.

## Tipos de tests

| Tipo | Alcance | Herramienta | Frecuencia |
|------|---------|-------------|------------|
| Unit | Funciones puras, lógica de dominio | pytest | Cada commit |
| Integration | Servicios de aplicación + BD | pytest + PostgreSQL | Cada commit |
| Database | Esquema, constraints, triggers, migraciones | pytest + PostgreSQL | Cada commit |
| API | Endpoints HTTP (contrato OpenAPI) | pytest + httpx | Cada commit |
| Worker | Worker de extracción (claim, ejecución) | pytest + PostgreSQL | Cada commit |
| Extraction | Pipeline de extracción (XML, PDF, OCR, LLM) | pytest + fixtures | Cada commit |
| Frontend | UI (estados, revisión, correcciones) | Playwright | Cada PR |
| E2E | Flujo completo (upload → extracción → aceptación) | Playwright + PostgreSQL | Cada PR |
| Regression | Regresión de features aceptadas | pytest + Playwright | Cada release |

## Cobertura por capa

### 1. Capa de dominio (unit tests)

- **Alcance**: funciones puras, lógica de negocio, validaciones.
- **Ejemplos**:
  - Validación de NIF/CIF (VR-NORM-3).
  - Cálculo de totales (INV-1: identidad aritmética).
  - Normalización de moneda (ISO-4217 decimal exacto).
  - Normalización de fecha (ISO-8601).
  - Detección de duplicado por clave lógica (DUP-2/3).
  - Aplicación de reglas de validación (VR-xxx).
- **Cobertura**: > 90% de las funciones de dominio.
- **Derivación**: de `docs/requirements/05-invariants.md`,
  `docs/requirements/06-validation-rules.md`,
  `docs/requirements/07-duplicates.md`.

### 2. Capa de servicios de aplicación (integration tests)

- **Alcance**: orquestación de servicios, transacciones, idempotencia.
- **Ejemplos**:
  - Subida de documento (V1-S1): validación, fingerprint, almacenamiento,
    registro en BD, creación de job.
  - Extracción (V2-S1): claim atómico, ejecución, persistencia de valores.
  - Normalización (V3-S1): creación de valores normalizados (E4).
  - Validación (V3-S2): creación de valores validados (E5).
  - Creación de gasto (V3-S3): líneas, totales, identidad aritmética.
  - Revisión (V4-S2): decisiones, correcciones, revalidación.
  - Aceptación (V4-S3): revalidación, snapshot, auditoría.
- **Cobertura**: > 80% de los servicios de aplicación.
- **Derivación**: de `docs/project/VERTICAL-SLICES.md` (criterios de
  aceptación), `docs/api/openapi.yaml` (contratos).

### 3. Capa de persistencia (database tests)

- **Alcance**: esquema, constraints, triggers, migraciones.
- **Ejemplos**:
  - Constraints de unicidad (DUP-1: `uq_docs_owner_fingerprint`).
  - Constraints de integridad (INV-10: cadena E3→E4→E5).
  - Trigger de append-only (ADR-0012: `audit_events`).
  - Migraciones Alembic (upgrade/downgrade).
  - Índices (verificación de que existen y se usan).
  - Aislamiento por `owner_id` (NFR-7).
- **Cobertura**: 100% de las constraints y triggers.
- **Derivación**: de `docs/design/persistence/` (esquema, invariantes,
  migraciones).

### 4. Capa de API (API tests)

- **Alcance**: endpoints HTTP, contrato OpenAPI, errores.
- **Ejemplos**:
  - `POST /documents`: 202 Accepted, Location header.
  - `GET /documents/{id}`: 200 OK, estados del ciclo A.
  - `POST /documents/{id}/verify-fingerprint`: 200 OK, integridad.
  - `GET /expenses/{id}/review`: 200 OK, cinco niveles.
  - `POST /expenses/{id}/review/decisions`: 200 OK, correcciones.
  - `POST /expenses/{id}/accept`: 200 OK, snapshot.
  - `POST /expenses/{id}/reject`: 200 OK, terminal.
  - `POST /expenses/{id}/void`: 200 OK, anulación.
  - Errores: 400, 401, 403, 404, 409, 413, 415, 422, 429.
- **Cobertura**: 100% de los endpoints (happy path + errores).
- **Derivación**: de `docs/api/openapi.yaml` (contrato),
  `docs/project/VERTICAL-SLICES.md` (criterios de aceptación).

### 5. Capa de worker (worker tests)

- **Alcance**: claim atómico, ejecución, reintentos.
- **Ejemplos**:
  - Claim atómico: dos workers no claiman el mismo job.
  - Ejecución: el job se marca como `completed`/`failed`.
  - Reintento: el job se reintenta hasta `max_attempts`.
  - Timeout: el job se marca como `failed` si se excede el timeout.
  - OOM: el job se marca como `failed` si se excede la memoria.
- **Cobertura**: > 80% de la lógica del worker.
- **Derivación**: de `docs/design/persistence/04-work-queue-design.md`,
  `docs/design/security/04-worker-sandbox.md`.

### 6. Capa de extracción (extraction tests)

- **Alcance**: pipeline de extracción (XML, PDF, OCR, LLM).
- **Ejemplos**:
  - XML: extracción de campos de factura XML (Facturae).
  - PDF texto: extracción de campos de PDF con texto.
  - OCR: extracción de campos de PDF escaneado.
  - LLM: extracción de campos de documento no estructurado.
  - Validación de esquema (VR-SCHEMA-1): output no conforme → `failed`.
  - Confidence: asignación de confidence + provenance (INV-11).
- **Cobertura**: > 70% del pipeline de extracción.
- **Derivación**: de `docs/requirements/03-functional-requirements.md`
  (FR-EXT-1..5), `docs/design/persistence/01-schema-design.md` (E3).

### 7. Capa de frontend (frontend tests)

- **Alcance**: UI, estados, revisión, correcciones.
- **Ejemplos**:
  - Upload: formulario de subida, validación de tamaño/formato.
  - Estados: visualización de estados del ciclo A.
  - Revisión: pantalla por campo, cinco niveles.
  - Correcciones: corrección manual, antes/después.
  - Aceptación: botón de aceptación, snapshot.
- **Cobertura**: > 70% de la UI.
- **Derivación**: de `docs/project/VERTICAL-SLICES.md` (V4-S1..S4),
  `docs/requirements/04-lifecycle.md`.

### 8. E2E (end-to-end tests)

- **Alcance**: flujo completo (upload → extracción → aceptación).
- **Ejemplos**:
  - Upload de documento → extracción → normalización → validación →
    creación de gasto → revisión → aceptación.
  - Upload de documento duplicado → detección de duplicado → resolución.
  - Upload de documento no soportado → error 415.
- **Cobertura**: > 50% de los flujos E2E.
- **Derivación**: de `docs/project/VERTICAL-SLICES.md` (verticales 1..4).

### 9. Regression tests

- **Alcance**: regresión de features aceptadas.
- **Ejemplos**:
  - Todos los tests de las verticales aceptadas.
  - Tests de seguridad (aislamiento, autenticación, autorización).
  - Tests de rendimiento (NFR-6).
- **Cobertura**: 100% de las features aceptadas.
- **Derivación**: de los tests de las verticales aceptadas.

## Herramientas

| Herramienta | Uso |
|-------------|-----|
| `pytest` | Unit, integration, database, API, worker, extraction tests. |
| `httpx` | Client HTTP para API tests. |
| `PostgreSQL` | BD de tests (instancia dedicada). |
| `Alembic` | Migraciones de tests (upgrade/downgrade). |
| `Playwright` | Frontend y E2E tests. |
| `fixtures` | Datos de prueba (documentos XML, PDF, imágenes). |
| `factory_boy` | Generación de datos de prueba. |

## Estrategia de datos de prueba

### 1. Fixtures de documentos

- **XML**: facturas XML (Facturae) con campos conocidos.
- **PDF texto**: PDFs con texto extraíble.
- **PDF escaneado**: PDFs con imagen (OCR).
- **Imágenes**: JPEG/PNG con texto.
- **Documentos maliciosos**: PDFs con JavaScript, XML con XXE, etc.

### 2. Fixtures de datos

- **Organizaciones**: 2 organizaciones (para tests de aislamiento).
- **Usuarios**: usuarios con diferentes roles (reader, reviewer, approver,
  admin).
- **Documentos**: documentos en diferentes estados.
- **Gastos**: gastos en diferentes estados.
- **Proveedores**: proveedores con NIF/CIF válidos e inválidos.

### 3. Generación de datos

- **`factory_boy`**: generación de datos aleatorios pero válidos.
- **Seed**: datos de prueba determinísticos (para tests reproducibles).

## Ejecución de tests

### 1. Cada commit

- Unit tests.
- Integration tests.
- Database tests.
- API tests.
- Worker tests.
- Extraction tests.

### 2. Cada PR

- Todos los tests de cada commit.
- Frontend tests.
- E2E tests.

### 3. Cada release

- Todos los tests.
- Regression tests.
- Performance tests (NFR-6).

## Quality gates

| Gate | Criterio |
|------|----------|
| Unit tests | > 90% cobertura de funciones de dominio. |
| Integration tests | > 80% cobertura de servicios de aplicación. |
| Database tests | 100% de constraints y triggers. |
| API tests | 100% de endpoints (happy path + errores). |
| Worker tests | > 80% de la lógica del worker. |
| Extraction tests | > 70% del pipeline de extracción. |
| Frontend tests | > 70% de la UI. |
| E2E tests | > 50% de los flujos E2E. |
| Security tests | 100% de tests de aislamiento y autenticación. |
| Performance tests | NFR-6 cumplido (< 2s para búsquedas, < 5s para uploads). |

## Notas

- **PostgreSQL**: los tests de BD usan una instancia de PostgreSQL dedicada
  (no SQLite).
- **Migraciones**: los tests de BD ejecutan las migraciones Alembic
  (upgrade/downgrade).
- **Fixtures**: los fixtures de documentos se almacenan en `tests/fixtures/`.
- **Reproducibilidad**: los tests son determinísticos (misma entrada → misma
  salida).
