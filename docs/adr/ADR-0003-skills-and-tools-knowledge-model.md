# ADR-0003: El conocimiento reutilizable se implementa como Skills y las comprobaciones deterministas como Tools

Status: accepted
Date: 2026-08-31

## Context

Los agentes necesitan (a) conocimiento de dominio y procedimientos
reutilizables (reglas del dominio, patrones de arquitectura, diseño de DB,
seguridad, Docker, git) y (b) acciones deterministas de verificación
(ejecutar tests, linters, comprobar migraciones, validar OpenAPI, health del
stack, comprobar scope de cambios). Repetir ese conocimiento en el prompt de
cada agente duplica información, diverge con el tiempo y satura el contexto
de cada sesión. OpenCode soporta skills nativas (cargadas bajo demanda con la
tool `skill`) y tools custom (vía plugin, con API oficial `@opencode-ai/plugin`).

## Decision

- **Skills** (`.opencode/skills/<name>/SKILL.md`): conocimiento y
  checklists reutilizables, cargados bajo demanda por el agente que los
  necesita. Skills definidas: `expense-domain`, `architecture`,
  `database-design`, `api-design`, `document-extraction`,
  `frontend-patterns`, `testing`, `security`, `docker`, `git-workflow`.
- **Tools** (plugin `.opencode/plugin/tools.js`): acciones deterministas
  ejecutables por OpenCode. Tools definidas: `run-tests`, `lint`,
  `migration-check`, `openapi-check`, `docker-health`, `scope-check`.
- Cada agente declara en su definición qué skills debe cargar y qué tools
  debe usar (ver `.opencode/agent/*.md`).
- Las tools deben ser tolerantes a la Phase 0: si el stack no existe aún,
  devuelven SKIP con motivo, no error.
- El conocimiento de una skill es la fuente de verdad del procedimiento;
  los prompts de los agentes solo contienen responsabilidades y referencias,
  no copias del conocimiento.

## Alternatives considered

1. **Todo el conocimiento en los prompts de los agentes**: rechazado —
   duplicación, divergencia, contexto saturado en cada sesión.
2. **Solo documentación en `docs/` sin skills**: rechazado — el agente
   tendría que buscar y leer archivos a mano; sin mecanismo nativo de carga
   bajo demanda ni de descubrimiento.
3. **Scripts sueltos invocados por bash**: rechazado — sin integración
   nativa (permisos, metadatos, descubrimiento), sin esquema de argumentos
   validado.

## Consequences

- Actualizar una skill actualiza el comportamiento de todos los agentes que
  la usan (cambio en un solo sitio).
- Las tools son auditablemente deterministas: mismo input, mismo resultado;
  sus salidas (PASS/FAIL/SKIP) alimentan los quality gates.
- Los prompts de agentes se mantienen cortos y estables.
- El plugin debe mantenerse compatible con la API de plugins de la versión
  de OpenCode instalada (1.18.20).
