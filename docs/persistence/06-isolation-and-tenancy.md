# 06 — Aislamiento y tenencia (GastosE)

Cómo se aplica el aislamiento de datos por propietario/tenant (OQ-9, NFR-7) a
nivel de persistencia. **OQ-9 resuelta (ADR-0008)**: el modelo es
**aislamiento por organización (multi-usuario)**.

## 1. Modelo: aislamiento por organización (ADR-0008)

Cada organización solo accede a sus documentos, gastos, proveedores y
catálogos. Varios usuarios de la misma organización comparten datos; no hay
acceso cruzado entre organizaciones.

**Aplicación en persistencia**:

- **Columna `owner_id`**: todas las tablas de negocio llevan una columna
  `owner_id` (UUID) que identifica a la **organización propietaria**
  (`owner_id` = `organization_id`). Las tablas que llevan `owner_id` son:
  - `source_documents`, `extractions`, `extracted_values`,
    `normalized_values`, `validated_values`
  - `expenses`, `expense_lines`, `tax_lines`, `payments`
  - `suppliers`, `categories`, `payment_methods`, `tax_rates`
  - `reviews`, `manual_corrections`, `duplications`, `document_splits`
  - `audit_events`, `extraction_jobs`
- **Tablas sin `owner_id`**: `organizations` (tabla de organizaciones),
  `currencies` (catálogo global ISO-4217), `users` (tabla de usuarios, con
  `organization_id` FK), `review_field_results` (hereda el owner de la
  revisión), `split_expenses` (hereda el owner del split).

## 2. Filtro por propietario en todas las queries

**Regla**: todas las queries filtran por `owner_id` a nivel de servicio de
aplicación/persistencia, **no solo en la UI**.

- **Derivación del propietario**: la organización se deriva de la **sesión
  autenticada** (nunca de un parámetro de la petición). El servicio de
  aplicación obtiene el `organization_id` del usuario autenticado (vía
  `users.organization_id`) y lo aplica como `owner_id` a todas las queries.
- **Ejemplo conceptual**:
  ```
  -- Listado de gastos del usuario autenticado:
  SELECT * FROM expenses
  WHERE owner_id = :session_owner_id
    AND state = 'under_review'
  ORDER BY document_date DESC;
  ```
- **Prohibido**: aceptar `owner_id` como parámetro de la petición. El
  `owner_id` siempre viene de la sesión.

## 3. Índices de aislamiento

Los índices que incluyen `owner_id` como primera columna garantizan el
rendimiento de las queries filtradas por propietario:

- `idx_docs_owner`, `idx_exp_owner`, `idx_sup_owner_nif`,
  `idx_dup_owner_state`, `idx_audit_owner_date`, etc. (ver
  [05-indexes-and-performance.md](05-indexes-and-performance.md)).

## 4. Test de aislamiento (NFR-7)

**Criterio**: dado un usuario A de la organización X; cuando intenta acceder
a un gasto de la organización Y; entonces el acceso se deniega.

**Aplicación en persistencia**:

- La query del usuario A (org X) filtra por `owner_id = X`. El gasto de la
  org Y (con `owner_id = Y`) no aparece en los resultados.
- El acceso directo por ID (p. e.g. `GET /api/v1/expenses/{id}`) también
  filtra por `owner_id`: si el gasto no pertenece a la organización
  autenticada, se devuelve 404 (no 403, para no revelar la existencia del
  recurso).
- **Dentro de la organización**: todos los usuarios de la misma org ven los
  mismos datos. El rol (NFR-7) determina qué acciones puede hacer (lectura,
  revisión, aceptación, administración), no qué datos ve.

## 5. Modelo resuelto: organización (ADR-0008)

**Decisión (2026-08-31)**: OQ-9 resuelta por ADR-0008. El modelo es
**aislamiento por organización (multi-usuario)**:

- Tabla `organizations` (id, name, state, timestamps).
- `users.organization_id` (FK NOT NULL): un usuario pertenece a una
  organización.
- `owner_id` en las tablas de negocio = `organization_id`.
- La atribución de auditoría (`audit_events.actor`) sigue siendo por usuario.
- Los roles (NFR-7) se aplican dentro de la organización.
- En Phase 2 (v1): 1 organización + 1 usuario por onboarding; la estructura
  soporta multi-usuario (invitaciones, roles) en una vertical posterior.

## 6. Aislamiento de FacturaE (ADR-0001)

GastosE tiene su propia base de datos y su propio volumen de documentos. No
se comparte ninguna tabla, schema, migración ni almacenamiento con FacturaE.

**Aplicación en persistencia**:

- **BD propia**: GastosE usa su propia instancia de PostgreSQL (o su propio
  schema, si se comparte instancia). No se comparten tablas con FacturaE.
- **Volumen propio**: el volumen de documentos es dedicado a GastosE (ADR-0006).
  No se monta el volumen de FacturaE.
- **Integración futura**: solo vía API versionada o contrato de eventos
  versionado (ADR-0001). No hay acceso directo a las tablas de FacturaE.

## 7. Seguridad adicional

- **Permisos de BD**: el usuario de aplicación de GastosE tiene permisos solo
  sobre las tablas de GastosE. No tiene permisos sobre las tablas de FacturaE.
- **Cifrado en reposo**: la BD y el volumen de documentos se cifran (Phase
  2/devops).
- **No repudio**: la auditoría (`audit_events`) registra el `actor` (usuario)
  de cada acción, garantizando la atribución (NFR-7).
