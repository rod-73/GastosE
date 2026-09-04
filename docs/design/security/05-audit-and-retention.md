# 05 — Auditoría y retención (GastosE Phase 2)

Diseño de implementación de la auditoría append-only (ADR-0012) y la
política de retención. Cubre: append-only, permisos, trigger, retención.

**Amenazas cubiertas**: T5 (tampereamiento de auditoría), G19..G20.
**ADR**: ADR-0012 (append-only audit log).
**NFR**: NFR-1 (auditabilidad).

## 1. Registro de auditoría append-only (ADR-0012)

### 1.1 Tabla `audit_events`

Ver `docs/design/persistence/07-audit-and-retention.md` §1.1 para el diseño
completo de la tabla.

**Resumen**:
- `id`: UUIDv7 (PK).
- `owner_id`: UUID (FK → organizations.id).
- `actor`: UUID (FK → users.id).
- `action`: TEXT (p. e.g. `document.uploaded`, `expense.accepted`).
- `entity_type`: TEXT (p. e.g. `source_document`, `expense`).
- `entity_id`: UUID (ID de la entidad).
- `before`: JSONB (estado antes, nullable).
- `after`: JSONB (estado después, nullable).
- `occurred_at`: TIMESTAMPTZ (timestamp del evento).
- `created_at`: TIMESTAMPTZ (timestamp de inserción).

### 1.2 Acciones auditadas

Ver `docs/design/persistence/07-audit-and-retention.md` §1.2 para la lista
completa de acciones.

**Resumen**: todas las acciones de dominio se registran:
- `document.uploaded`, `document.state_changed`
- `extraction.completed`, `extraction.failed`
- `expense.created`, `expense.state_changed`, `expense.accepted`,
  `expense.rejected`, `expense.voided`
- `review.decision`, `manual_correction`
- `duplication.detected`, `duplication.resolved`
- `supplier.created`, `supplier.updated`
- `session.created`, `session.revoked`
- `access.denied`

### 1.3 Append-only: permisos + trigger

Ver `docs/design/persistence/07-audit-and-retention.md` §1.3 para el diseño
completo.

**Resumen**:
- **Permisos**: `REVOKE UPDATE, DELETE ON audit_events FROM gastosE_app`.
- **Trigger**: `BEFORE UPDATE OR DELETE ON audit_events` → RAISE EXCEPTION.
- **Hash-chain**: NO es requisito de V1 (ADR-0012).

## 2. Retención

### 2.1 Decisión

**Sin purga automática en V1.** Las políticas de retención son configurables
por organización/tipo/estado, pero no se ejecutan automáticamente.

Ver `docs/design/persistence/07-audit-and-retention.md` §2 para el diseño
completo.

### 2.2 Justificación

- En V1, el volumen es bajo (~1.000 documentos/mes). No hay necesidad de
  purga automática.
- La purga automática requiere decisiones legales (plazos de retención fiscal)
  que varían por jurisdicción. No se hardcodean en V1.
- La retención se configura por organización, pero la ejecución es manual.

## 3. Seguridad adicional

### 3.1 No repudio

- La auditoría registra el `actor` (usuario) de cada acción.
- El `actor` se deriva de la sesión autenticada (nunca de la petición).
- Esto garantiza la atribución (NFR-7).

### 3.2 Integridad

- **Append-only**: no se puede modificar ni eliminar eventos.
- **Hash-chain** (Phase 3): si se necesita integridad criptográfica, se
  añadirá hash-chain (cada evento incluye el hash del evento anterior).

### 3.3 Logging de accesos denegados

- Cada acceso denegado (403/404) se registra en `audit_events`:
  - `action`: `access.denied`
  - `entity_type`: tipo de recurso
  - `entity_id`: ID del recurso
  - `after`: `{reason: 'insufficient_role' | 'cross_tenant'}`

## 4. Notas

- **Append-only**: la auditoría es append-only (permisos + trigger).
- **Hash-chain**: no es requisito de V1 (ADR-0012).
- **Retención**: sin purga automática en V1.
- **No repudio**: el `actor` se deriva de la sesión.
