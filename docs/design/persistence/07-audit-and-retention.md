# 07 — Auditoría y retención (GastosE Phase 2)

Diseño de implementación del registro de auditoría append-only (ADR-0012) y
la política de retención de documentos y auditoría (D3/OQ-10).

**Nota**: este documento materializa el diseño conceptual de
`docs/persistence/07-open-questions.md` (PQ-2) en decisiones concretas de
implementación.

## 1. Registro de auditoría append-only (ADR-0012)

### 1.1 Tabla `audit_events`

```sql
CREATE TABLE audit_events (
    id              UUID PRIMARY KEY,
    owner_id        UUID NOT NULL REFERENCES organizations(id) ON DELETE RESTRICT,
    actor           UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    action          TEXT NOT NULL,
    entity_type     TEXT NOT NULL,
    entity_id       UUID NOT NULL,
    before          JSONB,
    after           JSONB,
    occurred_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

- **PK**: `id` (UUIDv7).
- **FK**: `owner_id` → `organizations.id`; `actor` → `users.id`.
- **`before`/`after`**: JSONB con el estado antes/después de la acción.
  Nullable (no todas las acciones tienen antes/después).
- **`occurred_at`**: timestamp del evento de dominio (no de la inserción).
- **`created_at`**: timestamp de la inserción en la BD.

### 1.2 Acciones auditadas

Todas las acciones de dominio se registran en `audit_events`:

| Acción | entity_type | before | after |
|--------|-------------|--------|-------|
| `document.uploaded` | `source_document` | NULL | `{state: 'uploaded', fingerprint, ...}` |
| `document.state_changed` | `source_document` | `{state: 'uploaded'}` | `{state: 'extracted'}` |
| `extraction.completed` | `extraction` | NULL | `{state: 'completed', method, ...}` |
| `extraction.failed` | `extraction` | NULL | `{state: 'failed', failure_reason, ...}` |
| `expense.created` | `expense` | NULL | `{state: 'draft', total, ...}` |
| `expense.state_changed` | `expense` | `{state: 'draft'}` | `{state: 'under_review'}` |
| `expense.accepted` | `expense` | `{state: 'ready_for_acceptance'}` | `{state: 'accepted', accepted_snapshot, ...}` |
| `expense.rejected` | `expense` | `{state: 'under_review'}` | `{state: 'rejected', rejection_reason, ...}` |
| `expense.voided` | `expense` | `{state: 'accepted'}` | `{state: 'voided', voided_reason, ...}` |
| `review.decision` | `review` | NULL | `{field, decision, before, after, ...}` |
| `manual_correction` | `manual_correction` | NULL | `{field, before, after, ...}` |
| `duplication.detected` | `duplication` | NULL | `{state: 'probable', dup_key, ...}` |
| `duplication.resolved` | `duplication` | `{state: 'probable'}` | `{state: 'resolved', resolution, ...}` |
| `supplier.created` | `supplier` | NULL | `{name, nif_cif, ...}` |
| `supplier.updated` | `supplier` | `{name, ...}` | `{name, ...}` |
| `session.created` | `session` | NULL | `{user_id, organization_id, ...}` |
| `session.revoked` | `session` | `{revoked_at: NULL}` | `{revoked_at: '...'}` |

### 1.3 Append-only: permisos + trigger

#### 1.3.1 Permisos de BD

```sql
-- El usuario de aplicación solo puede INSERT en audit_events:
REVOKE UPDATE, DELETE ON audit_events FROM gastosE_app;
GRANT INSERT ON audit_events TO gastosE_app;
GRANT SELECT ON audit_events TO gastosE_app;
```

- **No UPDATE**: no se puede modificar un evento de auditoría.
- **No DELETE**: no se puede eliminar un evento de auditoría.
- **INSERT**: la aplicación inserta nuevos eventos.
- **SELECT**: la aplicación lee eventos (auditoría, trazabilidad).

#### 1.3.2 Trigger de protección

```sql
-- Trigger para prevenir UPDATE/DELETE (defensa en profundidad):
CREATE OR REPLACE FUNCTION trg_audit_events_append_only()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'audit_events is append-only: % not allowed', TG_OP;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_audit_events_append_only
    BEFORE UPDATE OR DELETE ON audit_events
    FOR EACH ROW
    EXECUTE FUNCTION trg_audit_events_append_only();
```

- El trigger es una segunda línea de defensa: si por error se concede UPDATE
  o DELETE, el trigger lo bloquea.
- **Nota**: el trigger no reemplaza los permisos. Es una red de seguridad.

### 1.4 Hash-chain: NO es requisito de V1 (ADR-0012)

- **Decisión**: no se implementa hash-chain en V1.
- **Justificación**: el append-only (permisos + trigger) es suficiente para
  V1. El hash-chain añade complejidad (cálculo de hash, verificación de
  cadena) sin beneficio claro en V1.
- **Phase 3**: si se necesita integridad criptográfica de la auditoría, se
  añadirá hash-chain (cada evento incluye el hash del evento anterior).

## 2. Retención de documentos (D3/OQ-10)

### 2.1 Decisión

**Sin purga automática en V1.** Las políticas de retención son configurables
por organización/tipo/estado, pero no se ejecutan automáticamente.

### 2.2 Justificación

- En V1, el volumen es bajo (~1.000 documentos/mes). No hay necesidad de
  purga automática.
- La purga automática requiere decisiones legales (plazos de retención fiscal)
  que varían por jurisdicción. No se hardcodean en V1.
- La retención se configura por organización (tabla `organizations` o tabla
  de configuración), pero la ejecución es manual (operador).

### 2.3 Diseño de retención (preparación para Phase 3)

```sql
-- Tabla de configuración de retención (no se usa en V1, pero se diseña):
CREATE TABLE retention_policies (
    id              UUID PRIMARY KEY,
    owner_id        UUID NOT NULL REFERENCES organizations(id) ON DELETE RESTRICT,
    doc_type        TEXT NOT NULL,
    state           TEXT NOT NULL,
    retention_days  INTEGER NOT NULL CHECK (retention_days > 0),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

- **`retention_days`**: días antes de que un documento en un estado dado sea
  candidato a purga.
- **Ejecución**: un job periódico (Phase 3) consulta `retention_policies` y
  marca documentos como `retention_candidate`. La purga es manual.
- **V1**: la tabla existe pero no se usa. No hay job de purga.

## 3. Retención de auditoría

### 3.1 Decisión

**Sin purga automática en V1.** La auditoría es append-only y no se purga.

### 3.2 Justificación

- La auditoría es un requisito legal (NFR-1). No se puede eliminar.
- En V1, el volumen de auditoría es bajo (~10 eventos/documento/mes =
  ~10.000 eventos/mes). No hay necesidad de purga.
- El particionamiento por fecha (ver `05-indexes-and-performance.md` §3)
  facilita la gestión de la auditoría a largo plazo.

### 3.3 Particionamiento (preparación para Phase 3)

```sql
-- Particionamiento por mes (no se activa en V1):
CREATE TABLE audit_events (
    -- ... columnas ...
    occurred_at     TIMESTAMPTZ NOT NULL
) PARTITION BY RANGE (occurred_at);

-- Particiones mensuales:
CREATE TABLE audit_events_2026_09 PARTITION OF audit_events
    FOR VALUES FROM ('2026-09-01') TO ('2026-10-01');
```

- **V1**: sin particionamiento (volumen bajo).
- **Phase 3**: si el volumen crece, se activa particionamiento por mes.
- **Retención**: la purga de particiones antiguas es una operación de
  retención, no de modificación (la auditoría sigue siendo append-only).

## 4. Índices de auditoría

Ver `05-indexes-and-performance.md` §1.16 para los índices de `audit_events`:

- `idx_audit_entity`: `(entity_type, entity_id)` — trazabilidad por entidad.
- `idx_audit_owner_date`: `(owner_id, occurred_at DESC)` — listado por fecha.
- `idx_audit_action`: `(action)` — búsqueda por acción.

## 5. Queries de auditoría

### 5.1 Trazabilidad por entidad (INV-10)

```sql
-- Historial de un gasto:
SELECT * FROM audit_events
WHERE entity_type = 'expense'
  AND entity_id = :expense_id
  AND owner_id = :session_owner_id
ORDER BY occurred_at ASC;
```

- **Índice**: `idx_audit_entity` soporta esta query.
- **Rendimiento**: < 2s (NFR-6).

### 5.2 Listado por fecha

```sql
-- Eventos de auditoría de una organización en un rango de fecha:
SELECT * FROM audit_events
WHERE owner_id = :session_owner_id
  AND occurred_at BETWEEN :start AND :end
ORDER BY occurred_at DESC;
```

- **Índice**: `idx_audit_owner_date` soporta esta query.
- **Rendimiento**: < 2s (NFR-6).

### 5.3 Búsqueda por acción

```sql
-- Todos los eventos de aceptación:
SELECT * FROM audit_events
WHERE owner_id = :session_owner_id
  AND action = 'expense.accepted'
ORDER BY occurred_at DESC;
```

- **Índice**: `idx_audit_action` soporta esta query.
- **Rendimiento**: < 2s (NFR-6).

## 6. Notas

- **Append-only**: la auditoría es append-only (permisos + trigger). No se
  puede modificar ni eliminar.
- **Hash-chain**: no es requisito de V1 (ADR-0012). Se documenta como opción
  para Phase 3.
- **Retención**: sin purga automática en V1. Las políticas son configurables
  pero no se ejecutan.
- **Particionamiento**: no se activa en V1. Se documenta como preparación
  para Phase 3.
- **Cifrado**: el cifrado en reposo de la auditoría es responsabilidad de
  devops (Phase 2). No se prescribe aquí.
