# 06 — Reglas de validación (GastosE)

Reglas de validación determinísticas (aritméticas, de esquema, de
normalización, de referencias) y reglas de negocio. Para cada regla se
indica si **bloquea la aceptación** (el gasto no puede pasar a `accepted`
mientras la regla falle) o solo genera **advertencia** (warning; el gasto
puede aceptarse, pero la advertencia queda registrada y visible).

Convención: `VR-n`. Severidad: `BLOCK` (bloquea aceptación) o `WARN`
(advertencia). Algunas reglas tienen severidad configurable (se indica).

## 1. Reglas aritméticas

| ID | Regla | Descripción | Severidad |
|---|---|---|---|
| VR-ARITH-1 | Identidad del total | `total == sum(bases) + sum(IVA) − sum(retenciones)` con tolerancia ≤ 0,01 por línea (INV-1). | BLOCK |
| VR-ARITH-2 | Cuota de línea fiscal | `cuota == round(base × tipo impositivo, 2)` con tolerancia ≤ 0,01 (INV-1). | BLOCK |
| VR-ARITH-3 | Suma de bases | `sum(bases de líneas) == base total declarada` con tolerancia ≤ 0,01. | BLOCK |
| VR-ARITH-4 | Importe no negativo | Todo importe (base, cuota, total) ≥ 0. | BLOCK |
| VR-ARITH-5 | Pago vs total | En pago único, `importe pagado == total` con tolerancia ≤ 0,01. | WARN (configurable a BLOCK) |

## 2. Reglas de esquema

| ID | Regla | Descripción | Severidad |
|---|---|---|---|
| VR-SCHEMA-1 | Esquema de extracción | Todo output de extracción (incluido LLM) cumple el esquema estricto JSON. | BLOCK (sobre la extracción) |
| VR-SCHEMA-2 | Campos obligatorios | Los campos obligatorios del gasto (proveedor, fecha, moneda, total, al menos una línea) están presentes. | BLOCK |
| VR-SCHEMA-3 | Tipos de dato | Cada campo tiene el tipo esperado (moneda decimal, fecha ISO-8601, etc.). | BLOCK |

## 3. Reglas de normalización

| ID | Regla | Descripción | Severidad |
|---|---|---|---|
| VR-NORM-1 | Moneda ISO-4217 | La moneda es un código ISO-4217 conocido. | BLOCK |
| VR-NORM-2 | Fecha ISO-8601 | La fecha está en formato ISO-8601 y es una fecha válida (no futura más allá de un umbral razonable, p. e.g. 1 día — configurable). | BLOCK |
| VR-NORM-3 | NIF/CIF válido | El NIF/CIF del proveedor pasa la validación de dígito de control. | BLOCK |
| VR-NORM-4 | Tipo impositivo conocido | El tipo impositivo usado existe en el catálogo (E18). | BLOCK |
| VR-NORM-5 | Tipo impositivo vigente | El tipo impositivo estaba vigente en la fecha del documento. | WARN (configurable a BLOCK) |
| VR-NORM-6 | Decimales de moneda | El número de decimales del importe coincide con el de la moneda (p. e.g. EUR: 2). | BLOCK |

## 4. Reglas de referencias

| ID | Regla | Descripción | Severidad |
|---|---|---|---|
| VR-REF-1 | Proveedor existe | El proveedor referenciado existe y está `active` (o se permite `inactive` con advertencia — OQ). | BLOCK |
| VR-REF-2 | Categoría existe | La categoría referenciada existe (si se asigna). | BLOCK |
| VR-REF-3 | Método de pago existe | El método de pago referenciado existe. | BLOCK |
| VR-REF-4 | Documento fuente válido | El documento fuente referenciado existe, está íntegro (fingerprint OK) y es de un tipo compatible. | BLOCK |
| VR-REF-5 | Split documentado | Si hay más de un gasto por documento, existe un split documentado (E19). | BLOCK |

## 5. Reglas de negocio

| ID | Regla | Descripción | Severidad |
|---|---|---|---|
| VR-BIZ-1 | Proveedor con datos fiscales | El proveedor tiene NIF/CIF válido antes de aceptar (INV-5). | BLOCK |
| VR-BIZ-2 | Duplicado probable resuelto | No hay duplicación `probable` pendiente sobre el gasto (INV-6). | BLOCK |
| VR-BIZ-3 | Valores validados | Todos los valores obligatorios están validados (INV-8). | BLOCK |
| VR-BIZ-4 | Confianza suficiente | Todo campo con confidence < umbral (OQ-1) ha sido revisado y confirmado/corregido por humano. | BLOCK |
| VR-BIZ-5 | Moneda única | El gasto usa una única moneda (INV-13). | BLOCK |
| VR-BIZ-6 | Ticket sin desglose | Si el documento es ticket y no hay desglose fiscal, la base y la cuota de IVA se derivan del total (regla documentada) o el campo está marcado `uncertain` y revisado. | BLOCK (si no se deriva ni se revisa) |
| VR-BIZ-7 | Categoría obligatoria | Si la política lo exige (OQ-5), el gasto tiene categoría. | BLOCK (si política activa) / WARN (si no) |
| VR-BIZ-8 | Fecha coherente | La fecha del documento no es anterior a un umbral razonable (p. e.g. 10 años — configurable) ni posterior a hoy + umbral. | WARN |
| VR-BIZ-9 | Importe razonable | El total está dentro de un rango razonable (p. e.g. > 0 y < umbral configurable, p. e.g. 1.000.000 en la moneda). | WARN |
| VR-BIZ-10 | Proveedor coherente | El proveedor extraído coincide con el proveedor registrado (mismo NIF/CIF); si no, requiere revisión. | WARN (si coincide con otro proveedor conocido) / BLOCK (si no coincide con ninguno y no se revisa) |

## 6. Reglas específicas por tipo de documento

| ID | Regla | Descripción | Severidad |
|---|---|---|---|
| VR-INV-1 | Número de factura presente | Una factura recibida tiene número de documento. | BLOCK |
| VR-INV-2 | Desglose fiscal presente | Una factura recibida tiene base, cuota de IVA y total. | BLOCK |
| VR-TCK-1 | Total presente | Un ticket tiene total. | BLOCK |
| VR-TCK-2 | Derivación de IVA | Si un ticket no tiene desglose, la base y la cuota de IVA se derivan del total usando el tipo impositivo por defecto (OQ-3) o se marcan `uncertain`. | BLOCK (si no se deriva ni se marca) |
| VR-TCK-3 | Proveedor asociable | Un ticket permite asociar proveedor manualmente si no se extrae. | BLOCK (si no se asocia antes de aceptar) |

## 7. Semántica de severidad

- **BLOCK**: la regla falla => el gasto no puede pasar a `accepted`. El
  gasto queda en `validation_error` (o el campo en `uncertain` si es de
  confianza) y requiere corrección o rechazo.
- **WARN**: la regla falla => se registra una advertencia visible en la
  revisión y en el gasto; el gasto **puede** aceptarse, pero la advertencia
  queda en auditoría.
- **Configurable**: algunas reglas (VR-ARITH-5, VR-NORM-5, VR-BIZ-7,
  VR-BIZ-8, VR-BIZ-9) tienen severidad configurable por el director/usuario
  (ver OQ). La configuración de severidad queda registrada y es auditable.

## 8. Ejecución de la validación

- La validación se ejecuta sobre valores **normalizados** (no sobre valores
  extraídos crudos).
- La validación es **determinística** e **idempotente** (FR-VAL-2): no
  modifica valores, solo produce resultados y transiciones de estado.
- El resultado de cada regla (passed/failed/warning) se registra y es
  auditable (parte de la trazabilidad, INV-10).
- La validación puede ejecutarse en varios momentos: al completar la
  extracción, al enviar a revisión, y al intentar aceptar (la última es la
  definitiva).
