# 03 — Requisitos funcionales (GastosE)

Requisitos funcionales por área, con criterios de aceptación en formato
dado/cuando/entonces. Identificadores: `FR-<área>-<n>`.

Áreas: SUP (proveedor), INV (factura recibida), TCK (ticket), DOC (documento
fuente), EXP (gasto), LIN (líneas de gasto), TAX (líneas fiscales), TOT
(totales), CUR (moneda), CAT (categoría), PAY (pago), EXT (extracción), NOR
(normalización), VAL (validación), REV (revisión humana), ACC (aceptación),
REJ (rechazo), DUP (duplicados), FST (estados de fallo).

---

## SUP — Proveedor y datos fiscales

- **FR-SUP-1**: El sistema permite registrar un proveedor con nombre legal,
  NIF/CIF y dirección fiscal.
  - AC: dado un nombre legal, un NIF/CIF con dígito de control válido y una
    dirección; cuando se guarda el proveedor; entonces el proveedor queda
    registrado con estado `active` y sus datos fiscales disponibles para
    gastos.
- **FR-SUP-2**: El sistema valida el dígito de control del NIF/CIF al
  registrar o actualizar un proveedor.
  - AC: dado un NIF/CIF con dígito de control incorrecto; cuando se intenta
    guardar; entonces el sistema bloquea el guardado y muestra el error
    (regla VR-NIF).
- **FR-SUP-3**: El sistema permite buscar proveedores por NIF/CIF o nombre.
  - AC: dado un proveedor registrado; cuando se busca por su NIF/CIF exacto;
    entonces aparece en los resultados.
- **FR-SUP-4**: Un proveedor con gastos aceptados no puede eliminarse; puede
  marcarse `inactive`.
  - AC: dado un proveedor con al menos un gasto aceptado; cuando se intenta
    eliminar; entonces el sistema lo bloquea y ofrece solo `inactive`.
- **FR-SUP-5**: Los datos fiscales del proveedor deben existir (registrados y
  válidos) antes de aceptar un gasto (INV-5).
  - AC: dado un gasto cuyo proveedor no tiene NIF/CIF válido; cuando se
    intenta aceptar el gasto; entonces la aceptación se bloquea.

## INV — Factura recibida

- **FR-INV-1**: El sistema permite registrar una factura recibida como
  documento fuente de tipo `received_invoice`, con número de factura, fecha,
  proveedor, base imponible, cuota de IVA y total.
  - AC: dado un documento fuente de tipo `received_invoice` con valores
    validados de proveedor, número, fecha, base, IVA y total; cuando se crea
    el gasto asociado; entonces el gasto referencia esos valores validados.
- **FR-INV-2**: Una factura recibida debe cumplir la identidad aritmética
  `total == base + cuota IVA − retenciones` (tolerancia documentada, INV-1).
  - AC: dado un gasto de factura recibida cuya suma no coincide con el total
    dentro de la tolerancia; cuando se ejecuta la validación; entonces el
    gasto queda en `validation_error` y no puede aceptarse.
- **FR-INV-3**: El número de factura se usa en la clave de duplicación
  (DUP-1).
  - AC: dado un gasto nuevo con (proveedor, nº factura, fecha, importe)
    idénticos a un gasto existente; cuando se completa la extracción;
    entonces se crea una duplicación `probable` y la aceptación queda
    bloqueada hasta resolución.

## TCK — Ticket / documento menor

- **FR-TCK-1**: El sistema permite registrar un ticket como documento fuente
  de tipo `ticket`, que puede no contener desglose fiscal completo.
  - AC: dado un ticket con solo total e IVA incluido; cuando se crea el gasto
    asociado; entonces el sistema permite derivar la base imponible y la
    cuota de IVA del total (regla VR-TICKET) o marcar el campo como
    incierto para revisión humana.
- **FR-TCK-2**: Un ticket sin NIF/CIF del proveedor visible debe permitir
    asociar el proveedor manualmente en la revisión.
  - AC: dado un ticket cuyo proveedor no se pudo extraer; cuando un usuario
    asigna el proveedor en la revisión; entonces el gasto queda con proveedor
    y puede continuar a validación.
- **FR-TCK-3**: Los tickets no requieren número de documento; si no hay
    número, la clave de duplicación usa (proveedor, fecha, importe) y la
    detección se marca como menos fiable (DUP-2).

## DOC — Documento fuente

- **FR-DOC-1**: El sistema acepta como documento fuente archivos PDF (texto o
  escaneado), imágenes y XML estructurado (Facturae/e-invoice), dentro de
  límites de tamaño y páginas.
  - AC: dado un archivo PDF de 10 MB con 20 páginas; cuando se sube; entonces
    se registra como documento fuente con estado `uploaded`.
  - AC: dado un archivo que supera el tamaño máximo; cuando se sube; entonces
    el sistema lo rechaza con motivo y no crea documento fuente.
- **FR-DOC-2**: El sistema calcula el fingerprint SHA-256 del contenido al
  subir y lo asocia al documento fuente.
  - AC: dado un documento fuente subido; cuando se consulta; entonces su
    fingerprint SHA-256 es visible y coincide con el contenido.
- **FR-DOC-3**: El documento fuente es inmutable: su contenido no puede
  modificarse tras la subida (NFR-3).
  - AC: dado un documento fuente ya subido; cuando se intenta reemplazar su
    contenido; entonces el sistema lo bloquea; la única vía es subir un
    documento nuevo (con nuevo fingerprint).
- **FR-DOC-4**: El nombre de archivo se normaliza a un nombre seguro
  generado por el sistema; el nombre original no se usa en rutas.
  - AC: dado un archivo subido con nombre `factura (1).pdf`; cuando se
    almacena; entonces el nombre interno es generado por el sistema y el
    nombre original solo se conserva como dato descriptivo.
- **FR-DOC-5**: El sistema detecta el formato real del archivo (sniffing de
  magic bytes), no confía en la extensión.
  - AC: dado un archivo `.pdf` cuyo contenido es en realidad una imagen;
    cuando se sube; entonces el formato detectado es `image` y el pipeline
    usa el método correspondiente.

## EXP — Gasto

- **FR-EXP-1**: El sistema permite crear un gasto a partir de un documento
  fuente, asociando proveedor, número de documento, fecha, moneda, categoría
  y método de pago.
  - AC: dado un documento fuente con valores validados; cuando se crea el
    gasto; entonces el gasto queda en estado `draft` (borrador) con esos
    valores.
- **FR-EXP-2**: Un gasto referencia exactamente un documento fuente (salvo
  split explícito, INV-3/INV-4).
  - AC: dado un gasto; cuando se consulta; entonces tiene exactamente un
  documento fuente asociado (o un split documentado).
- **FR-EXP-3**: El sistema permite modificar un gasto solo mientras no esté
  en estado terminal (`accepted`, `rejected`, `failed`); las modificaciones
  quedan auditadas.
  - AC: dado un gasto en `draft`; cuando se modifica su categoría; entonces
    el cambio queda registrado en auditoría (usuario, fecha, antes/después).
  - AC: dado un gasto en `accepted`; cuando se intenta modificar; entonces el
    sistema lo bloquea.
- **FR-EXP-4**: Un gasto solo puede ser aceptado si todos sus valores
  obligatorios están validados (INV-8).
  - AC: dado un gasto con un valor obligatorio no validado; cuando se intenta
    aceptar; entonces la aceptación se bloquea.
- **FR-EXP-5**: El sistema permite anular (cancelar) un gasto aceptado,
  creando un registro de anulación auditado; el gasto aceptado original no se
  modifica (inmutabilidad del hecho contable, NFR-3 aplicada a hechos
  aceptados).
  - AC: dado un gasto aceptado; cuando un usuario autorizado lo anula con
    motivo; entonces el gasto original conserva su estado `accepted` y se
    crea un registro de anulación que lo neutraliza en consultas posteriores.

## LIN — Líneas de gasto

- **FR-LIN-1**: Un gasto contiene una o más líneas de gasto, cada una con
  descripción, cantidad, importe (base) y tipo impositivo.
  - AC: dado un gasto; cuando se añade una línea con descripción, cantidad,
    importe y tipo impositivo; entonces la línea queda asociada al gasto.
- **FR-LIN-2**: La suma de las bases de las líneas de gasto debe coincidir
  con la base imponible total del gasto (tolerancia documentada, INV-1).
  - AC: dado un gasto cuyas líneas suman una base distinta de la base total
    declarada; cuando se valida; entonces el gasto queda en
    `validation_error`.
- **FR-LIN-3**: El importe de una línea de gasto no puede ser negativo.
  - AC: dada una línea con importe negativo; cuando se valida; entonces la
    validación falla (VR-NEG).

## TAX — Líneas fiscales

- **FR-TAX-1**: Cada línea de gasto puede tener una o más líneas fiscales
  (IVA y/o retención), cada una con tipo impositivo, base imponible y cuota.
  - AC: dada una línea de gasto con IVA al 21 %; cuando se añade la línea
    fiscal; entonces la cuota calculada es `base × 21 %` redondeada según la
    regla de redondeo documentada.
- **FR-TAX-2**: La cuota de una línea fiscal debe ser coherente con
  `base × tipo impositivo` (tolerancia de redondeo documentada, INV-1).
  - AC: dada una línea fiscal cuya cuota no coincide con `base × tipo` dentro
    de la tolerancia; cuando se valida; entonces la validación falla
    (VR-ARITH).
- **FR-TAX-3**: Los tipos impositivos usados deben ser conocidos y vigentes en
  la fecha del documento (VR-TAXRATE).
  - AC: dada una línea fiscal con un tipo de IVA no existente o no vigente en
    la fecha del documento; cuando se valida; entonces la validación falla o
    genera advertencia según la severidad configurada (ver 06-validation-
    rules.md).
- **FR-TAX-4**: Las retenciones reducen el total a pagar; se registran como
  líneas fiscales de tipo `withholding`.
  - AC: dado un gasto con base 100, IVA 21 y retención IRPF 15 sobre base 100;
    cuando se calcula el total; entonces total = 100 + 21 − 15 = 106.

## TOT — Totales

- **FR-TOT-1**: El total de un gasto se calcula como
  `base + cuota IVA − retenciones` (decimal exacto, tolerancia de redondeo
  documentada, INV-1).
  - AC: dado un gasto con base 100, IVA 21, retención 0; cuando se calcula el
    total; entonces total = 121.
- **FR-TOT-2**: El total mostrado al usuario es el total validado; nunca el
  total extraído sin validar (08-value-semantics.md).
  - AC: dado un gasto en revisión cuyo total extraído difiere del total
    recalculado; cuando se muestra la pantalla de revisión; entonces se
    muestran ambos valores y el total extraído está marcado como no
    confirmado.

## CUR — Moneda

- **FR-CUR-1**: Todo valor monetario se denomina en una moneda ISO-4217 y se
  almacena como decimal exacto (nunca float, INV-2).
  - AC: dado un valor monetario; cuando se almacena; entonces su
    representación es decimal exacto con el número de decimales de la moneda.
- **FR-CUR-2**: No se mezclan monedas en un mismo gasto ni en una suma sin
  conversión explícita y documentada.
  - AC: dado un gasto en EUR; cuando se intenta añadir una línea en USD;
    entonces el sistema lo bloquea (o exige conversión explícita con tipo de
    cambio registrado, según decisión OQ-4).
- **FR-CUR-3**: La conversión entre monedas usa un tipo de cambio con fecha de
  referencia y origen, registrado.
  - AC: dada una conversión EUR→USD; cuando se aplica; entonces el tipo de
    cambio usado queda registrado junto con la conversión.

## CAT — Categoría

- **FR-CAT-1**: El sistema permite definir categorías de gasto (nombre,
  descripción) y asignar una categoría a cada gasto.
  - AC: dada una categoría registrada; cuando se asigna a un gasto; entonces
    el gasto queda clasificado.
- **FR-CAT-2**: Un gasto aceptado debe tener categoría asignada (si la
  política lo exige — ver OQ-5).
  - AC: dado un gasto sin categoría y política de categoría obligatoria;
    cuando se intenta aceptar; entonces la aceptación se bloquea.
- **FR-CAT-3**: El sistema permite listar gastos por categoría.
  - AC: dada una categoría con gastos aceptados; cuando se consulta la
    categoría; entonces se listan sus gastos aceptados.

## PAY — Método de pago y pago

- **FR-PAY-1**: El sistema permite definir métodos de pago (efectivo, tarjeta,
  transferencia, cheque, otro) y registrar el pago de un gasto.
  - AC: dado un gasto; cuando se registra su pago con método, fecha y
    referencia; entonces el gasto queda con pago registrado.
- **FR-PAY-2**: El importe pagado se registra como decimal exacto y, en pago
  único, debe coincidir con el total del gasto (tolerancia documentada).
  - AC: dado un gasto con total 121 y un pago único de 120; cuando se valida;
    entonces se genera advertencia o bloqueo según severidad (VR-PAY).
- **FR-PAY-3**: (Opcional, ver OQ-6) El sistema permite pagos parciales:
  varios pagos cuyo importe sume el total del gasto.

## EXT — Extracción

- **FR-EXT-1**: El sistema extrae valores del documento fuente usando una
  cascada determinística: XML estructurado → PDF con texto → OCR →
  visión/LLM como último recurso.
  - AC: dado un documento XML Facturae; cuando se procesa; entonces la
    extracción usa el método `xml_schema` y no recurre a OCR ni LLM.
  - AC: dado un PDF escaneado sin capa de texto; cuando se procesa; entonces
    la extracción usa `ocr` (o `vision_llm` si OCR no es viable).
- **FR-EXT-2**: Cada valor extraído lleva confidence (0..1) y provenance
  (método, página, coordenadas, regla).
  - AC: dado un valor extraído; cuando se consulta; entonces su confidence y
    provenance son visibles.
- **FR-EXT-3**: Todo output de extracción (incluido el de LLM) se valida
  contra un esquema estricto; si falla, no se guarda como valor extraído.
  - AC: dado un output de LLM que no cumple el esquema; cuando se procesa;
    entonces la extracción queda en `validation_error` y no produce valores
    extraídos válidos.
- **FR-EXT-4**: El método de extracción usado se registra en la extracción
  (`provenance.method`) y es visible en la revisión.
  - AC: dada una extracción completada; cuando se abre la revisión; entonces
    el método usado es visible.
- **FR-EXT-5**: La extracción es idempotente: re-procesar el mismo documento
  fuente produce el mismo resultado o un resultado equivalente, sin crear
  duplicados de valores (NFR-4).
  - AC: dado un documento fuente ya extraído; cuando se re-procesa; entonces
    no se duplican valores extraídos y el estado se actualiza de forma
    consistente.

## NOR — Normalización

- **FR-NOR-1**: El sistema normaliza valores extraídos a formatos canónicos:
  moneda ISO-4217 decimal exacto, fecha ISO-8601, NIF/CIF validado, tipo
  impositivo conocido.
  - AC: dado un valor extraído de fecha `31/12/2025`; cuando se normaliza;
    entonces el valor normalizado es `2025-12-31`.
  - AC: dado un valor extraído de importe `1.234,56 €`; cuando se normaliza;
    entonces el valor normalizado es `1234.56` en EUR (decimal exacto).
- **FR-NOR-2**: La normalización es determinística: el mismo valor extraído
  produce siempre el mismo valor normalizado.
  - AC: dado un valor extraído; cuando se normaliza dos veces; entonces el
    resultado es idéntico.
- **FR-NOR-3**: Si un valor no puede normalizarse (p. e.g. moneda
  desconocida), se marca como incierto para revisión humana.
  - AC: dado un valor extraído con moneda no reconocible; cuando se
    normaliza; entonces el campo queda `uncertain` y requiere revisión.

## VAL — Validación

- **FR-VAL-1**: El sistema ejecuta validación determinística sobre valores
  normalizados: aritmética, esquema, normalización, referencias (ver
  06-validation-rules.md).
  - AC: dado un gasto con valores normalizados; cuando se ejecuta la
    validación; entonces cada regla VR-xxx produce un resultado
    (`passed`/`failed`/`warning`) registrado.
- **FR-VAL-2**: La validación es idempotente y no modifica valores: solo
  produce resultados y transiciones de estado.
  - AC: dado un gasto validado; cuando se re-valida sin cambios; entonces el
    resultado es el mismo y no se alteran valores.
- **FR-VAL-3**: Un valor solo puede ser validado si es normalizado; un gasto
  solo puede aceptarse si sus valores obligatorios están validados (INV-8).
  - AC: dado un valor no normalizado; cuando se intenta marcar como validado;
    entonces el sistema lo bloquea.
- **FR-VAL-4**: Los valores con confidence por debajo del umbral (configurable,
  OQ-1) requieren revisión humana antes de validarse.
  - AC: dado un valor extraído con confidence 0.7 y umbral 0.9; cuando se
    intenta validar sin revisión; entonces el sistema lo bloquea y lo marca
    `uncertain`.

## REV — Revisión humana

- **FR-REV-1**: El sistema proporciona una pantalla de revisión que muestra,
  por campo: valor extraído, valor normalizado, confidence, provenance y el
  documento fuente (snippet/imagen) para contraste.
  - AC: dado un gasto en revisión; cuando se abre la pantalla; entonces cada
    campo muestra los valores de los distintos niveles y su estado.
- **FR-REV-2**: Un usuario puede confirmar, corregir o rechazar cada campo en
  revisión.
  - AC: dado un campo en revisión; cuando el usuario corrige su valor;
    entonces la corrección queda auditada (E14) y el campo pasa a validado
    (`corrected`).
- **FR-REV-3**: Toda corrección manual queda auditada: usuario, fecha/hora,
    valor anterior, valor posterior (INV-7).
  - AC: dada una corrección manual; cuando se consulta la auditoría; entonces
    el registro contiene usuario, fecha/hora, antes y después.
- **FR-REV-4**: La revisión es obligatoria para campos `uncertain` y para
  gastos con duplicación `probable` no resuelta.
  - AC: dado un gasto con un campo `uncertain`; cuando se intenta aceptar sin
    revisar ese campo; entonces el sistema lo bloquea.
- **FR-REV-5**: El contenido del documento fuente es dato, nunca instrucción
  (protección contra prompt injection; ver skill `security`).
  - AC: dado un documento cuyo texto contiene instrucciones dirigidas a un
    LLM; cuando se procesa; entonces el contenido se trata solo como dato de
    extracción.

## ACC — Aceptación

- **FR-ACC-1**: Un gasto se acepta mediante aprobación explícita (humana o
  regla aprobada) tras validación completa (INV-8).
  - AC: dado un gasto con todos los valores obligatorios validados y sin
    duplicación `probable` pendiente; cuando un usuario autorizado acepta;
    entonces el gasto pasa a `accepted` y queda registrado en auditoría.
- **FR-ACC-2**: La aceptación es una transición irreversible: un gasto
  `accepted` no vuelve a estados anteriores (solo puede anularse, FR-EXP-5).
  - AC: dado un gasto `accepted`; cuando se intenta devolverlo a `draft`;
    entonces el sistema lo bloquea.
- **FR-ACC-3**: Un valor extraído nunca se acepta sin pasar por
    normalización y validación (08-value-semantics.md).
  - AC: dado un valor solo extraído; cuando se intenta aceptar el gasto;
    entonces el sistema lo bloquea.
- **FR-ACC-4**: La aceptación registra: usuario (o regla), fecha/hora,
    valores aceptados (snapshot) y documento fuente de referencia.
  - AC: dado un gasto aceptado; cuando se consulta; entonces el snapshot de
    valores aceptados y la referencia al documento fuente son visibles.

## REJ — Rechazo

- **FR-REJ-1**: Un gasto puede rechazarse en cualquier estado no terminal,
  con motivo obligatorio.
  - AC: dado un gasto en `draft`; cuando un usuario lo rechaza con motivo;
    entonces el gasto pasa a `rejected` (terminal) y el motivo queda
    registrado.
- **FR-REJ-2**: El rechazo es irreversible: un gasto `rejected` no puede
  aceptarse directamente; debe crearse un gasto nuevo a partir del mismo
  documento fuente (si procede).
  - AC: dado un gasto `rejected`; cuando se intenta aceptar; entonces el
    sistema lo bloquea y ofrece crear un gasto nuevo.
- **FR-REJ-3**: El rechazo no elimina el documento fuente ni la extracción:
  quedan disponibles para un nuevo gasto.
  - AC: dado un gasto rechazado; cuando se consulta el documento fuente;
    entonces sigue disponible y su extracción es reutilizable.

## DUP — Duplicados

Ver 07-duplicates.md (DUP-1..DUP-7). Resumen funcional:

- **FR-DUP-1**: El sistema detecta duplicados por fingerprint SHA-256 (mismo
  archivo) y por clave de duplicación (proveedor, nº documento, fecha,
  importe).
- **FR-DUP-2**: Un duplicado `probable` bloquea la aceptación hasta
  resolución humana.
- **FR-DUP-3**: La resolución (confirmar duplicado / confirmar no-duplicado)
  es humana, auditada y reversible solo mientras no haya gasto aceptado
  afectado.

## FST — Estados de fallo

- **FR-FST-1**: Todo fallo (de extracción, validación o de sistema) deja el
  objeto en un estado de fallo con motivo registrado.
  - AC: dada una extracción que falla por archivo corrupto; cuando termina;
    entonces el documento fuente queda en `failed` con motivo "archivo
    corrupto".
- **FR-FST-2**: Un estado de fallo es terminal para el objeto afectado, pero
  no impide crear un nuevo intento (nueva extracción o nuevo gasto) a partir
  del mismo documento fuente si el fallo es recuperable.
  - AC: dado un documento fuente en `failed` por fallo de OCR; cuando se
    reintenta la extracción; entonces se crea una nueva extracción y el
    documento fuente sale de `failed` al nuevo intento.
- **FR-FST-3**: Los fallos no se silencian: todo `failed` es visible y
  auditable.
  - AC: dado un objeto en `failed`; cuando se consulta el listado de
    documentos/gastos; entonces aparece con su estado y motivo.
