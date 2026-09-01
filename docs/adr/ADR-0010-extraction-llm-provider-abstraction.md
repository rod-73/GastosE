# ADR-0010: ExtractionLLM provider abstraction

Status: accepted
Date: 2026-09-01
Resuelve: D5 del threat review (docs/security/threat-review.md), G8.

## Context

La cascada de extracción (docs/architecture/03-flows.md) usa un LLM como
último recurso (XML → PDF texto → OCR → LLM). El threat review (PHASE1-004)
identificó que no se prescribía si el LLM se usa como servicio externo (API)
o local (G8, LOW). Si es externo, el contenido del documento (datos
financieros, NIF/CIF) sale del perímetro → riesgo de confidencialidad (NFR-7).
Si es local, no hay dependencia de terceros pero hay que gestionar la
infraestructura de inferencia.

La infraestructura local actual utiliza un LLM servido mediante un endpoint
compatible con OpenAI (p. e.g. Qwen/vLLM). No se debe asumir que "LLM local"
significa un modelo pequeño ejecutándose en CPU.

## Decision

GastosE introduce una **abstracción `ExtractionLLM`** que aísla la aplicación
de cualquier proveedor concreto de LLM:

- **Provider-neutral**: la aplicación NO depende directamente de Qwen, vLLM,
  OpenAI, Anthropic ni de ningún proveedor concreto. `ExtractionLLM` es la
  única interfaz que el worker de extracción usa para invocar un LLM.
- **Abstracción mínima** (lo que `ExtractionLLM` debe encapsular):
  - `endpoint`: URL del servicio LLM (compatible con OpenAI API).
  - `model`: identificador del modelo (p. e.g. `qwen-72b`, `gpt-4o`).
  - `authentication`: API key o mecanismo de autenticación cuando
    corresponda (solo para proveedores externos; en local puede ser nulo).
  - `timeout`: límite de tiempo por llamada (configurable, NFR-9).
  - `structured output`: el LLM debe producir JSON conforme al esquema
    estricto (VR-SCHEMA-1). La abstracción no modifica el esquema; solo
    garantiza que el output se valida contra él.
  - `errores/reintentos`: manejo de errores de red, timeout, rate limiting.
    Reintentos con backoff (configurable, NFR-9).
  - `identificación del modelo/proveedor para provenance`: el output de la
    extracción incluye el modelo/proveedor usado (INV-11, provenance).
- **Backend por defecto para el despliegue de GastosE: LOCAL**. La
  infraestructura local sirve un LLM mediante un endpoint compatible con
  OpenAI. El worker se configura con el endpoint local.
- **Proveedores externos como alternativa configurable**: si se necesita un
  proveedor externo, se configura `ExtractionLLM` con el endpoint externo, el
  modelo y la API key. No se requiere cambiar código.
- **La elección local/external NO modifica**:
  - el dominio (Expense Core, Document Ingestion, etc.);
  - la API pública de GastosE (openapi.yaml);
  - el modelo de Expense (entidades, invariantes);
  - la cascada conceptual de extracción (XML → PDF texto → OCR → LLM).
- **Confidencialidad (NFR-7)**: si se usa un proveedor externo, el contenido
  del documento sale del perímetro. La política de datos (qué se envía,
  cifrado, DPA) se define en el despliegue, no en la arquitectura. La
  abstracción permite elegir local para evitar esta salida de datos.
- **Deterministic first (regla dura)**: el LLM es último recurso de la
  cascada. El output se valida contra esquema estricto (VR-SCHEMA-1) y se
  marca con confidence/provenance (INV-11). `LLM OUTPUT != ACCOUNTING FACT`
  (INV-8) en ambos casos (local o externo).
- **Sin credenciales reales ni endpoints privados en el repositorio**: la
  configuración (endpoint, modelo, API key) se gestiona en el entorno de
  despliegue (secret manager, 07-sec §6).

## Alternatives considered

1. **LLM externo fijo** (API de proveedor): la aplicación depende directamente
   de un proveedor externo. Rechazado: acopla la aplicación a un proveedor,
   sale del perímetro el contenido (NFR-7), y no permite usar la
   infraestructura local existente.
2. **LLM local fijo** (modelo autoalojado): la aplicación depende directamente
   de un modelo local. Rechazado: acopla la aplicación a un modelo concreto,
   no permite usar proveedores externos si se necesita, y no refleja la
   realidad de la infraestructura (endpoint compatible con OpenAI, no un
   modelo embebido).
3. **Abstracción `ExtractionLLM` con backend configurable (elegido)**: la
   interfaz es estable (entrada: texto/página; salida: JSON estricto); el
   cambio de backend no afecta al dominio, a la API ni a la cascada. El
   backend por defecto es local (infraestructura existente); los proveedores
   externos son una alternativa configurable.

## Consequences

- **Positivas**:
  - Provider-neutral: la aplicación no depende de ningún proveedor concreto.
  - Backend local por defecto: el contenido no sale del perímetro (NFR-7).
  - Flexibilidad: se puede cambiar de local a externo (o viceversa) sin
    cambiar código.
  - Coherencia con la infraestructura existente (endpoint compatible con
    OpenAI).
- **Negativas / riesgos**:
  - La abstracción añade una capa de indirección (pequeño coste de
    complejidad).
  - Si se usa un proveedor externo, hay que gestionar la política de datos
    (DPA, cifrado, residencia).
- **Reversibilidad**: **Alta**. La interfaz `ExtractionLLM` es estable;
  cambiar de backend no cambia el dominio, la API ni la cascada. Es la
  decisión más reversible de D4..D7.

## Implicaciones

- **Slices**: V2-S1 (worker de extracción: selección de método, ejecución del
  LLM, validación del output).
- **Contratos**: `docs/project/CONTRACTS.md` (contrato conceptual de
  `ExtractionLLM`: esquema de entrada/salida, versión). openapi.yaml no
  cambia (el LLM es interno al worker).
- **Seguridad**: cierra G8; condiciona G6/G7 (la validación estricta y la
  revisión humana son independientes del backend).
- **DevOps**: configuración del endpoint LLM (local o externo) en el
  despliegue. Si externo, red saliente del worker (D6/ADR-0011).
