# DECISIONS — Índice de ADRs (GastosE)

| ADR | Título | Estado | Fecha |
|-----|--------|--------|-------|
| [ADR-0001](../adr/ADR-0001-gastosE-independent-bounded-context.md) | GastosE es un bounded context independiente de FacturaE | accepted | 2026-08-31 |
| [ADR-0002](../adr/ADR-0002-director-governed-multi-agent-architecture.md) | GastosE usa una arquitectura multiagente OpenCode gobernada por un Director | accepted | 2026-08-31 |
| [ADR-0003](../adr/ADR-0003-skills-and-tools-knowledge-model.md) | El conocimiento reutilizable se implementa como Skills y las comprobaciones deterministas como Tools | accepted | 2026-08-31 |
| [ADR-0004](../adr/ADR-0004-modular-monolith-with-separate-extraction-workers.md) | GastosE se implementa como monolito modular con workers de extracción separados | proposed | 2026-08-31 |
| [ADR-0005](../adr/ADR-0005-database-backed-work-queue-for-extraction.md) | El procesamiento asíncrono de extracción usa una cola en base de datos + worker | proposed | 2026-08-31 |
| [ADR-0006](../adr/ADR-0006-local-filesystem-document-store.md) | Los documentos fuente se almacenan en filesystem local en volumen dedicado, inmutable, por fingerprint | proposed | 2026-08-31 |
| [ADR-0007](../adr/ADR-0007-no-internal-events-in-phase-1-2.md) | GastosE no introduce eventos internos en Phase 1/2 (acoplamiento directo por servicios de aplicación) | proposed | 2026-08-31 |
| [ADR-0008](../adr/ADR-0008-organization-based-tenancy.md) | Modelo de tenancy por organización (multi-usuario); `owner_id` = `organization_id` | accepted | 2026-08-31 |
| [ADR-0009](../adr/ADR-0009-authentication-and-session-revocation.md) | Autenticación con token opaco + sesión server-side en BD; revocación inmediata por usuario y organización | accepted | 2026-09-01 |
| [ADR-0010](../adr/ADR-0010-extraction-llm-provider-abstraction.md) | Abstracción `ExtractionLLM` provider-neutral; backend por defecto local (endpoint compatible con OpenAI) | accepted | 2026-09-01 |
| [ADR-0011](../adr/ADR-0011-extraction-worker-sandbox-and-resource-isolation.md) | Worker de extracción en contenedor con límites cgroup, no-root, seccomp, network egress restringido | accepted | 2026-09-01 |
| [ADR-0012](../adr/ADR-0012-append-only-audit-log.md) | Registro de auditoría append-only protegido a nivel de persistencia (permisos + trigger); hash-chain no es requisito de V1 | accepted | 2026-09-01 |
| [ADR-0013](../adr/ADR-0013-multi-agent-runtime-safeguards.md) | Salvaguardas deterministas de ejecución del runtime multiagente (delegación exclusiva del Director, steps=25, fail-fast, handoff estructurado, concurrencia máx. 2) — **baseline operativo vigente**; M1.3 (circuit breaker) registrado como experimento NO OPERATIVO / descartado para uso | accepted | 2026-09-03 (actualizado 2026-09-04) |

Formato de ADR: Title / Status / Context / Decision / Alternatives
considered / Consequences. Un ADR por decisión importante; no inventar
decisiones técnicas sin análisis previo.
