# 10 — Preguntas abiertas (GastosE)

Decisiones funcionales que quedan abiertas para el director/usuario.
Identificadores: `OQ-n`. Cada pregunta incluye el valor por defecto asumido
en este baseline (para que el baseline sea usable) y la decisión pendiente.

## OQ-1 — Umbral de confianza

- **Pregunta**: ¿cuál es el umbral de confidence por debajo del cual un campo
  requiere revisión humana obligatoria?
- **Por defecto en el baseline**: 0.9 (configurable, NFR-9).
- **Decisión pendiente**: fijar el umbral inicial y si varía por método de
  extracción (p. e.g. XML => umbral más alto, LLM => umbral más bajo).

## OQ-2 — Política de splits de documento

- **Pregunta**: ¿se permiten splits de documento (un documento fuente →
  varios gastos)? ¿Bajo qué condiciones y con qué permisos?
- **Por defecto en el baseline**: permitido, pero solo con split explícito y
  documentado (E19, INV-4, FR-EXP-2).
- **Decisión pendiente**: si se permite, quiénes pueden crear splits y si
  requiere aprobación adicional.

## OQ-3 — Tipos impositivos por defecto para tickets

- **Pregunta**: ¿qué tipo de IVA por defecto se usa para derivar la base y la
  cuota de un ticket sin desglose fiscal?
- **Por defecto en el baseline**: tipo general (21 %), configurable.
- **Decisión pendiente**: fijar el tipo por defecto y si se permite
  configurarlo por proveedor o categoría.

## OQ-4 — Multimoneda

- **Pregunta**: ¿se soporta multimoneda (gastos en distintas monedas con
  conversión)? ¿Con qué fuente de tipos de cambio?
- **Por defecto en el baseline**: cada gasto en una única moneda (INV-13); la
  conversión es explícita y registrada (FR-CUR-3) pero no se prescribe fuente.
- **Decisión pendiente**: si se soporta conversión automática, qué fuente de
  tipos de cambio y con qué fecha de referencia.

## OQ-5 — Categorías predefinidas vs libres

- **Pregunta**: ¿las categorías son un catálogo predefinido (fijo) o pueden
  crearse libremente por el usuario? ¿Son obligatorias?
- **Por defecto en el baseline**: catálogo administrable (E10); categoría
  opcional salvo que la política la exija (VR-BIZ-7).
- **Decisión pendiente**: si la categoría es obligatoria para aceptar y si el
  catálogo es fijo o administrable por el usuario.

## OQ-6 — Pagos parciales

- **Pregunta**: ¿se permiten pagos parciales (varios pagos que suman el
  total)?
- **Por defecto en el baseline**: no se prescribe (FR-PAY-3 opcional); el
  pago único debe coincidir con el total (VR-ARITH-5, WARN).
- **Decisión pendiente**: si se soportan pagos parciales y cómo se valida la
  suma.

## OQ-7 — Resolución automática de duplicados

- **Pregunta**: ¿se permite resolver duplicados por regla aprobada (p. e.g.
  fingerprint idéntico + mismo usuario + mismo día => auto-confirmar) en vez
  de siempre humana?
- **Por defecto en el baseline**: no; la resolución es siempre humana
  (DUP-4).
- **Decisión pendiente**: si se permite auto-resolución en casos muy fiables
  (fingerprint) y con qué permisos.

## OQ-8 — Umbral de similitud para la clave de duplicación

- **Pregunta**: ¿la clave de duplicación exige coincidencia exacta o se
  permite tolerancia (p. e.g. fecha ±1 día, importe ±0,01)?
- **Por defecto en el baseline**: coincidencia exacta (DUP-2).
- **Decisión pendiente**: si se introduce tolerancia y con qué valores.

## OQ-9 — Modelo de multi-tenancy / aislamiento por usuario

- **Pregunta**: ¿el aislamiento de datos es por usuario individual, por
  organización/empresa, o por otro modelo?
- **Por defecto en el baseline**: aislamiento por usuario (NFR-7).
- **RESUELTA (2026-08-31, ADR-0008)**: aislamiento por **organización
  (multi-usuario)**. `owner_id` = `organization_id`. Varios usuarios de la
  misma organización comparten datos; el aislamiento es entre organizaciones.
  La atribución de auditoría sigue siendo por usuario. Ver ADR-0008.

## OQ-10 — Retención de documentos

- **Pregunta**: ¿cuánto tiempo se conservan los documentos fuente y los
  registros de auditoría? ¿Hay obligación legal de retención (p. e.g. 5-10
  años para documentos fiscales)?
- **Por defecto en el baseline**: conservación duradera (NFR-8), sin plazo
  fijado.
- **Decisión pendiente**: fijar el plazo de retención (legal y operativo) y
  la política de purga (si la hay).

## OQ-11 — Retenciones aplicables

- **Pregunta**: ¿qué tipos de retención se soportan (solo IRPF, o también
  otras)? ¿En qué supuestos aparecen en facturas recibidas?
- **Por defecto en el baseline**: se soporta `withholding` genérico (E8) con
  IRPF como caso típico; no se prescribe catálogo.
- **Decisión pendiente**: definir el catálogo de retenciones soportadas.

## OQ-12 — Inversión del sujeto pasivo (IVA intracomunitario)

- **Pregunta**: ¿se soporta la inversión del sujeto pasivo (IVA al 0 % con
  obligación de autoliquidación)?
- **Por defecto en el baseline**: se menciona como tipo de IVA (01-
  terminology.md) pero no se detallan reglas específicas.
- **Decisión pendiente**: si se soporta y qué validaciones específicas
  requiere.

## OQ-13 — Anulación de gastos aceptados: permisos

- **Pregunta**: ¿quiénes pueden anular un gasto aceptado? ¿Requiere motivo
  obligatorio?
- **Por defecto en el baseline**: usuario autorizado con permiso de
  anulación; motivo obligatorio (FR-EXP-5).
- **Decisión pendiente**: definir el rol exacto y si la anulación requiere
  doble aprobación.

## OQ-14 — Proveedor `inactive` en gastos nuevos

- **Pregunta**: ¿se permite asociar un gasto nuevo a un proveedor `inactive`?
- **Por defecto en el baseline**: bloqueado (VR-REF-1); se permite con
  advertencia si se decide.
- **Decisión pendiente**: si se permite con advertencia.

## OQ-15 — Formato de fecha canónico

- **Pregunta**: ¿la fecha canónica es solo la fecha (YYYY-MM-DD) o incluye
  hora (YYYY-MM-DDTHH:MM:SS)?
- **Por defecto en el baseline**: fecha del documento = YYYY-MM-DD; las
  fechas/hora de eventos (subida, revisión, aceptación) = con hora.
- **Decisión pendiente**: confirmar.

## OQ-16 — Varios pagos por gasto y conciliación

- **Pregunta**: ¿se registra el hecho de pago como parte del gasto o como una
  entidad separada con conciliación?
- **Por defecto en el baseline**: entidad separada (E12) asociada al gasto;
  sin conciliación bancaria (fuera de scope).
- **Decisión pendiente**: si se necesita conciliación en una fase posterior.

## OQ-17 — Jerarquía de categorías

- **Pregunta**: ¿las categorías son planas o jerárquicas?
- **Por defecto en el baseline**: se permite jerarquía (E10) pero no se
  prescribe.
- **Decisión pendiente**: si se usa jerarquía y a cuántos niveles.

## OQ-18 — Idiomas de los documentos

- **Pregunta**: ¿se soportan documentos en otros idiomas (p. e.g. facturas en
  inglés, francés)?
- **Por defecto en el baseline**: el sistema es es/ES (NFR-5) pero no se
  restringe el idioma del documento fuente; la extracción debe manejar el
  idioma del documento.
- **Decisión pendiente**: si se limita a documentos en español o se soporta
  multilingüe.
