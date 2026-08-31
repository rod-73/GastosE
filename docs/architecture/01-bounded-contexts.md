# 01 — Bounded contexts y context map (GastosE)

GastosE es **un bounded context independiente** ("Gestión de gastos y
documentos recibidos") respecto a FacturaE (ADR-0001). Dentro de GastosE se
definen **sub-contextos** (subdomains) como límites de módulo, no como
servicios independientes: comparten la misma base de datos y el mismo
despliegue (ADR-0004), pero tienen modelos de dominio propios, lenguaje
propio (terminología canónica de `docs/requirements/01-terminology.md`) y
contratos internos versionados.

## 1. Sub-contextos

Se mantienen los cinco contextos sugeridos por la skill `architecture`,
refinados según el baseline de dominio. No se renombra ninguno; se afina el
confín de cada uno.

### 1.1 Document Ingestion (ingesta de documentos)

**Pregunta de dominio**: ¿cómo entra un documento fuente al sistema y cómo se
garantiza que es íntegro, inmutable y único?

**Dentro del confín**:

- Subida de archivos (PDF texto/escaneado, imágenes, XML Facturae/e-invoice)
  (FR-DOC-1).
- Validación de archivo: tamaño, páginas, detección de formato real por
  magic bytes (sniffing; FR-DOC-5), nombre seguro generado por el sistema
  (FR-DOC-4).
- Cálculo de fingerprint SHA-256 (FR-DOC-2) y detección de duplicado por
  fingerprint (DUP-1).
- Almacenamiento inmutable del documento fuente (INV-9, NFR-3) y verificación
  de integridad bajo demanda (NFR-3).
- Ciclo de vida A del documento fuente (04-lifecycle.md): estados
  `uploaded`, `processing`, `extracted`, `uncertain`, `validation_error`,
  `duplicate`, `manually_corrected`, `validated`, `accepted`, `rejected`,
  `confirmed_duplicate`, `failed`.
- Cola de trabajo de extracción (crear/consultar tareas; ADR-0005).

**Fuera del confín**: la extracción en sí (sub-contexto Extraction), la
creación de gastos (Expense Core), la resolución humana de duplicados
(Review & Acceptance).

**Lenguaje propio**: documento fuente, fingerprint, formato detectado,
nombre seguro, clave de duplicación.

### 1.2 Extraction (extracción)

**Pregunta de dominio**: ¿cómo se obtienen valores extraídos fiables-en-origen
de un documento fuente, con confianza y proveniencia?

**Dentro del confín**:

- Cascada determinística de métodos: `xml_schema` → `pdf_text_rules` →
  `ocr` → `vision_llm` (FR-EXT-1), con registro del nivel alcanzado.
- Esquema estricto del output de extracción (VR-SCHEMA-1): todo output
  (incluido LLM) se valida contra el esquema; si falla, no se guarda como
  valor extraído (FR-EXT-3).
- Valores extraídos (E3) con confidence (0..1) y provenance (método, página,
  coordenadas/bbox, regla) (INV-11, FR-EXT-2).
- Ciclo de vida B de la extracción (04-lifecycle.md): `pending`, `running`,
  `completed`, `failed`, `reprocessed`.
- Idempotencia de la extracción (FR-EXT-5, NFR-4).
- Construcción de la clave de duplicación al completar la extracción (DUP-2,
  DUP-3) y notificación al sub-contexto que gestiona duplicaciones.

**Fuera del confín**: normalización (Expense Core), validación (Expense
Core), revisión humana (Review & Acceptance). El pipeline de extracción NUNCA
produce valores normalizados ni validados: solo valores extraídos.

**Lenguaje propio**: método de extracción, confianza, proveniencia, esquema
estricto, cascada.

**Trust boundary**: el contenido del documento es dato, nunca instrucción
(FR-REV-5); ver [07-security-boundaries.md](07-security-boundaries.md).

### 1.3 Expense Core (núcleo de gastos)

**Pregunta de dominio**: ¿cómo se construye, normaliza, valida y estructura un
gasto a partir de valores extraídos?

**Dentro del confín**:

- Gastos (E6), líneas de gasto (E7), líneas fiscales (E8).
- Normalización determinística (N3): moneda ISO-4217 decimal exacto, fecha
  ISO-8601, NIF/CIF validado, tipo impositivo conocido (FR-NOR-1..3, INV-12).
- Validación determinística (N4): reglas VR-xxx (aritméticas, esquema,
  normalización, referencias, negocio) (FR-VAL-1..4).
- Ciclo de vida C del gasto (04-lifecycle.md): `draft`, `under_review`,
  `validation_error`, `duplicate`, `ready_for_acceptance`, `accepted`,
  `voided`, `rejected`, `confirmed_duplicate`, `failed`.
- Totales e identidad aritmética (INV-1, FR-TOT-1..2).
- Moneda única por gasto (INV-13), conversiones explícitas registradas
  (FR-CUR-3).
- Referencias a catálogo: categorías (E10), métodos de pago (E11), tipos
  impositivos (E18), monedas (E17) — los catálogos son parte de este
  sub-contexto (ver 1.5).
- Splits de documento (E19, INV-4, VR-REF-5).
- Anulación de gastos aceptados (FR-EXP-5, INV-14).

**Fuera del confín**: la decisión humana de aceptar/rechazar (Review &
Acceptance), el almacenamiento del documento (Document Ingestion), la
detección de duplicados por fingerprint (Document Ingestion) — aunque la
resolución de duplicados afecta al estado del gasto.

**Lenguaje propio**: valor normalizado, valor validado, base imponible,
cuota, total, tolerancia, severidad BLOCK/WARN.

### 1.4 Supplier (proveedores)

**Pregunta de dominio**: ¿quién emite el documento y qué datos fiscales tiene?

**Dentro del confín**:

- Proveedor (E9): nombre legal, NIF/CIF con dígito de control validado
  (VR-NORM-3), dirección fiscal, estado `active`/`inactive`.
- Búsqueda por NIF/CIF o nombre (FR-SUP-3).
- Política de eliminación: con gastos aceptados no se elimina, solo
  `inactive` (FR-SUP-4).
- Datos fiscales válidos antes de aceptar (INV-5, FR-SUP-5).

**Fuera del confín**: la emisión de facturas (FacturaE), la validación de
gastos (Expense Core).

**Lenguaje propio**: proveedor, datos fiscales, NIF/CIF.

### 1.5 Review & Acceptance (revisión y aceptación)

**Pregunta de dominio**: ¿cómo interviene el humano para convertir valores
validados en hechos contables, y cómo se resuelven los casos que la máquina no
puede decidir?

**Dentro del confín**:

- Revisión humana (E13): pantalla de revisión por campo con valor extraído,
  valor normalizado, confidence, provenance y documento fuente para contraste
  (FR-REV-1).
- Confirmar / corregir / rechazar por campo (FR-REV-2); corrección manual
  auditada (E14, INV-7).
- Ciclo de vida D de la revisión (04-lifecycle.md): `in_progress`,
  `completed`, `aborted`.
- Aceptación (FR-ACC-1..4): aprobación explícita, snapshot inmutable de
  valores aceptados (INV-14).
- Rechazo (FR-REJ-1..3): terminal, con motivo obligatorio.
- Resolución de duplicaciones (DUP-4..DUP-10): confirmar duplicado /
  confirmar no-duplicado, humana, auditada.
- Anulación de gastos aceptados (FR-EXP-5).

**Fuera del confín**: la validación determinística (Expense Core) — la
revisión la consume, no la ejecuta; la detección de duplicados (Document
Ingestion / Expense Core) — la resolución la ejecuta aquí.

**Lenguaje propio**: revisión, corrección manual, aceptación, rechazo,
anulación, duplicado probable/confirmado.

### 1.6 Catálogos (sub-contexto transversal dentro de Expense Core)

Las entidades de referencia E10 (categoría), E11 (método de pago), E17
(moneda) y E18 (tipo impositivo) se modelan dentro de Expense Core como
catálogos administrables. No se crea un sub-contexto separado porque no
tienen lenguaje propio ni ciclo de vida propio (solo `active`/`inactive`), y
separarlos crearía acoplamiento innecesario (verificación de referencias
VR-REF-2/3/4). La administración (CRUD) queda sujeta al rol de
administración (NFR-7).

## 2. Context map

Relaciones entre sub-contextos (dentro de GastosE) y con el exterior.
Convenciones: **U/D** = upstream/downstream (upstream produce, downstream
consume); **OHS** = Open Host Service (publica un contrato interno versionado);
**PL** = Published Language (el contrato es el "lenguaje publicado");
**ACL** = Anti-Corruption Layer (traductor de modelos, si aplica).

```mermaid
flowchart LR
    subgraph GastosE
        DI[Document Ingestion]
        EX[Extraction]
        EC[Expense Core]
        SU[Supplier]
        RA[Review & Acceptance]
    end
    FE[Frontend / UI]
    USR[Usuario]

    USR --> FE
    FE -->|OHS: API /api/v1| DI
    FE -->|OHS: API /api/v1| EC
    FE -->|OHS: API /api/v1| SU
    FE -->|OHS: API /api/v1| RA

    DI -->|U/D: cola de extracción + documento íntegro| EX
    EX -->|U/D: valores extraídos (E3, esquema estricto)| EC
    EC -->|U/D: valores normalizados/validados + estados| RA
    RA -->|U/D: decisión (aceptar/rechazar/corregir/resolver)| EC
    SU -->|U/D: proveedor válido (NIF/CIF)| EC
    DI -.->|detección fingerprint (DUP-1)| RA
    EX -.->|clave de duplicación (DUP-2)| RA
```

| Relación | Tipo | Contrato |
|---|---|---|
| Frontend → cada sub-contexto | OHS | API REST versionada `/api/v1/` (docs/api/). |
| Document Ingestion → Extraction | U/D | Tarea de cola (ADR-0005) que referencia el documento fuente íntegro (fingerprint verificado) y el formato detectado. |
| Extraction → Expense Core | U/D | Valores extraídos (E3) que cumplen el esquema estricto de extracción (VR-SCHEMA-1), con confidence y provenance (INV-11). |
| Expense Core → Review & Acceptance | U/D | Valores normalizados/validados, resultados de reglas VR-xxx, estados del ciclo C. |
| Review & Acceptance → Expense Core | U/D | Decisiones: confirmar/corregir/rechazar por campo, aceptar, rechazar, anular, resolver duplicado. |
| Supplier → Expense Core | U/D | Proveedor con datos fiscales válidos (INV-5). |
| Document Ingestion / Extraction → Review & Acceptance | señal | Detección de duplicado (fingerprint o clave) → duplicación `probable` (DUP-1/2/3). |

**Reglas del context map**:

1. El flujo de valor es unidireccional: DI → EX → EC → RA → (decisión) → EC.
   No hay dependencias circulares entre sub-contextos (ver
   [02-components.md](02-components.md), sección 3).
2. Cada frontera de sub-contexto expone un **contrato interno versionado**
   (lenguaje publicado). Los contratos internos se registran en
   `docs/project/CONTRACTS.md` y se versionan igual que los externos.
3. La UI (frontend) solo habla con la API pública; no accede directamente a
   sub-contextos ni a la base de datos.
4. No hay ACL en Phase 1: los sub-contextos comparten la terminología canónica
   del baseline, por lo que no hay modelos contradictorios que traducir. Si un
   sub-contexto desarrolla un modelo propio contradictorio, se documentará una
   ACL.

## 3. Qué vive fuera de GastosE

| Sistema / ámbito | Relación con GastosE |
|---|---|
| **FacturaE** (emisión de facturas, `/workspace/facturaE`) | Sistema EXTERNO de solo lectura. Prohibido compartir código, ORM, DB, tablas, migraciones, almacenamiento (ADR-0001). Integración futura solo vía API versionada o contrato de eventos versionado, pendiente de decisión explícita. Ver [06-facturae-isolation.md](06-facturae-isolation.md). |
| **Contabilidad general** | Fuera de scope. GastosE produce el hecho contable (gasto aceptado); su contabilidad (asientos, mayor, balances) es otro bounded context. El snapshot de valores aceptados (INV-14) es el punto de exportación futuro. |
| **Conciliación bancaria** | Fuera de scope (OQ-16). El pago (E12) se registra como hecho, sin conciliación. |
| **Pagos reales** (banco, pasarelas) | Fuera de scope. GastosE registra el método de pago y el hecho de pago; no ejecuta pagos. |
| **Aprobación presupuestaria** | Fuera de scope (README de requirements). |
| **Identidad / IdP externo** | Fuera de scope en Phase 1: autenticación nativa de GastosE (ver [07-security-boundaries.md](07-security-boundaries.md)). Un IdP externo sería una integración futura vía contrato. |

## 4. Decisiones de confín (justificación)

- **No se separa "Duplicación" como sub-contexto propio**: la detección vive
  en Document Ingestion (fingerprint) y Extraction (clave lógica), y la
  resolución en Review & Acceptance. La entidad E15 (duplicación) es un
  registro transversal gestionado por Expense Core (estado del gasto) y
  resuelto por Review & Acceptance. Separarlo crearía un sub-contexto sin
  lenguaje propio.
- **No se separa "Auditoría" como sub-contexto propio**: la auditoría (E16)
  es un mecanismo transversal (append-only) que todos los sub-contextos
  alimentan; no es un dominio con comportamiento propio.
- **Normalización y validación viven en Expense Core, no en Extraction**:
  porque operan sobre el modelo de gasto (líneas, totales, referencias a
  catálogos) y no sobre el documento. Extraction termina en valores
  extraídos; esto preserva la frontera N2 → N3 (08-value-semantics.md).
