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

- **G1 (MEDIUM)**: PDFs maliciosos (JavaScript/acciones, bombas de
  descompresión, PDFs con miles de páginas). Se menciona "sandbox si es
  posible" pero no se garantiza. El worker aísla parsers (ADR-0004), pero el
  límite de memoria/tiempo por parser debe ser **obligatorio y medible**, no
  opcional.
- **G2 (MEDIUM)**: Imágenes con dimensiones extremas (decompression bomb) →
  DoS en OCR. Se menciona "límites de dimensiones" pero sin valores concretos
  ni política de sanitización definida.
- **G3 (LOW)**: El contrato OpenAPI no especifica explícitamente el
  `Content-Type` aceptado ni el límite de tamaño en la operación de subida
  (solo se declara en arquitectura). Debe fijarse en el contrato para que el
  cliente/servidor lo aplique de forma consistente.

**Recomendaciones**:

- Fijar valores concretos de límites (páginas, dimensiones, profundidad) y
  hacerlos configurables (NFR-9).
- Definir política de sanitización de imágenes y PDFs (stripping de
  JS/acciones) como requisito de Phase 2.
- Asegurar que el worker ejecute parsers con **timeout + límite de memoria**
  por diseño (no "si es posible").

## 3. Parsers

**Mitigaciones presentes** (07-sec §5, ADR-0004):

- Parsers con límites (tamaño, profundidad, tiempo) y de memoria.
- Worker aísla los parsers (ADR-0004: modular monolith con workers
  separados).
- XML: sin DTD/external entities (XXE); schema validado.

**Gaps / riesgos**:

- **G4 (MEDIUM)**: El aislamiento del worker (ADR-0004) es a nivel de
  proceso, pero no se describe el mecanismo de sandbox (contenedor, seccomp,
  límites cgroup). Un parser comprometido (p. e.g. librería de PDF con CVE)
  podría escapar del proceso.
- **G5 (LOW)**: Las dependencias de parsing (PDF, imagen, XML) deben ser
  **pinneadas y auditadas** (07-sec §9). No se prescribe aún el inventario de
  dependencias; debe hacerse en Phase 2.

**Recomendaciones**:

- Especificar el mecanismo de sandbox del worker (p. e.g. contenedor con
  límites de CPU/memoria/disco, sin red saliente) como requisito de Phase 2.
- Inventario de dependencias de parsing con política de actualización y
  auditoría de CVEs.

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
  confidence < umbral (OQ-1, por defecto 0.9).
- **G7 (MEDIUM)**: El umbral de confidence (OQ-1) **no está decidido**. Si se
  fija demasiado alto, se reduce la revisión humana y aumenta el riesgo de
  aceptar valores inyectados. Si se fija demasiado bajo, se satura la
  revisión.
- **G8 (LOW)**: No se prescribe si el LLM se usa como servicio externo (API
  key) o local. Si es externo, el contenido del documento sale del perímetro
  → riesgo de confidencialidad (NFR-7) y dependencia de un tercero.

**Recomendaciones**:

- Decidir OQ-1 (umbral de confidence) **antes de Phase 2**, idealmente con
  umbrales por método (XML > LLM).
- Si se usa LLM externo, definir política de datos (qué se envía, cifrado,
  DPA) y evaluar alternativa local.
- Considerar **validación cruzada** (p. e.g. comparar valores extraídos por
  OCR con los del XML si existe) para reducir el riesgo de inyección.
- Documentar el prompt de extracción como artefacto versionado y revisable
  (no solo "fijo").

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
- **G10 (MEDIUM)**: El mecanismo de autenticación (JWT vs cookie opaca)
  **no está decidido** (se deja para Phase 2). Esto afecta a la gestión de
  sesiones, revocación y expiración.
- **G11 (LOW)**: No se describe la política de **revocación** de
  tokens/sesiones (p. e.g. en cambio de contraseña o cierre de sesión).
- **G12 (LOW)**: No se prescribe la política de **contraseñas** (longitud,
  complejidad, hash) ni el mecanismo de recuperación de cuenta.

**Recomendaciones**:

- OQ-9 **resuelta (ADR-0008)**: el diseño de authZ debe implementar
  usuario→organización y roles dentro de la organización (ver G14).
- Decidir el mecanismo de autenticación (JWT vs cookie) y la política de
  revocación.
- Definir política de contraseñas y recuperación de cuenta.
- Asegurar que el filtro por owner/tenant se aplique **en la capa de
  persistencia** (no solo en la UI) y que haya tests de aislamiento
  (criterio NFR-7).

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
  diseño en Phase 2 (V8-S2, authZ).
- **G15 (LOW → RESUELTO, ADR-0008)**: los recursos compartidos (catálogos:
  `categories`, `payment_methods`, `tax_rates`, `suppliers`) son **por
  organización** (llevan `owner_id` = `organization_id`). `currencies` es
  global (ISO-4217).

**Recomendaciones**:

- OQ-9 **resuelta (ADR-0008)**: implementar el filtro por `owner_id`
  (= `organization_id`) en la capa de persistencia y tests de aislamiento.
- Rediseñar el modelo de roles para incluir roles **por organización** (G14).
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

**Recomendaciones**:

- Definir el mecanismo de secret manager en Phase 2.
- Documentar la política de rotación de credenciales.

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

**Recomendaciones**:

- Automatizar la verificación de aislamiento (búsqueda de referencias) como
  parte del quality gate.
- Añadir un test de aislamiento que falle si aparece una referencia a
  FacturaE.

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

- **G20 (LOW)**: No se prescribe el **mecanismo de inmutabilidad** del
  registro de auditoría (p. e.g. append-only a nivel de DB, hash chain, WORM
  storage).
- **G21 (LOW)**: No se describe la **retención** de la auditoría (OQ-10,
  pendiente). Si hay obligación legal de retención (5-10 años), el diseño de
  almacenamiento debe contemplarlo.
- **G22 (LOW)**: No se prescribe el **acceso** al registro de auditoría
  (quién puede consultarlo, si es solo admin).

**Recomendaciones**:

- Definir el mecanismo de inmutabilidad del registro de auditoría en Phase 2.
- Decidir OQ-10 (retención) antes de Phase 2.
- Definir la política de acceso al registro de auditoría.

## 10. Riesgos residuales y recomendaciones

**Riesgos residuales principales** (ordenados por severidad):

1. **OQ-9 (modelo de tenancy) — RESUELTO (ADR-0008)**: aislamiento por
   organización. Riesgo residual: implementación correcta del filtro por
   `owner_id` en todas las queries (tests de aislamiento).
2. **Prompt injection indirecta** — MEDIUM. Mitigado por esquema estricto +
   revisión humana, pero el umbral de confidence (OQ-1) no está decidido.
3. **Uploads maliciosos (DoS/RCE)** — MEDIUM. Mitigado por límites y
   aislamiento del worker, pero el sandbox no está garantizado.
4. **Cifrado en reposo** — MEDIUM. Pendiente de Phase 2.
5. **Mecanismo de autenticación no decidido** — MEDIUM. Afecta a la gestión
   de sesiones y revocación.

**Recomendaciones globales**:

- **Decidir OQ-1 antes de Phase 2** (bloqueante). OQ-9 resuelta (ADR-0008).
- **Decidir OQ-10 (retención)** antes de Phase 2.
- **Especificar el sandbox del worker** (mecanismo, límites) como requisito
  de Phase 2.
- **Automatizar la verificación de aislamiento** de FacturaE (NFR-10).
- **Definir el mecanismo de inmutabilidad** del registro de auditoría.
- **Inventario de dependencias** de parsing con política de CVEs.
- **Documentar el prompt de extracción** como artefacto versionado.

## 11. Decisiones necesarias del director

| # | Decisión | Impacto | Severidad |
|---|---|---|---|
| D1 | **OQ-9**: modelo de tenancy — **RESUELTO (ADR-0008)**: organización multi-usuario | Aislamiento de datos, modelo de roles, authZ | HIGH → resuelta |
| D2 | **OQ-1**: umbral de confidence (y si varía por método) | Revisión humana, riesgo de prompt injection | MEDIUM |
| D3 | **OQ-10**: retención de documentos y auditoría | Almacenamiento, cumplimiento legal | MEDIUM |
| D4 | Mecanismo de autenticación (JWT vs cookie) y política de revocación | Gestión de sesiones, seguridad | MEDIUM |
| D5 | Si se usa LLM externo (API) o local | Confidencialidad, dependencia de terceros | MEDIUM |
| D6 | Mecanismo de sandbox del worker (contenedor, límites) | Aislamiento de parsers, DoS/RCE | MEDIUM |
| D7 | Mecanismo de inmutabilidad del registro de auditoría | Trazabilidad, no repudio | LOW |
| D8 | Política de recursos compartidos (catálogos) por tenant — **RESUELTO (ADR-0008)**: por organización | Catálogos por organización; `currencies` global | LOW → resuelta |

**Fin del threat review (PHASE1-004).** No se han modificado ni creado
archivos por el subagente security (read-only); este archivo es la
materialización del informe por el director (condición C2 de la revisión
PHASE1-005).
