# ADR-0011: Extraction worker sandbox and resource isolation

Status: accepted
Date: 2026-09-01
Resuelve: D6 del threat review (docs/security/threat-review.md), G1/G2/G4/G5.

## Context

El worker de extracción (ADR-0004) ejecuta parsers de PDF/imagen/XML y el LLM
(ADR-0010). El threat review (PHASE1-004) identificó que el aislamiento del
worker es a nivel de proceso (ADR-0004) pero no se describe el mecanismo de
sandbox (G4, MEDIUM), que los límites de memoria/tiempo por parser deben ser
obligatorios y medibles (G1, MEDIUM), que las imágenes con dimensiones
extremas pueden causar DoS (G2, MEDIUM), y que las dependencias de parsing
deben ser pinneadas y auditadas (G5, LOW).

El runtime es podman 5.8.2 (docker CLI lo emula). ADR-0004/0005/0006 ya
asumen contenedores.

## Decision

El worker de extracción se ejecuta **aislado en un contenedor (podman)** con
los siguientes mecanismos de aislamiento y límites:

### Aislamiento

- **Contenedor**: el worker corre en un contenedor podman (no en el proceso
  de la API). El aislamiento es kernel-level (mitiga CVE en librerías de
  parsing, G4).
- **Usuario no-root**: el contenedor corre como usuario no-root (mínimo
  privilegio).
- **seccomp/AppArmor** (o mecanismo equivalente disponible): perfil
  restrictivo de syscalls.
- **Filesystem restringido**: el contenedor solo tiene acceso a los
  filesystems que necesita (volumen de documentos, BD). Sin acceso al
  filesystem del host.
- **Documento fuente montado read-only**: el volumen de documentos se monta
  solo de lectura en el contenedor (refuerza INV-9, inmutabilidad del
  documento fuente).

### Límites de recursos (cgroup)

Los siguientes límites se aplican mediante cgroup. Los valores indicados son
**defaults/candidatos iniciales**, NO constantes arquitectónicas definitivas.
Deben ser **configurables** (NFR-9) y **validados mediante pruebas** en Phase
2:

- **Memoria por worker**: default 1-2 GB (cgroup `memory.max`).
- **CPU por worker**: default 1-2 cores (cgroup `cpu.max`).
- **Timeout por operación/parser**: default 20-60 s (PDF 30 s, OCR 20 s, LLM
  60 s — alineado con NFR-6: < 60 s por documento).
- **Límite de tamaño documental**: default 20 MB (NFR-6).
- **Límite de páginas**: default 50 (NFR-6).
- **Límite de dimensiones de imagen**: default 10.000 × 10.000 px
  (decompression bomb, G2).

### Network policy

- **Sin acceso de red arbitrario**: el contenedor del worker NO tiene acceso
  de red por defecto.
- **Egress restringido al mínimo necesario**: el worker solo puede realizar
  egress hacia servicios explícitamente autorizados que necesite para su
  función. Específicamente:
  - El endpoint configurado de `ExtractionLLM` (ADR-0010), ya sea local o
    externo.
  - La base de datos PostgreSQL (claim de tareas, persistencia de valores).
- **Esto funciona tanto si `ExtractionLLM` apunta a infraestructura local
  como a proveedor externo**: la política de red se configura según el
  endpoint del LLM.

### Dependencias

- **Pinneadas y auditadas** (G5): las librerías de parsing (PDF, imagen, XML)
  se pinnean en el Dockerfile/requirements y se auditan periódicamente (CVEs).
  El sandbox no sustituye la auditoría de dependencias; la contiene.

### Fallo por exceder límites

- Si una tarea excede los límites (memoria, tiempo, dimensiones), el worker
  la marca como `failed` con motivo (FR-FST-1, INV-15). El contenedor se
  reinicia si es necesario (el lease/timeout de la cola, ADR-0005, gestiona
  workers muertos).

## Alternatives considered

1. **Worker en proceso separado (sin contenedor)** con límites de
   memoria/tiempo por parser (ulimit, timeouts en Python). Rechazado: el
   aislamiento es a nivel de proceso, no kernel-level; un parser comprometido
   (CVE en librería de PDF) podría escapar del proceso (G4).
2. **Worker en contenedor + micro-sandbox por parser** (cada parser en un
   proceso hijo aislado o en un contenedor efímero). Rechazado: complejidad
   operativa desproporcionada para el volumen bajo (~1.000 docs/mes).
3. **Worker en contenedor (podman) con límites cgroup (elegido)**: el runtime
   es podman (ADR-0004/0005/0006 ya asumen contenedores) → el sandbox es
   nativo. El aislamiento kernel-level mitiga G4. Los límites cgroup hacen
   obligatorios y medibles los límites (G1). El volumen de documentos se
   monta solo de lectura (refuerza INV-9).

## Consequences

- **Positivas**:
  - Aislamiento kernel-level (G4): un parser comprometido no afecta a la API
    ni a la BD.
  - Límites obligatorios y medibles (G1): memoria, CPU, tiempo, tamaño,
    páginas, dimensiones.
  - Contención de decompression bomb (G2): límite de dimensiones de imagen.
  - Network egress restringido (mínimo privilegio): solo al endpoint LLM y a
    la BD.
  - Documento fuente read-only (refuerza INV-9).
  - Sin componente nuevo: el contenedor ya es parte del despliegue
    (ADR-0004/0005/0006).
- **Negativas / riesgos**:
  - Complejidad operativa del despliegue (configurar cgroup, seccomp, red).
  - Los límites por defecto pueden no ser adecuados para todos los
    documentos; hay que validarlos con pruebas (NFR-9).
- **Reversibilidad**: **Alta**. El sandbox es una capa de despliegue; el
  contrato de cola (ADR-0005) y la API no cambian. Migrar de contenedor a
  proceso (o viceversa) no afecta al dominio. Los límites son configurables
  (NFR-9).

## Implicaciones

- **Slices**: V2-S1 (worker de extracción: ejecución con sandbox, timeouts,
  límites).
- **DevOps**: `docker-compose.yml` (o equivalente podman) con los límites
  cgroup, volumen solo de lectura, red acotada. Skill `docker`.
- **Seguridad**: cierra G1, G2, G4, G5 (parcial — G5 requiere además
  inventario de dependencias).
- **Contratos**: no cambia el contrato de cola (ADR-0005) ni la API.
- **Dependencia de D5/ADR-0010**: la política de red (egress) depende del
  endpoint de `ExtractionLLM` (local o externo).
