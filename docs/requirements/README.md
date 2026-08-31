# Baseline funcional — GastosE (PHASE1-001)

Requisitos funcionales del dominio de GastosE: gestión automatizada de gastos,
facturas recibidas, tickets y documentos asociados.

- **Tarea**: PHASE1-001 (estado: DESIGNING; solo el director transita estados).
- **Autor**: subagente `domain`.
- **Fecha**: 2026-08-31.
- **Fase**: Phase 1 — solo documentación y diseño. Prohibido implementar
  código de aplicación, backend, frontend, workers, schema productivo, OCR/LLM.
- **Fuente de conocimiento**: skill `expense-domain` (terminología canónica,
  ciclo de vida, invariantes, checklists) y skill `document-extraction`
  (filosofía *deterministic first*). Este baseline las extiende y refina;
  no las contradice.

## Regla fundamental (obligatoria en todo el baseline)

```
SOURCE DOCUMENT != EXTRACTED VALUES != NORMALIZED VALUES != VALIDATED VALUES != ACCEPTED EXPENSE
```

Documento original (evidencia inmutable) ≠ valores extraídos (no fiables, con
confidence y provenance) ≠ valores normalizados (formatos canónicos) ≠ valores
validados (determinísticos + revisión humana si procede) ≠ gasto aceptado
(único hecho contable, por aprobación explícita).

Nunca: `LLM OUTPUT == ACCOUNTING FACT`.

## Índice

| Archivo | Contenido |
|---|---|
| [01-terminology.md](01-terminology.md) | Glosario canónico completo: término, definición, sinónimos prohibidos/desaconsejados. |
| [02-entities.md](02-entities.md) | Entidades y conceptos del dominio: atributos clave, relaciones, papel. |
| [03-functional-requirements.md](03-functional-requirements.md) | Requisitos funcionales por área (FR-xxx) con criterios de aceptación. |
| [04-lifecycle.md](04-lifecycle.md) | Modelo de estados y transiciones: documento fuente, extracción, gasto, revisión/aceptación; estados de fallo y duplicado; reversibilidad. |
| [05-invariants.md](05-invariants.md) | Invariantes de negocio numerados, verificables, con justificación. |
| [06-validation-rules.md](06-validation-rules.md) | Reglas de validación determinísticas y de negocio; bloqueo vs advertencia. |
| [07-duplicates.md](07-duplicates.md) | Detección y resolución de duplicados: definición, estrategia, estados, reglas. |
| [08-value-semantics.md](08-value-semantics.md) | Semántica de los cinco niveles de valor y reglas de flujo entre niveles. |
| [09-non-functional-requirements.md](09-non-functional-requirements.md) | Requisitos no funcionales (NFR-xxx): auditoría, exactitud numérica, inmutabilidad, idempotencia, localización, rendimiento, seguridad de dominio. |
| [10-open-questions.md](10-open-questions.md) | Preguntas abiertas (OQ-xxx) para director/usuario. |

## Convenciones de identificación

- `FR-<área>-<n>`: requisito funcional (área: SUP, INV, TCK, DOC, EXP, LIN,
  TAX, TOT, CUR, CAT, PAY, EXT, NOR, VAL, REV, ACC, REJ, DUP, FST).
- `NFR-<n>`: requisito no funcional.
- `INV-<n>`: invariante de negocio.
- `VR-<n>`: regla de validación.
- `DUP-<n>`: regla de duplicados.
- `OQ-<n>`: pregunta abierta.
- `AC-<FR>`: criterio de aceptación (dado/cuando/entonces) de un FR.

## Ámbito (scope)

- **Dentro**: recepción de documentos (facturas recibidas, tickets, otros),
  extracción y normalización de valores, validación, revisión humana,
  aceptación/rechazo, registro de gastos con líneas y fiscalidad (IVA,
  retenciones), proveedores y datos fiscales, detección de duplicados,
  auditoría.
- **Fuera** (otro bounded context o fase posterior): emisión de facturas
  (FacturaE), contabilidad general, conciliación bancaria, pagos reales,
  aprobación presupuestaria, integración con FacturaE (solo vía API o
  contrato de eventos versionado, pendiente de decisión — ver ADR-0001).
