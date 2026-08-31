# ADR-0002: GastosE usa una arquitectura multiagente OpenCode gobernada por un Director

Status: accepted
Date: 2026-08-31

## Context

GastosE se desarrolla con OpenCode (1.18.20). Un desarrollo por capas con un
único agente generalista tiende a: perder coherencia arquitectónica, mezclar
responsabilidades (quien implementa también se auto-valida), y escalar mal
con el crecimiento del proyecto. OpenCode soporta de forma nativa agentes
primarios, subagentes con permisos propios, delegación mediante la tool
`task`, profundidad de subagentes configurable, skills y tools custom.

## Decision

Se adopta una arquitectura de orquestación multiagente:

- **`director`** es el único agente PRIMARIO y el agente por defecto
  (`default_agent: director`). Representa simultáneamente Chief Architect,
  Engineering Manager, Technical PM, Integration Manager y Quality Gate
  Owner. Su mecanismo principal es DELEGAR; no implementa tareas de
  especialista.
- **Subagentes** (mode: subagent, solo invocables por director): `domain`,
  `architect`, `database`, `backend`, `extraction`, `frontend`, `qa`,
  `security`, `reviewer`, `devops`.
- **Jerarquía estricta de dos niveles**: USUARIO -> DIRECTOR ->
  especialistas. `subagent_depth: 1` impide que un subagente delegue en
  otro subagente.
- **Permisos least-privilege** por agente: scopes de archivos (edit),
  comandos bash permitidos, y read-only absoluto para `security` y
  `reviewer`.
- **Solo el director** declara una tarea ACCEPTED/MERGED/DONE y transita
  los estados de `docs/project/TASKS.md`.
- **Quality gates**: requirements (domain) -> contratos (architect) ->
  implementación -> QA -> security (si aplica) -> review (reviewer) ->
  decisión del director.
- **Estado persistente** en `docs/project/` (STATE, TASKS, DECISIONS,
  CONTRACTS) para que el estado no dependa de una sesión.

## Alternatives considered

1. **Un único agente generalista (build) con instrucciones**: rechazado —
   sin separación de responsabilidades ni de permisos; el mismo agente
   implementa y valida.
2. **Múltiples agentes primarios elegidos por el usuario**: rechazado —
   transfiere la orquestación al usuario, pierde coherencia global y
   duplica la gestión del estado.
3. **Jerarquía de subagentes en cascada (A delega en B que delega en C)**:
   rechazado — contextos anidados caros, ownership difuso, difícil de
   auditar.

## Consequences

- El director es cuello de botella deliberado: toda decisión de
  integración pasa por un único punto de control.
- Coste de contexto: cada delegación crea una sesión de subagente; el
  director debe delegar con contexto suficiente y resultados acotados.
- Los subagentes no ven al usuario: toda comunicación pasa por el director.
- La gobernanza depende de que el director consulte y actualice el estado
  persistente en cada tarea significativa.
