# 01 — Terminología canónica (GastosE)

Glosario canónico. Todo documento de GastosE usa estos términos. La primera
aparición de un término puede incluir el inglés entre paréntesis; después,
solo la forma canónica. Los sinónimos prohibidos/desaconsejados se usan para
evitar ambigüedad; su aparición en documentos del proyecto se considera error
de terminología.

## 1. Documentos

| Término canónico | Definición | Sinónimos prohibidos / desaconsejados |
|---|---|---|
| **Documento fuente** (source document) | Archivo original recibido (PDF, imagen, XML) asociado a un gasto. Evidencia primaria, inmutable, identificada por fingerprint SHA-256. | "original" (ambiguo), "archivo" (genérico), "escaneo" (solo un tipo). |
| **Factura recibida** (received invoice) | Documento fiscal de compra emitido por un proveedor, con base imponible, cuota de IVA y total. Puede ser estructurada (Facturae/XML) o no estructurada (PDF/imagen). | "factura" (ambiguo: puede referirse a factura emitida por FacturaE), "factura de compra" (redundante en este contexto). |
| **Ticket** (ticket / receipt) | Documento menor de compra (ticket de caja, recibo). Puede no contener desglose fiscal completo (p. ej. solo total con IVA incluido). | "recibo" (se reserva para *recibo de pago*), "comprobante" (genérico). |
| **Documento menor** (minor document) | Clase de documento fuente que incluye tickets y recibos sin desglose fiscal completo. | "documento no fiscal" (puede ser fiscal incompleto, no inexistente). |
| **Fingerprint** (fingerprint) | Huella SHA-256 del contenido del documento fuente. Identifica el archivo de forma inequívoca. | "hash" (aceptable informalmente; canónico: fingerprint). |
| **Clave de duplicación** (duplicate key) | Tupla lógica (proveedor, número de documento, fecha, importe total) usada para detectar duplicados semánticos. | "identificador lógico" (ambiguo). |

## 2. Partes y fiscalidad

| Término canónico | Definición | Sinónimos prohibidos / desaconsejados |
|---|---|---|
| **Proveedor** (supplier) | Emisor del documento fuente; tiene datos fiscales (NIF/CIF, nombre, dirección). | "vendedor", "fornecedor" (error), "emisor" (aceptable solo en contexto de documento). |
| **Datos fiscales** (tax data) | Atributos fiscales del proveedor: NIF/CIF, nombre legal, dirección fiscal. | "datos de facturación" (confunde con FacturaE). |
| **NIF/CIF** (tax identifier) | Identificador fiscal español (NIF persona física, CIF persona jurídica) con dígito de control. | "DNI" (solo un subtipo), "tax ID" (aceptable como genérico internacional). |
| **Gasto** (expense) | Registro contable de un gasto: referencia a un documento fuente, líneas de gasto, fiscalidad, categoría, método de pago. Solo existe como hecho contable cuando está **aceptado**. | "gasto registrado" (ambiguo con el estado), "compra" (es el hecho, no el registro). |
| **Línea de gasto** (expense line) | Concepto de un gasto: descripción, cantidad, importe, tipo impositivo aplicado. | "ítem" (informal), "partida" (se reserva para contabilidad general). |
| **Línea fiscal** (tax line) | Desglose de un impuesto sobre una base: tipo de impuesto (IVA/retención), tipo impositivo, base imponible, cuota. | "línea de impuesto" (aceptable informalmente). |
| **Base imponible** (taxable base) | Importe sobre el que se calcula la cuota de un impuesto. | "base" (ambiguo), "importes gravados" (coloquial). |
| **Cuota** (tax amount) | Importe del impuesto resultante de aplicar el tipo impositivo a la base imponible. | "impuesto" (genérico), "IVA" (solo cuando el impuesto es IVA). |
| **IVA** (VAT) | Impuesto sobre el valor añadido soportado en la compra. Tipos: general, reducido, superreducido, exento, inverso (inversión del sujeto pasivo). | "VAT" (solo en inglés), "impuesto" (genérico). |
| **Retención** (withholding) | Retención a cuenta soportada (p. ej. IRPF) que reduce el total a pagar. | "retención IRPF" (es un subtipo), "deducción" (concepto distinto). |
| **Total** (total) | Importe total del documento: base + cuota IVA − retenciones (según tipo de documento y reglas de redondeo documentadas). | "importe total" (aceptable), "total a pagar" (solo si no hay retenciones; ambiguo en caso contrario). |
| **Tipo impositivo** (tax rate) | Porcentaje aplicado a una base imponible para obtener la cuota (p. e.g. 21 %, 10 %, 4 %). | "tipo de IVA" (solo para IVA), "porcentaje" (genérico). |
| **Moneda** (currency) | Moneda ISO-4217 (EUR, USD, ...). Nunca se mezclan monedas en una suma sin conversión explícita y documentada. | "divisa" (aceptable informalmente). |
| **Tipo de cambio** (exchange rate) | Par de conversión entre dos monedas, con fecha de referencia y origen. Solo se usa en conversión explícita. | "cambio" (ambiguo). |
| **Categoría** (category) | Clasificación interna del gasto (p. e.g. "Desplazamientos", "Software"). Jerárquica u optativa según decisión pendiente (OQ). | "tipo de gasto" (aceptable informalmente), "rubro" (coloquial). |
| **Método de pago** (payment method) | Medio por el que se pagó el gasto: efectivo, tarjeta, transferencia, cheque, etc. | "forma de pago" (aceptable), "pago" (se reserva para la entidad *pago*). |
| **Pago** (payment) | Registro del hecho de pago asociado a un gasto (método, fecha, referencia). | "pago realizado" (redundante). |

## 3. Pipeline de valores

| Término canónico | Definición | Sinónimos prohibidos / desaconsejados |
|---|---|---|
| **Valor extraído** (extracted value) | Dato obtenido del documento fuente por un método de extracción (XML, texto, OCR, LLM). NO es fiable: lleva `confidence` (0..1) y `provenance` (método, página, coordenadas, regla). | "dato del documento" (ambiguo), "valor leído" (informal). |
| **Confianza** (confidence) | Puntuación 0..1 de fiabilidad de un valor extraído, asignada por el método de extracción. | "seguridad" (ambiguo). |
| **Proveniencia** (provenance) | Origen de un valor extraído: método usado, página, coordenadas (bbox), patrón/regla aplicada. | "fuente" (ambiguo con *documento fuente*). |
| **Valor normalizado** (normalized value) | Valor extraído convertido a formato canónico: moneda ISO-4217 con decimal exacto, fecha ISO-8601, NIF/CIF validado, tipo impositivo conocido. | "valor limpio" (informal). |
| **Valor validado** (validated value) | Valor normalizado que ha pasado validación determinística (aritmética, esquema, normalización, referencias) y, si procede, revisión humana. | "valor correcto" (no verificable). |
| **Gasto aceptado** (accepted expense) | Gasto aprobado explícitamente (humano o regla aprobada). ÚNICO hecho contable de GastosE. | "gasto aprobado" (aceptable informalmente), "gasto confirmado" (ambiguo con duplicado confirmado). |
| **Extracción** (extraction) | Proceso de obtener valores extraídos de un documento fuente. | "parsing" (informal), "lectura" (genérico). |
| **Normalización** (normalization) | Proceso de convertir valores extraídos a valores normalizados (formatos canónicos). | "limpieza" (informal). |
| **Validación** (validation) | Proceso de comprobar valores normalizados con reglas determinísticas y, si procede, revisión humana, produciendo valores validados. | "verificación" (se usa para el fingerprint). |
| **Revisión humana** (human review) | Intervención de un usuario para confirmar, corregir o rechazar valores en el proceso de validación. Toda corrección queda auditada. | "revisión manual" (aceptable), "corrección" (solo la acción, no el proceso). |
| **Aceptación** (acceptance) | Aprobación explícita de un gasto (o de sus valores) que lo convierte en hecho contable. | "aprobación" (aceptable informalmente), "confirmación" (ambiguo). |
| **Rechazo** (rejection) | Decisión explícita de no aceptar un gasto, con motivo. Terminal negativo. | "denegación" (aceptable), "cancelación" (se reserva para anulación posterior). |
| **Duplicado** (duplicate) | Documento o gasto que representa el mismo hecho que otro ya existente. Se distingue **duplicado probable** (detectado, sin resolver) de **duplicado confirmado** (resuelto por humano). | "doble" (informal), "repetición" (genérico). |
| **Duplicado probable** (probable duplicate) | Pareja de documentos/gastos que coincide por fingerprint o clave de duplicación y está pendiente de resolución humana. | "duplicado" (sin calificar: ambiguo). |
| **Duplicado confirmado** (confirmed duplicate) | Pareja resuelta por un humano como el mismo hecho. El segundo queda marcado y no se acepta. | "duplicado" (sin calificar). |
| **Split de documento** (document split) | Operación explícita y documentada por la que un documento fuente alimenta más de un gasto. | "división" (informal). |
| **Corrección manual** (manual correction) | Modificación de un valor por un humano durante la revisión. Se registra quién, cuándo, valor anterior y valor posterior. | "edición" (informal), "fix" (prohibido). |

## 4. Estados (resumen; detalle en 04-lifecycle.md)

| Término canónico | Definición |
|---|---|
| **Estado** (state) | Condición de un documento fuente, extracción, gasto o revisión en un momento dado. Transiciones definidas en 04-lifecycle.md. |
| **Estado terminal** (terminal state) | Estado sin salidas: `accepted`, `rejected`, `failed` (y `confirmed_duplicate`). |
| **Estado de fallo** (failure state) | `failed`: terminal negativo con motivo registrado. |
| **Estado incierto** (uncertain state) | `uncertain`: confianza por debajo del umbral; requiere revisión humana. |

## 5. Reglas de uso

1. En este baseline y en todos los documentos posteriores de GastosE, cada
   término se usa con su definición canónica. Si un término no está en este
   glosario, debe añadirse antes de usarse (decisión del director).
2. Los sinónimos prohibidos no aparecen en requisitos, ADRs, contratos ni
   código (cuando exista).
3. La distinción de los cinco niveles de valor (08-value-semantics.md) es
   obligatoria: no se usa "valor" sin calificar (extraído/normalizado/
   validado/aceptado) cuando el nivel importa.
