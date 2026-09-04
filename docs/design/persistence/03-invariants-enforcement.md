# 03 — Aplicación de invariantes a nivel de BD (GastosE Phase 2)

Cómo se aplican los invariantes de dominio (INV-1..INV-15, definidos en
`docs/requirements/05-invariants.md`) a nivel de base de datos. No todos los
invariantes son aplicables a nivel de BD; algunos requieren lógica de
dominio. Este documento especifica cuál es cuál y cómo.

## Resumen

| Invariante | Aplicación BD | Mecanismo |
|---|---|---|
| INV-1 (suma de líneas = base_total) | **Parcial** | `CHECK (total >= 0)` en `expenses`. La suma se verifica en dominio. |
| INV-2 (dinero NUMERIC) | **Total** | Tipo `NUMERIC(14,2)` en todas las columnas monetarias. |
| INV-3 (gasto requiere documento) | **Total** | `document_id` NOT NULL en `expenses`. |
| INV-4 (documento requiere proveedor) | **Total** | `supplier_id` NOT NULL en `expenses`. |
| INV-5 (proveedor con NIF/CIF) | **Total** | `nif_cif` NOT NULL en `suppliers`. |
| INV-6 (duplicado probable bloquea aceptación) | **Parcial** | `CHECK` en `duplications.state`. La verificación se hace en dominio. |
| INV-7 (corrección manual completa) | **Total** | `old_value`, `new_value`, `corrected_by`, `corrected_at` NOT NULL. |
| INV-8 (no validar sin normalizar) | **Total** | `normalized_value_id` NOT NULL en `validated_values`. |
| INV-9 (fingerprint SHA-256) | **Total** | `fingerprint_sha256` CHAR(64) NOT NULL. |
| INV-10 (cadena E3→E4→E5) | **Total** | FK NOT NULL: `extracted_value_id` en E4, `normalized_value_id` en E5. |
| INV-11 (confidence y provenance) | **Total** | `confidence` NOT NULL, `provenance` NOT NULL en `extracted_values`. |
| INV-12 (estado de documento) | **Total** | `CHECK` constraint en `source_documents.state`. |
| INV-13 (una moneda por gasto) | **Total** | `currency` CHAR(3) NOT NULL en `expenses`. |
| INV-14 (snapshot inmutable) | **Parcial** | `CHECK (state != 'accepted' OR accepted_snapshot IS NOT NULL)`. Inmutabilidad por trigger. |
| INV-15 (motivo en fallo) | **Total** | `CHECK (state != 'failed' OR failure_reason IS NOT NULL)`. |

## Detalle por invariante

### INV-1: La suma de líneas de gasto debe coincidir con el base_total

**Aplicación BD**: parcial.

- `expenses.total` tiene `CHECK (total >= 0)`.
- `expense_lines.amount` tiene `CHECK (amount >= 0)`.
- La **suma** de `expense_lines.amount` debe coincidir con
  `expenses.base_total`. Esto **no** se puede garantizar con una constraint
  de tabla simple (requiere una subquery). Se verifica en **dominio** antes
  de insertar/actualizar.

**Mecanismo BD**:
```sql
-- En expenses:
total NUMERIC(14,2) NOT NULL CHECK (total >= 0),

-- En expense_lines:
amount NUMERIC(14,2) NOT NULL CHECK (amount >= 0)
```

**Mecanismo dominio**:
```python
# Pseudocódigo
assert sum(line.amount for line in expense.lines) == expense.base_total
```

### INV-2: Valores monetarios exactos (nunca float)

**Aplicación BD**: total.

Todas las columnas monetarias usan `NUMERIC(14,2)` (importes) o
`NUMERIC(14,4)` (importes unitarios). Nunca `FLOAT`, `REAL` o
`DOUBLE PRECISION`.

**Columnas afectadas**:
- `expenses.base_total`, `expenses.vat_total`, `expenses.withholding_total`,
  `expenses.total` → `NUMERIC(14,2)`
- `expense_lines.amount` → `NUMERIC(14,2)`
- `expense_lines.quantity` → `NUMERIC(14,4)`
- `tax_lines.taxable_base`, `tax_lines.tax_amount` → `NUMERIC(14,2)`
- `payments.amount_paid` → `NUMERIC(14,2)`
- `tax_rates.percentage` → `NUMERIC(5,2)`

### INV-3: Un gasto requiere un documento fuente

**Aplicación BD**: total.

```sql
-- En expenses:
document_id UUID NOT NULL REFERENCES source_documents(id) ON DELETE RESTRICT
```

`NOT NULL` garantiza que no existe un gasto sin documento. `ON DELETE
RESTRICT` impide eliminar un documento que tiene gastos asociados.

### INV-4: Un gasto requiere un proveedor

**Aplicación BD**: total.

```sql
-- En expenses:
supplier_id UUID NOT NULL REFERENCES suppliers(id) ON DELETE RESTRICT
```

### INV-5: Un proveedor requiere NIF/CIF

**Aplicación BD**: total.

```sql
-- En suppliers:
nif_cif TEXT NOT NULL
```

### INV-6: Un duplicado probable bloquea la aceptación

**Aplicación BD**: parcial.

- `duplications.state` tiene `CHECK (state IN ('probable', 'confirmed',
  'resolved_not_duplicate'))`.
- La **verificación** de que no hay duplicados probables antes de aceptar se
  hace en **dominio** (query a `duplications` con `state = 'probable'`).

**Mecanismo BD**:
```sql
-- En duplications:
state TEXT NOT NULL DEFAULT 'probable'
    CHECK (state IN ('probable', 'confirmed', 'resolved_not_duplicate'))
```

**Mecanismo dominio**:
```python
# Antes de aceptar un gasto:
has_probable_dup = db.query(Duplication).filter(
    Duplication.expense_a_id == expense.id,
    Duplication.state == 'probable'
).first()
assert has_probable_dup is None, "Hay un duplicado probable sin resolver"
```

### INV-7: Una corrección manual debe tener old_value, new_value, corrected_by, corrected_at

**Aplicación BD**: total.

```sql
-- En manual_corrections:
old_value     TEXT NOT NULL,
new_value     TEXT NOT NULL,
corrected_by  UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
corrected_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
```

### INV-8: No se puede validar un valor que no ha sido normalizado

**Aplicación BD**: total.

```sql
-- En validated_values:
normalized_value_id UUID NOT NULL REFERENCES normalized_values(id) ON DELETE RESTRICT
```

`NOT NULL` garantiza que no existe un valor validado sin un valor
normalizado de origen.

### INV-9: El fingerprint es SHA-256

**Aplicación BD**: total.

```sql
-- En source_documents:
fingerprint_sha256 CHAR(64) NOT NULL
```

`CHAR(64)` es la longitud exacta de un hash SHA-256 en hexadecimal.

### INV-10: Cadena E3→E4→E5 (no se salta nivel)

**Aplicación BD**: total.

La cadena se fuerza con FK NOT NULL:

```
extracted_values (E3)
    ↑
normalized_values (E4)  -- extracted_value_id NOT NULL
    ↑
validated_values (E5)   -- normalized_value_id NOT NULL
```

No hay camino para crear un E4 sin E3, ni un E5 sin E4.

### INV-11: Confidence y provenance son obligatorios en valores extraídos

**Aplicación BD**: total.

```sql
-- En extracted_values:
confidence NUMERIC(4,3) NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
provenance JSONB NOT NULL
```

### INV-12: El estado de un documento sigue el ciclo A

**Aplicación BD**: total.

```sql
-- En source_documents:
state TEXT NOT NULL DEFAULT 'uploaded'
    CHECK (state IN (
        'uploaded', 'processing', 'extracted', 'uncertain',
        'validation_error', 'duplicate', 'manually_corrected',
        'validated', 'accepted', 'rejected',
        'confirmed_duplicate', 'failed'
    ))
```

La **transición** entre estados se verifica en dominio (máquina de estados).
La BD solo garantiza que el estado es uno de los válidos.

### INV-13: Un gasto tiene una única moneda

**Aplicación BD**: total.

```sql
-- En expenses:
currency CHAR(3) NOT NULL REFERENCES currencies(code) ON DELETE RESTRICT
```

### INV-14: El snapshot de aceptación es inmutable

**Aplicación BD**: parcial.

- `CHECK (state != 'accepted' OR accepted_snapshot IS NOT NULL)` garantiza
  que si el gasto está aceptado, hay snapshot.
- La **inmutabilidad** (no modificar `accepted_snapshot` una vez aceptado)
  se garantiza con un **trigger** (ver `07-audit-and-retention.md`).

**Mecanismo BD**:
```sql
-- En expenses:
CONSTRAINT chk_exp_accepted_snapshot
    CHECK (state != 'accepted' OR accepted_snapshot IS NOT NULL)
```

**Trigger** (pseudocódigo):
```sql
CREATE OR REPLACE FUNCTION trg_expenses_snapshot_immutable()
RETURNS TRIGGER AS $$
BEGIN
    IF OLD.state = 'accepted' AND NEW.accepted_snapshot IS DISTINCT FROM OLD.accepted_snapshot THEN
        RAISE EXCEPTION 'accepted_snapshot is immutable once accepted';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER expenses_snapshot_immutable
    BEFORE UPDATE ON expenses
    FOR EACH ROW EXECUTE FUNCTION trg_expenses_snapshot_immutable();
```

### INV-15: Un estado de fallo requiere motivo

**Aplicación BD**: total.

```sql
-- En source_documents:
CONSTRAINT chk_docs_failure_reason
    CHECK (state != 'failed' OR failure_reason IS NOT NULL)

-- En extractions:
CONSTRAINT chk_ext_failure_reason
    CHECK (state != 'failed' OR failure_reason IS NOT NULL)

-- En expenses:
CONSTRAINT chk_exp_failure_reason
    CHECK (state != 'failed' OR failure_reason IS NOT NULL)

-- En extraction_jobs:
CONSTRAINT chk_job_failure_reason
    CHECK (state != 'failed' OR failure_reason IS NOT NULL)
```

## Invariantes que NO se aplican a nivel de BD

| Invariante | Razón |
|---|---|
| Transiciones de estado (ciclos A/B/C/D) | Requiere lógica de máquina de estados en dominio. La BD solo valida el valor del estado. |
| Suma de líneas = base_total (INV-1) | Requiere agregación; se verifica en dominio. |
| Bloqueo de aceptación por duplicado (INV-6) | Requiere query a otra tabla; se verifica en dominio. |
| Inmutabilidad de snapshot (INV-14) | Parcial en BD (CHECK); la inmutabilidad total requiere trigger. |

## Triggers necesarios

| Trigger | Tabla | Función |
|---|---|---|
| `trg_audit_events_append_only` | `audit_events` | Prohíbe UPDATE y DELETE. |
| `trg_manual_corrections_append_only` | `manual_corrections` | Prohíbe UPDATE y DELETE. |
| `trg_expenses_snapshot_immutable` | `expenses` | Prohíbe modificar `accepted_snapshot` una vez `state = 'accepted'`. |

Ver `07-audit-and-retention.md` para el diseño completo de triggers y
permisos.

## Permisos necesarios

| Permiso | Tabla | Justificación |
|---|---|---|
| `REVOKE UPDATE, DELETE` | `audit_events` | Append-only (ADR-0012). |
| `REVOKE UPDATE, DELETE` | `manual_corrections` | Append-only (ADR-0012). |

El trigger es una **segunda capa** de protección: aunque el permiso se
revogue, el trigger impide la modificación incluso por un superusuario.
