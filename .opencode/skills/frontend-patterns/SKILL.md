---
name: frontend-patterns
description: Use when building or reviewing GastosE UI/UX: upload flows, processing states, human review, corrections, confidence display, validation errors, acceptance, failures.
---

# Frontend Patterns — GastosE

Patrones UX para GastosE. Regla de oro: **nunca presentar un valor extraído
automáticamente como confirmado si no ha sido validado**.

## Estados del documento (siempre visibles)

| Estado | UI |
|---|---|
| `uploaded` | "Recibido" — pendiente de procesar. |
| `processing` | Spinner + "Procesando…"; no mostrar datos parciales. |
| `extracted` | Datos extraídos marcados como "extraído" (no confirmado). |
| `uncertain` | Destacar campos con confianza baja (ej. ámbar) + "requiere revisión". |
| `validation error` | Rojo + motivo concreto por campo; no bloquear la vista. |
| `manually corrected` | Badge "corregido manualmente" + quién/cuándo. |
| `validated` | Verde suave; listo para aceptar. |
| `accepted` | Verde + sello de aceptación (inmutable). |
| `failed` | Rojo + motivo + opción de reintentar o descartar. |

## Upload

- Drag & drop + selector; mostrar tipo/tamaño antes de subir.
- Feedback de progreso; error de validación de archivo (MIME/tamaño) con
  mensaje accionable.
- Tras subir: estado `uploaded`/`processing` inmediato (202 + polling o
  webhook según contrato).

## Revisión (review)

- Layout: valor extraído | confianza | original (snippet/imagen del documento
  con bbox si hay provenance).
- Campo editable solo en revisión; cada edición marca `manually corrected`
  y registra el cambio (antes/después visible).
- Botón de aceptación deshabilitado hasta `validated`; si hay campos
  `uncertain` sin revisar, advertir explícitamente.

## Confidence

- Barra o porcentaje por campo; umbral visible ("confianza baja").
- Provenance accesible (dónde se extrajo: página, método).

## Errores de validación

- Mensajes por campo, concretos y accionables ("El total no coincide con
  base + IVA: diferencia 0,05 €").
- Nunca solo un "error" genérico; nunca exponer stack traces.

## Aceptación y fallos

- Aceptación: confirmación explícita (no accidental); tras aceptar el
  registro es inmutable (solo anulación documentada).
- Fallos: motivo + acciones disponibles (reintentar, descartar, reportar).

## Accesibilidad y rendimiento

- Estados no solo por color (iconos/texto).
- Listados con paginación; búsqueda con debounce.
- Optimistic UI solo para acciones reversibles.

## Checklist

- [ ] ¿Todos los estados del ciclo de vida tienen UI distinta?
- [ ] ¿Extraído vs validado vs aceptado visualmente distinguibles?
- [ ] ¿Confidence + provenance visibles en revisión?
- [ ] ¿Correcciones manuales marcadas y auditadas en UI?
- [ ] ¿Errores concretos por campo?
- [ ] ¿Aceptación explícita e inmutable después?
