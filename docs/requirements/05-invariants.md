# 05 — Invariantes de negocio (GastosE)

Lista numerada, verificable, con justificación. Un invariante es una
propiedad que debe ser cierta en todo momento para todo objeto del dominio
que esté en un estado coherente. Se numera `INV-n`. Los INV-1..INV-8
proceden de la skill `expense-domain` (se mantienen y refinan); INV-9..INV-15
son extensiones de este baseline.

## Invariantes

### INV-1 — Identidad aritmética del total

`total == sum(bases de líneas) + sum(cuotas IVA) − sum(cuotas retención)`,
con tolerancia de redondeo ≤ 0,01 por línea (regla de redondeo documentada:
redondeo a 2 decimales, medio hacia arriba, por línea fiscal antes de sumar).

- **Verificable**: recalculando el total a partir de las líneas y
  comparando con el total declarado.
- **Justificación**: coherencia contable básica; un total que no cuadra con
  sus líneas no es un hecho contable fiable.

### INV-2 — Exactitud numérica

Todo valor monetario se almacena y manipula como decimal exacto (nunca
float). Las fechas se almacenan en formato canónico (ISO-8601).

- **Verificable**: inspección del tipo de almacenamiento y de las
  operaciones aritméticas.
- **Justificación**: los float binarios introducen errores de redondeo
  acumulativos inaceptables en contabilidad (p. e.g. 0.1 + 0.2 ≠ 0.3).

### INV-3 — Un gasto, un documento fuente

Todo gasto aceptado referencia exactamente un documento fuente válido.

- **Verificable**: conteo de documentos fuente asociados a un gasto
  aceptado.
- **Justificación**: trazabilidad de la evidencia; sin documento no hay
  hecho contable demostrable.

### INV-4 — Un documento, un gasto (salvo split)

Un documento fuente no puede aceptar dos gastos distintos salvo split
explícito y documentado (E19).

- **Verificable**: conteo de gastos aceptados por documento fuente (sin
  split).
- **Justificación**: evita doble contabilización del mismo hecho; el split
  es la única vía legítima de 1→N y debe ser explícito.

### INV-5 — Proveedor válido antes de aceptar

Los datos fiscales del proveedor (mínimo NIF/CIF válido) deben existir antes
de aceptar el gasto.

- **Verificable**: comprobación del proveedor del gasto en el momento de la
  aceptación.
- **Justificación**: el gasto aceptado es un hecho contable que debe
  identificar al contraparte fiscal.

### INV-6 — Duplicado probable bloquea aceptación

Mismo (proveedor, número de documento, fecha, importe) => duplicación
`probable` => bloqueo de aceptación hasta resolución humana.

- **Verificable**: estado de la duplicación asociada al gasto en el momento
  de la aceptación.
- **Justificación**: evitar doble contabilización por error de
  re-registro; la resolución debe ser humana porque la coincidencia de la
  clave no prueba por sí sola que es el mismo hecho.

### INV-7 — Auditoría de correcciones manuales

Toda corrección manual queda auditada: usuario, fecha/hora, valor anterior,
valor posterior.

- **Verificable**: existencia del registro E14 para cada campo con resultado
  `corrected`.
- **Justificación**: trazabilidad y no repudio; un valor validado por
  corrección debe poder reconstruirse.

### INV-8 — Solo se acepta lo validado

Un valor solo puede ser `accepted` si es `validated`; un gasto solo puede
aceptarse si todos sus valores obligatorios están validados.

- **Verificable**: estado de cada valor obligatorio en el momento de la
  aceptación.
- **Justificación**: la distinción fundamental
  (EXTRACTED ≠ VALIDATED ≠ ACCEPTED); nunca `LLM OUTPUT == ACCOUNTING FACT`.

### INV-9 — Inmutabilidad del documento fuente

El contenido del documento fuente no se modifica tras la subida; su
fingerprint SHA-256 es estable y verificable.

- **Verificable**: recalculando el fingerprint y comparando con el
  registrado.
- **Justificación**: el documento es la evidencia primaria; si se altera, la
  trazabilidad se rompe.

### INV-10 — Trazabilidad completa

Para todo gasto aceptado, debe poder reconstruirse la cadena completa:
documento fuente → extracción (método) → valores extraídos (confidence,
provenance) → valores normalizados → valores validados (reglas aplicadas) →
revisión (si hubo) → aceptación (usuario, fecha, snapshot).

- **Verificable**: recorrido de las referencias entre entidades (E1→E2→E3→
  E4→E5→E13→E6).
- **Justificación**: auditoría y fiscalidad; un hecho contable debe ser
  demostrable de extremo a extremo.

### INV-11 — Confianza y provenance obligatorias

Todo valor extraído lleva confidence (0..1) y provenance (método, página,
coordenadas, regla). Un valor sin provenance no es un valor extraído válido.

- **Verificable**: presencia de los atributos en cada E3.
- **Justificación**: sin provenance no hay forma de auditar de dónde viene el
  valor ni de decidir si requiere revisión.

### INV-12 — Normalización determinística

La normalización es determinística: el mismo valor extraído produce siempre
el mismo valor normalizado.

- **Verificable**: re-normalizando un valor y comparando.
- **Justificación**: reproducibilidad; si la normalización varía, la
  validación posterior no es fiable.

### INV-13 — Moneda única por gasto

Un gasto está denominado en una única moneda ISO-4217; no se mezclan monedas
en sus líneas sin conversión explícita y registrada.

- **Verificable**: comprobación de la moneda de todas las líneas del gasto.
- **Justificación**: sumar importes de monedas distintas sin conversión
  produce totales sin sentido.

### INV-14 — Aceptación irreversible

Una vez aceptado, un gasto no cambia de estado ni de valores; la única
salida es la anulación (registro separado, FR-EXP-5).

- **Verificable**: inmutabilidad del snapshot de valores aceptados.
- **Justificación**: el hecho contable aceptado es inmutable; corregir
  errores posteriores se hace con nuevas operaciones, no alterando el hecho.

### INV-15 — Fallo con motivo

Todo objeto en estado de fallo (`failed`, `validation_error`) lleva motivo
registrado.

- **Verificable**: presencia del motivo en cada objeto en estado de fallo.
- **Justificación**: un fallo sin motivo no es accionable ni auditable.

## Tabla de verificación rápida

| INV | Propiedad | Cómo se verifica | Severidad si se viola |
|---|---|---|---|
| INV-1 | Identidad aritmética | Recalcular total | Bloquea aceptación |
| INV-2 | Decimal exacto | Tipo de almacenamiento | Bloquea (diseño) |
| INV-3 | 1 gasto → 1 documento | Conteo | Bloquea aceptación |
| INV-4 | 1 documento → 1 gasto (salvo split) | Conteo | Bloquea aceptación |
| INV-5 | Proveedor válido | Comprobar NIF/CIF | Bloquea aceptación |
| INV-6 | Duplicado probable bloquea | Estado duplicación | Bloquea aceptación |
| INV-7 | Auditoría de correcciones | Existencia E14 | Bloquea validación |
| INV-8 | Solo se acepta lo validado | Estado de valores | Bloquea aceptación |
| INV-9 | Documento inmutable | Fingerprint | Bloquea (integridad) |
| INV-10 | Trazabilidad completa | Recorrido de referencias | Bloquea aceptación |
| INV-11 | Confidence + provenance | Presencia de atributos | Bloquea extracción |
| INV-12 | Normalización determinística | Re-normalizar | Bloquea validación |
| INV-13 | Moneda única | Comprobar líneas | Bloquea validación |
| INV-14 | Aceptación irreversible | Inmutabilidad snapshot | Bloquea (diseño) |
| INV-15 | Fallo con motivo | Presencia de motivo | Bloquea transición a fallo |
