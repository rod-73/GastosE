# ADR-0006: Almacenamiento de documentos fuente en filesystem local (volumen dedicado, inmutable)

Status: proposed
Date: 2026-08-31

## Context

Los documentos fuente (PDF, imágenes, XML) son la evidencia primaria inmutable
de un gasto (INV-9, NFR-3). Hay que decidir dónde y cómo se almacenan.
Restricciones:

- Inmutabilidad: el contenido no se modifica tras la subida; el fingerprint
  SHA-256 es estable y verificable (INV-9, NFR-3).
- Aislamiento de FacturaE (ADR-0001): el almacenamiento debe ser propio, sin
  compartir volumen con FacturaE.
- Runtime: podman 5.8.2 (volumen local disponible), sin infraestructura de
  object storage gestionada en el entorno.
- Acceso: la API (subida, descarga, verificación) y el worker (lectura para
  extracción) necesitan acceso.
- Seguridad: fuera del webroot, sin ejecución de scripts, nombres seguros
  (docs/architecture/07-security-boundaries.md).

## Decision

Los documentos fuente se almacenan en un **filesystem local en un volumen
dedicado a GastosE** (montado en el despliegue podman). No se usa object
storage (S3/GCS) ni el almacenamiento de FacturaE.

- **Inmutabilidad**: cada documento se escribe una única vez, con un nombre
  seguro generado por el sistema (UUID); después es solo de lectura. No existe
  operación de "reemplazar contenido": la única vía es subir un documento
  nuevo (FR-DOC-3).
- **Identidad por fingerprint**: el documento se identifica por su fingerprint
  SHA-256 (registrado en la base de datos). El almacenamiento se organiza de
  forma que el contenido se recupere por fingerprint/nombre seguro.
- **Verificación de integridad**: bajo demanda (endpoint
  `/documents/{id}/verify-fingerprint`) y periódica (task), recalculando el
  SHA-256 y comparando con el registrado (NFR-3).
- **Volumen dedicado**: el volumen se declara explícitamente en el despliegue
  de GastosE; no se monta el volumen de FacturaE (ADR-0001).
- **Copias de seguridad**: el volumen se incluye en la política de
  copias de seguridad (NFR-8).
- **Cifrado en reposo**: el volumen se cifra (detalle de Phase 2/devops).

## Alternatives considered

1. **Object storage** (S3/GCS/MinIO): ofrece durabilidad, escalado y
   inmutabilidad nativa (versioning, object lock). Rechazado para Phase 1/2:
   no hay infraestructura de object storage gestionada en el entorno; añadir
   MinIO u otro introduce un componente nuevo y una dependencia de red. Se
   revisará si el despliegue productivo dispone de object storage gestionado
   (la interfaz de acceso — leer/escribir por fingerprint — es estable, por lo
   que el cambio de backend de almacenamiento no afecta al dominio).
2. **Almacenamiento en la base de datos** (BLOB en PostgreSQL): rechazado:
   los documentos son grandes (hasta 20 MB); almacenarlos en la BD degrada el
   rendimiento de las queries, complica las copias de seguridad y no es el uso
   natural de PostgreSQL.
3. **Filesystem local en volumen dedicado (elegido)**: sin componente nuevo;
   inmutabilidad garantizada por convención + verificación de fingerprint;
   acceso directo y rápido para la API y el worker; cumple ADR-0001 (volumen
   propio).

## Consequences

- **Positivas**:
  - Sin componente nuevo; simplicidad operativa.
  - Inmutabilidad + verificación de fingerprint (INV-9, NFR-3).
  - Acceso directo y rápido (API y worker en el mismo despliegue).
  - Cumple ADR-0001 (volumen propio, no compartido con FacturaE).
- **Negativas / riesgos**:
  - La durabilidad depende de la copia de seguridad del volumen (NFR-8): se
    debe garantizar una política de backup.
  - No hay inmutabilidad nativa del sistema de archivos: se garantiza por
    convención (solo de lectura tras la subida) + verificación de fingerprint.
  - Escalado horizontal de la API requiere que el volumen sea accesible por
    todas las réplicas (o migrar a object storage).
- **Reversibilidad**: la interfaz de acceso (leer/escribir por fingerprint) es
  estable; migrar a object storage en el futuro no cambia el dominio ni la API,
  solo el backend de almacenamiento.
