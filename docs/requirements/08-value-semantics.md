# 08 — Semántica de documento / extracción / revisión / aceptación (GastosE)

Este documento es la pieza central del baseline. Distingue **explícitamente y
de forma prominente** los cinco niveles de valor y fija las reglas de flujo
entre ellos.

## Los cinco niveles

```
┌─────────────────────────────────────────────────────────────────────────┐
│ NIVEL 1: SOURCE DOCUMENT (documento fuente)                             │
│   El archivo original (PDF, imagen, XML). Evidencia primaria.           │
│   INMUTABLE. Identificado por fingerprint SHA-256.                      │
│   NO contiene "valores": contiene el documento.                         │
├─────────────────────────────────────────────────────────────────────────┤
│ NIVEL 2: EXTRACTED VALUES (valores extraídos)                           │
│   Datos obtenidos del documento por un método (XML, texto, OCR, LLM).   │
│   NO fiables. Cada valor lleva confidence (0..1) y provenance          │
│   (método, página, coordenadas, regla).                                 │
│   Un valor extraído NO es un hecho: es una hipótesis sobre el documento.│
├─────────────────────────────────────────────────────────────────────────┤
│ NIVEL 3: NORMALIZED VALUES (valores normalizados)                       │
│   Valores extraídos convertidos a formato canónico: moneda ISO-4217     │
│   decimal exacto, fecha ISO-8601, NIF/CIF validado, tipo impositivo     │
│   conocido. Determinístico (INV-12).                                    │
│   Todavía NO fiables por sí solos: son el valor extraído en formato    │
│   correcto.                                                             │
├─────────────────────────────────────────────────────────────────────────┤
│ NIVEL 4: VALIDATED VALUES (valores validados)                           │
│   Valores normalizados que han pasado validación determinística        │
│   (aritmética, esquema, normalización, referencias) y, si procede,     │
│   revisión humana. Llevan el resultado de las reglas VR-xxx.           │
│   Fiables dentro de lo que la validación garantiza.                    │
├─────────────────────────────────────────────────────────────────────────┤
│ NIVEL 5: ACCEPTED EXPENSE (gasto aceptado)                              │
│   Gasto aprobado explícitamente (humano o regla aprobada) tras         │
│   validación completa. ÚNICO hecho contable de GastosE.                │
│   Inmutable (INV-14). Snapshot de valores aceptados registrado.        │
└─────────────────────────────────────────────────────────────────────────┘
```

Regla fundamental:

```
SOURCE DOCUMENT != EXTRACTED VALUES != NORMALIZED VALUES != VALIDATED VALUES != ACCEPTED EXPENSE
```

Nunca: `LLM OUTPUT == ACCOUNTING FACT`.

## 1. Qué puede pasar de un nivel a otro

| De | A | Condición | Regla |
|---|---|---|---|
| N1 (documento) | N2 (extraído) | Extracción completada con método registrado; output cumple esquema estricto. | FR-EXT-1..FR-EXT-4, VR-SCHEMA-1. |
| N2 (extraído) | N3 (normalizado) | Normalización determinística aplicada con éxito. | FR-NOR-1..FR-NOR-3, INV-12. |
| N3 (normalizado) | N4 (validado) | Validación determinística pasa (todas las reglas BLOCK) y, si hay campos `uncertain`, revisión humana los confirma/corrige. | FR-VAL-1..FR-VAL-4, INV-7, INV-8. |
| N4 (validado) | N5 (aceptado) | Aprobación explícita (humana o regla aprobada) de un gasto cuyos valores obligatorios están validados y sin duplicación `probable` pendiente. | FR-ACC-1..FR-ACC-4, INV-5, INV-6, INV-8. |

## 2. Qué NO puede pasar (prohibiciones)

| Prohibición | Justificación |
|---|---|
| Un valor **extraído** nunca se acepta sin pasar por normalización y validación. | INV-8; FR-ACC-3. El valor extraído no es fiable. |
| Un valor **extraído** nunca se usa como hecho contable. | `LLM OUTPUT != ACCOUNTING FACT`. |
| Un valor **normalizado** nunca se acepta sin validación. | INV-8. La normalización solo corrige formato, no verifica coherencia. |
| Un valor **validado** nunca se acepta sin aprobación explícita. | La validación es necesaria pero no suficiente: la aceptación requiere aprobación (FR-ACC-1). |
| Un **documento fuente** nunca se modifica tras la subida. | INV-9. Es la evidencia primaria. |
| Un **gasto aceptado** nunca se modifica; solo se anula. | INV-14; FR-EXP-5. |
| Un valor extraído **sin provenance** no es válido. | INV-11. |
| Un valor extraído **sin confidence** no es válido. | INV-11. |
| Un gasto **sin documento fuente** no se acepta. | INV-3. |
| Un gasto **con duplicación probable** no se acepta. | INV-6. |
| Un valor con **confidence < umbral** no se valida sin revisión humana. | FR-VAL-4; VR-BIZ-4. |

## 3. Reglas de flujo entre niveles

1. **Flujo unidireccional**: el flujo normal es N1 → N2 → N3 → N4 → N5. No
   hay "salto de nivel": no se pasa de N2 a N4 sin pasar por N3, ni de N3 a
   N5 sin pasar por N4.
2. **Referencias obligatorias**: cada valor de un nivel superior referencia
   explícitamente su origen en el nivel inferior (E3→E4→E5). Esto permite la
   trazabilidad completa (INV-10).
3. **Corrección manual**: ocurre entre N3 y N4 (o durante la revisión de N4).
   Un humano corrige un valor normalizado; la corrección queda auditada (E14,
   INV-7) y el valor pasa a validado con resultado `corrected`.
4. **Rechazo en cualquier nivel**: un gasto puede rechazarse en cualquier
   momento antes de la aceptación (FR-REJ-1). El rechazo no "contamina" los
   niveles: el documento fuente y la extracción siguen disponibles.
5. **Snapshot en aceptación**: al aceptar, se registra un snapshot de los
   valores validados que se aceptan. Ese snapshot es inmutable (INV-14).
6. **Confianza decae con el nivel**: la confianza en un valor es máxima en N5
   (aceptado) y mínima en N2 (extraído). La UI debe reflejar esto: los
   valores de N2/N3 se muestran como "no confirmados" hasta que alcanzan N4.

## 4. Ejemplo de flujo completo

```
1. Subida: factura.pdf (N1, fingerprint abc123..., estado uploaded)
2. Extracción: método pdf_text_rules (N2)
   - supplier.nif = "B12345678"  confidence=0.95 provenance={página:1, bbox:[..], regla:patron_nif}
   - invoice.number = "F-2025-001" confidence=0.98
   - total = "1.234,56 €" confidence=0.90
3. Normalización (N3)
   - supplier.nif = "B12345678" (validado dígito)
   - invoice.number = "F-2025-001"
   - total = 1234.56 EUR (decimal exacto)
4. Validación (N4)
   - VR-ARITH-1: total == base + IVA - retenciones → passed
   - VR-NORM-3: NIF válido → passed
   - VR-BIZ-4: confidence de total (0.90) < umbral (0.9) → requiere revisión
   - Revisión humana: usuario confirma total=1234.56 → validado (confirmed)
5. Aceptación (N5)
   - Usuario acepta el gasto → snapshot registrado, hecho contable.
```

## 5. Responsabilidad por nivel

| Nivel | Quién lo produce | Fiabilidad |
|---|---|---|
| N1 | Sistema (subida) | Máxima (evidencia original) |
| N2 | Pipeline de extracción (XML/texto/OCR/LLM) | Baja-media (confidence) |
| N3 | Pipeline de normalización (determinístico) | Media (formato correcto, valor aún no verificado) |
| N4 | Validación determinística + revisión humana | Alta (verificado) |
| N5 | Aprobación explícita (humano/regla) | Máxima (hecho contable) |
