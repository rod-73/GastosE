# 02 — Relaciones entre tablas (GastosE)

Relaciones conceptuales entre las tablas del modelo. Se indican cardinalidad
(1:1, 1:N, M:N) y la regla de negocio que las justifica. La cadena de
referencias entre niveles de valor (E3→E4→E5) es la pieza central: hace
estructuralmente imposible saltar niveles (INV-10, INV-8).

## 1. Cadena de niveles de valor (E3 → E4 → E5)

```
source_documents (E1)
    │ 1:N
    ▼
extractions (E2)
    │ 1:N
    ▼
extracted_values (E3)          ← N2: valor extraído (confidence + provenance)
    │ 1:1 (referencia obligatoria)
    ▼
normalized_values (E4)         ← N3: valor normalizado (determinístico)
    │ 1:1 (referencia obligatoria)
    ▼
validated_values (E5)          ← N4: valor validado (reglas VR-xxx)
    │ (referencia a manual_corrections si corrected)
    ▼
expenses (E6)                  ← N5: gasto aceptado (snapshot inmutable)
```

**Reglas de la cadena**:

- **E3 → E4 (1:1)**: cada `normalized_values.extracted_value_id` referencia
  exactamente un `extracted_values.id`. NOT NULL. Un valor normalizado sin
  origen extraído no es válido (INV-10, INV-12).
- **E4 → E5 (1:1)**: cada `validated_values.normalized_value_id` referencia
  exactamente un `normalized_values.id`. NOT NULL. Un valor validado sin
  origen normalizado no es válido (INV-10, INV-8).
- **E5 → E6 (N:1)**: un gasto referencia sus valores validados. La aceptación
  verifica que todos los valores obligatorios están validados (INV-8,
  VR-BIZ-3) antes de transitar a `accepted`.
- **No hay salto de nivel**: no existe FK de `extracted_values` a
  `validated_values` (saltando E4), ni de `normalized_values` a `expenses`
  (saltando E5). El flujo N1→N2→N3→N4→N5 está forzado por las referencias
  obligatorias.

**Idempotencia de la cadena**: el re-procesamiento (`reprocessed`) reemplaza
atómicamente los valores de una extracción (FR-EXT-5, NFR-4). La cadena se
reconstruye desde la nueva extracción.

## 2. Relaciones por entidad

### 2.1 Documento fuente (E1)

| Relación | Cardinalidad | Justificación |
|---|---|---|
| `source_documents` → `extractions` | 1:N | Un documento puede tener varias extracciones (reintentos). |
| `source_documents` → `expenses` | 1:N (salvo split) | Un documento alimenta uno o más gastos. Sin split: 1:1 (INV-4). |
| `source_documents` → `document_splits` | 1:N | Un documento puede tener varios splits (raro). |
| `source_documents` → `duplications` | 1:N | Un documento puede ser parte de varias duplicaciones (DUP-10). |
| `source_documents` → `audit_events` | 1:N | Auditoría de acciones sobre el documento. |
| `source_documents` → `users` (owner) | N:1 | Propietario (OQ-9). |

### 2.2 Extracción (E2)

| Relación | Cardinalidad | Justificación |
|---|---|---|
| `extractions` → `extracted_values` | 1:N | Una extracción produce varios valores extraídos. |
| `extractions` → `source_documents` | N:1 | Cada extracción pertenece a un documento. |

### 2.3 Valores (E3, E4, E5)

| Relación | Cardinalidad | Justificación |
|---|---|---|
| `extracted_values` → `normalized_values` | 1:1 | Cada valor extraído se normaliza a un valor normalizado. |
| `normalized_values` → `validated_values` | 1:1 | Cada valor normalizado se valida a un valor validado. |
| `validated_values` → `manual_corrections` | 1:0..1 | Si `corrected`, referencia a la corrección manual. |
| `validated_values` → `expenses` | N:1 | Los valores validados alimentan el gasto. |

### 2.4 Gasto (E6)

| Relación | Cardinalidad | Justificación |
|---|---|---|
| `expenses` → `expense_lines` | 1:N | Un gasto contiene una o más líneas. |
| `expenses` → `tax_lines` | 1:N | Un gasto contiene líneas fiscales (para totales). |
| `expenses` → `payments` | 1:N | Un gasto puede tener varios pagos (pago parcial, OQ-6). |
| `expenses` → `reviews` | 1:N | Un gasto puede tener varias revisiones. |
| `expenses` → `duplications` | 1:N | Un gasto puede ser parte de varias duplicaciones. |
| `expenses` → `suppliers` | N:1 | Cada gasto tiene un proveedor. |
| `expenses` → `categories` | N:0..1 | Cada gasto tiene una categoría (opcional). |
| `expenses` → `payment_methods` | N:0..1 | Cada gasto tiene un método de pago. |
| `expenses` → `currencies` | N:1 | Cada gasto está denominado en una moneda. |
| `expenses` → `source_documents` | N:1 | Cada gasto referencia un documento fuente. |
| `expenses` → `audit_events` | 1:N | Auditoría de acciones sobre el gasto. |

### 2.5 Líneas (E7, E8)

| Relación | Cardinalidad | Justificación |
|---|---|---|
| `expense_lines` → `tax_lines` | 1:N | Una línea de gasto tiene una o más líneas fiscales. |
| `expense_lines` → `tax_rates` | N:1 | Cada línea aplica un tipo impositivo. |
| `tax_lines` → `tax_rates` | N:1 | Cada línea fiscal usa un tipo impositivo. |

### 2.6 Proveedor (E9)

| Relación | Cardinalidad | Justificación |
|---|---|---|
| `suppliers` → `source_documents` | 1:N | Un proveedor emite muchos documentos. |
| `suppliers` → `expenses` | 1:N | Un proveedor tiene muchos gastos. |

### 2.7 Catálogos (E10, E11, E17, E18)

| Relación | Cardinalidad | Justificación |
|---|---|---|
| `categories` → `expenses` | 1:N | Una categoría clasifica muchos gastos. |
| `categories` → `categories` (parent) | 1:N | Jerarquía de categorías (OQ-17). |
| `payment_methods` → `payments` | 1:N | Un método de pago se usa en muchos pagos. |
| `tax_rates` → `expense_lines` | 1:N | Un tipo impositivo se aplica en muchas líneas. |
| `tax_rates` → `tax_lines` | 1:N | Un tipo impositivo se usa en muchas líneas fiscales. |
| `currencies` → `expenses` | 1:N | Una moneda denomina muchos gastos. |

### 2.8 Revisión (E13, E14)

| Relación | Cardinalidad | Justificación |
|---|---|---|
| `reviews` → `review_field_results` | 1:N | Una revisión tiene resultados por campo. |
| `reviews` → `manual_corrections` | 1:N | Una revisión contiene correcciones manuales. |
| `manual_corrections` → `validated_values` | 1:0..1 | Una corrección alimenta un valor validado `corrected`. |

### 2.9 Duplicación (E15)

| Relación | Cardinalidad | Justificación |
|---|---|---|
| `duplications` → `source_documents` (A) | N:1 | Documento A. |
| `duplications` → `source_documents` (B) | N:1 | Documento B. |
| `duplications` → `expenses` (A) | N:0..1 | Gasto A (si aplica). |
| `duplications` → `expenses` (B) | N:0..1 | Gasto B (si aplica). |

### 2.10 Split (E19)

| Relación | Cardinalidad | Justificación |
|---|---|---|
| `document_splits` → `split_expenses` | 1:N | Un split produce varios gastos. |
| `split_expenses` → `expenses` | N:1 | Cada gasto resultante referencia el split. |

### 2.11 Auditoría (E16)

| Relación | Cardinalidad | Justificación |
|---|---|---|
| `audit_events` → (entidad afectada) | N:1 | Polimórfico: `entity_type` + `entity_id`. |
| `audit_events` → `users` (actor) | N:1 | Usuario (o sistema) que actuó. |

## 3. Reglas de cardinalidad clave (resumen)

- **Un gasto referencia exactamente un documento fuente** (salvo split
  explícito y documentado). `expenses.document_id` NOT NULL (INV-3).
- **Un documento fuente no puede aceptar dos gastos distintos salvo split**
  (E19). Sin split: 1:1 (INV-4). Con split: 1:N vía `document_splits`.
- **Una línea de gasto tiene una base imponible y una o varias líneas
  fiscales** (p. e.g. IVA + retención).
- **Un proveedor puede emitir muchos documentos; un documento tiene un
  proveedor**.
- **Un pago pertenece a un gasto; un gasto puede tener varios pagos** (pago
  parcial, OQ-6).
- **Cada valor de un nivel superior referencia su origen en el nivel
  inferior** (E3→E4→E5, INV-10). Sin referencia no hay valor válido en el
  nivel superior.
