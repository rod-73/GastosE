# 06 — Tenencia y aislamiento (GastosE Phase 2)

Diseño de implementación del modelo de tenencia por organización (ADR-0008) y
el aislamiento de datos a nivel de persistencia.

**Nota**: este documento materializa el diseño conceptual de
`docs/persistence/06-isolation-and-tenancy.md` en decisiones concretas de
implementación.

## 1. Modelo: aislamiento por organización (ADR-0008)

Cada organización solo accede a sus documentos, gastos, proveedores y
catálogos. Varios usuarios de la misma organización comparten datos; no hay
acceso cruzado entre organizaciones.

### 1.1 Columna `owner_id`

Todas las tablas de negocio llevan una columna `owner_id` (UUID NOT NULL) que
identifica a la **organización propietaria** (`owner_id` = `organization_id`).

**Tablas con `owner_id`**:
- `source_documents`, `extractions`, `extracted_values`, `normalized_values`,
  `validated_values`
- `expenses`, `expense_lines`, `tax_lines`, `payments`
- `suppliers`, `categories`, `payment_methods`, `tax_rates`
- `reviews`, `manual_corrections`, `duplications`, `document_splits`
- `audit_events`, `extraction_jobs`

**Tablas sin `owner_id`**:
- `organizations` (tabla de organizaciones)
- `currencies` (catálogo global ISO-4217)
- `users` (tabla de usuarios, con `organization_id` FK)
- `sessions` (con `organization_id` FK, no `owner_id`)
- `review_field_results` (hereda el owner de la revisión)
- `split_expenses` (hereda el owner del split)

### 1.2 Constraint de integridad

```sql
-- En todas las tablas de negocio:
owner_id UUID NOT NULL REFERENCES organizations(id) ON DELETE RESTRICT
```

- `NOT NULL`: toda fila de negocio pertenece a una organización.
- `ON DELETE RESTRICT`: no se puede eliminar una organización que tiene datos
  de negocio (protección de datos contables).

## 2. Filtro por propietario en todas las queries

### 2.1 Regla fundamental

**Todas las queries filtran por `owner_id` a nivel de servicio de
aplicación/persistencia, no solo en la UI.**

- **Derivación del propietario**: la organización se deriva de la **sesión
  autenticada** (nunca de un parámetro de la petición). El servicio de
  aplicación obtiene el `organization_id` del usuario autenticado (vía
  `users.organization_id`) y lo aplica como `owner_id` a todas las queries.
- **Ejemplo conceptual**:
  ```sql
  -- Listado de gastos del usuario autenticado:
  SELECT * FROM expenses
  WHERE owner_id = :session_owner_id
    AND state = 'under_review'
  ORDER BY document_date DESC;
  ```
- **Prohibido**: aceptar `owner_id` como parámetro de la petición. El
  `owner_id` siempre viene de la sesión.

### 2.2 Patrón de implementación

```
Sesión autenticada
    │
    ▼
users.organization_id  ──►  owner_id
    │
    ▼
Todas las queries: WHERE owner_id = :session_owner_id
```

- El middleware de autenticación (V8-S1) resuelve el token y carga la sesión.
- El servicio de aplicación inyecta `owner_id` en todas las queries de
  persistencia.
- El repositorio (capa de persistencia) **siempre** aplica el filtro
  `owner_id`. No hay queries sin filtro.

### 2.3 Acceso directo por ID

El acceso directo por ID (p. e.g. `GET /api/v1/expenses/{id}`) también filtra
por `owner_id`:

```sql
SELECT * FROM expenses
WHERE id = :expense_id
  AND owner_id = :session_owner_id;
```

- Si el gasto no pertenece a la organización autenticada, se devuelve **404**
  (no 403, para no revelar la existencia del recurso).
- Esto aplica a todas las entidades: documentos, gastos, proveedores,
  duplicaciones, auditoría.

## 3. RLS (Row-Level Security) como defensa en profundidad

### 3.1 Decisión

**RLS no es obligatorio en V1**, pero se documenta como opción de defensa en
profundidad.

### 3.2 Justificación

- El filtro por `owner_id` a nivel de aplicación es la línea principal de
  defensa.
- RLS añade una segunda línea de defensa a nivel de BD, protegiendo contra
  errores de programación (queries sin filtro).
- RLS tiene un coste de rendimiento (cada query evalúa la política).
- En V1 con volumen bajo (~1.000 documentos/mes), el coste es despreciable.

### 3.3 Diseño de RLS (si se activa)

```sql
-- Habilitar RLS en todas las tablas de negocio:
ALTER TABLE source_documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE expenses ENABLE ROW LEVEL SECURITY;
-- ... (todas las tablas con owner_id)

-- Política: solo ver filas de la organización de la sesión actual:
CREATE POLICY tenant_isolation ON source_documents
    USING (owner_id = current_setting('app.current_organization_id')::UUID);

-- La aplicación debe setear el GUC antes de cada transacción:
SET app.current_organization_id = '<organization_id>';
```

- La aplicación setea `app.current_organization_id` al inicio de cada
  transacción (derivado de la sesión).
- RLS actúa como red de seguridad: si una query olvida el filtro `owner_id`,
  RLS lo aplica a nivel de BD.
- **Nota**: RLS no reemplaza el filtro a nivel de aplicación. Es una segunda
  línea de defensa.

## 4. Modelo de permisos de BD

### 4.1 Principio de mínimo privilegio

El usuario de aplicación de GastosE tiene permisos solo sobre las tablas de
GastosE. No tiene permisos sobre las tablas de FacturaE (ADR-0001).

### 4.2 Roles de BD

```sql
-- Usuario de aplicación (permisos de lectura/escritura):
CREATE ROLE gastosE_app WITH LOGIN;
GRANT CONNECT ON DATABASE gastosE TO gastosE_app;
GRANT USAGE ON SCHEMA public TO gastosE_app;

-- Permisos por tabla:
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO gastosE_app;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO gastosE_app;

-- Excepción: audit_events es append-only (ADR-0012):
REVOKE UPDATE, DELETE ON audit_events FROM gastosE_app;
REVOKE UPDATE, DELETE ON manual_corrections FROM gastosE_app;

-- Excepción: sessions solo se modifica vía aplicación (no UPDATE directo):
-- (el UPDATE de sessions lo hace la aplicación, no un trigger)
```

### 4.3 Permisos de administrador

```sql
-- Usuario de administrador (migraciones, mantenimiento):
CREATE ROLE gastosE_admin WITH LOGIN;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO gastosE_admin;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO gastosE_admin;
```

## 5. Test de aislamiento (NFR-7)

### 5.1 Criterio

Dado un usuario A de la organización X; cuando intenta acceder a un gasto de
la organización Y; entonces el acceso se deniega.

### 5.2 Aplicación en persistencia

- La query del usuario A (org X) filtra por `owner_id = X`. El gasto de la
  org Y (con `owner_id = Y`) no aparece en los resultados.
- El acceso directo por ID también filtra por `owner_id`: si el gasto no
  pertenece a la organización autenticada, se devuelve 404.
- **Dentro de la organización**: todos los usuarios de la misma org ven los
  mismos datos. El rol (NFR-7) determina qué acciones puede hacer (lectura,
  revisión, aceptación, administración), no qué datos ve.

### 5.3 Tests de integración

```
Test 1: Usuario A (org X) no ve gastos de org Y
  - Crear gasto en org Y
  - Usuario A (org X) hace GET /expenses/{id}
  - Esperado: 404

Test 2: Usuario A (org X) no ve documentos de org Y
  - Crear documento en org Y
  - Usuario A (org X) hace GET /documents/{id}
  - Esperado: 404

Test 3: Usuario A (org X) no ve proveedores de org Y
  - Crear proveedor en org Y
  - Usuario A (org X) hace GET /suppliers/{id}
  - Esperado: 404

Test 4: Usuario A (org X) no ve auditoría de org Y
  - Crear evento de auditoría en org Y
  - Usuario A (org X) hace GET /audit-events?entity_type=expense&entity_id={id}
  - Esperado: 404 o lista vacía
```

## 6. Aislamiento de FacturaE (ADR-0001)

GastosE tiene su propia base de datos y su propio volumen de documentos. No
se comparte ninguna tabla, schema, migración ni almacenamiento con FacturaE.

### 6.1 Aplicación en persistencia

- **BD propia**: GastosE usa su propia instancia de PostgreSQL (o su propio
  schema, si se comparte instancia). No se comparten tablas con FacturaE.
- **Volumen propio**: el volumen de documentos es dedicado a GastosE
  (ADR-0006). No se monta el volumen de FacturaE.
- **Integración futura**: solo vía API versionada o contrato de eventos
  versionado (ADR-0001). No hay acceso directo a las tablas de FacturaE.

### 6.2 Permisos de BD

- El usuario de aplicación de GastosE tiene permisos solo sobre las tablas de
  GastosE. No tiene permisos sobre las tablas de FacturaE.
- Si se comparte instancia de PostgreSQL, GastosE usa un schema separado
  (`gastosE`) y FacturaE usa otro (`facturaE`). No hay objetos compartidos.

## 7. Seguridad adicional

- **Cifrado en reposo**: la BD y el volumen de documentos se cifran (Phase
  2/devops).
- **No repudio**: la auditoría (`audit_events`) registra el `actor` (usuario)
  de cada acción, garantizando la atribución (NFR-7).
- **Revocación de sesión**: al revocar una sesión (ADR-0009), el usuario
  pierde acceso inmediato. La sesión se marca como `revoked_at = NOW()` y el
  middleware de autenticación la rechaza.

## 8. Notas

- **RLS**: no es obligatorio en V1, pero se documenta como opción. Si se
  activa, debe ser en todas las tablas con `owner_id`.
- **Particionamiento**: no se usa en V1 (volumen bajo). Si se activa, las
  particiones deben respetar el aislamiento por `owner_id`.
- **Cifrado**: el cifrado en reposo es responsabilidad de devops (Phase 2).
  No se prescribe aquí.
