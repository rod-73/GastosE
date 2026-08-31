# 08 — Notas de rendimiento (NFR-6, orientativo)

Los valores de NFR-6 son orientativos para Phase 1; este documento explica
cómo la arquitectura los atiende y qué decisiones de Phase 2 los refinarán.

## 1. Objetivos (NFR-6) y cómo los atiende la arquitectura

| Objetivo (orientativo) | Mecanismo arquitectónico |
|---|---|
| Subida de documento ≤ 20 MB: confirmación < 5 s | La subida es síncrona pero ligera: validación de tamaño/formato, hash SHA-256 (rápido en CPU moderna: ~100-500 MB/s), escritura en volumen local. La extracción NO está en la petición (asíncrona, ADR-0005). La respuesta es `202 Accepted` tras registrar documento + tarea en cola. |
| Extracción ≤ 50 páginas: < 60 s (puede ser asíncrono) | Asíncrona (worker, ADR-0005). La cascada determinística prioriza métodos rápidos (XML → texto antes que OCR/LLM). El cliente consulta el estado; no hay timeout de conexión. Si un documento supera 60 s, el worker sigue procesando (no hay límite duro de petición). |
| Validación de un gasto: < 2 s | Síncrona y ligera: aritmética decimal, comprobaciones de esquema, referencias (queries indexadas). Sin llamadas externas. |
| Búsqueda de gastos por proveedor/fecha: < 2 s para 100.000 gastos | Queries indexadas (índices en proveedor, fecha, propietario — el modelo de persistencia, PHASE1-003, los definirá). Paginación por cursor (docs/api/README.md) para no transferir resultados grandes. |
| Volumen Phase 2: ~1.000 documentos/mes | Bajo volumen: cola en BD (ADR-0005) sin problemas; worker con 1-2 réplicas; PostgreSQL instancia única. |

## 2. Decisiones que protegen el rendimiento

- **Extracción asíncrona** (ADR-0005): desacopla la operación larga de la
  petición de subida; la API no bloquea.
- **Cascada determinística** (FR-EXT-1): los métodos rápidos (XML, texto) se
  prueban antes que los costosos (OCR, LLM); un documento XML no pasa por
  OCR.
- **Worker escalable**: N réplicas consumiendo la cola; la concurrencia se
  limita para no saturar CPU en OCR (configurable).
- **API stateless**: escala horizontalmente sin estado compartido.
- **Paginación por cursor** en colecciones: evita transferencias grandes y
  permite listados estables.
- **ETags** para recursos inmutables (documentos fuente): la UI puede cachear
  el documento y no re-descargarlo (skill `api-design`).
- **Validación previa de subida** (tamaño/formato antes de procesar):
  rechaza rápido los archivos inválidos sin coste de procesamiento.

## 3. Cuellos de botella previstos y mitigaciones

| Cuello de botella | Mitigación |
|---|---|
| OCR/LLM lento (CPU/GPU) | Worker separado; reintentos con backoff; umbral de páginas/tamaño; en el futuro, servicio externo de OCR/LLM (contrato, no acoplamiento). |
| Hash SHA-256 de archivos grandes | Rápido en CPU moderna; si un archivo de 20 MB tardara > 1 s, se procesaría en segundo plano (no bloquea la API más allá de la lectura). |
| Queries de listado con muchos filtros | Índices compuestos (PHASE1-003); paginación por cursor; filtros limitados (docs/api/README.md). |
| Crecimiento de la cola (picos) | La cola en BD acumula tareas; el worker las drena. Si el volumen crece mucho, migrar a broker (ADR-0005, consecuencia). |
| Auditoría append-only (crecimiento) | Tabla append-only con particionamiento por fecha (PHASE1-003); no es cuello de botella de escritura (inserts). |

## 4. Qué NO se prescribe en Phase 1

- No se prescribe hardware, ni número exacto de réplicas, ni caché
  (Redis/Memcached), ni CDN.
- No se prescribe el motor de búsqueda (PostgreSQL es suficiente para
  100.000 gastos).
- Los objetivos se refinarán en Phase 2 con la carga real (NFR-6: "el
  arquitecto los refinará con los objetivos de carga reales").
