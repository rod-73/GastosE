# Threat review temprano — GastosE (PHASE1-004)

- **Tarea**: PHASE1-004 (estado: ACCEPTED).
- **Autor**: subagente `security` (read-only).
- **Fecha**: 2026-08-31.
- **Fase**: Phase 1 — solo documentación y diseño. No hay código de aplicación.
- **Alcance**: uploads, parsers, OCR/LLM, auth, aislamiento por usuario,
  secrets, aislamiento FacturaE, auditoría/logs.
- **Entrada consumida**: `docs/requirements/` (NFR-1..10, INV-1..15,
  FR-DOC/EXT/REV/ACC/FST, OQ-1..18), `docs/architecture/` (02-components,
  03-flows, 04-async, 05-failure, 06-facturae-isolation,
  07-security-boundaries), `docs/api/openapi.yaml`, ADR-0001..0007.

> Nota: la skill `security` no estaba disponible en este entorno; se
> aplicaron checklists de seguridad estándar (OWASP / threat-modeling STRIDE)
> de forma manual.

## 1. Modelo de amenazas (resumen)

**Activos a proteger**

- Datos financieros (importes, NIF/CIF, documentos fuente) — confidencialidad
  (NFR-7).
- Integridad del documento fuente (INV-9, NFR-3) y de los hechos contables
  aceptados (INV-14).
- Trazabilidad / no repudio (NFR-1, INV-10).
- Disponibilidad del pipeline de extracción (NFR-8).
- Aislamiento de FacturaE (ADR-0001, NFR-10).

**Amenazas principales (STRIDE condensado)**

| # | Amenaza | Superficie | Mitigación existente | Severidad residual |
|---|---|---|---|---|
| T1 | Prompt injection desde contenido de documento → LLM | OCR/LLM | Trust boundary 2/3 (07-sec §1, §5); esquema estricto VR-SCHEMA-1; confidence/provenance INV-11 | MEDIUM |
| T2 | Upload malicioso (PDF/imagen/XML) → RCE/DoS en worker | Uploads | MIME por magic bytes, tamaño máx., UUID, fuera webroot, timeouts/limits, sandbox (07-sec §4) | MEDIUM |
| T3 | Aislamiento por usuario (IDOR) → acceso cruzado a datos financieros | AuthZ | Filtro por owner en cada query; owner de sesión (07-sec §3) | HIGH (si OQ-9 no se decide) |
| T4 | Secrets expuestos (DB, claves OCR/LLM) | Secrets | Solo entorno/secret manager; no en repo (07-sec §6) | LOW |
| T5 | Acoplamiento accidental a FacturaE | Aislamiento | ADR-0001; prohibiciones (06-facturae §1); verificable NFR-10 | LOW |
| T6 | Alteración del documento fuente | Integridad | Fingerprint SHA-256 + verificación (NFR-3, INV-9) | LOW |
| T7 | LLM "inventa" valores fuera de esquema | OCR/LLM | VR-SCHEMA-1 descarta output no conforme; INV-8 solo se acepta lo validado | LOW |
| T8 | DoS por cola de extracción / reintentos | Async | Cola DB + claim atómico + reintentos (ADR-0005) | MEDIUM |
| T9 | Logs/auditoría con datos sensibles | Logs | No se loguean documentos/NIF/importes completos (07-sec §7) | LOW |
| T10 | Cifrado en reposo insuficiente | Datos | TLS en tránsito; reposo pendiente Phase 2 (07-sec §8) | MEDIUM |

## 2. Uploads

**Mitigaciones presentes** (07-sec §4, FR-DOC-4/5):

- Validación MIME por **contenido** (magic bytes), no por extensión.
- Límite de tamaño (archivo y páginas) **antes** de procesar (NFR-6, NFR-9).
- Filename interno **UUID** generado por el sistema; el nombre original nunca
  se usa en rutas/SQL → mitiga path traversal.
- Almacenamiento **fuera del webroot**; sin ejecución de scripts.
- Fingerprint SHA-256 al subir (NFR-3).

**Gaps / riesgos**:

- **G1 (MEDIUM → RESUELTO, ADR-0011)**: PDFs maliciosos (JavaScript/acciones,
  bombas de descompresión, PDFs con miles de páginas). El worker se ejecuta
  en contenedor podman con límites cgroup (memoria, CPU, timeout por
  operación/parser), no-root, seccomp, filesystem restringido, documento
  fuente montado read-only. Los límites son configurables (NFR-9) y se
  validan mediante pruebas en Phase 2.
- **G2 (MEDIUM → RESUELTO, ADR-0011)**: Imágenes con dimensiones extremas
  (decompression bomb) → DoS en OCR. Límite de dimensiones de imagen
  (default 10.000 × 10.000 px, configurable) como parte del sandbox del
  worker.
- **G3 (LOW)**: El contrato OpenAPI no especifica explícitamente el
  `Content-Type` aceptado ni el límite de tamaño en la operación de subida
  (solo se declara en arquitectura). Debe fijarse en el contrato para que el
  cliente/servidor lo aplique de forma consistente. — Pendiente Phase 2.

**Recomendaciones** (estado 2026-09-01):

- **RESUELTO (ADR-0011)**: valores de límites (páginas, dimensiones,
  profundidad) documentados como defaults/candidatos iniciales, configurables
  (NFR-9), a validar mediante pruebas en Phase 2.
- Definir política de sanitización de imágenes y PDFs (stripping de
  JS/acciones) como requisito de Phase 2.
- **RESUELTO (ADR-0011)**: el worker ejecuta parsers con **timeout + límite
  de memoria** por diseño (cgroup, no "si es posible").

## 3. Parsers

**Mitigaciones presentes** (07-sec §5, ADR-0004):

- Parsers con límites (tamaño, profundidad, tiempo) y de memoria.
- Worker aísla los parsers (ADR-0004: modular monolith con workers
  separados).
- XML: sin DTD/external entities (XXE); schema validado.

**Gaps / riesgos**:

- **G4 (MEDIUM → RESUELTO, ADR-0011)**: El aislamiento del worker es a nivel
  de **contenedor podman** (kernel-level), con seccomp/AppArmor, usuario
  no-root, filesystem restringido, documento fuente montado read-only. Un
  parser comprometido no puede escapar del contenedor.
- **G5 (LOW)**: Las dependencias de parsing (PDF, imagen, XML) deben ser
  **pinneadas y auditadas** (07-sec §9). No se prescribe aún el inventario de
  dependencias; debe hacerse en Phase 2. (El sandbox de ADR-0011 no
  sustituye la auditoría de dependencias; la contiene.)

**Recomendaciones** (estado 2026-09-01):

- **RESUELTO (ADR-0011)**: mecanismo de sandbox del worker especificado:
  contenedor podman con límites cgroup (CPU/memoria), no-root, seccomp,
  filesystem restringido, network egress restringido al mínimo necesario
  (endpoint ExtractionLLM + BD).
- Inventario de dependencias de parsing con política de actualización y
  auditoría de CVEs — pendiente Phase 2.

## 4. OCR/LLM — trust boundary

**Mitigaciones presentes** (07-sec §1, §5; FR-REV-5; INV-8, INV-11;
VR-SCHEMA-1):

- **Trust boundary 2**: contenido del documento = dato, nunca instrucción.
- **Trust boundary 3**: output del LLM no se confía; se valida contra esquema
  estricto (VR-SCHEMA-1) y se marca con confidence/provenance (INV-11).
- El prompt separa "instrucciones del sistema" (fijas) de "datos del
  documento" (no fiables).
- Nunca se ejecuta código derivado de documentos.
- INV-8: solo se acepta lo validado → `LLM OUTPUT != ACCOUNTING FACT`.

**Gaps / riesgos**:

- **G6 (MEDIUM)**: **Prompt injection indirecta** sigue siendo un riesgo
  residual. Aunque el esquema estricto descarta outputs no conformes, un LLM
  puede ser inducido a producir valores **conformes al esquema pero
  incorrectos** (p. e.g. cambiar un importe dentro del rango válido). La
  mitigación principal es la **revisión humana** (FR-VAL-4) cuando la
  confidence < umbral. **RESUELTO (D2, 2026-09-01)**: la política de
  confidence es configurable (no thresholds fijos); la confidence nunca
  constituye por sí sola aceptación contable; debe combinarse con provenance,
  validaciones determinísticas, reglas de negocio, estado del documento y
  revisión humana cuando corresponda.
- **G7 (MEDIUM → RESUELTO, D2)**: El umbral de confidence (OQ-1) es
  **configurable** (NFR-9). No se adoptan thresholds numéricos fijos como
  política definitiva. Los thresholds definitivos se calibrarán
  posteriormente utilizando un corpus representativo de documentos reales.
  Hasta entonces son configurables y no constituyen una decisión
  arquitectónica irreversible.
- **G8 (LOW → RESUELTO, ADR-0010)**: La abstracción `ExtractionLLM`
  (provider-neutral) aísla la aplicación de cualquier proveedor concreto.
  El backend por defecto es **local** (endpoint compatible con OpenAI). Los
  proveedores externos son una alternativa configurable. Si se usa un
  proveedor externo, el contenido del documento sale del perímetro → la
  política de datos se define en el despliegue.

**Recomendaciones** (estado 2026-09-01):

- **RESUELTO (D2)**: OQ-1 (umbral de confidence) resuelta: política
  configurable, no thresholds fijos; confidence ≠ aceptación automática.
  Calibración de thresholds con corpus representativo: tarea de Phase 2, no
  bloqueante.
- **RESUELTO (ADR-0010)**: LLM local por defecto (endpoint compatible con
  OpenAI). Si se usa LLM externo, la política de datos (qué se envía,
  cifrado, DPA) se define en el despliegue.
- Considerar **validación cruzada** (p. e.g. comparar valores extraídos por
  OCR con los del XML si existe) para reducir el riesgo de inyección —
  pendiente Phase 2.
- Documentar el prompt de extracción como artefacto versionado y revisable
  (no solo "fijo") — pendiente Phase 2.

## 5. AuthN / AuthZ

**Mitigaciones presentes** (07-sec §2; NFR-7; openapi.yaml):

- Autenticación obligatoria en todos los endpoints (salvo `/healthz`).
- Esquema `bearerAuth` (token opaco o cookie de sesión) — openapi.yaml
  §securitySchemes.
- Autorización por rol: `reader`, `reviewer`, `approver`, `admin` (mínimo
  privilegio).
- Solo `approver` acepta gastos (NFR-7).
- Object-level authorization: filtro por owner en cada query, owner derivado
  de la sesión (07-sec §3).
- Rate limiting en login y endpoints costosos.

**Gaps / riesgos**:

- **G9 (HIGH → MITIGADO, ADR-0008)**: OQ-9 (modelo de tenancy) **resuelta
  (2026-08-31)**: aislamiento por **organización (multi-usuario)**.
  `owner_id` = `organization_id`; el filtro de propietario se aplica sobre la
  organización derivada de la sesión. Riesgo de IDOR mitigado siempre que el
  filtro por `owner_id` se aplique en la capa de persistencia (ver §6).
- **G10 (MEDIUM → RESUELTO, ADR-0009)**: El mecanismo de autenticación es
  **token opaco + sesión server-side persistida en BD**. El token es opaco
  (no JWT); la sesión se persiste en la tabla `sessions` con expiración por
  inactividad y absoluta, y revocación inmediata por usuario y por
  organización.
- **G11 (LOW → RESUELTO, ADR-0009)**: La política de **revocación** es
  inmediata: cierre de sesión, cambio de contraseña, desactivación de
  usuario, desactivación de organización.
- **G12 (LOW → RESUELTO, ADR-0009)**: La política de **contraseñas** es hash
  con algoritmo adaptativo (argon2id o bcrypt), longitud mínima configurable.
  Recuperación de cuenta: fuera de scope de Phase 2 v1 (1 org + 1 usuario,
  ADR-0008).

**Recomendaciones** (estado 2026-09-01):

- OQ-9 **resuelta (ADR-0008)**: el diseño de authZ debe implementar
  usuario→organización y roles dentro de la organización (ver G14).
- **RESUELTO (ADR-0009)**: mecanismo de autenticación (token opaco + sesión
  server-side en BD) y política de revocación (inmediata por usuario y
  organización).
- **RESUELTO (ADR-0009)**: política de contraseñas (hash adaptativo,
  longitud mínima configurable). Recuperación de cuenta: fuera de scope v1.
- Asegurar que el filtro por owner/tenant se aplique **en la capa de
  persistencia** (no solo en la UI) y que haya tests de aislamiento
  (criterio NFR-7) — pendiente Phase 2 (V8-S2).

## 6. Aislamiento por usuario / tenant (OQ-9)

**Mitigaciones presentes** (07-sec §3; NFR-7):

- Filtro por propietario en cada query (a nivel de servicio/persistencia).
- El propietario se deriva de la sesión autenticada (nunca de un parámetro de
  la petición).
- Test de aislamiento: usuario A no ve recurso de B.

**Gaps / riesgos**:

- **G13 (HIGH → MITIGADO, ADR-0008)**: OQ-9 **resuelta**: aislamiento por
  organización. El modelo de aislamiento queda fijado; el riesgo residual es
  la implementación correcta del filtro por `owner_id` en todas las queries
  (tests de aislamiento, criterio NFR-7).
- **G14 (MEDIUM, APLICABLE)**: el modelo es por organización, por lo que se
  necesitan **roles dentro de la organización** (p. e.g. un admin de empresa
  que no es admin global). El modelo actual de roles
  (reader/reviewer/approver/admin) debe reinterpretarse como **por
  organización** (atributo del usuario en su organización). Pendiente de
  diseño en Phase 2 (V8-S2, authZ). **RESUELTO (ADR-0009)**: el rol se
  almacena en la sesión y se actualiza si cambia (la siguiente petición
  refleja el nuevo rol).
- **G15 (LOW → RESUELTO, ADR-0008)**: los recursos compartidos (catálogos:
  `categories`, `payment_methods`, `tax_rates`, `suppliers`) son **por
  organización** (llevan `owner_id` = `organization_id`). `currencies` es
  global (ISO-4217).

**Recomendaciones** (estado 2026-09-01):

- OQ-9 **resuelta (ADR-0008)**: implementar el filtro por `owner_id`
  (= `organization_id`) en la capa de persistencia y tests de aislamiento —
  pendiente Phase 2 (V8-S2).
- Rediseñar el modelo de roles para incluir roles **por organización** (G14)
  — pendiente Phase 2 (V8-S2).
- Política de recursos compartidos: **por organización** (G15, ADR-0008).

## 7. Secrets

**Mitigaciones presentes** (07-sec §6; AGENTS.md regla 9):

- Secrets solo en entorno/secret manager; nunca en código, config versionada
  ni logs.
- Credenciales de PostgreSQL, claves de cifrado, API keys de OCR/LLM en el
  entorno de despliegue.
- Rotación de credenciales.
- El repositorio no contiene `.env`, credentials ni secretos (denegado por
  permisos).

**Gaps / riesgos**:

- **G16 (LOW)**: No se prescribe el **mecanismo concreto** de secret manager
  (podman secrets, Vault, etc.). Se deja para Phase 2/devops.
- **G17 (LOW)**: No se describe la política de **rotación** (frecuencia,
  procedimiento).

**Recomendaciones** (estado 2026-09-01):

- Definir el mecanismo de secret manager en Phase 2 — pendiente.
- Documentar la política de rotación de credenciales — pendiente Phase 2.

## 8. Aislamiento de FacturaE (ADR-0001)

**Mitigaciones presentes** (06-facturae-isolation; ADR-0001; NFR-10):

- Prohibiciones explícitas: sin compartir código, ORM, DB, tablas,
  migraciones, almacenamiento.
- Garantías arquitectónicas: sin dependencias en el grafo, DB propia,
  almacenamiento propio, migraciones propias, despliegue independiente.
- Verificable (NFR-10): no hay referencias a `/workspace/facturaE`.
- Riesgo de acoplamiento accidental mitigado por regla dura en AGENTS.md +
  revisión + tool `scope-check`/`lint`.

**Gaps / riesgos**:

- **G18 (LOW)**: La verificación de aislamiento (NFR-10) **no está
  automatizada** aún. Se menciona que "puede automatizarse" como parte del
  quality gate, pero no se ha implementado.
- **G19 (LOW)**: No se prescribe un **test de aislamiento** (p. e.g. un test
  que falle si aparece una referencia a `/workspace/facturaE` en el
  código/config).

**Recomendaciones** (estado 2026-09-01):

- Automatizar la verificación de aislamiento (búsqueda de referencias) como
  parte del quality gate — pendiente Phase 2.
- Añadir un test de aislamiento que falle si aparece una referencia a
  FacturaE — pendiente Phase 2.

## 9. Auditoría y logs

**Mitigaciones presentes** (07-sec §7; NFR-1; INV-10):

- Registro de auditoría inmutable (E16, append-only) con datos de negocio
  (antes/después).
- Logs operativos **sin** datos financieros completos (no se loguean
  documentos, NIF/CIF, importes completos, tokens).
- Los logs son estructurados (JSON) y usan IDs internos (UUID), no datos
  sensibles.
- Auditoría ≠ logs: la auditoría contiene datos de negocio; los logs
  operativos no.

**Gaps / riesgos**:

- **G20 (LOW → RESUELTO, ADR-0012)**: El **mecanismo de inmutabilidad** es
  append-only a nivel de persistencia: INSERT permitido, SELECT permitido
  según autorización, UPDATE prohibido, DELETE prohibido. Se aplica mediante
  permisos de BD y/o trigger. Hash-chain NO es requisito de V1 (posible
  hardening futuro).
- **G21 (LOW → RESUELTO, D3/OQ-10)**: La **retención** de la auditoría es
  indefinida en V1 (sin purga automática). Los `audit_events` no tendrán
  eliminación automática en V1. Una futura política/job de purga deberá
  respetar invariantes de trazabilidad, auditoría e integridad.
- **G22 (LOW → RESUELTO, ADR-0012)**: El **acceso** al registro de auditoría
  es solo lectura, restringido a roles autorizados (recomendado:
  `admin`/`approver`).

**Recomendaciones** (estado 2026-09-01):

- **RESUELTO (ADR-0012)**: mecanismo de inmutabilidad del registro de
  auditoría: append-only a nivel de persistencia (permisos + trigger).
- **RESUELTO (D3/OQ-10)**: retención de la auditoría: indefinida en V1 (sin
  purga automática).
- **RESUELTO (ADR-0012)**: política de acceso al registro de auditoría: solo
  lectura, restringido a roles autorizados (recomendado: `admin`/`approver`).

## 10. Riesgos residuales y recomendaciones

**Riesgos residuales principales** (ordenados por severidad):

1. **OQ-9 (modelo de tenancy) — RESUELTO (ADR-0008)**: aislamiento por
   organización. Riesgo residual: implementación correcta del filtro por
   `owner_id` en todas las queries (tests de aislamiento).
2. **Prompt injection indirecta** — MEDIUM. Mitigado por esquema estricto +
   revisión humana. El umbral de confidence (OQ-1) es **configurable** (D2
   resuelta); la calibración con corpus representativo es tarea de Phase 2.
3. **Uploads maliciosos (DoS/RCE)** — MEDIUM. Mitigado por límites y
   aislamiento del worker en contenedor (ADR-0011: sandbox con límites
   cgroup, no-root, seccomp, network egress restringido).
4. **Cifrado en reposo** — MEDIUM. Pendiente de Phase 2.
5. **Mecanismo de autenticación** — RESUELTO (ADR-0009): token opaco +
   sesión server-side en BD con revocación inmediata.

**Recomendaciones globales** (estado 2026-09-01):

- **OQ-1 (D2) resuelta**: política de confidence configurable; calibración
  de thresholds con corpus representativo en Phase 2 (no bloqueante).
- **OQ-10 (D3) resuelta**: sin purga automática en V1; políticas
  configurables por org/tipo/estado.
- **Sandbox del worker (D6) resuelto**: ADR-0011 (contenedor podman + límites
  cgroup + no-root + seccomp + network egress restringido).
- **Mecanismo de autenticación (D4) resuelto**: ADR-0009 (token opaco +
  sesión server-side en BD).
- **LLM (D5) resuelto**: ADR-0010 (abstracción `ExtractionLLM`
  provider-neutral, backend local por defecto).
- **Inmutabilidad de auditoría (D7) resuelta**: ADR-0012 (append-only BD con
  permisos + trigger; hash-chain no es requisito de V1).
- **Automatizar la verificación de aislamiento** de FacturaE (NFR-10) —
  pendiente Phase 2.
- **Inventario de dependencias** de parsing con política de CVEs — pendiente
  Phase 2.
- **Documentar el prompt de extracción** como artefacto versionado — pendiente
  Phase 2.

## 11. Decisiones necesarias del director

| # | Decisión | Impacto | Severidad |
|---|---|---|---|
| D1 | **OQ-9**: modelo de tenancy — **RESUELTO (ADR-0008)**: organización multi-usuario | Aislamiento de datos, modelo de roles, authZ | HIGH → resuelta |
| D2 | **OQ-1**: umbral de confidence (y si varía por método) — **RESUELTO (2026-09-01)**: política configurable, no thresholds fijos; confidence ≠ aceptación automática; calibración con corpus en Phase 2 | Revisión humana, riesgo de prompt injection | MEDIUM → resuelta |
| D3 | **OQ-10**: retención de documentos y auditoría — **RESUELTO (2026-09-01)**: sin purga automática en V1; políticas configurables por org/tipo/estado; sin plazos legales hardcoded | Almacenamiento, cumplimiento legal | MEDIUM → resuelta |
| D4 | Mecanismo de autenticación (JWT vs cookie) y política de revocación — **RESUELTO (ADR-0009)**: token opaco + sesión server-side en BD; revocación por usuario y organización | Gestión de sesiones, seguridad | MEDIUM → resuelta |
| D5 | Si se usa LLM externo (API) o local — **RESUELTO (ADR-0010)**: abstracción `ExtractionLLM` provider-neutral; backend por defecto local (endpoint compatible con OpenAI) | Confidencialidad, dependencia de terceros | MEDIUM → resuelta |
| D6 | Mecanismo de sandbox del worker (contenedor, límites) — **RESUELTO (ADR-0011)**: contenedor podman + límites cgroup + no-root + seccomp + network egress restringido | Aislamiento de parsers, DoS/RCE | MEDIUM → resuelta |
| D7 | Mecanismo de inmutabilidad del registro de auditoría — **RESUELTO (ADR-0012)**: append-only BD (permisos + trigger); hash-chain no es requisito de V1 | Trazabilidad, no repudio | LOW → resuelta |
| D8 | Política de recursos compartidos (catálogos) por tenant — **RESUELTO (ADR-0008)**: por organización | Catálogos por organización; `currencies` global | LOW → resuelta |

**Fin del threat review (PHASE1-004).** No se han modificado ni creado
archivos por el subagente security (read-only); este archivo es la
materialización del informe por el director (condición C2 de la revisión
PHASE1-005).

**Actualización 2026-09-01 (PHASE2-000)**: decisiones D2..D7 resueltas.
D2/D3 por política configurable (OQ-1/OQ-10 actualizadas); D4 por ADR-0009;
D5 por ADR-0010; D6 por ADR-0011; D7 por ADR-0012. Gaps G1, G2, G4, G6, G7,
G8, G10, G11, G12, G20, G21, G22 marcados como RESUELTO. Gaps pendientes
para Phase 2: G3, G5, G14, G16, G17, G18, G19.
