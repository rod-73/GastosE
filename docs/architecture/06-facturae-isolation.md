# 06 — Aislamiento de FacturaE (garantías de ADR-0001)

FacturaE (`/workspace/facturaE`) es un sistema EXTERNO de solo lectura.
ADR-0001 declara que GastosE es un bounded context independiente y prohíbe
compartir código, ORM, base de datos, tablas, migraciones o almacenamiento.
Este documento describe cómo la arquitectura **garantiza** ese aislamiento.

## 1. Prohibiciones (no negociables)

| Recurso | Prohibición |
|---|---|
| Código | GastosE no importa, copia ni reutiliza código de FacturaE. |
| Modelos ORM | GastosE define sus propios modelos; no comparte clases ORM. |
| Base de datos | GastosE usa su propia instancia/base de datos PostgreSQL; no conecta a la de FacturaE. |
| Tablas / migraciones | GastosE tiene su propio esquema y sus propias migraciones (Alembic); no comparte tablas ni migraciones. |
| Almacenamiento | GastosE almacena sus documentos fuente en su propio volumen (ADR-0006); no lee ni escribe el almacenamiento de FacturaE. |
| Directorios | GastosE no referencia rutas de `/workspace/facturaE` en su código, configuración ni despliegue. |

## 2. Garantías arquitectónicas

1. **Sin dependencias en el grafo**: el grafo de dependencias de GastosE
   (02-components.md, sección 3) no contiene ningún nodo de FacturaE. Ni la
   API, ni el worker, ni el dominio, ni la persistencia dependen de
   FacturaE.
2. **Base de datos propia**: GastosE declara su propia conexión a PostgreSQL
   (credenciales propias, en secrets de GastosE). No hay DSN compartido.
3. **Almacenamiento propio**: el document store (C6) es un volumen dedicado a
   GastosE (ADR-0006). El fingerprint SHA-256 identifica los documentos de
   GastosE; no hay índice compartido con FacturaE.
4. **Migraciones propias**: GastosE usa Alembic con su propio historial de
   migraciones (verificación con la tool `migration-check`).
5. **Despliegue independiente**: GastosE se despliega en sus propios
   contenedores (podman); no comparte contenedores, redes ni volúmenes con
   FacturaE.
6. **Verificable** (NFR-10): dado un despliegue de GastosE; cuando se
   inspecciona; entonces no hay referencias a `/workspace/facturaE` ni a sus
   recursos. Esta comprobación puede automatizarse (búsqueda de referencias
   en código/config) como parte del quality gate.

## 3. Punto de integración futuro (pendiente de decisión)

Si en el futuro se aprueba una integración con FacturaE, SOLO mediante:

- **API versionada** (`/api/v1/...` de FacturaE, o de GastosE), con contrato
  OpenAPI propio y versionado, O
- **Contrato de eventos versionado** (schema + versión), con un bus/cola
  inter-sistema.

Hasta que el director/usuario decida explícitamente, **no existe
integración**: el registro de contratos (`docs/project/CONTRACTS.md`) marca
el contrato con FacturaE como "no aprobado". Cualquier propuesta de
integración requiere un ADR nuevo y la aprobación del director.

### Formas de integración futuras (orientativo, no decidido)

- GastosE como consumidor de datos de FacturaE (p. e.g. facturas emitidas
  que podrían relacionarse con gastos): vía API de solo lectura.
- GastosE publicando hechos contables (gastos aceptados) para contabilidad:
  vía contrato de eventos versionado.

Ninguna de estas formas implica compartir DB, código ni almacenamiento.

## 4. Riesgo de acoplamiento accidental y mitigación

| Riesgo | Mitigación |
|---|---|
| Un desarrollador copia un modelo de FacturaE por conveniencia | Regla dura en AGENTS.md; revisión (reviewer) comprueba ausencia de referencias; la tool `scope-check`/`lint` puede detectar imports de rutas ajenas. |
| Conexión a la DB de FacturaE por error de configuración | Las credenciales de GastosE son propias; no hay DSN de FacturaE en el entorno de GastosE. |
| Almacenamiento compartido por error de despliegue | El volumen del document store se declara explícitamente en el despliegue de GastosE (ADR-0006); no se monta el volumen de FacturaE. |
| Términos ambiguos ("factura") | La terminología canónica distingue "factura recibida" (GastosE) de la factura emitida (FacturaE) (01-terminology.md). |
