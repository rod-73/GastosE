# 06 — Secrets y logging (GastosE Phase 2)

Diseño de implementación de la gestión de secrets y el logging seguro.
Cubre: gestión de secrets, redacción de logs, error messages, dependency
security.

**Amenazas cubiertas**: T6 (fuga de secrets), G21..G22.
**NFR**: NFR-1 (auditabilidad), NFR-7 (aislamiento).

## 1. Gestión de secrets

### 1.1 Principio

- **Nunca en código**: los secrets no se almacenan en el código fuente.
- **Nunca en logs**: los secrets no se loguean.
- **Nunca en BD**: los secrets no se almacenan en la BD (excepto
  `password_hash`, que es un hash, no un secret en claro).
- **Env vars**: los secrets se inyectan como variables de entorno.

### 1.2 Secrets de GastosE

| Secret | Descripción | Fuente |
|--------|-------------|--------|
| `DATABASE_URL` | URL de conexión a PostgreSQL. | Env var. |
| `JWT_SECRET` | (No se usa: token opaco, no JWT). | N/A. |
| `LLM_API_KEY` | API key del LLM (si es externo). | Env var. |
| `LLM_ENDPOINT` | Endpoint del LLM. | Env var. |
| `DOCUMENT_STORAGE_PATH` | Ruta del almacenamiento de documentos. | Env var. |
| `REDIS_URL` | URL de Redis (si se usa para rate limiting). | Env var. |

### 1.3 Inyección de secrets

- **Docker**: `--env-file .env` o `environment` en `docker-compose.yml`.
- **Kubernetes**: `Secret` objects o `ConfigMap` (no secommited).
- **Prohibido**: commitear `.env` al repositorio (`.gitignore`).

### 1.4 Rotación de secrets

- **`DATABASE_URL`**: rotar credenciales de BD cada 90 días.
- **`LLM_API_KEY`**: rotar API key cada 90 días.
- **Procedimiento**:
  1. Generar nuevo secret.
  2. Actualizar el secret en el sistema de gestión (env vars, Kubernetes
     Secret).
  3. Reiniciar los servicios (o hacer rolling update).
  4. Revocar el secret antiguo.

## 2. Logging seguro

### 2.1 Principio

- **No loguear secrets**: nunca loguear tokens, passwords, API keys.
- **No loguear datos financieros completos**: no loguear importes, NIFs,
  direcciones fiscales.
- **Redacción**: si se necesita loguear datos sensibles, se redactan
  (p. e.g. `NIF: 1234****`).
- **Estructurado**: los logs son estructurados (JSON) para facilitar el
  parsing y la redacción.

### 2.2 Niveles de log

| Nivel | Uso | Ejemplo |
|-------|-----|---------|
| `DEBUG` | Detalles de debugging. | `Parsing PDF page 1/10` |
| `INFO` | Eventos normales. | `Document uploaded: id=a1b2c3d4` |
| `WARNING` | Eventos anómalos. | `Document too large: 25MB > 20MB` |
| `ERROR` | Errores. | `Extraction failed: timeout` |
| `CRITICAL` | Errores críticos. | `Database connection lost` |

### 2.3 Formato de log

```json
{
  "timestamp": "2026-09-04T12:00:00Z",
  "level": "INFO",
  "message": "Document uploaded",
  "document_id": "a1b2c3d4-...",
  "organization_id": "b2c3d4e5-...",
  "user_id": "c3d4e5f6-...",
  "size_bytes": 1024000,
  "format": "pdf"
}
```

- **IDs**: se loguean los IDs (UUIDs), no los datos sensibles.
- **Tamaño**: se loguea el tamaño (no el contenido).
- **Formato**: se loguea el formato (no el contenido).

### 2.4 Redacción de datos sensibles

- **NIF/CIF**: `1234****` (solo los primeros 4 dígitos).
- **Importes**: no se loguean (solo en auditoría, no en logs).
- **Tokens**: no se loguean (ni el token, ni el hash).
- **Passwords**: no se loguean (ni en claro, ni el hash).

### 2.5 Ejemplo de redacción

```python
import logging

logger = logging.getLogger(__name__)

def log_document_upload(document: Document):
    logger.info(
        "Document uploaded",
        extra={
            "document_id": str(document.id),
            "organization_id": str(document.owner_id),
            "user_id": str(document.uploaded_by),
            "size_bytes": document.size_bytes,
            "format": document.format_detected,
            # NO loguear: original_filename, fingerprint_sha256
        }
    )

def log_supplier_creation(supplier: Supplier):
    logger.info(
        "Supplier created",
        extra={
            "supplier_id": str(supplier.id),
            "organization_id": str(supplier.owner_id),
            "legal_name": supplier.legal_name,
            # Redactar NIF:
            "nif_cif": supplier.nif_cif[:4] + "****" if supplier.nif_cif else None,
        }
    )
```

## 3. Error messages

### 3.1 Principio

- **No stack traces al cliente**: los errores devueltos al cliente no
  incluyen stack traces.
- **Mensajes genéricos**: los mensajes de error son genéricos (no revelan
  detalles internos).
- **Logs internos**: los detalles (stack traces, queries SQL) se loguean
  internamente (no se devuelven al cliente).

### 3.2 Formato de error

```json
{
  "error": {
    "code": "document.too_large",
    "message": "The document exceeds the maximum size of 20 MB.",
    "details": {}
  }
}
```

- **`code`**: código de error estandarizado (p. e.g. `document.too_large`).
- **`message`**: mensaje genérico (no revela detalles internos).
- **`details`**: detalles opcionales (vacío por defecto).

### 3.3 Ejemplos

| Error | Code | Message |
|-------|------|---------|
| File too large | `document.too_large` | "The document exceeds the maximum size of 20 MB." |
| Unsupported format | `document.unsupported_format` | "The document format is not supported." |
| Unauthorized | `auth.unauthorized` | "Authentication required." |
| Forbidden | `auth.forbidden` | "Insufficient permissions." |
| Not found | `resource.not_found` | "Resource not found." |
| Validation error | `validation.error` | "Validation failed." |

## 4. Dependency security

### 4.1 Pinning de dependencias

- **`requirements.txt`**: todas las dependencias están pinnadas (versión
  exacta).
- **`pip-compile`**: se usa `pip-compile` para generar `requirements.txt`
  desde `requirements.in`.
- **Prohibido**: dependencias sin pin (`package>=1.0`).

### 4.2 CVE monitoring

- **`pip-audit`**: se ejecuta `pip-audit` periódicamente (CI/CD) para
  detectar CVEs.
- **`safety`**: se usa `safety` para detectar dependencias vulnerables.
- **Proceso**:
  1. Ejecutar `pip-audit` en CI/CD.
  2. Si hay CVEs críticos, actualizar la dependencia.
  3. Si no hay CVEs críticos, documentar la excepción.

### 4.3 Actualización de dependencias

- **Frecuencia**: mensual (o cuando hay CVEs críticos).
- **Proceso**:
  1. Actualizar `requirements.in`.
  2. Ejecutar `pip-compile` para regenerar `requirements.txt`.
  3. Ejecutar tests.
  4. Commitear los cambios.

## 5. Notas

- **Secrets**: nunca en código, logs, o BD. Solo en env vars.
- **Logging**: estructurado, sin secrets, sin datos financieros completos.
- **Error messages**: genéricos, sin stack traces al cliente.
- **Dependencies**: pinnadas, con CVE monitoring.
