# 05 — Semántica de fallos (GastosE)

Principio (skill `architecture`): **toda operación tiene estado de fallo
explícito y recuperable**. Los fallos no se silencian (FR-FST-3): todo
`failed` es visible y auditable, con motivo registrado (INV-15, FR-FST-1).

## 1. Fallos por componente

### 1.1 Subida de documento (API / Document Ingestion)

| Fallo | Comportamiento | Estado resultante |
|---|---|---|
| Tamaño/páginas fuera de límites | Rechazo en la validación previa; no se crea documento fuente. | Sin objeto; error 422 con motivo. |
| Formato no soportado (magic bytes) | Rechazo; no se almacena. | Sin objeto; error 422 con motivo. |
| Error de escritura en document store | Transacción de registro no se completa; el archivo (si se escribió) se limpia. | Sin documento fuente; error 500 (o 503) con motivo. |
| Error de DB al registrar | Transacción se revierte; no hay documento a medio registrar. | Sin documento fuente; error 500. |
| Fingerprint coincide con existente | No es fallo: se crea duplicación `probable` (DUP-1). | Documento `uploaded` + duplicación `probable`. |

**Recuperación**: el usuario puede reintentar la subida (nuevo archivo o
corregido). La subida es idempotente por `Idempotency-Key` (repetir la misma
key no duplica).

### 1.2 Extracción (worker)

| Fallo | Comportamiento | Estado resultante |
|---|---|---|
| Documento corrupto / ilegible | Extracción `failed` con motivo; documento `failed` con motivo (FR-FST-1). | Extracción `failed` (T); documento `failed` (T, recuperable por reintento). |
| Fingerprint no coincide al leer (integridad) | Extracción `failed` (motivo: integridad); alerta (NFR-3). | Como arriba. |
| Output no cumple esquema estricto (VR-SCHEMA-1) | Extracción `failed`/`validation_error`; **no se guardan valores parciales**. | Extracción `failed`; documento `validation_error`. |
| Timeout / límite de memoria en parser | El parser se aborta (límites de skill `security`); extracción `failed` con motivo. | Como "corrupto". |
| Fallo de OCR/LLM (servicio no disponible) | Reintento con backoff (máx. N); si se agota, `failed`. | Extracción `failed` (T); documento `failed` (T, recuperable). |
| Worker muere a mitad de tarea | La tarea vuelve a `pending` (claim con timeout/lease); otro worker la reclama. | Sin cambio visible (o `processing` hasta el lease expira). |

**Recuperación** (FR-FST-2): un fallo de extracción es terminal para ESA
extracción, pero permite crear una **nueva extracción** (reintento) a partir
del mismo documento fuente si el fallo es recuperable. El documento sale de
`failed` al nuevo intento (`failed -> processing`, 04-lifecycle.md). Nunca se
aceptan datos parciales de una extracción fallida.

### 1.3 Normalización / validación (Expense Core)

| Fallo | Comportamiento | Estado resultante |
|---|---|---|
| Valor no normalizable (p. e.g. moneda desconocida) | Campo marcado `uncertain` (FR-NOR-3); requiere revisión humana. | Documento/gasto `uncertain`. |
| Regla VR BLOCK falla (aritmética, esquema, referencias) | Gasto `validation_error` con las reglas fallidas registradas (INV-15). | Gasto `validation_error`; documento `validation_error`. |
| Regla VR WARN falla | Advertencia registrada y visible; no bloquea. | Gasto continúa; advertencia en auditoría. |
| Confidence < umbral sin revisión | Campo `uncertain`; validación bloqueada hasta revisión (FR-VAL-4, VR-BIZ-4). | Gasto `uncertain`/`under_review`. |

**Recuperación**: corrección manual (revisión humana) → revalidación →
`validated` (04-lifecycle.md: `validation_error -> manually_corrected ->
validated`). La validación es idempotente (FR-VAL-2): revalidar sin cambios
produce el mismo resultado.

### 1.4 Revisión / aceptación (Review & Acceptance)

| Fallo | Comportamiento | Estado resultante |
|---|---|---|
| Aceptación con regla BLOCK fallida | La aceptación se bloquea; error 409 con las reglas fallidas. | Gasto no cambia (p. e.g. sigue `ready_for_acceptance` o `validation_error`). |
| Aceptación con duplicación `probable` pendiente | Bloqueada (INV-6). | Gasto `duplicate`; error 409. |
| Rechazo sin motivo | Rechazado (motivo obligatorio, FR-REJ-1). | Error 422. |
| Transición inválida (p. e.g. aceptar un `rejected`) | Bloqueada por la máquina de estados del dominio. | Error 409 (estado inválido). |
| Error de DB en la transacción de aceptación | Transacción se revierte; el gasto no queda a medio aceptar. | Sin cambio; error 500. |

**Recuperación**: el gasto sigue en su estado previo; el usuario corrige y
reintenta. Los estados terminales (`accepted`, `rejected`, `failed`,
`confirmed_duplicate`, `voided`) son irreversibles: la única salida "lógica"
es crear un nuevo objeto (nueva extracción, nuevo gasto) o anular (FR-EXP-5).

## 2. Reintentos

- **Subida**: reintento manual por el usuario (nueva petición). Idempotente
  por `Idempotency-Key`.
- **Extracción**: reintentos automáticos con backoff exponencial (máximo de
  intentos configurable, NFR-9). Agotados → `failed` con motivo. Reintento
  manual (nueva extracción) si el fallo es recuperable (FR-FST-2).
- **Validación**: idempotente; no requiere reintento (re-ejecutar produce el
  mismo resultado, FR-VAL-2).
- **Aceptación**: síncrona; si falla por regla BLOCK, el usuario corrige y
  reintenta. Si falla por error de sistema, la transacción se revierte y el
  usuario reintenta (idempotente por diseño: estado actual + transición
  esperada; skill `api-design`).

## 3. Idempotencia (NFR-4)

- **Subida**: `Idempotency-Key` en `POST /api/v1/documents`; repetir la misma
  key devuelve la misma respuesta sin re-ejecutar. Un fingerprint ya
  existente no crea un segundo documento idéntico: se detecta como duplicación
  (DUP-1).
- **Extracción**: re-procesar el mismo documento no duplica valores
  (FR-EXT-5): reemplazo atómico (estado `reprocessed`).
- **Validación**: revalidar sin cambios produce el mismo resultado
  (FR-VAL-2).
- **Aceptación/corrección**: idempotentes por diseño (estado actual +
  transición esperada): intentar aceptar un gasto ya `accepted` devuelve el
  estado actual (o 409 si la transición no es válida), sin efectos
  secundarios.
- **Claim de cola**: atómico; una tarea no se procesa dos veces a la vez.

## 4. Estados de fallo con motivo (FR-FST)

- Todo objeto en estado de fallo (`failed`, `validation_error`) lleva motivo
  registrado (INV-15). El motivo es una cadena legible + código de error
  estable (p. e.g. `file_corrupt`, `schema_violation`, `ocr_unavailable`,
  `arithmetic_mismatch`).
- Los motivos se registran en auditoría (E16) y son visibles en listados
  (FR-FST-3).
- El motivo de fallo de una extracción incluye el método que falló y el
  nivel de la cascada alcanzado.

## 5. Imposibilidad de saltar los cinco niveles de valor

La arquitectura hace **estructuralmente imposible** saltar niveles
(08-value-semantics.md), no solo por convención:

| Garantía | Mecanismo arquitectónico |
|---|---|
| N2 (extraído) solo lo produce el pipeline de extracción | Solo el worker (C5) escribe valores extraídos (E3), y solo tras validar el esquema estricto (VR-SCHEMA-1). La API y el dominio no pueden "inventar" valores extraídos. |
| N3 (normalizado) solo a partir de N2 | La normalización (Expense Core) solo opera sobre valores extraídos persistidos (E3→E4 con referencia obligatoria). No hay camino para normalizar un valor que no tiene origen E3. |
| N4 (validado) solo a partir de N3 | La validación solo opera sobre valores normalizados (E4→E5 con referencia). Un valor no normalizado no puede marcarse validado (FR-VAL-3). |
| N5 (aceptado) solo a partir de N4 | La aceptación (transacción) verifica que todos los valores obligatorios están validados (INV-8) antes de transitar a `accepted`. Si no, 409. |
| Referencias obligatorias entre niveles | Cada valor de nivel superior referencia su origen (E3→E4→E5, INV-10). Sin referencia no hay valor válido en el nivel superior. |
| Prohibiciones (08-value-semantics.md §2) | Implementadas como comprobaciones de transición en el dominio (máquina de estados): aceptar un valor extraído sin normalizar/validar → bloqueado; aceptar con duplicación probable → bloqueado; valor sin confidence/provenance → no es valor extraído válido (INV-11). |
| Snapshot inmutable en N5 | Al aceptar, se registra el snapshot de valores validados (INV-14); el gasto aceptado no se modifica (solo se anula). |

**Conclusión**: el flujo N1→N2→N3→N4→N5 está forzado por la separación de
componentes (quién puede escribir cada nivel) + las referencias obligatorias
+ las comprobaciones de transición. `LLM OUTPUT == ACCOUNTING FACT` es
imposible: el output del LLM es N2 (valor extraído con confidence y
provenance), y para llegar a N5 debe pasar por N3, N4 y aprobación explícita.

## 6. Transacciones acotadas

- Una unidad de trabajo = una operación de negocio (skill `architecture`).
  Ejemplos: "subir documento" (registro + fingerprint + tarea en cola),
  "aceptar gasto" (revalidación + transición + snapshot + auditoría),
  "resolver duplicado" (transición + auditoría).
- La extracción (larga) NO está en una transacción de la API: es asíncrona
  (ADR-0005); el worker persiste sus efectos en transacciones acotadas.
- Si una transacción falla, se revierte completa: no hay estados intermedios
  visibles (p. e.g. no hay "gasto a medio aceptar").
