---
name: git-workflow
description: Use when working on GastosE Git workflow: multi-agent branches, worktrees, ownership, task states, merge/accept process, protected operations, commits.
---

# Git Workflow — GastosE

Workflow Git multiagente para GastosE.

## Reglas base

- Rama principal: `main`. Solo el DIRECTOR integra en `main`.
- NO `git push`, NO remotos, NO commits sin aprobación explícita del usuario
  (política actual del proyecto).
- Operaciones protegidas (deny en permisos): `git push`,
  `git reset --hard`, `git clean -f`, `rm -rf`.
- Commits: mensaje `tipo(scope): resumen` (ej. `feat(backend): add expense
  validation`), uno por unidad de trabajo coherente.

## Convención de ramas (multiagente)

```
agent/domain/EXP-001
agent/architect/EXP-001
agent/database/EXP-001
agent/backend/EXP-001
agent/extraction/EXP-001
agent/frontend/EXP-001
agent/qa/EXP-001
agent/devops/EXP-001
```

- `EXP-NNN` = ID de tarea de `docs/project/TASKS.md`.
- Una rama por (agente, tarea). Ownership: cada rama pertenece a UN agente;
  el Director la revisa e integra.
- `security` y `reviewer` no crean ramas (read-only): trabajan sobre la
  rama del agente que auditan/revisan.

## Worktrees (desarrollo paralelo)

Preparado para worktrees; NO crearlos salvo necesidad validada:

```bash
git worktree add /workspace/gastosE-wt-backend  agent/backend/EXP-001
git worktree add /workspace/gastosE-wt-frontend agent/frontend/EXP-001
git worktree add /workspace/gastosE-wt-extraction agent/extraction/EXP-001
```

- Un worktree por agente/tarea; nunca dos worktrees con la misma rama.
- Paralelismo seguro: solo si los scopes de archivos NO se solapan.
  DOMAIN -> ARCHITECT -> DATABASE es secuencial si hay dependencia.
- Al terminar: el Director integra (merge) y elimina el worktree:
  `git worktree remove /workspace/gastosE-wt-<agente>`.

## Estados de tarea (docs/project/TASKS.md)

```
PROPOSED -> DESIGNING -> READY -> IMPLEMENTING -> TESTING -> REVIEW
        -> ACCEPTED -> MERGED -> DONE
        (BLOCKED en cualquier punto; se documenta el blocker)
```

- Solo el Director transita estados y declara ACCEPTED/MERGED/DONE.
- Cada transición se registra con fecha y agente responsable.

## Proceso de integración

1. Especialista termina en su rama; tests del scope pasan.
2. QA valida (tests completos), Security (si aplica), Reviewer revisa.
3. `scope-check`: los archivos modificados están dentro del scope del agente.
4. Director: ACCEPTED -> merge en `main` (o en la rama de integración del
   slice) -> MERGED.
5. Conflictos: los resuelve el Director con el agente dueño del archivo.

## Checklist

- [ ] ¿Rama con convención `agent/<agente>/<TASK-ID>`?
- [ ] ¿Scope de archivos dentro del ownership del agente?
- [ ] ¿Tests del scope pasan antes de proponer merge?
- [ ] ¿Transición de estado registrada en TASKS.md?
- [ ] ¿Sin push/remotos sin aprobación?
