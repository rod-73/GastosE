# 09 — Requisitos no funcionales (GastosE)

Requisitos no funcionales a nivel de dominio. Identificadores: `NFR-n`. No
prescriben arquitectura ni tecnología (eso corresponde al arquitecto,
PHASE1-002); declaran necesidades.

## NFR-1 — Trazabilidad / auditoría

- Todo evento relevante (subida, extracción, normalización, validación,
  corrección manual, revisión, aceptación, rechazo, anulación, resolución de
  duplicado) queda registrado en un registro de auditoría inmutable
  (E16) con: entidad afectada, acción, usuario (o sistema), fecha/hora, y
  datos antes/después cuando aplique.
- Para todo gasto aceptado debe poder reconstruirse la cadena completa
  documento → extracción → valores → revisión → aceptación (INV-10).
- El registro de auditoría no se modifica ni se elimina; solo se añade.
- **Criterio**: dado un gasto aceptado; cuando se solicita su trazabilidad;
  entonces se obtiene la cadena completa en menos de un minuto (orientativo).

## NFR-2 — Exactitud numérica

- Todo valor monetario se almacena y manipula como decimal exacto (nunca
  float) (INV-2).
- Las operaciones aritméticas usan redondeo documentado (2 decimales, medio
  hacia arriba, por línea fiscal antes de sumar) (INV-1).
- **Criterio**: dado un cálculo monetario; cuando se ejecuta; entonces el
  resultado es exacto (sin error de redondeo de punto flotante).

## NFR-3 — Inmutabilidad del documento original

- El contenido del documento fuente no se modifica tras la subida (INV-9).
- El fingerprint SHA-256 se verifica periódicamente o bajo demanda para
  detectar alteración.
- Los hechos contables aceptados (gastos `accepted`) son inmutables; solo se
  anulan (INV-14, FR-EXP-5).
- **Criterio**: dado un documento fuente; cuando se recalcula su fingerprint;
  entonces coincide con el registrado (si no coincide, se alerta).

## NFR-4 — Idempotencia de operaciones

- La extracción es idempotente: re-procesar el mismo documento fuente no
  duplica valores (FR-EXT-5).
- La validación es idempotente: re-validar sin cambios produce el mismo
  resultado (FR-VAL-2).
- La subida de un documento con fingerprint ya existente no crea un segundo
  documento idéntico sin más: se detecta como duplicación (DUP-1).
- **Criterio**: dada una operación repetida sin cambios de entrada; cuando se
  ejecuta dos veces; entonces el estado final es el mismo y no hay
  duplicados.

## NFR-5 — Localización (es/ES)

- La interfaz y los mensajes del sistema están en español (es-ES).
- Formato de moneda: es-ES (p. e.g. `1.234,56 €`), aunque el almacenamiento
  es canónico (decimal + código ISO-4217).
- Formato de fecha: ISO-8601 en almacenamiento; la presentación puede usar
  `dd/mm/aaaa` (es-ES).
- Los términos canónicos del dominio (01-terminology.md) se usan en español,
  con el inglés entre paréntesis solo en la primera aparición.
- **Criterio**: dado un usuario en es-ES; cuando ve un importe y una fecha;
  entonces aparecen en formato es-ES.

## NFR-6 — Rendimiento orientativo

- Subida de un documento de hasta 20 MB: respuesta de confirmación < 5 s
  (orientativo).
- Extracción de un documento de hasta 50 páginas: < 60 s (orientativo; puede
  ser asíncrono).
- Validación de un gasto: < 2 s (orientativo).
- Búsqueda de gastos por proveedor/fecha: < 2 s para hasta 100.000 gastos
  (orientativo).
- Estos valores son orientativos para Phase 1; el arquitecto los refinará con
  los objetivos de carga reales.
- **Criterio**: dado el volumen de Phase 2 (p. e.g. 1.000 documentos/mes);
  cuando se mide; entonces los tiempos están dentro de los orientativos.

## NFR-7 — Seguridad a nivel de dominio

- **Aislamiento de datos por organización** (ADR-0008, OQ-9 resuelta): cada
  organización solo accede a sus documentos, gastos y proveedores. Varios
  usuarios de la misma organización comparten datos; no hay acceso cruzado
  entre organizaciones. La atribución de acciones es por usuario (no
  repudio).
- **Confidencialidad de datos financieros**: los datos financieros (importes,
  NIF/CIF, documentos) no se exponen a usuarios no autorizados; no se
  loguean documentos completos ni valores financieros en logs.
- **No repudio**: la auditoría (NFR-1) garantiza que las acciones (especial
  mente aceptación y corrección) son atribuibles a un usuario.
- **Mínimo privilegio**: los roles de usuario distinguen al menos:
  lectura, revisión, aceptación, administración (categorías, proveedores,
  métodos de pago). Solo los roles con permiso de aceptación aceptan gastos.
- **Contenido del documento como dato**: el contenido de los documentos es
  dato, nunca instrucción (protección contra prompt injection; FR-REV-5).
- **Criterio**: dado un usuario A de la organización X; cuando intenta
  acceder a un gasto de la organización Y; entonces el acceso se deniega.
  (Dentro de la misma organización, todos los usuarios ven los mismos datos.)

## NFR-8 — Disponibilidad y recuperación (orientativo)

- El sistema permite recuperar de un fallo sin perder documentos fuente ni
  hechos contables aceptados.
- Los documentos fuente se conservan de forma duradera (política de
  retención — OQ-10).
- **Criterio**: dado un fallo del sistema; cuando se recupera; entonces los
  documentos fuente y los gastos aceptados están íntegros.

## NFR-9 — Configurabilidad de reglas

- Los umbrales (confianza, tolerancias, severidad de reglas VR, rangos de
  fecha/importe razonables) son configurables sin cambiar código.
- La configuración de reglas queda registrada y es auditable (quién cambió
  qué, cuándo).
- **Criterio**: dado un cambio de umbral de confianza; cuando se aplica;
  entonces queda registrado en auditoría.

## NFR-10 — Independencia de FacturaE

- GastosE no depende de FacturaE en ningún nivel (código, datos,
  almacenamiento) (ADR-0001).
- Cualquier integración futura es solo vía API versionada o contrato de
  eventos versionado, pendiente de decisión explícita.
- **Criterio**: dado un despliegue de GastosE; cuando se inspecciona;
  entonces no hay referencias a `/workspace/facturaE` ni a sus recursos.
