# GastosE — Instrucciones de proyecto

GastosE es una aplicación (futuro) para la gestión automatizada de gastos,
facturas recibidas, tickets y documentos asociados.

## Arquitectura multiagente

Este proyecto se desarrolla con una infraestructura multiagente de OpenCode:

- **`director`** es el agente PRIMARIO y por defecto: único orquestador.
  Recibe peticiones del usuario, delega en subagentes, coordina quality
  gates y es el único que declara ACCEPTED/MERGED/DONE.
- Subagentes especialistas (solo invocables por director, `subagent_depth=1`):
  `domain`, `architect`, `database`, `backend`, `extraction`, `frontend`,
  `qa`, `security` (read-only), `reviewer` (read-only), `devops`.
- Jerarquía estricta: USUARIO -> DIRECTOR -> especialistas. Los subagentes
  no delegan en otros subagentes.

## Conocimiento y herramientas

- Skills (conocimiento reutilizable, cargar bajo demanda con la tool `skill`):
  `expense-domain`, `architecture`, `database-design`, `api-design`,
  `document-extraction`, `frontend-patterns`, `testing`, `security`,
  `docker`, `git-workflow`.
- Custom tools (acciones deterministas): `run-tests`, `lint`,
  `migration-check`, `openapi-check`, `docker-health`, `scope-check`.

## Estado persistente

- `docs/project/STATE.md` — fase, milestone, estado actual, blockers, next gate.
- `docs/project/TASKS.md` — tareas con estados PROPOSED/DESIGNING/READY/
  IMPLEMENTING/TESTING/REVIEW/ACCEPTED/MERGED/BLOCKED/DONE.
- `docs/project/DECISIONS.md` — índice de decisiones (ADRs).
- `docs/project/CONTRACTS.md` — registro de contratos entre componentes.
- El director consulta y actualiza estos archivos en cada tarea significativa.

## Reglas duras

1. **Aislamiento FacturaE**: `/workspace/facturaE` (y sus backups) es un
   sistema EXTERNO de SOLO LECTURA. Prohibido modificarlo, copiar su código,
   importar sus módulos, compartir su DB/tablas/migraciones/almacenamiento.
   Integración futura solo vía API o contrato de eventos versionados.
2. **GastosE es un bounded context independiente** (ADR-0001).
3. **Deterministic first** en extracción documental: nunca
   `LLM OUTPUT == ACCOUNTING FACT` (skill `document-extraction`).
4. **Documento original != valor extraído != valor validado != valor
   aceptado** (skill `expense-domain`).
5. **PostgreSQL** para producción; valores monetarios exactos (NUMERIC,
   nunca float) (skill `database-design`).
6. **Quality gates**: ninguna feature significativa salta
   requirements -> contratos -> implementación -> QA -> security (si aplica)
   -> review -> decisión del director.
7. **Git**: rama `main`; sin push ni remotos sin aprobación explícita del
   usuario; sin `git reset --hard` ni `rm -rf` (denegado por permisos).
   Convención de ramas `agent/<agente>/<TASK-ID>` (skill `git-workflow`).
8. **Desarrollo por vertical slices**, no por capas.
9. **Secrets**: nunca leer, loguear ni commitear `.env`, credentials ni
   secretos (denegado por permisos).
10. **Phase 0 (actual)**: solo infraestructura multiagente. NO implementar
    la aplicación (sin modelos de gastos, sin FastAPI, sin frontend, sin
    schema productivo, sin OCR/LLM, sin stack productivo).

## Bounded contexts (conceptuales, refinar en Phase 1)

Document Ingestion · Extraction · Expense Core · Supplier ·
Review & Acceptance.
