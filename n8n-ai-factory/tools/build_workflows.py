#!/usr/bin/env python3
"""Generate the six importable n8n workflow JSON files for AI Agent Factory.

Design: every sub-workflow is triggered by its own webhook and answers with
a Respond to Webhook node, so workflows call each other over HTTP
(localhost) and stay importable in any order — no hard-coded workflow IDs.
"""
import json
import os
import uuid

OUT = os.environ.get("FACTORY_OUT") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "workflows")
os.makedirs(OUT, exist_ok=True)

BASE = "={{ ($env.AI_FACTORY_BASE_URL || 'http://localhost:5678') + '/webhook/ai-factory/"
CES = "={{ ($env.CODE_EXEC_URL || 'http://code-exec-service:8080')"


def nid():
    return str(uuid.uuid4())


def node(name, type_, tv, params, x, y, **extra):
    n = {"parameters": params, "id": nid(), "name": name, "type": type_,
         "typeVersion": tv, "position": [x, y]}
    n.update(extra)
    return n


def webhook(name, path, x, y):
    return node(name, "n8n-nodes-base.webhook", 2,
                {"httpMethod": "POST", "path": path, "responseMode": "responseNode",
                 "options": {}}, x, y, webhookId=nid())


def respond(name, body_expr, x, y):
    return node(name, "n8n-nodes-base.respondToWebhook", 1.4,
                {"respondWith": "json", "responseBody": body_expr, "options": {}}, x, y)


def code(name, js, x, y):
    return node(name, "n8n-nodes-base.code", 2, {"jsCode": js}, x, y)


def http(name, url, body_expr, x, y, timeout=900000):
    return node(name, "n8n-nodes-base.httpRequest", 4.2,
                {"method": "POST", "url": url, "sendBody": True, "contentType": "json",
                 "specifyBody": "json", "jsonBody": body_expr,
                 "options": {"timeout": timeout}}, x, y)


def ces_db(name, path_suffix, body_expr, x, y):
    """Persistence now goes through the Code Execution Service, which stores
    everything in MongoDB (the user's stack) — no Postgres nodes remain."""
    return http(name, CES + " + '" + path_suffix + "' }}", body_expr, x, y)


def if_node(name, condition, x, y):
    return node(name, "n8n-nodes-base.if", 2.2,
                {"conditions": {"options": {"caseSensitive": True, "leftValue": "",
                                            "typeValidation": "loose"},
                                "conditions": [condition], "combinator": "and"},
                 "options": {}}, x, y)


def bool_cond(left):
    return {"id": nid(), "leftValue": left,
            "operator": {"type": "boolean", "operation": "true", "singleValue": True}}


def sticky(content, x, y, w=560, h=180):
    return node("Sticky Note", "n8n-nodes-base.stickyNote", 1,
                {"content": content, "height": h, "width": w, "color": 4}, x, y)


def link(conns, src, dst, output=0):
    conns.setdefault(src, {"main": []})
    while len(conns[src]["main"]) <= output:
        conns[src]["main"].append([])
    conns[src]["main"][output].append({"node": dst, "type": "main", "index": 0})


def chain(conns, names):
    for a, b in zip(names, names[1:]):
        link(conns, a, b)


def save(filename, name, nodes, conns, notes=None):
    wf = {"name": name, "nodes": nodes, "connections": conns,
          "settings": {"executionOrder": "v1"}, "staticData": None, "pinData": {}}
    if notes:
        wf["meta"] = {"notes": notes}
    path = os.path.join(OUT, filename)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(wf, fh, ensure_ascii=False, indent=2)
    print(f"wrote {filename}: {len(nodes)} nodes")


ESC_JS = """
const esc = (v) => (v === null || v === undefined) ? 'NULL' : `'${String(v).replace(/'/g, "''")}'`;
const escJson = (v) => (v === null || v === undefined) ? 'NULL' : `'${JSON.stringify(v).replace(/'/g, "''")}'::jsonb`;
"""

# =====================================================================
# Workflow 2 — Agent Execution (built first: everything else calls it)
# =====================================================================
AGENTS_JS = r"""
const SCHEMA_RULE = 'Always respond with ONE valid JSON object and nothing else (no markdown fences, no commentary). The object MUST follow this unified schema: {"task_id": <echo task_id>, "project_id": <echo project_id>, "agent_id": "<your agent id>", "status": "COMPLETED", "output": {...}, "artifacts": [], "error": null}. Put your role-specific result inside "output" using exactly the keys specified for your role. If you truly cannot complete the task, set "status" to "FAILED" and "error" to a short reason.';

const AGENTS = {
  project_manager: {
    name: 'Project Manager', models: { openrouter: 'anthropic/claude-sonnet-4.5', groq: 'openai/gpt-oss-120b', ollama: 'gpt-oss:120b' },
    role: 'You are the Project Manager of a multi-agent software team. Analyse the user requirement, break it into tasks, assign each task to exactly one agent, define dependencies and the order of work. You coordinate — you do not write code. Decide which agents are actually needed: a full website needs all of them; a single module or a small change needs only the relevant ones.',
    output: '"output" keys: {"summary": string, "tasks": [{"task_key": string, "agent_id": string, "title": string, "description": string, "depends_on": [task_key]}], "agents_needed": [agent_id], "risks": [string]}. Valid agent_id values: project_manager, business_analyst, ui_ux_designer, frontend_architect, frontend_developer, backend_architect, backend_developer, integration_agent, qa_engineer, code_reviewer.'
  },
  business_analyst: {
    name: 'Business Analyst', models: { openrouter: 'openai/gpt-5', groq: 'openai/gpt-oss-120b', ollama: 'gpt-oss:120b' },
    role: 'You are the Business Analyst. Turn the requirement and the PM plan into concrete features, user stories and testable acceptance criteria.',
    output: '"output" keys: {"features": [string], "user_stories": [{"as_a": string, "want": string, "so_that": string}], "acceptance_criteria": [string], "out_of_scope": [string]}.'
  },
  ui_ux_designer: {
    name: 'UI/UX Designer', models: { openrouter: 'google/gemini-2.5-pro', groq: 'openai/gpt-oss-120b', ollama: 'gpt-oss:120b' },
    role: 'You are the UI/UX Designer. Design the sitemap, the structure of every page, the shared components and a concrete design system (colors, typography, spacing, border radius, style notes) that the frontend must follow exactly. Aim for a modern, professional, consistent and fully responsive design.',
    output: '"output" keys: {"sitemap": [string], "pages": [{"name": string, "route": string, "sections": [string]}], "components": [string], "design_system": {"primary_color": string, "font": string, "style_notes": string}}.'
  },
  frontend_architect: {
    name: 'Frontend Architect', models: { openrouter: 'anthropic/claude-sonnet-4.5', groq: 'openai/gpt-oss-120b', ollama: 'gpt-oss:120b' },
    role: 'You are the Frontend Architect. Define the frontend architecture for a Vite + React + Tailwind project: folder structure, routes, component tree with props, and the state management approach. Be concrete and consistent with the design system in your context.',
    output: '"output" keys: {"stack": string, "folder_structure": [string], "routes": [{"path": string, "component": string}], "components": [{"name": string, "props": [string]}], "state_management": string}.'
  },
  frontend_developer: {
    name: 'Frontend Developer', models: { openrouter: 'qwen/qwen3-coder', groq: 'openai/gpt-oss-20b', ollama: 'qwen3-coder:480b' },
    role: 'You are the Frontend Developer. Write the COMPLETE frontend (React + Vite + Tailwind CSS) exactly per the architecture and design system in your context. Build every page and component — not only the home page. Every button, filter, form and navigation must actually work (client-side logic included). Use only stable, mutually compatible dependency versions (React 19, Vite 6, Tailwind CSS 3, react-router-dom 7). Return full file contents — never placeholders, never truncated code, never "...rest unchanged".',
    output: '"output" keys: {"summary": string, "files": [{"path": string, "content": string}], "notes": [string]}. files MUST include package.json (with install/dev/build scripts), index.html AT THE PROJECT ROOT containing <div id="root"></div> and <script type="module" src="/src/main.jsx"></script>, vite.config.js, tailwind.config.js, postcss.config.js, src/main.jsx, src/index.css, src/App.jsx, every component/page/data file that is imported, and README.md.'
  },
  backend_architect: {
    name: 'Backend Architect', models: { openrouter: 'openai/gpt-5', groq: 'openai/gpt-oss-120b', ollama: 'gpt-oss:120b' },
    role: 'You are the Backend Architect. Design the backend: folder structure, database schema, the complete REST API contract, and the authentication/authorisation approach. If the project genuinely needs no backend, say so in the output and return an empty api_contract.',
    output: '"output" keys: {"stack": string, "folder_structure": [string], "database": {"tables": [{"name": string, "columns": [string]}]}, "api_contract": [{"method": string, "path": string, "request": string, "response": string}], "auth": {"strategy": string, "roles": [string]}}.'
  },
  backend_developer: {
    name: 'Backend Developer', models: { openrouter: 'qwen/qwen3-coder', groq: 'openai/gpt-oss-20b', ollama: 'qwen3-coder:480b' },
    role: 'You are the Backend Developer. Write the COMPLETE backend (Node.js) exactly per the API contract in your context. Backend files go under a server/ folder inside the same project and must not break the frontend build; document how to run the server in your notes. If the architecture says no backend is needed, return an empty files array and explain why in notes. Return full file contents — never placeholders.',
    output: '"output" keys: {"summary": string, "files": [{"path": string, "content": string}], "notes": [string]}.'
  },
  integration_agent: {
    name: 'Integration Agent', models: { openrouter: 'anthropic/claude-sonnet-4.5', groq: 'openai/gpt-oss-120b', ollama: 'gpt-oss:120b' },
    role: 'You are the Integration Agent. Check the frontend and backend file sets against each other and the API contract: every API route the frontend calls exists in the backend, payload shapes match, all imports resolve, package.json covers every imported package, and there are no conflicting files. Return corrected FULL contents only for files that must change.',
    output: '"output" keys: {"verdict": "ok" or "fixed", "conflicts": [{"file": string, "issue": string}], "files": [{"path": string, "content": string}]}.'
  },
  qa_engineer: {
    name: 'QA Engineer', models: { openrouter: 'deepseek/deepseek-r1', groq: 'openai/gpt-oss-120b', ollama: 'deepseek-v3.1:671b' },
    role: 'You are the QA Engineer. Derive test cases from the acceptance criteria, study the build/test logs and results in your context, and report every functional problem together with the agent who must fix it (frontend_developer or backend_developer).',
    output: '"output" keys: {"verdict": "pass" or "fail", "test_cases": [{"name": string, "result": "pass" or "fail", "details": string}], "issues": [{"severity": "critical" or "major" or "minor", "target_agent": string, "description": string, "file": string}]}.'
  },
  code_reviewer: {
    name: 'Code Reviewer', models: { openrouter: 'anthropic/claude-sonnet-4.5', groq: 'openai/gpt-oss-120b', ollama: 'gpt-oss:120b' },
    role: 'You are the Code Reviewer. Review the whole project: structure, security (no hard-coded secrets, no unsafe patterns), code quality and maintainability. Approve only when there are no critical or major issues left.',
    output: '"output" keys: {"verdict": "approve" or "request_changes", "score": number 0-100, "issues": [{"severity": "critical" or "major" or "minor", "target_agent": string, "description": string, "file": string}], "comments": [string]}.'
  }
};
"""

RESOLVE_JS = AGENTS_JS + r"""
const PROVIDERS = {
  openrouter: { url: 'https://openrouter.ai/api/v1/chat/completions', env_key: 'OPENROUTER_API_KEY' },
  groq: { url: 'https://api.groq.com/openai/v1/chat/completions', env_key: 'GROQ_API_KEY' },
  ollama: { url: 'https://ollama.com/v1/chat/completions', env_key: 'OLLAMA_API_KEY' }
};
const DEFAULT_PROVIDER = '__DEFAULT_PROVIDER__';
const input = $input.first().json;
const body = input.body ?? input;
const agentId = String(body.agent_id || '');
const cfg = AGENTS[agentId];
if (!cfg) {
  return [{ json: { fatal: { task_id: body.task_id ?? null, project_id: body.project_id ?? null, agent_id: agentId, status: 'FAILED', output: null, error: 'unknown_agent: ' + agentId, artifacts: [] } } }];
}
const provider = body.provider || (body.providers && body.providers[agentId]) || DEFAULT_PROVIDER;
const prov = PROVIDERS[provider];
if (!prov) {
  return [{ json: { fatal: { task_id: body.task_id ?? null, project_id: body.project_id ?? null, agent_id: agentId, status: 'FAILED', output: null, error: 'unknown_provider: ' + provider, artifacts: [] } } }];
}
const model = body.model || (body.models && body.models[agentId]) || (cfg.models && (cfg.models[provider] || cfg.models.openrouter));
const apiKey = $env[prov.env_key] || '';
if (!apiKey) {
  return [{ json: { fatal: { task_id: body.task_id ?? null, project_id: body.project_id ?? null, agent_id: agentId, status: 'FAILED', output: null, error: `missing_env_key: set ${prov.env_key} in the n8n environment (.env file next to docker-compose.yml) to use provider "${provider}"`, artifacts: [] } } }];
}
const taskId = body.task_id || `${body.project_id || 'task'}-${agentId}`;
const systemPrompt = `${cfg.role}\n\n${cfg.output}\n\n${SCHEMA_RULE}`;
const userContent = [
  'TASK: ' + (body.task_description || ''),
  '',
  'INPUT CONTEXT (JSON):',
  JSON.stringify(body.input_context ?? {}, null, 2),
  '',
  `Echo task_id="${taskId}" and project_id="${body.project_id}" in your JSON answer.`
].join('\n');
""" + ESC_JS + r"""
const contextForDb = { task_description: body.task_description || '', input_context: body.input_context ?? {}, provider, model };
const run_doc = {
  project_id: body.project_id ?? null, task_id: taskId, agent_id: agentId, agent_name: cfg.name,
  model, provider, status: 'RUNNING', input_context: contextForDb,
  started_at: new Date().toISOString(), created_at: new Date().toISOString()
};
return [{ json: { agent_id: agentId, agent_name: cfg.name, model, provider, api_url: prov.url, auth_header: 'Bearer ' + apiKey, task_id: taskId, project_id: body.project_id ?? null, system_prompt: systemPrompt, user_content: userContent, started_ms: Date.now(), run_doc } }];
"""

RESOLVE_JS = RESOLVE_JS.replace("__DEFAULT_PROVIDER__", os.environ.get("FACTORY_DEFAULT_PROVIDER", "openrouter"))

BUILD_BODY_JS = r"""
const cfg = $('Resolve Agent Config').first().json;
const row = $input.first().json;
return [{ json: {
  run_id: row.id || null,
  agent_id: cfg.agent_id, task_id: cfg.task_id, project_id: cfg.project_id,
  model: cfg.model, started_ms: cfg.started_ms,
  provider: cfg.provider, api_url: cfg.api_url, auth_header: cfg.auth_header,
  provider_body: {
    model: cfg.model,
    temperature: 0.3,
    usage: { include: true },
    messages: [
      { role: 'system', content: cfg.system_prompt },
      { role: 'user', content: cfg.user_content }
    ]
  }
} }];
"""

PARSE_JS = r"""
const meta = $('Build Provider Request').first().json;
const resp = $input.first().json;
const duration = Date.now() - (meta.started_ms || Date.now());
const usage = (resp && resp.usage) || {};
let status = 'COMPLETED', error = null, roleOutput = null;
const content = resp && resp.choices && resp.choices[0] && resp.choices[0].message ? resp.choices[0].message.content : null;
if (!content) {
  status = 'FAILED';
  error = (resp && resp.error && (resp.error.message || resp.error)) || 'empty_or_error_response_from_provider';
} else {
  let text = String(content).trim().replace(/^```(?:json)?/i, '').replace(/```\s*$/, '').trim();
  let parsed = null;
  try { parsed = JSON.parse(text); } catch {
    const m = text.match(/\{[\s\S]*\}/);
    if (m) { try { parsed = JSON.parse(m[0]); } catch { parsed = null; } }
  }
  if (!parsed) {
    status = 'FAILED'; error = 'model_did_not_return_valid_json';
    roleOutput = { raw: String(content).slice(0, 4000) };
  } else if (parsed.status === 'FAILED') {
    status = 'FAILED'; error = parsed.error || 'agent_reported_failure';
    roleOutput = parsed.output ?? null;
  } else {
    roleOutput = parsed.output ?? parsed;
  }
}
""" + ESC_JS + r"""
const run_update = {
  id: meta.run_id, task_id: meta.task_id,
  set: {
    status, output: roleOutput, error,
    prompt_tokens: usage.prompt_tokens ?? null, completion_tokens: usage.completion_tokens ?? null,
    total_tokens: usage.total_tokens ?? null, cost_usd: usage.cost ?? null,
    duration_ms: duration, finished_at: new Date().toISOString()
  }
};
return [{ json: {
  run_update,
  response: {
    task_id: meta.task_id, project_id: meta.project_id, agent_id: meta.agent_id,
    status, output: roleOutput, error, artifacts: [],
    usage: { prompt_tokens: usage.prompt_tokens ?? null, completion_tokens: usage.completion_tokens ?? null, total_tokens: usage.total_tokens ?? null, cost: usage.cost ?? null },
    duration_ms: duration
  }
} }];
"""


def workflow_agent_execution():
    nodes = [
        sticky("## Agent Execution — runs ONE agent through OpenRouter\n"
               "Input (POST JSON): {project_id, task_id, agent_id, task_description, input_context, models?}\n"
               "Output: the unified schema {task_id, project_id, agent_id, status, output, error, artifacts, usage}.\n\n"
               "**Setup:** API keys come from the n8n environment variables GROQ_API_KEY / OLLAMA_API_KEY / "
               "OPENROUTER_API_KEY (set them in the .env file next to docker-compose.yml) — keys are "
               "NEVER stored in this JSON. Default provider, per-agent models & prompts live in the "
               "**Resolve Agent Config** code node — edit them there.", 0, 40),
        webhook("Webhook — Agent Execute", "ai-factory/agent-execute", 240, 320),
        code("Resolve Agent Config", RESOLVE_JS, 500, 320),
        if_node("Config OK?", bool_cond("={{ !!$json.fatal }}"), 760, 320),
        respond("Respond — Fatal", "={{ JSON.stringify($json.fatal) }}", 1020, 520),
        ces_db("Insert Run (CES)", "/db/runs", "={{ JSON.stringify($json.run_doc) }}", 1020, 220),
        code("Build Provider Request", BUILD_BODY_JS, 1280, 220),
        node("Provider Chat Completions", "n8n-nodes-base.httpRequest", 4.2,
             {"method": "POST", "url": "={{ $json.api_url }}",
              "sendHeaders": True,
              "headerParameters": {"parameters": [
                  {"name": "Authorization", "value": "={{ $json.auth_header }}"},
                  {"name": "X-Title", "value": "AI Agent Factory"}]},
              "sendBody": True, "contentType": "json", "specifyBody": "json",
              "jsonBody": "={{ JSON.stringify($json.provider_body) }}",
              "options": {"timeout": 600000}},
             1540, 220, retryOnFail=True, maxTries=2,
             waitBetweenTries=5000, onError="continueRegularOutput"),
        code("Parse Result", PARSE_JS, 1800, 220),
        ces_db("Update Run (CES)", "/db/runs/update", "={{ JSON.stringify($json.run_update) }}", 2060, 220),
        respond("Respond — Result", "={{ JSON.stringify($('Parse Result').first().json.response) }}", 2320, 220),
    ]
    conns = {}
    chain(conns, ["Webhook — Agent Execute", "Resolve Agent Config", "Config OK?"])
    link(conns, "Config OK?", "Respond — Fatal", output=0)       # fatal present → true
    link(conns, "Config OK?", "Insert Run (CES)", output=1)  # ok → false
    chain(conns, ["Insert Run (CES)", "Build Provider Request",
                  "Provider Chat Completions", "Parse Result",
                  "Update Run (CES)", "Respond — Result"])
    save("02-agent-execution.json", "AI Factory — Agent Execution", nodes, conns)


# =====================================================================
# Workflow 3 — Parallel Agent Execution
# =====================================================================
PARALLEL_JS = r"""
const helpers = this.helpers;
const input = $input.first().json;
const body = input.body ?? input;
const calls = Array.isArray(body.calls) ? body.calls : [];
const base = ($env.AI_FACTORY_BASE_URL || 'http://localhost:5678').replace(/\/$/, '');
async function runOne(call) {
  try {
    if (helpers && helpers.httpRequest) {
      return await helpers.httpRequest({
        method: 'POST', url: `${base}/webhook/ai-factory/agent-execute`,
        body: call, json: true, timeout: 900000
      });
    }
    const res = await fetch(`${base}/webhook/ai-factory/agent-execute`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(call)
    });
    return await res.json();
  } catch (e) {
    return { task_id: call.task_id ?? null, project_id: call.project_id ?? null, agent_id: call.agent_id, status: 'FAILED', output: null, error: String((e && e.message) || e), artifacts: [] };
  }
}
const results = await Promise.all(calls.map(runOne));
const requiredPairs = calls.map((c, i) => ({ call: c, result: results[i] })).filter(p => p.call.required !== false);
const allOk = requiredPairs.every(p => p.result && p.result.status === 'COMPLETED');
return [{ json: {
  project_id: body.project_id ?? null,
  phase: body.phase ?? null,
  results,
  all_required_completed: allOk,
  failures: results.filter(r => !r || r.status !== 'COMPLETED').map(r => ({ agent_id: r && r.agent_id, error: r && r.error }))
} }];
"""


def workflow_parallel():
    nodes = [
        sticky("## Parallel Agent Execution\n"
               "Input: {project_id, phase, calls: [{agent_id, task_description, input_context, required}]}\n"
               "Runs every call against the Agent Execution webhook **in parallel**, "
               "collects all results (a failing agent does not sink the others) and reports "
               "whether every *required* call completed.", 0, 40),
        webhook("Webhook — Parallel Execute", "ai-factory/parallel", 240, 320),
        code("Run Calls In Parallel", PARALLEL_JS, 500, 320),
        respond("Respond — Parallel Results", "={{ JSON.stringify($json) }}", 760, 320),
    ]
    conns = {}
    chain(conns, ["Webhook — Parallel Execute", "Run Calls In Parallel", "Respond — Parallel Results"])
    save("03-parallel-agent-execution.json", "AI Factory — Parallel Agent Execution", nodes, conns)


# =====================================================================
# Workflow 4 — Code Generation (dev agents → integration → CES store)
# =====================================================================
PREPARE_DEV_JS = r"""
const input = $input.first().json;
const body = input.body ?? input;
const spec = body.spec || {};
const isFix = body.mode === 'fix';
const DESCRIPTIONS = {
  frontend_developer: 'Build the complete frontend (React + Vite + Tailwind) from the architecture and design system in your context (spec). Return EVERY file with full content in output.files, including package.json and a root index.html.',
  backend_developer: 'Build the complete backend (Node.js, server/ folder) from the API contract in your context (spec). Return EVERY file with full content in output.files. If no backend is needed, return an empty files array and explain in notes.'
};
const calls = (body.agents || []).map(a => ({
  project_id: body.project_id,
  task_id: `${body.project_id}-${a}-${body.attempt ?? 0}`,
  agent_id: a,
  task_description: isFix
    ? 'Fix the issues listed in your context for YOUR area. Return the COMPLETE corrected files (full contents) in output.files — the files you return replace the stored ones.'
    : (DESCRIPTIONS[a] || 'Produce your part of the project source in output.files.'),
  input_context: isFix
    ? { issues: (body.issues || []).filter(i => i.target_agent === a), spec }
    : { spec },
  models: body.models || {},
  providers: body.providers || {},
  required: true
}));
return [{ json: {
  project_id: body.project_id,
  attempt: body.attempt ?? 0,
  mode: body.mode || 'full',
  models: body.models || {},
  with_integration: Boolean(body.with_integration),
  providers: body.providers || {},
  spec,
  parallel_body: { project_id: body.project_id, phase: 'codegen', calls }
} }];
"""

COLLECT_JS = r"""
const prep = $('Prepare Dev Calls').first().json;
const par = $input.first().json;
const filesByPath = new Map();
const overrides = [];
for (const r of par.results || []) {
  const files = (r.output && Array.isArray(r.output.files)) ? r.output.files : [];
  for (const f of files) {
    if (!f || typeof f.path !== 'string' || typeof f.content !== 'string') continue;
    if (filesByPath.has(f.path)) overrides.push(f.path);
    filesByPath.set(f.path, f.content);
  }
}
const files = [...filesByPath.entries()].map(([p, content]) => ({ path: p, content }));
const integrationCall = {
  project_id: prep.project_id,
  task_id: `${prep.project_id}-integration-${prep.attempt}`,
  agent_id: 'integration_agent',
  task_description: 'Verify frontend/backend consistency against the API contract in spec. Return corrected full contents ONLY for files that must change (output.files); verdict "ok" when nothing must change.',
  input_context: {
    spec: prep.spec,
    files: files.map(f => ({ path: f.path, content: f.content.slice(0, 4000) }))
  },
  models: prep.models,
  providers: prep.providers || {},
  required: false
};
return [{ json: {
  project_id: prep.project_id,
  attempt: prep.attempt,
  mode: prep.mode,
  with_integration: prep.with_integration && files.length > 0,
  has_files: files.length > 0,
  files,
  overrides,
  integration_call: integrationCall,
  dev_results: (par.results || []).map(r => ({ agent_id: r.agent_id, status: r.status, error: r.error }))
} }];
"""

MERGE_JS = r"""
const collected = $('Collect Files').first().json;
let files = collected.files;
let integrationSummary = null;
const incoming = $input.first().json;
if (incoming && incoming.agent_id === 'integration_agent' && incoming.output) {
  integrationSummary = { verdict: incoming.output.verdict || null, conflicts: incoming.output.conflicts || [] };
  if (Array.isArray(incoming.output.files)) {
    const map = new Map(files.map(f => [f.path, f.content]));
    for (const f of incoming.output.files) {
      if (f && typeof f.path === 'string' && typeof f.content === 'string') map.set(f.path, f.content);
    }
    files = [...map.entries()].map(([p, content]) => ({ path: p, content }));
  }
}
return [{ json: {
  project_id: collected.project_id,
  attempt: collected.attempt,
  mode: collected.mode,
  files,
  dev_results: collected.dev_results,
  integration_summary: integrationSummary,
  ces_body: { files }
} }];
"""

ARTIFACTS_DOC_JS = r"""
const merged = $('Merge Final Files').first().json;
const stored = $input.first().json;
const written = (stored && stored.written) || [];
const artifact_docs = written.map(w => ({
  project_id: merged.project_id, kind: 'source_file', path: w.path,
  size_bytes: Number(w.size_bytes) || 0, sha256: w.sha256 || null,
  created_at: new Date().toISOString()
}));
return [{ json: { artifact_docs, stored } }];
"""

CODEGEN_RESPONSE_JS = r"""
const merged = $('Merge Final Files').first().json;
const stored = $('Build Artifacts Docs').first().json.stored || {};
return [{ json: { response: {
  project_id: merged.project_id,
  attempt: merged.attempt,
  mode: merged.mode,
  files_stored: (stored.written || []).length,
  rejected: stored.rejected || [],
  file_paths: (stored.written || []).map(w => w.path),
  dev_results: merged.dev_results,
  integration: merged.integration_summary
} } }];
"""


def workflow_codegen():
    nodes = [
        sticky("## Code Generation\n"
               "Input: {project_id, mode, attempt, agents: [frontend_developer?, backend_developer?], "
               "with_integration, models, spec{...}, issues? (mode=fix)}\n"
               "Runs the developer agents in parallel (Workflow 3), lets the Integration Agent "
               "reconcile the file sets, then stores the final files in the Code Execution "
               "Service and records them as artifacts.", 0, 40),
        webhook("Webhook — Codegen", "ai-factory/codegen", 240, 320),
        code("Prepare Dev Calls", PREPARE_DEV_JS, 500, 320),
        http("Run Dev Agents (Parallel)", BASE + "parallel' }}",
             "={{ JSON.stringify($json.parallel_body) }}", 760, 320),
        code("Collect Files", COLLECT_JS, 1020, 320),
        if_node("Has Files?", bool_cond("={{ $json.has_files }}"), 1280, 320),
        respond("Respond — No Files",
                "={{ JSON.stringify({ project_id: $json.project_id, attempt: $json.attempt, files_stored: 0, error: 'developers_returned_no_files', dev_results: $json.dev_results }) }}",
                1540, 560),
        if_node("Integration Enabled?", bool_cond("={{ $json.with_integration }}"), 1540, 320),
        http("Call Integration Agent", BASE + "agent-execute' }}",
             "={{ JSON.stringify($json.integration_call) }}", 1800, 220),
        code("Merge Final Files", MERGE_JS, 2060, 320),
        http("Store Files in CES", CES + " + '/projects/' + $json.project_id + '/files' }}",
             "={{ JSON.stringify($json.ces_body) }}", 2320, 320),
        code("Build Artifacts Docs", ARTIFACTS_DOC_JS, 2580, 320),
        ces_db("Insert Artifacts (CES)", "/db/artifacts", "={{ JSON.stringify({ docs: $json.artifact_docs }) }}", 2840, 320),
        code("Build Response", CODEGEN_RESPONSE_JS, 3100, 320),
        respond("Respond — Codegen Result", "={{ JSON.stringify($json.response) }}", 3360, 320),
    ]
    conns = {}
    chain(conns, ["Webhook — Codegen", "Prepare Dev Calls", "Run Dev Agents (Parallel)",
                  "Collect Files", "Has Files?"])
    link(conns, "Has Files?", "Respond — No Files", output=1)
    link(conns, "Has Files?", "Integration Enabled?", output=0)
    link(conns, "Integration Enabled?", "Call Integration Agent", output=0)
    link(conns, "Integration Enabled?", "Merge Final Files", output=1)
    chain(conns, ["Call Integration Agent", "Merge Final Files", "Store Files in CES",
                  "Build Artifacts Docs", "Insert Artifacts (CES)", "Build Response",
                  "Respond — Codegen Result"])
    save("04-code-generation.json", "AI Factory — Code Generation", nodes, conns)


# =====================================================================
# Workflow 5 — QA and Review
# =====================================================================
QA_PREPARE_JS = r"""
const input = $input.first().json;
const body = input.body ?? input;
const cesBase = ($env.CODE_EXEC_URL || 'http://code-exec-service:8080').replace(/\/$/, '');
return [{ json: {
  project_id: body.project_id,
  attempt: body.attempt ?? 0,
  providers: body.providers || {},
  ces_url: `${cesBase}/projects/${body.project_id}/run`,
  ces_body: { steps: ['install', 'lint', 'test', 'build'] }
} }];
"""

QA_CALL_JS = r"""
const prep = $('Prepare QA Run').first().json;
const run = $input.first().json;
return [{ json: {
  project_id: prep.project_id, attempt: prep.attempt, run,
  agent_call: {
    project_id: prep.project_id,
    task_id: `${prep.project_id}-qa-${prep.attempt}`,
    agent_id: 'qa_engineer',
    task_description: 'Review the build/test results in your context: derive test cases from the project acceptance criteria, judge each build step, and list every issue with the agent who must fix it.',
    input_context: { build_results: run.results || [], build_ok: Boolean(run.build_ok) },
    providers: prep.providers || {},
    required: true
  }
} }];
"""

REVIEWER_CALL_JS = r"""
const prep = $('Prepare QA Run').first().json;
const qaStage = $('Build QA Call').first().json;
const qaResult = $input.first().json;
return [{ json: {
  project_id: prep.project_id, attempt: prep.attempt,
  agent_call: {
    project_id: prep.project_id,
    task_id: `${prep.project_id}-review-${prep.attempt}`,
    agent_id: 'code_reviewer',
    task_description: 'Review the project quality: structure, security, maintainability. Use the build results and the QA report in your context. Approve only when no critical or major issue remains.',
    input_context: { build_results: qaStage.run.results || [], build_ok: Boolean(qaStage.run.build_ok), qa_report: qaResult.output || null },
    providers: prep.providers || {},
    required: true
  }
} }];
"""

VERDICT_JS = ESC_JS + r"""
const prep = $('Prepare QA Run').first().json;
const run = $('Build QA Call').first().json.run;
const qaRes = $('Call QA Agent').first().json;
const revRes = $input.first().json;
const qa = (qaRes && qaRes.output) || {};
const rev = (revRes && revRes.output) || {};
const issues = [];
for (const i of [...(qa.issues || []), ...(rev.issues || [])]) {
  issues.push({ severity: i.severity || 'major', target_agent: i.target_agent || 'frontend_developer', description: i.description || '', file: i.file || '' });
}
if (!run.build_ok) {
  issues.push({ severity: 'critical', target_agent: 'frontend_developer', description: 'Build step failed in the sandbox — see build_results log tails.', file: '' });
}
const passed = Boolean(run.build_ok) && qa.verdict !== 'fail' && rev.verdict !== 'request_changes' && !issues.some(i => i.severity === 'critical');
const review_doc = {
  project_id: prep.project_id, attempt: Number(prep.attempt) || 0,
  build_ok: Boolean(run.build_ok), qa_verdict: qa.verdict || null,
  reviewer_verdict: rev.verdict || null, passed,
  issues, logs: run.results || [], created_at: new Date().toISOString()
};
return [{ json: {
  review_doc,
  response: {
    project_id: prep.project_id, attempt: prep.attempt, passed,
    build_ok: Boolean(run.build_ok),
    qa_verdict: qa.verdict || null, reviewer_verdict: rev.verdict || null,
    issues, build_results: run.results || []
  }
} }];
"""


def workflow_qa():
    nodes = [
        sticky("## QA and Review\n"
               "Input: {project_id, attempt}. Runs install/lint/test/build in the Code "
               "Execution Service sandbox, then QA Engineer and Code Reviewer agents judge "
               "the results. Output: {passed, issues[{severity, target_agent, ...}], ...}. "
               "The retry/fix loop itself lives in the Main Orchestrator.", 0, 40),
        webhook("Webhook — QA Review", "ai-factory/qa-review", 240, 320),
        code("Prepare QA Run", QA_PREPARE_JS, 500, 320),
        http("Run Build & Tests (CES)", "={{ $json.ces_url }}",
             "={{ JSON.stringify($json.ces_body) }}", 760, 320, timeout=1500000),
        code("Build QA Call", QA_CALL_JS, 1020, 320),
        http("Call QA Agent", BASE + "agent-execute' }}",
             "={{ JSON.stringify($json.agent_call) }}", 1280, 320),
        code("Build Reviewer Call", REVIEWER_CALL_JS, 1540, 320),
        http("Call Reviewer Agent", BASE + "agent-execute' }}",
             "={{ JSON.stringify($json.agent_call) }}", 1800, 320),
        code("Build Verdict", VERDICT_JS, 2060, 320),
        ces_db("Insert QA Review (CES)", "/db/reviews", "={{ JSON.stringify($json.review_doc) }}", 2320, 320),
        respond("Respond — QA Result",
                "={{ JSON.stringify($('Build Verdict').first().json.response) }}", 2580, 320),
    ]
    conns = {}
    chain(conns, ["Webhook — QA Review", "Prepare QA Run", "Run Build & Tests (CES)",
                  "Build QA Call", "Call QA Agent", "Build Reviewer Call",
                  "Call Reviewer Agent", "Build Verdict", "Insert QA Review (CES)",
                  "Respond — QA Result"])
    save("05-qa-and-review.json", "AI Factory — QA and Review", nodes, conns)


# =====================================================================
# Workflow 6 — ZIP Packaging
# =====================================================================
PKG_PREPARE_JS = r"""
const input = $input.first().json;
const body = input.body ?? input;
const cesBase = ($env.CODE_EXEC_URL || 'http://code-exec-service:8080').replace(/\/$/, '');
return [{ json: {
  project_id: body.project_id,
  ces_url: `${cesBase}/projects/${body.project_id}/package`,
  ces_body: {}
} }];
"""

PKG_UPDATE_JS = r"""
const prep = $('Prepare Package').first().json;
const pkg = $input.first().json;
const project_update = { project_id: prep.project_id, set: { zip_url: pkg.download_url || null } };
return [{ json: {
  project_update,
  response: {
    project_id: prep.project_id,
    download_url: pkg.download_url || null,
    file_count: pkg.file_count ?? null,
    size_bytes: pkg.size_bytes ?? null
  }
} }];
"""


def workflow_package():
    nodes = [
        sticky("## ZIP Packaging\n"
               "Input: {project_id}. Asks the Code Execution Service to zip the project "
               "workspace (node_modules, .git and .env files are always excluded), stores "
               "the download URL on the project and returns it.", 0, 40),
        webhook("Webhook — Package", "ai-factory/package", 240, 320),
        code("Prepare Package", PKG_PREPARE_JS, 500, 320),
        http("Package ZIP (CES)", "={{ $json.ces_url }}",
             "={{ JSON.stringify($json.ces_body) }}", 760, 320),
        code("Build Project Update", PKG_UPDATE_JS, 1020, 320),
        ces_db("Update Project (CES)", "/db/projects/update", "={{ JSON.stringify($json.project_update) }}", 1280, 320),
        respond("Respond — Package Result",
                "={{ JSON.stringify($('Build Project Update').first().json.response) }}", 1540, 320),
    ]
    conns = {}
    chain(conns, ["Webhook — Package", "Prepare Package", "Package ZIP (CES)",
                  "Build Project Update", "Update Project (CES)",
                  "Respond — Package Result"])
    save("06-zip-packaging.json", "AI Factory — ZIP Packaging", nodes, conns)


# =====================================================================
# Workflow 1 — Main Orchestrator
# =====================================================================
VALIDATE_JS = r"""
const input = $input.first().json;
const body = input.body ?? input;
const mode = ['full', 'module', 'existing'].includes(body.mode) ? body.mode : null;
const requirement = typeof body.requirement === 'string' ? body.requirement.trim() : '';
const errors = [];
if (!mode) errors.push('mode must be one of: full, module, existing');
if (!requirement) errors.push('requirement is required');
if (mode === 'module' && !String(body.module_name || '').trim()) errors.push('module_name is required for mode=module');
if (mode === 'existing' && !body.existing_zip_base64) errors.push('existing_zip_base64 is required for mode=existing');
return [{ json: {
  valid: errors.length === 0, errors,
  mode, requirement,
  module_name: body.module_name || null,
  project_name: body.project_name || null,
  models: body.models || {},
  providers: body.providers || {},
  existing_zip_base64: body.existing_zip_base64 || null
} }];
"""

PROJECT_DOC_JS = r"""
const v = $input.first().json;
const name = v.project_name || v.requirement.slice(0, 60);
const project_doc = {
  name, mode: v.mode, module_name: v.module_name, requirement: v.requirement,
  status: 'RUNNING', models: v.models, providers: v.providers,
  created_at: new Date().toISOString()
};
return [{ json: { ...v, project_doc } }];
"""

PM_CALL_JS = r"""
const project = $('Create Project (CES)').first().json;
const v = $('Validate Request').first().json;
let existingFiles = [];
try {
  const imp = $('Import Existing ZIP').first().json;
  existingFiles = (imp.written || []).map(w => w.path);
} catch { existingFiles = []; }
const modeNotes = {
  full: 'Plan the COMPLETE website described below: every page, feature and component. The plan must cover analysis, UX design, frontend and backend architecture, development, integration, QA and review.',
  module: `Plan ONLY the module "${v.module_name}" of a larger product: just the agents and tasks this module needs.`,
  existing: 'The user uploaded an EXISTING project (its file tree is in the context). Plan the minimal, surgical set of changes that satisfies the requirement. Never plan to delete or rewrite files outside the task scope.'
};
const agentCall = {
  project_id: project.id,
  task_id: `${project.id}-pm`,
  agent_id: 'project_manager',
  task_description: `${modeNotes[v.mode]}\n\nUSER REQUIREMENT:\n${v.requirement}`,
  input_context: { mode: v.mode, module_name: v.module_name, requirement: v.requirement, existing_files: existingFiles },
  models: v.models,
  providers: v.providers
};
return [{ json: { project_id: project.id, agent_call: agentCall } }];
"""

PARSE_PLAN_JS = ESC_JS + r"""
const pm = $input.first().json;
const plan = (pm && pm.output) || {};
const projectId = $('Build PM Call').first().json.project_id;
const v = $('Validate Request').first().json;
const ALL = ['project_manager', 'business_analyst', 'ui_ux_designer', 'frontend_architect', 'frontend_developer', 'backend_architect', 'backend_developer', 'integration_agent', 'qa_engineer', 'code_reviewer'];
let needed = (Array.isArray(plan.agents_needed) && plan.agents_needed.length)
  ? plan.agents_needed.filter(a => ALL.includes(a)) : [...ALL];
if (v.mode === 'full') needed = [...ALL];
for (const must of ['qa_engineer', 'code_reviewer']) if (!needed.includes(must)) needed.push(must);
const tasks = Array.isArray(plan.tasks) ? plan.tasks : [];
const task_docs = tasks.map(t => ({
  project_id: projectId, task_key: t.task_key || '', agent_id: t.agent_id || '',
  title: t.title || '', description: t.description || '', status: 'PENDING',
  depends_on: t.depends_on || [], created_at: new Date().toISOString()
}));
return [{ json: { project_id: projectId, plan_summary: plan.summary || '', plan_tasks: tasks, agents_needed: needed, task_docs } }];
"""

PHASE1_JS = r"""
const plan = $('Parse Plan').first().json;
const v = $('Validate Request').first().json;
const pm = $('Call Project Manager').first().json;
const DESCRIPTIONS = {
  business_analyst: 'Analyse the requirement and the PM plan: produce features, user stories and acceptance criteria.',
  ui_ux_designer: 'Design the sitemap, every page structure, the shared components and the complete design system for this project.'
};
const wanted = ['business_analyst', 'ui_ux_designer'].filter(a => plan.agents_needed.includes(a));
const calls = wanted.map(a => ({
  project_id: plan.project_id,
  task_id: `${plan.project_id}-${a}`,
  agent_id: a,
  task_description: DESCRIPTIONS[a],
  input_context: { requirement: v.requirement, mode: v.mode, module_name: v.module_name, pm_plan: pm.output || {} },
  models: v.models,
  providers: v.providers,
  required: true
}));
return [{ json: { project_id: plan.project_id, parallel_body: { project_id: plan.project_id, phase: 'analysis_design', calls } } }];
"""

PHASE2_JS = r"""
const plan = $('Parse Plan').first().json;
const v = $('Validate Request').first().json;
const pm = $('Call Project Manager').first().json;
const phase1 = $input.first().json;
const byAgent = {};
for (const r of phase1.results || []) byAgent[r.agent_id] = r.output || null;
const DESCRIPTIONS = {
  frontend_architect: 'Define the complete frontend architecture (Vite + React + Tailwind): folder structure, routes, components with props, state management — following the design system in your context.',
  backend_architect: 'Design the backend architecture: folder structure, database schema, the full REST API contract and the auth approach. If this project needs no backend, state that clearly.'
};
const CONTEXTS = {
  frontend_architect: { requirement: v.requirement, business: byAgent.business_analyst, design: byAgent.ui_ux_designer, pm_plan: pm.output || {} },
  backend_architect: { requirement: v.requirement, business: byAgent.business_analyst, design_summary: byAgent.ui_ux_designer ? byAgent.ui_ux_designer.design_system : null, pm_plan: pm.output || {} }
};
const wanted = ['frontend_architect', 'backend_architect'].filter(a => plan.agents_needed.includes(a));
const calls = wanted.map(a => ({
  project_id: plan.project_id,
  task_id: `${plan.project_id}-${a}`,
  agent_id: a,
  task_description: DESCRIPTIONS[a],
  input_context: CONTEXTS[a],
  models: v.models,
  providers: v.providers,
  required: true
}));
return [{ json: { project_id: plan.project_id, phase1_by_agent: byAgent, parallel_body: { project_id: plan.project_id, phase: 'architecture', calls } } }];
"""

CODEGEN_INPUT_JS = r"""
const plan = $('Parse Plan').first().json;
const v = $('Validate Request').first().json;
const pm = $('Call Project Manager').first().json;
const phase2 = $input.first().json;
const byAgent = {};
const phase1 = $('Run Phase 1 — BA + UX').first().json;
for (const r of phase1.results || []) byAgent[r.agent_id] = r.output || null;
for (const r of phase2.results || []) byAgent[r.agent_id] = r.output || null;
const devs = ['frontend_developer', 'backend_developer'].filter(a => plan.agents_needed.includes(a));
const codegen_input = {
  project_id: plan.project_id,
  mode: v.mode,
  module_name: v.module_name,
  attempt: 0,
  agents: devs,
  with_integration: plan.agents_needed.includes('integration_agent'),
  providers: v.providers,
  models: v.models,
  spec: {
    requirement: v.requirement,
    business: byAgent.business_analyst || null,
    design: byAgent.ui_ux_designer || null,
    frontend_arch: byAgent.frontend_architect || null,
    backend_arch: byAgent.backend_architect || null,
    pm_plan: pm.output || {}
  }
};
return [{ json: { project_id: plan.project_id, codegen_input } }];
"""

FIX_JS = r"""
const qa = $input.first().json;
const plan = $('Parse Plan').first().json;
const base = $('Build Codegen Input').first().json.codegen_input;
const targets = [...new Set((qa.issues || []).map(i => i.target_agent).filter(a => ['frontend_developer', 'backend_developer'].includes(a)))];
const codegen_input = {
  ...base,
  mode: 'fix',
  attempt: (qa.attempt ?? 0) + 1,
  agents: targets.length ? targets : base.agents,
  issues: qa.issues || []
};
return [{ json: { project_id: plan.project_id, codegen_input } }];
"""

FINAL_SUMMARY_JS = r"""
const qa = $input.first().json;
const plan = $('Parse Plan').first().json;
return [{ json: {
  project_id: plan.project_id,
  status: qa.passed ? 'COMPLETED' : 'COMPLETED_WITH_ISSUES',
  qa
} }];
"""

FINAL_UPDATE_JS = ESC_JS + r"""
const pkg = $input.first().json;
const fin = $('Final Summary').first().json;
const summary = {
  qa_passed: fin.qa.passed ?? null,
  qa_attempts: (fin.qa.attempt ?? 0) + 1,
  issues_remaining: fin.qa.issues || [],
  zip: { download_url: pkg.download_url || null, file_count: pkg.file_count ?? null, size_bytes: pkg.size_bytes ?? null }
};
const project_update = { project_id: fin.project_id, set: { status: fin.status, zip_url: pkg.download_url || null, summary } };
return [{ json: {
  project_update,
  response: {
    project_id: fin.project_id,
    status: fin.status,
    download_url: pkg.download_url || null,
    file_count: pkg.file_count ?? null,
    size_bytes: pkg.size_bytes ?? null,
    qa: { passed: fin.qa.passed ?? null, attempts: (fin.qa.attempt ?? 0) + 1, remaining_issues: fin.qa.issues || [] }
  }
} }];
"""


def workflow_main():
    x = 0

    def px(step):
        return 240 + step * 280

    nodes = [
        sticky("## Main Orchestrator — AI Agent Factory\n"
               "POST /webhook/ai-factory/start with {mode: full|module|existing, requirement, module_name?, "
               "project_name?, models?, existing_zip_base64?}.\n\n"
               "Pipeline: PM → (BA ∥ UI/UX) → (FE Architect ∥ BE Architect) → Code Generation "
               "(devs ∥ → Integration → store) → QA & Review → fix loop (max 2 extra rounds) → ZIP.\n"
               "Sub-workflows are called over their webhooks — **activate all 6 workflows** and create the "
               "no n8n credentials are needed — provider keys come from the environment (.env), and all data is stored in MongoDB via the Code Execution Service.", 0, 40, 720, 200),
        webhook("Webhook — Start", "ai-factory/start", px(0), 420),
        code("Validate Request", VALIDATE_JS, px(1), 420),
        if_node("Request Valid?", bool_cond("={{ $json.valid }}"), px(2), 420),
        respond("Respond — Invalid Request",
                "={{ JSON.stringify({ error: 'invalid_request', details: $json.errors }) }}", px(2), 700),
        code("Build Project Doc", PROJECT_DOC_JS, px(3), 420),
        ces_db("Create Project (CES)", "/db/projects", "={{ JSON.stringify($json.project_doc) }}", px(4), 420),
        if_node("Existing Project?",
                {"id": nid(), "leftValue": "={{ $json.mode }}", "rightValue": "existing",
                 "operator": {"type": "string", "operation": "equals"}}, px(5), 420),
        http("Import Existing ZIP", CES + " + '/projects/' + $json.id + '/import' }}",
             "={{ JSON.stringify({ zip_base64: $('Validate Request').first().json.existing_zip_base64 }) }}",
             px(5), 700),
        code("Build PM Call", PM_CALL_JS, px(6), 420),
        http("Call Project Manager", BASE + "agent-execute' }}",
             "={{ JSON.stringify($json.agent_call) }}", px(7), 420),
        code("Parse Plan", PARSE_PLAN_JS, px(8), 420),
        ces_db("Insert Tasks (CES)", "/db/tasks", "={{ JSON.stringify({ docs: $json.task_docs }) }}", px(9), 420),
        code("Build Phase 1 Calls", PHASE1_JS, px(10), 420),
        http("Run Phase 1 — BA + UX", BASE + "parallel' }}",
             "={{ JSON.stringify($json.parallel_body) }}", px(11), 420),
        code("Build Phase 2 Calls", PHASE2_JS, px(12), 420),
        http("Run Phase 2 — Architects", BASE + "parallel' }}",
             "={{ JSON.stringify($json.parallel_body) }}", px(13), 420),
        code("Build Codegen Input", CODEGEN_INPUT_JS, px(14), 420),
        http("Run Code Generation", BASE + "codegen' }}",
             "={{ JSON.stringify($json.codegen_input) }}", px(15), 420),
        http("Run QA & Review", BASE + "qa-review' }}",
             "={{ JSON.stringify({ project_id: $json.project_id, attempt: $json.attempt ?? 0, providers: $('Validate Request').first().json.providers || {} }) }}",
             px(16), 420, timeout=1500000),
        if_node("QA Passed?", bool_cond("={{ $json.passed }}"), px(17), 420),
        if_node("Fix Attempts Left?",
                {"id": nid(), "leftValue": "={{ $json.attempt }}", "rightValue": 2,
                 "operator": {"type": "number", "operation": "smaller"}}, px(17), 700),
        code("Build Fix Round", FIX_JS, px(16), 980),
        code("Final Summary", FINAL_SUMMARY_JS, px(18), 420),
        http("Package ZIP", BASE + "package' }}",
             "={{ JSON.stringify({ project_id: $json.project_id }) }}", px(19), 420),
        code("Build Final Update", FINAL_UPDATE_JS, px(20), 420),
        ces_db("Update Project (CES)", "/db/projects/update", "={{ JSON.stringify($json.project_update) }}", px(21), 420),
        respond("Respond — Result",
                "={{ JSON.stringify($('Build Final Update').first().json.response) }}", px(22), 420),
    ]
    conns = {}
    chain(conns, ["Webhook — Start", "Validate Request", "Request Valid?"])
    link(conns, "Request Valid?", "Respond — Invalid Request", output=1)
    link(conns, "Request Valid?", "Build Project Doc", output=0)
    chain(conns, ["Build Project Doc", "Create Project (CES)", "Existing Project?"])
    link(conns, "Existing Project?", "Import Existing ZIP", output=0)
    link(conns, "Existing Project?", "Build PM Call", output=1)
    link(conns, "Import Existing ZIP", "Build PM Call")
    chain(conns, ["Build PM Call", "Call Project Manager", "Parse Plan",
                  "Insert Tasks (CES)", "Build Phase 1 Calls", "Run Phase 1 — BA + UX",
                  "Build Phase 2 Calls", "Run Phase 2 — Architects", "Build Codegen Input",
                  "Run Code Generation", "Run QA & Review", "QA Passed?"])
    link(conns, "QA Passed?", "Final Summary", output=0)
    link(conns, "QA Passed?", "Fix Attempts Left?", output=1)
    link(conns, "Fix Attempts Left?", "Build Fix Round", output=0)
    link(conns, "Fix Attempts Left?", "Final Summary", output=1)
    link(conns, "Build Fix Round", "Run Code Generation")
    chain(conns, ["Final Summary", "Package ZIP", "Build Final Update",
                  "Update Project (CES)", "Respond — Result"])
    save("01-main-orchestrator.json", "AI Factory — Main Orchestrator", nodes, conns)


if __name__ == "__main__":
    workflow_agent_execution()
    workflow_parallel()
    workflow_codegen()
    workflow_qa()
    workflow_package()
    workflow_main()
