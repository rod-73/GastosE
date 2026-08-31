---
name: docker
description: Use when working on GastosE infrastructure: Docker/podman, Docker Compose, container images, healthchecks, PostgreSQL runtime, workers, persistent storage, credentials, non-root containers, startup order, reproducibility, deployment.
---

# Docker — GastosE

Infraestructura contenedizada para GastosE. Stack TOTALMENTE INDEPENDIENTE de
FacturaE: containers, DB, volumes, credentials y storage propios.

Nota de runtime: en este servidor `docker` es un emulador de CLI sobre
**podman** (podman 5.x). Los archivos siguen siendo `Dockerfile` y
`docker-compose.yml` estándar; los comandos pueden ejecutarse con `docker`
(emula) o `podman`/`podman compose`.

## Stack mínimo (cuando se implemente)

```
gastosE-db        (postgres:16)      — volumen gastosE_db
gastosE-api       (imagen app)       — healthcheck /health
gastosE-worker    (misma imagen, CMD worker) — healthcheck de cola
gastosE-frontend  (imagen web)       — opcional en dev
```

- Red propia `gastosE_net`; NO unir a redes de FacturaE.
- Volumes propios: `gastosE_db`, `gastosE_storage` (documentos).
- Credentials propias (usuario DB `gastosE`, password desde env/secret).
- Puertos: solo los expuestos son necesarios (API); DB solo en la red
  interna.

## Imágenes

- Multi-stage builds; base `python:3.12-slim` (o la que elija Architect).
- Non-root: `USER appuser` (UID fijo, p. ej. 10001); permisos de volumes
  correctos.
- Sin secrets en la imagen; solo por env en runtime.
- Etiquetas/versiones reproducibles (git sha); `HEALTHCHECK` en cada
  servicio.

## Healthchecks

- DB: `pg_isready` (o query `SELECT 1`).
- API: endpoint `/health` (liveness) + `/ready` (dependencias: DB).
- Worker: heartbeat de última tarea procesada.
- Compose: `healthcheck` con `start_period` razonable; dependencias con
  `condition: service_healthy`.

## Startup

1. DB (healthy) -> 2. migraciones Alembic (entrypoint o init job) ->
   3. API -> 4. worker.
- Migraciones en startup: `alembic upgrade head`; si falla, el contenedor
  no arranca (fail fast).

## Persistencia y operaciones

- Documentos en volumen `gastosE_storage` con permisos no-root.
- Backups: `pg_dump` programado (fuera del scope de Phase 0).
- Logs: stdout/stderr estructurados (JSON); sin datos financieros sensibles.
- Observabilidad: métricas básicas opcionales; siempre logs + health.

## Comandos de referencia

```bash
docker compose config -q          # validar compose (tool docker-health)
docker compose up -d
docker compose ps
docker compose logs --tail=50
docker compose down               # NUNCA -v sin aprobación (borra datos)
```

## Checklist

- [ ] ¿Stack independiente (red/volumes/credentials propios)?
- [ ] ¿Non-root en todas las imágenes?
- [ ] ¿Healthchecks en todos los servicios?
- [ ] ¿Startup ordenado con migraciones fail-fast?
- [ ] ¿Sin secrets en imágenes?
- [ ] ¿Reproducibilidad (versión por git sha)?
