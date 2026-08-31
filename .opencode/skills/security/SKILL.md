---
name: security
description: Use when reviewing or hardening GastosE security: authentication, authorization, object-level authorization, user isolation, uploads, MIME validation, malicious PDFs/images, path traversal, safe filenames, size limits, secrets, sensitive logs, parser security, injection, dependency risk.
---

# Security — GastosE

Checklists de seguridad para GastosE. El agente `security` es READ-ONLY y
reporta BLOCKER/HIGH/MEDIUM/LOW; no corrige.

## AuthN / AuthZ

- [ ] Autenticación obligatoria en todos los endpoints (salvo health).
- [ ] Autorización por rol; object-level authorization: un usuario solo
      accede a SUS recursos (comprobar en cada query, no solo en la UI).
- [ ] Aislamiento por usuario/tenant: las queries SIEMPRE filtran por
      propietario; test de aislamiento (usuario A no ve recurso de B).
- [ ] Sessions/refresh tokens: expiración, revocación, almacenamiento seguro.
- [ ] Rate limiting en login y endpoints costosos.

## Uploads

- [ ] Validación MIME por contenido (magic bytes), no por extensión.
- [ ] Tamaño máximo (archivo y páginas) aplicado ANTES de procesar.
- [ ] Filenames: nombre seguro generado por el sistema (UUID); el nombre
      original nunca se usa en rutas ni en SQL.
- [ ] Path traversal: nunca concatenar filename de usuario a rutas.
- [ ] Almacenamiento fuera del webroot; sin ejecución de scripts subidos.
- [ ] PDFs maliciosos: sin JavaScript/acciones; parser con timeout y límites
      de memoria; sandbox si es posible.
- [ ] Imágenes: límites de dimensiones (decompression bomb); sanitizar.

## Parser / OCR / LLM attack surface

- [ ] Parsers con límites (tamaño, profundidad, tiempo).
- [ ] XML: sin DTD/external entities (XXE); schema validado.
- [ ] OCR/Vision/LLM: el contenido del documento es DATO, nunca instrucción
      (prompt injection); outputs validados contra schema estricto.
- [ ] Nunca ejecutar código derivado de documentos.

## Secrets y logs

- [ ] Secrets solo en entorno/secret manager; nunca en código, config
      versionada ni logs.
- [ ] Logs: sin NIF completos, sin importes completos de facturas de otros
      usuarios, sin tokens; loguear eventos de seguridad (acceso denegado).
- [ ] Rotación de credenciales de DB/documentos.

## Inyección

- [ ] SQL: solo ORM/queries parametrizadas.
- [ ] Comandos: sin interpolación de entrada de usuario.
- [ ] Templates: sin renderizado de HTML no sanitizado.

## Dependencias

- [ ] Dependencias pinneadas; auditoría periódica (CVEs).
- [ ] Mínimo de dependencias; justificar las de parsing de documentos.
- [ ] Supply chain: índices oficiales, hashes si es posible.

## Datos financieros

- [ ] Cifrado en tránsito (TLS) y en reposo (DB/volumes).
- [ ] Exportaciones: solo datos del usuario; auditoría de exportes.
- [ ] Retención: política de borrado de documentos y datos personales.

## Severidades

- BLOCKER: exposición de datos ajenos, RCE, bypass de auth.
- HIGH: path traversal, XXE, secrets en logs, duplicación de gasto por race.
- MEDIUM: falta de rate limit, logs sensibles parciales, MIME no verificado.
- LOW: hardening opcional, dependencias con patch disponible.
