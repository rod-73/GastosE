# 02 — Componentes, responsabilidades y dirección de dependencias (GastosE)

## 1. Componentes principales

Arquitectura de **monolito modular** con workers separados (ADR-0004). Los
componentes son procesos/contenedores desplegables; los módulos son límites
de código dentro del monolito.

| # | Componente | Proceso | Responsabilidades |
|---|---|---|---|
| C1 | **API** (API HTTP) | 1 (escalar horizontalmente) | Expone la API versionada `/api/v1/` (docs/api/). Autenticación y autorización. Orquesta servicios de aplicación. No contiene lógica de dominio. |
| C2 | **Dominio** (módulos de dominio) | dentro de C1 | Reglas de negocio, estados y transiciones de los ciclos A/B/C/D, invariantes (INV-1..15), reglas VR/DUP, normalización determinística, validación determinística. No depende de HTTP, DB ni UI. |
| C3 | **Servicios de aplicación** (application services) | dentro de C1 | Unidades de trabajo (una operación de negocio = una transacción acotada). Orquestan módulos de dominio y persistencia. Ejecutan la validación determinística en los momentos definidos (06-validation-rules.md §8). |
| C4 | **Persistencia** (capa de datos) | dentro de C1 y C5 | PostgreSQL. Valores monetarios NUMERIC exacto (INV-2). Auditoría append-only (NFR-1). Cola de trabajo (ADR-0005). |
| C5 | **Worker de extracción** (extraction worker) | N (escalar) | Consume la cola de extracción. Ejecuta la cascada determinística (XML → PDF texto → OCR → LLM). Valida el output contra el esquema estricto. Escribe valores extraídos. Reintentos con backoff. |
| C6 | **Almacenamiento de documentos** (document store) | volumen (no proceso) | Filesystem local en volumen dedicado (ADR-0006). Inmutable, identificado por fingerprint SHA-256. Fuera del webroot. |
| C7 | **Frontend / UI** | estático servido o separado | Pantallas de subida, revisión (FR-REV-1), listados, administración. Solo habla con la API. |
| C8 | **Configuración** | archivo/entorno | Umbrales y severidades configurables (NFR-9): umbral de confianza, tolerancias, severidad VR, rangos. Registrada y auditable. |

### Notas por componente

- **C1 API**: sin estado entre peticiones (stateless) para escalar. Las
  operaciones largas devuelven `202 Accepted` con estado consultable
  (docs/api/README.md, sección 6).
- **C2 Dominio**: los módulos de dominio son los sub-contextos de
  [01-bounded-contexts.md](01-bounded-contexts.md). La dirección de
  dependencias entre módulos sigue el context map (sin ciclos).
- **C3 Servicios de aplicación**: una unidad de trabajo = una operación de
  negocio (p. e.g. "aceptar gasto" = revalidación definitiva + transición +
  snapshot + auditoría, en una transacción).
- **C5 Worker**: es el único componente que toca el documento fuente para
  extraer (OCR/LLM). Aísla la superficie de ataque de parsers (skill
  `security`): timeouts, límites de memoria, sandbox de parsers.
- **C6 Document store**: la API y el worker acceden por fingerprint
  (lectura); solo la subida (API) escribe, una única vez, con nombre seguro.

## 2. Responsabilidades por sub-contexto (mapeo)

| Sub-contexto | Componentes que lo implementan |
|---|---|
| Document Ingestion | C1 (endpoints de subida/estado), C3 (servicios de subida), C4 (fingerprint, cola), C6 (almacenamiento). |
| Extraction | C5 (pipeline), C4 (valores extraídos, estado), C2 (esquema estricto, reglas de cascada). |
| Expense Core | C2 (normalización, validación, estados), C3 (unidades de trabajo), C4 (persistencia). |
| Supplier | C2, C3, C4. |
| Review & Acceptance | C1 (endpoints de revisión/aceptación), C2 (transiciones), C3 (unidades de trabajo), C4 (auditoría, snapshot). |

## 3. Dirección de dependencias

Regla general (skill `architecture`):

```
frontend -> API -> application services -> domain -> persistence
workers (extraction) -> cola -> persistence
```

- El **dominio no depende** de HTTP, DB ni UI. Depende solo de abstracciones
  (interfaces de repositorio/cola) definidas en la frontera de la capa de
  aplicación.
- Los **contratos** (`docs/api/` para el exterior; contratos internos
  registrados en `docs/project/CONTRACTS.md`) son la única fuente de verdad
  entre componentes.
- **Prohibidas las dependencias circulares**. El grafo de dependencias entre
  módulos de dominio es un DAG:

```mermaid
flowchart TD
    FE[C7 Frontend] --> API[C1 API]
    API --> APP[C3 Servicios de aplicación]
    APP --> DOM[C2 Dominio]
    DOM --> PERS[C4 Persistencia / interfaces]
    API --> PERS
    W[C5 Worker extracción] --> COLA[Cola (C4)]
    W --> PERS
    W --> DOC[C6 Document store]
    API --> DOC
    APP --> DOC
```

- Dependencias entre **módulos de dominio** (DAG, sin ciclos):

```
document_ingestion -> extraction (vía cola: referencia a documento)
extraction -> expense_core (valores extraídos)
expense_core -> supplier (referencia de proveedor)
review_acceptance -> expense_core (decisiones)
review_acceptance -> document_ingestion (consulta de duplicaciones)
```

  - `expense_core` no depende de `review_acceptance` (la revisión actúa
    sobre el gasto; el gasto no invoca a la revisión).
  - `extraction` no depende de `expense_core` (produce valores extraídos; la
    normalización la hace `expense_core`).
  - `document_ingestion` no depende de `extraction` (crea la tarea en cola;
    no ejecuta extracción).

- **Worker → API interna**: el worker NO consume la API pública HTTP. Accede
  a la persistencia y al document store directamente (mismo despliegue,
  ADR-0004). Esto evita un salto de trust boundary innecesario y mantiene la
  latencia baja. Si en el futuro el worker se separa del monolito, se
  definirá una API interna versionada (contrato interno).

## 4. Límites de servicio

- **Límite de servicio = límite de sub-contexto** (01-bounded-contexts.md).
  Cada sub-contexto expone operaciones a través de la API pública; no hay
  servicios intermedios.
- **Límite de proceso**: API (C1) y worker (C5) son procesos separados.
  Comparten base de datos y volumen (ADR-0004/0005/0006). No comparten
  memoria ni estado.
- **Límite de trust**: la frontera de confianza principal es
  `usuario → API`. La frontera `documento → pipeline OCR/LLM` es una trust
  boundary de datos no fiables (ver 07-security-boundaries.md, sección 4).
- **Límite de transacción**: una unidad de trabajo = una operación de
  negocio. La extracción (larga) NO está dentro de una transacción de la API:
  es asíncrona (ADR-0005) y sus efectos se persisten en transacciones
  acotadas del worker.

## 5. Escalabilidad y despliegue (orientativo)

- API stateless: N réplicas detrás de un balanceador.
- Worker: N réplicas consumiendo la cola (concurrencia limitada para no
  saturar CPU en OCR). La cola en BD (ADR-0005) garantiza que una tarea no se
  pierde y que no se procese dos veces (claim atómico).
- PostgreSQL: instancia única en Phase 1/2 (volumen persistente).
- Document store: volumen persistente; copias de seguridad según NFR-8.
