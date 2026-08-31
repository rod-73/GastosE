---
name: database-design
description: Use when designing or reviewing GastosE persistence: PostgreSQL schema, monetary values, PK/FK, constraints, indexes, transactions, Alembic migrations upgrade/downgrade, concurrency, auditability.
---

# Database Design — GastosE

Reglas de persistencia para GastosE. PostgreSQL es la base de datos de
producción. SQLite solo para pruebas concretas aprobadas por Director+Architect.

## Valores monetarios exactos

- SIEMPRE `NUMERIC(14,2)` (o `NUMERIC(14,4)` para importes unitarios con
  redondeo posterior). NUNCA `FLOAT`/`DOUBLE PRECISION`.
- Moneda como `CHAR(3)` ISO-4217 junto a cada importe.
- Redondeo: definir política por campo (ej. `ROUND_HALF_UP` a 2 decimales en
  totales); documentar en el ADR correspondiente.
- Validar aritméticamente en la app: `total = base + iva - retenciones`
  (tolerancia ≤ 0,01 por línea).

## Modelo relacional

- PK: `BIGINT`/`UUID` + `PRIMARY KEY`. Preferir UUIDv7 para recursos públicos.
- FK explícitas con `ON DELETE` declarado (normalmente `RESTRICT` para datos
  contables).
- Unicidad: `(supplier_id, invoice_number, invoice_date)` como candidato a
  unique para detección de duplicados.
- Índices: para cada FK, cada columna de búsqueda frecuente y cada unique.
- Estados como `TEXT` con `CHECK` (no enums nativos: migrar es más fácil).
- Soft delete solo si un ADR lo justifica; preferir estados.

## Constraints

- `CHECK (amount >= 0)` en importes (salvo señales documentadas).
- `CHECK (vat_rate >= 0 AND vat_rate <= 1)` si se almacena tasa fraccionaria,
  o `CHECK (vat_rate IN (...))` si es porcentaje entero.
- Fechas: `DATE`/`TIMESTAMPTZ`; timestamps SIEMPRE `TIMESTAMPTZ`.

## Transacciones y concurrencia

- Una transacción = una operación de negocio (p. ej. aceptar gasto).
- `SERIALIZABLE` solo cuando la semántica lo exija; por defecto
  `READ COMMITTED` + locks explícitos (`SELECT ... FOR UPDATE`) donde haga falta.
- Idempotencia a nivel DB: unique constraints como red de seguridad.

## Migraciones (Alembic)

- Toda modificación de esquema => migración con `upgrade()` Y `downgrade()`.
- Un head único: verificar con `alembic heads` (tool `migration-check`).
- Nombres: `NNNN_descripcion_corta.py` (alembic genera el rev id).
- Migraciones grandes: dividir (crear tabla -> backfill -> constraint).
- Nunca editar una migración ya aplicada; crear una nueva.

## Auditabilidad

- Tablas de negocio contable llevan `created_at`, `updated_at`,
  `created_by`, `updated_by`.
- Correcciones manuales: tabla de auditoría (quién, cuándo, campo, antes,
  después).
- Fingerprint del documento fuente: `SHA-256` + unique.

## Checklist de revisión de esquema

- [ ] ¿Moneda exacta (NUMERIC) en todos los importes?
- [ ] ¿PK/FK/unique/CHECK completos?
- [ ] ¿Índices para FK y búsquedas frecuentes?
- [ ] ¿Migración con upgrade y downgrade?
- [ ] ¿Un solo head?
- [ ] ¿Timestamps TIMESTAMPTZ?
- [ ] ¿Auditoría de correcciones manuales?
