---
name: expense-domain
description: Use when working on GastosE functional requirements, domain rules, terminology, validation, duplicates, review/acceptance, or any question about expenses, received invoices, receipts, tickets, suppliers, VAT, withholding, or document lifecycle states.
---

# Expense Domain — GastosE

Conocimiento funcional del dominio de gastos. Carga esta skill cuando
trabajes en requisitos, reglas, validaciones o terminología de GastosE.

## Distinción fundamental (obligatoria)

```
DOCUMENTO ORIGINAL  !=  VALOR EXTRAÍDO  !=  VALOR VALIDADO  !=  VALOR ACEPTADO
```

1. **Documento original**: el archivo recibido (PDF, imagen, XML). Es la
   evidencia primaria. Se conserva inmutable (fingerprint SHA-256).
2. **Valor extraído**: dato obtenido del documento (OCR/LLM/XML). NO es
   fiable: lleva `confidence` y `provenance` (página, coordenadas, método).
3. **Valor validado**: ha pasado validación determinística (aritmética,
   esquema, normalización) y, si hace falta, revisión humana.
4. **Valor aceptado**: aprobado explícitamente (humano o regla aprobada).
   Solo este valor es un hecho contable.

Nunca: `LLM OUTPUT == ACCOUNTING FACT`.

## Terminología canónica

| Término | Definición |
|---|---|
| Supplier (proveedor) | Emisor del documento; tiene datos fiscales (NIF/CIF, nombre, dirección). |
| Expense (gasto) | Registro contable de un gasto; referencia a un documento fuente y a líneas. |
| Received invoice (factura recibida) | Documento fiscal de compra con base, IVA, total. |
| Ticket / Receipt | Documento menor (ticket de caja, recibo); puede no ser fiscal completo. |
| Source document (documento fuente) | El archivo original asociado al gasto. |
| Expense line (línea de gasto) | Concepto, cantidad, importe, tipo impositivo. |
| Tax line (línea fiscal) | Tipo de impuesto (IVA/retención), tipo impositivo, base, cuota. |
| Taxable base (base imponible) | Importe sobre el que se calcula el impuesto. |
| VAT (IVA) | Impuesto sobre el valor añadido soportado. |
| Withholding (retención) | Retención a cuenta (ej. IRPF) soportada. |
| Total | Base + cuota IVA − retenciones (según tipo de documento). |
| Currency | Moneda ISO-4217; nunca mezclar monedas sin conversión explícita. |
| Category | Clasificación interna del gasto. |
| Payment method | Efectivo, tarjeta, transferencia, cheque, etc. |
| Duplicate | Documento o gasto duplicado (mismo proveedor, fecha, importe, nº factura). |

## Ciclo de vida del documento

```
uploaded -> processing -> extracted -> uncertain | validation_error
        -> manually_corrected -> validated -> accepted
        -> failed (en cualquier punto)
```

- `uncertain`: confidence por debajo del umbral; requiere revisión humana.
- `validation_error`: fallo determinístico (aritmética, esquema); no es
  necesariamente error humano.
- `manually_corrected`: un humano corrigió valores; se registra quién/cuándo/qué.
- `accepted`: terminal positivo. `failed`: terminal negativo con motivo.

## Invariantes del dominio

1. `total == sum(base_lines) + sum(vat_lines) - sum(withholding_lines)`
   (con tolerancia de redondeo ≤ 0,01 por línea, documentada).
2. Todo valor monetario se almacena como decimal exacto (nunca float).
3. Todo gasto aceptado referencia exactamente un documento fuente válido.
4. Un documento fuente no puede aceptar dos gastos distintos (salvo split
   explícito y documentado).
5. Los datos fiscales del proveedor deben existir antes de aceptar el gasto.
6. Duplicados: mismo (proveedor, número de factura, fecha, importe) =>
   bloqueo de aceptación hasta resolución humana.
7. Toda corrección manual queda auditada (usuario, timestamp, antes/después).
8. Un valor solo puede ser `accepted` si es `validated`.

## Checklist de requisitos por feature

- [ ] ¿Qué estados del ciclo de vida introduce o afecta?
- [ ] ¿Qué invariantes debe preservar?
- [ ] ¿Qué criterios de aceptación medibles (dado/cuando/entonces)?
- [ ] ¿Qué valores son extraídos vs validados vs aceptados en cada pantalla?
- [ ] ¿Qué pasa con duplicados y correcciones manuales?
- [ ] ¿Qué moneda y qué reglas de redondeo?
- [ ] ¿Qué se audita (quién, cuándo, qué)?
