import { tool } from "@opencode-ai/plugin/tool";

const ROOT = "/workspace/gastosE";

function sh(cmd, timeoutMs = 120000) {
  return new Promise((resolve) => {
    const child = Bun.spawn(["bash", "-lc", cmd], {
      cwd: ROOT,
      stdout: "pipe",
      stderr: "pipe",
      env: { ...process.env, GIT_TERMINAL_PROMPT: "0" },
    });
    const timer = setTimeout(() => {
      try { child.kill(); } catch {}
    }, timeoutMs);
    Promise.all([
      new Response(child.stdout).text(),
      new Response(child.stderr).text(),
      child.exited,
    ]).then(([out, err, code]) => {
      clearTimeout(timer);
      resolve({ code: code ?? -1, out: out.slice(0, 20000), err: err.slice(0, 20000) });
    });
  });
}

function fmt(res, header) {
  const body = [res.out, res.err].filter(Boolean).join("\n").trim() || "(sin salida)";
  return {
    title: header,
    output: `exit=${res.code}\n${body}`,
    metadata: { exit_code: res.code },
  };
}

const run_tests = tool({
  description:
    "Ejecuta los tests disponibles en GastosE. scope: all | backend | frontend | workers. Maneja el caso de proyecto sin inicializar (Phase 0).",
  args: {
    scope: tool.schema.string().describe("all | backend | frontend | workers").default("all"),
  },
  async execute(args, ctx) {
    const scope = args.scope || "all";
    const parts = [];
    const hasBackend = await Bun.file(`${ROOT}/backend`).stat().then(() => true).catch(() => false);
    const hasFrontend = await Bun.file(`${ROOT}/frontend`).stat().then(() => true).catch(() => false);
    const hasWorkers = await Bun.file(`${ROOT}/workers`).stat().then(() => true).catch(() => false);
    const hasTests = await Bun.file(`${ROOT}/tests`).stat().then(() => true).catch(() => false);

    if (!hasBackend && !hasFrontend && !hasWorkers && !hasTests) {
      return {
        title: "run-tests",
        output: "SKIP: el proyecto todavía no tiene backend/frontend/workers/tests (Phase 0). Nada que ejecutar.",
        metadata: { skipped: true, scope },
      };
    }

    if (scope === "all" || scope === "backend" || scope === "workers") {
      if (hasTests || hasBackend || hasWorkers) {
        const sel = scope === "backend" ? "tests/unit tests/integration tests/api tests/database"
          : scope === "workers" ? "tests/workers tests/extraction"
          : "tests";
        const r = await sh(`python3 -m pytest ${sel} -q --maxfail=20 2>&1 | tail -40`);
        parts.push(`[pytest ${scope}]\n${fmt(r, "pytest").output}`);
      } else {
        parts.push(`[pytest ${scope}] SKIP: no hay tests de Python todavía.`);
      }
    }
    if (scope === "all" || scope === "frontend") {
      if (hasFrontend) {
        const pkg = await Bun.file(`${ROOT}/frontend/package.json`).text().catch(() => "");
        const hasTest = pkg.includes('"test"');
        if (hasTest) {
          const r = await sh(`cd frontend && (npm test --if-present 2>&1 || npx vitest run 2>&1) | tail -40`, 300000);
          parts.push(`[frontend tests]\n${fmt(r, "frontend").output}`);
        } else {
          parts.push("[frontend tests] SKIP: frontend sin script de test definido.");
        }
      } else {
        parts.push("[frontend tests] SKIP: no existe frontend/ todavía.");
      }
    }
    return { title: "run-tests", output: parts.join("\n\n"), metadata: { scope } };
  },
});

const lint = tool({
  description:
    "Ejecuta los linters disponibles en GastosE detectando qué stack existe. No falla si durante Phase 0 no hay backend/frontend completo.",
  args: {
    scope: tool.schema.string().describe("all | backend | frontend").default("all"),
  },
  async execute(args, ctx) {
    const scope = args.scope || "all";
    const parts = [];
    const hasBackend = await Bun.file(`${ROOT}/backend`).stat().then(() => true).catch(() => false);
    const hasFrontend = await Bun.file(`${ROOT}/frontend`).stat().then(() => true).catch(() => false);

    if (scope === "all" || scope === "backend") {
      if (hasBackend) {
        const r = await sh(`python3 -m ruff check backend/ 2>&1 | tail -30 || python3 -m py_compile $(find backend -name '*.py' | head -50) 2>&1 | tail -30`);
        parts.push(`[lint backend]\n${fmt(r, "ruff").output}`);
      } else {
        parts.push("[lint backend] SKIP: no existe backend/ todavía (Phase 0).");
      }
    }
    if (scope === "all" || scope === "frontend") {
      if (hasFrontend) {
        const r = await sh(`cd frontend && (npx eslint . 2>&1 | tail -30)`, 180000);
        parts.push(`[lint frontend]\n${fmt(r, "eslint").output}`);
      } else {
        parts.push("[lint frontend] SKIP: no existe frontend/ todavía (Phase 0).");
      }
    }
    return { title: "lint", output: parts.join("\n\n"), metadata: { scope } };
  },
});

const migration_check = tool({
  description:
    "Comprueba el estado de las migraciones Alembic de GastosE cuando existen: heads, branches, grafo de migraciones y problemas básicos. Usado por database, qa, reviewer y director.",
  args: {
    extra: tool.schema.string().describe("Argumentos extra opcionales para alembic (p. ej. 'history -v'). Vacío por defecto.").default(""),
  },
  async execute(args, ctx) {
    const hasAlembic = await Bun.file(`${ROOT}/alembic`).stat().then(() => true).catch(() => false);
    const hasIni = await Bun.file(`${ROOT}/alembic.ini`).stat().then(() => true).catch(() => false);
    if (!hasAlembic && !hasIni) {
      return {
        title: "migration-check",
        output: "SKIP: todavía no existe Alembic en GastosE (Phase 0). No hay migraciones que comprobar.",
        metadata: { skipped: true },
      };
    }
    const extra = args.extra ? ` ; echo '--- extra: ${args.extra}' ; alembic ${args.extra} 2>&1 | tail -30` : "";
    const r = await sh(
      `alembic heads 2>&1 | tail -10 ; echo '--- branches' ; alembic branches 2>&1 | tail -10 ; echo '--- current' ; alembic current 2>&1 | tail -10 ; echo '--- history' ; alembic history 2>&1 | tail -20${extra}`
    );
    const out = fmt(r, "alembic").output;
    const heads = (out.match(/^rev_id:.*$/gm) || []);
    const verdict = heads.length > 1 ? "FAIL: múltiples heads (grafo ramificado)" : heads.length === 1 ? "OK: un único head" : "WARN: no se pudo determinar el head (¿DB no disponible?)";
    return { title: "migration-check", output: `${verdict}\n\n${out}`, metadata: { heads: heads.length } };
  },
});

const openapi_check = tool({
  description:
    "Valida el contrato OpenAPI de GastosE cuando existe (docs/api/openapi.yaml): sintaxis YAML, estructura mínima y coherencia básica. Usado por architect, backend, qa, reviewer y director.",
  args: {
    path: tool.schema.string().describe("Ruta del spec OpenAPI relativa a la raíz del proyecto").default("docs/api/openapi.yaml"),
  },
  async execute(args, ctx) {
    const p = `${ROOT}/${args.path}`;
    const exists = await Bun.file(p).stat().then(() => true).catch(() => false);
    if (!exists) {
      return {
        title: "openapi-check",
        output: `SKIP: no existe ${args.path} todavía (Phase 0). No hay contrato OpenAPI que validar.`,
        metadata: { skipped: true },
      };
    }
    const r = await sh(
      `python3 - <<'EOF'
import sys
try:
    import yaml
except ImportError:
    print("FAIL: PyYAML no disponible"); sys.exit(1)
try:
    spec = yaml.safe_load(open("${args.path}"))
except Exception as e:
    print(f"FAIL: YAML inválido: {e}"); sys.exit(1)
if not isinstance(spec, dict):
    print("FAIL: el spec no es un mapa"); sys.exit(1)
problems = []
if not str(spec.get("openapi", "")).startswith("3"):
    problems.append("falta 'openapi: 3.x'")
if not spec.get("info", {}).get("title"):
    problems.append("falta info.title")
paths = spec.get("paths", {})
if not paths:
    problems.append("no hay paths definidos")
for route, ops in paths.items():
    if not route.startswith("/"):
        problems.append(f"ruta inválida: {route}")
    for method, op in (ops or {}).items():
        if method in ("get","post","put","patch","delete") and not isinstance(op, dict):
            problems.append(f"operación inválida {method} en {route}")
if problems:
    print("FAIL:"); [print(" -", x) for x in problems]; sys.exit(1)
print(f"OK: spec OpenAPI válido. {len(paths)} paths.")
EOF`
    );
    return fmt(r, "openapi-check");
  },
});

const docker_health = tool({
  description:
    "Comprueba la infraestructura de GastosE cuando existe: configuración Compose, containers y estado de health. Contempla el runtime real del servidor (docker CLI emulando podman).",
  args: {
    file: tool.schema.string().describe("Ruta del compose relativo a la raíz").default("docker-compose.yml"),
  },
  async execute(args, ctx) {
    const file = args.file;
    const exists = await Bun.file(`${ROOT}/${file}`).stat().then(() => true).catch(() => false);
    if (!exists) {
      return {
        title: "docker-health",
        output: "SKIP: no existe infraestructura Compose todavía (Phase 0). No hay stack que comprobar.",
        metadata: { skipped: true },
      };
    }
    const r = await sh(
      `echo '--- compose config' ; docker compose -f ${file} config -q 2>&1 | tail -10 ; echo '--- ps' ; docker compose -f ${file} ps 2>&1 | tail -20 ; echo '--- runtime' ; docker version --format '{{.Server.Version}}' 2>&1 | tail -2`
    );
    return fmt(r, "docker-health");
  },
});

const SCOPES = {
  architect: ["docs/architecture/", "docs/adr/", "docs/api/", "docs/project/"],
  domain: ["docs/requirements/", "docs/project/"],
  database: ["backend/", "alembic/", "alembic.ini", "tests/", "docs/project/"],
  backend: ["backend/", "tests/", "docs/api/", "docs/project/"],
  extraction: ["workers/", "backend/", "tests/", "docs/project/"],
  frontend: ["frontend/", "tests/", "docs/project/"],
  qa: ["tests/", "docs/project/"],
  security: [],
  reviewer: [],
  devops: ["deploy/", "scripts/", "Dockerfile", "docker-compose", "docs/project/"],
};

const scope_check = tool({
  description:
    "Comprueba qué archivos ha modificado un agente (git status/diff) y los compara con su scope permitido. Report PASS o FAIL OUT-OF-SCOPE. Scopes: architect, domain, database, backend, extraction, frontend, qa, security, reviewer, devops.",
  args: {
    agent: tool.schema.string().describe("Nombre del agente a comprobar"),
    base: tool.schema.string().describe("Ref git contra la que comparar (p. ej. main, HEAD). Vacío = working tree vs HEAD + untracked").default(""),
  },
  async execute(args, ctx) {
    const agent = args.agent;
    const scopes = SCOPES[agent];
    if (!scopes) {
      return { title: "scope-check", output: `FAIL: agente desconocido '${agent}'. Válidos: ${Object.keys(SCOPES).join(", ")}`, metadata: { pass: false } };
    }
    if (scopes.length === 0) {
      const r = await sh(`git status --porcelain 2>&1`);
      const modified = r.out.trim();
      if (!modified) {
        return { title: "scope-check", output: `PASS: ${agent} es READ-ONLY y no hay archivos modificados.`, metadata: { pass: true, agent } };
      }
      return { title: "scope-check", output: `FAIL OUT-OF-SCOPE: ${agent} es READ-ONLY pero hay cambios:\n${modified}`, metadata: { pass: false, agent } };
    }
    const r = args.base
      ? await sh(`git diff --name-only ${args.base} 2>&1 ; git ls-files --others --exclude-standard 2>&1`)
      : await sh(`git diff --name-only HEAD 2>&1 ; git ls-files --others --exclude-standard 2>&1`);
    const files = r.out.split("\n").map((l) => l.trim()).filter(Boolean);
    if (files.length === 0) {
      return { title: "scope-check", output: `PASS: ${agent} no ha modificado archivos.`, metadata: { pass: true, agent, files: 0 } };
    }
    const inScope = (f) => scopes.some((s) => f === s || f.startsWith(s));
    const violations = files.filter((f) => !inScope(f));
    if (violations.length === 0) {
      return {
        title: "scope-check",
        output: `PASS: ${agent} ha modificado ${files.length} archivo(s), todos dentro de su scope.\n${files.join("\n")}`,
        metadata: { pass: true, agent, files: files.length },
      };
    }
    return {
      title: "scope-check",
      output: `FAIL OUT-OF-SCOPE: ${agent} ha modificado ${violations.length} archivo(s) fuera de su scope:\n${violations.join("\n")}\n\nArchivos dentro de scope:\n${files.filter((f) => !violations.includes(f)).join("\n") || "(ninguno)"}`,
      metadata: { pass: false, agent, violations },
    };
  },
});

export default async () => {
  return {
    tool: {
      "run-tests": run_tests,
      lint: lint,
      "migration-check": migration_check,
      "openapi-check": openapi_check,
      "docker-health": docker_health,
      "scope-check": scope_check,
    },
  };
};
