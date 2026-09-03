# ADR-0013: Salvaguardas deterministas de ejecución del runtime multiagente

Status: accepted
Date: 2026-09-03

## Context

Antes de continuar Phase 2, el runtime multiagente de GastosE (OpenCode
1.18.20) necesitaba endurecimiento para prevenir: (a) delegación en cascada
por subagentes, (b) ejecuciones de especialistas sin límite de duración,
(c) reintentos sin progreso y (d) ciclos autónomos de corrección en agentes
de validación. El subagente `domain` ha mostrado fallos operativos
(salidas vacías/degenerativas) que justifican controles de contención.

## Decision

Se aplican salvaguardas con los mecanismos nativos disponibles en OpenCode
1.18.20:

1. **Delegación exclusiva del Director**: `subagent_depth: 1` (ya existente)
   + `permission.task: deny` en los 10 especialistas (frontmatter de
   `.opencode/agent/*.md` y `agent.<name>.permission.task: deny` en
   `opencode.json`). Solo `director` conserva `task: allow` (limitado a
   agentes de subagente; `general`/`explore`/`build`/`plan` denegados).
2. **Límite duro de pasos**: `steps: 25` en todos los especialistas
   (frontmatter + `opencode.json`). Al alcanzar el límite, OpenCode fuerza
   una respuesta de solo texto (sin más herramientas). Valor elegido:
   mínimo razonable para una tarea vertical acotada (leer contexto +
   producir + validar con tools), sin permitir ejecuciones prolongadas.
3. **Fail-fast como política común** (prompts de todos los especialistas y
   del director): no repetir una acción sin progreso observable; máximo 1
   reintento cambiando de estrategia; 2 errores/resultados equivalentes
   consecutivos => STOP; loop, salida vacía, truncamiento o incoherencia =>
   STOP y reporte al Director; nunca relanzar automáticamente el mismo
   subagente.
4. **Handoff estructurado**: cada especialista devuelve un único mensaje
   final con estructura fija (STATUS / ENTREGABLES / VALIDACION / RIESGOS /
   AL_DIRECTOR). El Director consolida y actualiza el estado persistente.
   Security/Reviewer reportan findings al Director sin crear ciclos
   autónomos de corrección.
5. **Concurrencia**: máximo 2 especialistas concurrentes (política del
   Director; vLLM max_num_seqs=4, reserva de capacidad para el Director).
6. **`domain` NO DISPONIBLE temporalmente**: no invocarlo (riesgo
   operativo documentado en STATE.md).

## Alternatives considered

1. **Solo prompts sin controles nativos**: rechazado — los prompts son
   defensa adicional, no sustituto de controles deterministas.
2. **Límite de pasos más alto (p. ej. 50)**: rechazado — permite
   ejecuciones prolongadas; 25 cubre las tareas normales observadas en
   Phase 1 (documentación + validación con tools).
3. **Plugin que cuente pasos por sesión y aborte**: no soportado de forma
   fiable en la API de plugins 1.18.20; se usa el campo nativo `steps`.

## Consequences

- **Efectivo y determinista**: delegación de especialistas (denegado),
  límite de pasos (`steps`), `subagent_depth=1`.
- **Dependiente del LLM** (sin control nativo en 1.18.20): detección de
  loops por contenido, salida vacía, truncamiento e incoherencia. Se
  mitigan con `steps`, la política fail-fast en prompts y la revisión del
  resultado por el Director antes de aceptar.
- Tareas muy grandes pueden necesitar más de 25 pasos; el especialista debe
  devolver `STATUS: PARTIAL` y el Director decide reasignar el resto (no
  relanzar automáticamente la misma tarea).
- El Director conserva `task` permitido (es el único orquestador); su
  comportamiento de reintentos sigue la política fail-fast de su prompt.
