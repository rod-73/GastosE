# 04 — Límites asíncronos (GastosE)

## 1. Qué es asíncrono y qué es síncrono

| Operación | Síncrono / Asíncrono | Justificación |
|---|---|---|
| Subida de documento (validación + fingerprint + almacenamiento) | **Síncrono** (respuesta < 5 s, NFR-6) | El usuario necesita confirmación inmediata de que el documento se aceptó y su fingerprint. No hay procesamiento pesado: solo lectura del archivo, hash SHA-256 y escritura. |
| **Extracción** (XML/PDF/OCR/LLM) | **Asíncrono** | Puede tardar hasta 60 s (NFR-6) o más (OCR/LLM de 50 páginas). Mantener la conexión HTTP abierta no escala y expone el pipeline a timeouts de red. El cliente consulta el estado. |
| Normalización (N3) | **Asíncrono** (encadenado a la extracción) | Determinística y rápida, pero opera sobre el resultado de la extracción; se ejecuta en el worker o en un paso inmediato posterior, fuera de la petición de subida. |
| Validación determinística (N4) | **Síncrono** (< 2 s, NFR-6) | Rápida (aritmética, esquema, referencias). Se ejecuta en la petición que la dispara (envío a revisión, aceptación). La validación definitiva en la aceptación es síncrona porque el usuario espera la decisión. |
| Revisión (confirmar/corregir/rechazar campos) | **Síncrono** | Operación de usuario interactiva; respuesta inmediata. |
| Aceptación / rechazo / anulación | **Síncrono** | Transición de estado con revalidación definitiva; el usuario espera el resultado. |
| Resolución de duplicado | **Síncrono** | Decisión humana interactiva. |
| CRUD de catálogos (proveedores, categorías, métodos de pago, tipos impositivos) | **Síncrono** | Operaciones de referencia rápidas. |
| Verificación de fingerprint bajo demanda (NFR-3) | **Síncrono** (bajo demanda) / **periódico** (asíncrono, task) | Bajo demanda: rápido (hash de un archivo). Periódico: task programada fuera de petición. |

**Regla general**: solo la extracción es asíncrona de forma explícita. Todo
lo demás es síncrono porque es rápido (< 2 s) o es una decisión interactiva
del usuario. No se introduce asincronía "por defecto": cada límite asíncrono
se justifica (NFR-6, escalabilidad, timeouts).

## 2. Mecanismo: cola en base de datos + worker (ADR-0005)

- **Cola**: tabla de trabajo en PostgreSQL (no se prescriben columnas; eso
  es PHASE1-003). Cada tarea referencia: documento fuente (fingerprint),
  formato detectado, estado (`pending`/`running`/`completed`/`failed`),
  intentos, motivo de fallo, timestamps.
- **Claim atómico**: el worker reclama tareas con una operación atómica
  (p. e.g. `UPDATE ... WHERE estado='pending' RETURNING` con límite), de modo
  que dos workers no procesan la misma tarea (evita duplicación de trabajo).
- **Worker**: proceso separado (C5), N réplicas. Ejecuta la cascada
  determinística, valida el esquema estricto, persiste valores extraídos.
- **Reintentos**: backoff exponencial con máximo de intentos; si se agota, la
  tarea queda `failed` con motivo (FR-FST-1). El reintento manual (nueva
  extracción) está permitido si el fallo es recuperable (FR-FST-2).
- **Idempotencia**: re-procesar el mismo documento no duplica valores
  (FR-EXT-5): el worker reemplaza atómicamente los valores de la extracción
  (estado `reprocessed`).

### Por qué cola en BD y no broker externo (resumen; detalle en ADR-0005)

- Runtime disponible: podman + Python 3.9, sin Node.js; simplicidad operativa.
- PostgreSQL ya es la base de datos de producción (regla dura). Una cola en
  BD no añade un componente nuevo ni un nuevo sistema de fallo.
- El volumen (Phase 2: ~1.000 documentos/mes, NFR-6) es bajo; la cola en BD
  es más que suficiente.
- Transaccionalidad: la creación de la tarea de extracción y el registro del
  documento fuente pueden estar en la misma transacción (atomo
  "documento registrado + tarea en cola").
- Si en el futuro el volumen exige un broker (p. e.g. RabbitMQ/Redis), el
  contrato de cola (estado de tarea, claim, reintentos) permite migrar sin
  cambiar el dominio.

## 3. Contrato de la operación asíncrona (API)

- `POST /api/v1/documents` → `202 Accepted` con `Location:
  /api/v1/documents/{id}` (skill `api-design`).
- El cliente consulta el estado: `GET /api/v1/documents/{id}` → estado del
  ciclo A (`uploaded|processing|extracted|uncertain|validation_error|
  duplicate|manually_corrected|validated|accepted|rejected|
  confirmed_duplicate|failed`).
- El cliente **no asume duración** (skill `api-design`): el estado es la
  única fuente de verdad.
- No se prescribe websockets/SSE en Phase 1: polling del estado es
  suficiente para el volumen. Si la UI lo exige, se añadirá como mejora
  (contrato compatible).

## 4. Límites asíncronos y trust boundaries

- La frontera asíncrona `API → cola → worker` es un límite de proceso: la
  API no bloquea esperando al worker. El estado se comparte por la base de
  datos (fuente de verdad).
- El worker opera sobre un documento que es **dato no fiable** (contenido de
  terceros): ver 07-security-boundaries.md, sección 4 (trust boundary
  OCR/LLM).
- La normalización y la validación determinísticas se ejecutan tras la
  extracción, fuera de la petición de subida; sus resultados son visibles en
  el estado del documento/gasto.
