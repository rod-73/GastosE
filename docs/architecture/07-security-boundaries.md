# 07 — Límites de seguridad (GastosE)

Aplica la skill `security` (checklists) a la arquitectura. El agente
`security` hará el threat review detallado (Phase 1, en paralelo); este
documento fija los **límites** a nivel de arquitectura.

## 1. Trust boundaries

```mermaid
flowchart LR
    subgraph NoConfiable
        DOC[Documento fuente<br/>(contenido de terceros)]
    end
    subgraph Pipeline
        W[Worker extracción<br/>(parsers, OCR, LLM)]
    end
    subgraph Confiable
        API[API]
        DOM[Dominio]
        DB[(PostgreSQL)]
        DS[(Document store)]
    end
    USR[Usuario autenticado] -->|TLS| API
    DOC -->|dato, nunca instrucción| W
    W -->|valores extraídos (esquema estricto)| DB
    API --> DOM --> DB
    API --> DS
    W --> DS
```

- **Trust boundary 1 (usuario → API)**: todo lo que entra por la API es
  entrada de usuario; se autentica y autoriza. El contenido del documento
  subido es **dato no fiable** (proviene de terceros).
- **Trust boundary 2 (documento → pipeline OCR/LLM)**: el contenido del
  documento es dato, nunca instrucción (FR-REV-5). El pipeline trata el
  contenido exclusivamente como entrada de extracción.
- **Trust boundary 3 (output LLM → valores extraídos)**: el output del LLM no
  se confía: se valida contra el esquema estricto (VR-SCHEMA-1) y se marca
  con confidence/provenance (N2). Nunca se usa como hecho contable.

## 2. Autenticación y autorización (NFR-7)

- **Autenticación obligatoria** en todos los endpoints (salvo health).
  Mecanismo: **token opaco + sesión server-side en BD** (ADR-0009). El token
  es opaco (no JWT); la sesión se persiste en la tabla `sessions` con
  expiración por inactividad y absoluta, y revocación inmediata por usuario y
  por organización. El `organization_id` se deriva de la sesión (ADR-0008);
  nunca se confía en un `owner_id` proporcionado por el cliente. El contrato
  de API usa el esquema `bearerAuth` con `bearerFormat: opaque`
  (docs/api/openapi.yaml).
- **Autorización por rol** (mínimo privilegio, NFR-7). Roles canónicos:

| Rol | Permisos |
|---|---|
| `reader` (lectura) | Consultar documentos, gastos, proveedores, catálogos. Subir documentos (si se permite a lectores; por defecto sí para sus propios documentos). |
| `reviewer` (revisión) | Todo lo de `reader` + revisar gastos (confirmar/corregir/rechazar campos), resolver duplicados. |
| `approver` (aceptación) | Todo lo de `reviewer` + aceptar gastos, anular gastos aceptados (OQ-13). |
| `admin` (administración) | Todo lo de `approver` + gestionar catálogos (proveedores, categorías, métodos de pago, tipos impositivos), configuración de umbrales/severidades (NFR-9). |

- **Solo los roles con permiso de aceptación aceptan gastos** (NFR-7). La
  aceptación es una operación de la API sujeta a authZ por rol.
- **Object-level authorization**: un usuario solo accede a SUS recursos
  (comprobado en cada query, no solo en la UI). Ver sección 3.
- **Rate limiting** en login y endpoints costosos (subida, extracción).

## 3. Aislamiento de datos por usuario (OQ-9, NFR-7)

- **Modelo por defecto**: aislamiento por usuario individual (OQ-9). Cada
  usuario solo accede a sus documentos, gastos y proveedores. No hay acceso
  cruzado entre usuarios.
- **Implementación arquitectónica**: todas las queries filtran por
  propietario (owner) a nivel de servicio de aplicación/persistencia, no solo
  en la UI. El propietario se deriva de la sesión autenticada (nunca de un
  parámetro de la petición).
- **Test de aislamiento** (skill `security`): usuario A no ve recurso de B
  (criterio NFR-7).
- **Pendiente de decisión (OQ-9)**: si el modelo es por organización/empresa
  o multi-tenant, el filtro de propietario cambia a "tenant". La
  arquitectura lo soporta sin cambios estructurales: el criterio de
  aislamiento es un atributo (owner/tenant) aplicado en todas las queries. El
  director debe decidir OQ-9 antes de Phase 2.

## 4. Manejo de uploads (skill `security`)

- **Validación MIME por contenido** (magic bytes), no por extensión
  (FR-DOC-5). El formato detectado determina el método de extracción.
- **Tamaño máximo** (archivo y páginas) aplicado ANTES de procesar
  (configurable, NFR-9; p. e.g. 20 MB / 50 páginas, NFR-6).
- **Filenames**: nombre seguro generado por el sistema (UUID); el nombre
  original nunca se usa en rutas ni en SQL (FR-DOC-4).
- **Path traversal**: nunca se concatena un filename de usuario a rutas; el
  nombre interno es un UUID generado por el sistema.
- **Almacenamiento fuera del webroot**; sin ejecución de scripts subidos.
- **PDFs maliciosos**: sin JavaScript/acciones; parser con timeout y límites
  de memoria; sandbox si es posible (el worker aísla los parsers).
- **Imágenes**: límites de dimensiones (decompression bomb); sanitizar.
- **Fingerprint**: se calcula al subir (SHA-256) y se verifica bajo demanda
  (NFR-3) para detectar alteración.

## 5. Trust boundary del pipeline OCR/LLM (FR-REV-5)

- **Contenido del documento = dato, nunca instrucción**: el texto/XML del
  documento se trata exclusivamente como dato de extracción. Si un documento
  contiene instrucciones dirigidas a un LLM (prompt injection), el pipeline
  las ignora: el prompt de extracción separa claramente "instrucciones del
  sistema" (fijas, del pipeline) de "datos del documento" (no fiables).
- **Output validado contra esquema estricto** (VR-SCHEMA-1): cualquier
  output del LLM que no cumpla el esquema se descarta. El LLM no puede
  "inventar" campos ni valores fuera del esquema.
- **Confidence y provenance obligatorias** (INV-11): el output del LLM es un
  valor extraído (N2) con confidence (típicamente menor) y provenance
  (método `vision_llm`). Requiere revisión humana si la confidence está por
  debajo del umbral (FR-VAL-4).
- **Nunca ejecutar código derivado de documentos**: el pipeline no evalúa
  contenido del documento como código.
- **XML**: sin DTD/external entities (XXE); schema validado (skill
  `security`).
- **Parsers con límites** (tamaño, profundidad, tiempo): timeouts y límites
  de memoria en todos los parsers (PDF, imagen, XML).

## 6. Secrets management

- **Secrets solo en entorno/secret manager**; nunca en código,
  configuración versionada ni logs (skill `security`; regla dura AGENTS.md
  #9).
- Credenciales de PostgreSQL, claves de cifrado, API keys de OCR/LLM (si se
  usan servicios externos): en el entorno de despliegue (podman secrets /
  variables de entorno), no en el repositorio.
- **Rotación** de credenciales de DB/documentos (skill `security`).
- El repositorio no contiene `.env`, credentials ni secretos (denegado por
  permisos de opencode).

## 7. Logs (sin datos financieros completos)

- **No se loguean**: documentos completos, NIF/CIF completos, importes
  completos de facturas de otros usuarios, tokens (NFR-7, skill `security`).
- **Sí se loguean**: eventos de seguridad (acceso denegado, intentos de
  subida fallidos), errores de sistema con motivo (sin datos financieros),
  trazas de extracción (método, confidence, sin el contenido del documento).
- **Auditoría ≠ logs**: la auditoría (E16, NFR-1) es un registro inmutable
  de dominio (append-only) que SÍ contiene los datos de negocio (antes/
  después) porque es el registro de trazabilidad; los logs operativos no.
- Los logs son estructurados (JSON) y no incluyen campos sensibles
  completos; si se incluye un identificador, es el ID interno (UUID), no el
  dato sensible.

## 8. Cifrado y protección de datos financieros

- **Cifrado en tránsito**: TLS entre cliente y API (y entre componentes si
  están en redes distintas).
- **Cifrado en reposo**: base de datos y volumen de documentos (skill
  `security`). El detalle (LUKS, TDE) es de Phase 2/devops.
- **Exportaciones**: solo datos del usuario; auditoría de exportes.
- **Retención**: política de borrado de documentos y datos personales
  (OQ-10, pendiente).

## 9. Inyección y dependencias

- **SQL**: solo ORM/queries parametrizadas (skill `security`).
- **Comandos**: sin interpolación de entrada de usuario (el worker invoca
  parsers con argumentos controlados, no con contenido de usuario).
- **Templates/UI**: sin renderizado de HTML no sanitizado (el contenido del
  documento se muestra como dato, no como HTML).
- **Dependencias**: pinneadas; auditoría periódica de CVEs; mínimo de
  dependencias; justificar las de parsing de documentos (skill `security`).
