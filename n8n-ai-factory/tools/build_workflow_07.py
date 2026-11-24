#!/usr/bin/env python3
"""Generate workflow 07 — 7-Agent Dynamic Model Routing — as importable n8n JSON.

Implements ai-7-agent-dynamic-model-routing.md:
- 7 logical roles: AI Leader, AI Planner, AI Architect, AI Developer,
  AI Tester, AI Reviewer, AI Researcher. No role is hard-locked to a model.
- Model Capability Registry: only models whose provider key exists in the
  n8n environment ($env GROQ_API_KEY / OLLAMA_API_KEY / OPENROUTER_API_KEY)
  are marked available. No key value ever appears in the JSON.
- Model Router: validates the Leader's per-task model choices against the
  registry and reassigns deterministically by capability/complexity when a
  choice is missing, unavailable or capability-mismatched. Choices, reasons,
  fallbacks and durations are recorded per task.
- Review gate with at most 2 revision rounds; roles the plan does not need
  are reported as skipped with a reason.
"""
import json
import os
import uuid

OUT = os.environ.get("FACTORY_OUT") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "workflows")


def node(name, ntype, type_version, parameters, x, y, **extra):
    n = {"parameters": parameters, "id": str(uuid.uuid4()), "name": name,
         "type": ntype, "typeVersion": type_version, "position": [x, y]}
    n.update(extra)
    return n


def code(name, js, x, y):
    return node(name, "n8n-nodes-base.code", 2,
                {"mode": "runOnceForAllItems", "jsCode": js}, x, y)


def http(name, x, y):
    return node(name, "n8n-nodes-base.httpRequest", 4.2,
                {"method": "POST", "url": "={{ $json.api_url }}",
                 "sendHeaders": True,
                 "headerParameters": {"parameters": [
                     {"name": "Authorization", "value": "={{ $json.auth_header }}"},
                     {"name": "Content-Type", "value": "application/json"}]},
                 "sendBody": True, "contentType": "json", "specifyBody": "json",
                 "jsonBody": "={{ JSON.stringify($json.provider_body) }}",
                 "options": {"timeout": 600000}},
                x, y, retryOnFail=True, maxTries=2, waitBetweenTries=5000,
                onError="continueRegularOutput")


def if_node(name, json_key, x, y):
    return node(name, "n8n-nodes-base.if", 2.2,
                {"conditions": {"options": {"caseSensitive": True, "leftValue": "",
                                            "typeValidation": "loose", "version": 2},
                                "conditions": [{"id": "c1", "leftValue": f"={{{{ ${json_key} }}}}",
                                                "rightValue": True,
                                                "operator": {"type": "boolean", "operation": "true",
                                                             "singleValue": True}}],
                                "combinator": "and"},
                 "options": {}}, x, y)


def chain(workflow, *names):
    for a, b in zip(names, names[1:]):
        workflow["connections"].setdefault(a, {"main": [[]]})
        workflow["connections"][a]["main"][0].append(
            {"node": b, "type": "main", "index": 0})


def connect(workflow, src, dst, output_index=0, input_index=0):
    entry = workflow["connections"].setdefault(src, {"main": [[]]})
    while len(entry["main"]) <= output_index:
        entry["main"].append([])
    entry["main"][output_index].append(
        {"node": dst, "type": "main", "index": input_index})


def sticky(text, x, y, width=620, height=240):
    return {"parameters": {"content": text, "height": height, "width": width},
            "id": str(uuid.uuid4()), "name": "Sticky Note",
            "type": "n8n-nodes-base.stickyNote", "typeVersion": 1,
            "position": [x, y]}


# --------------------------------------------------------------------------
# Shared JS snippets
# --------------------------------------------------------------------------

PROVIDERS_JS = r"""
const PROVIDERS = {
  groq: { url: 'https://api.groq.com/openai/v1/chat/completions', env_key: 'GROQ_API_KEY' },
  ollama: { url: 'https://ollama.com/v1/chat/completions', env_key: 'OLLAMA_API_KEY' },
  openrouter: { url: 'https://openrouter.ai/api/v1/chat/completions', env_key: 'OPENROUTER_API_KEY' }
};
function providerCall(provider, model, systemPrompt, userContent, maxTokens) {
  const prov = PROVIDERS[provider];
  const key = $env[prov.env_key] || '';
  return {
    api_url: prov.url,
    auth_header: 'Bearer ' + key,
    provider_body: {
      model,
      messages: [
        { role: 'system', content: systemPrompt },
        { role: 'user', content: userContent }
      ],
      max_tokens: maxTokens || 8192,
      temperature: 0.3
    }
  };
}
"""

EXTRACT_JS = r"""
function extractJson(text) {
  if (typeof text !== 'string') return null;
  let t = text.trim();
  const fence = t.match(/```(?:json)?\s*([\s\S]*?)```/);
  if (fence) t = fence[1].trim();
  try { return JSON.parse(t); } catch (e) { /* fall through */ }
  const start = t.indexOf('{');
  if (start === -1) return null;
  let depth = 0, inStr = false, esc = false;
  for (let i = start; i < t.length; i++) {
    const ch = t[i];
    if (inStr) {
      if (esc) esc = false;
      else if (ch === '\\') esc = true;
      else if (ch === '"') inStr = false;
    } else if (ch === '"') inStr = true;
    else if (ch === '{') depth++;
    else if (ch === '}') {
      depth--;
      if (depth === 0) {
        try { return JSON.parse(t.slice(start, i + 1)); } catch (e) { return null; }
      }
    }
  }
  return null;
}
function responseText(item) {
  const j = item.json || {};
  if (j.error) return null;
  const choices = j.choices;
  if (Array.isArray(choices) && choices.length) {
    const msg = choices[0].message || {};
    if (typeof msg.content === 'string' && msg.content.trim()) return msg.content;
    if (Array.isArray(msg.content)) {
      const text = msg.content.filter(p => p && p.type === 'text').map(p => p.text).join('');
      if (text.trim()) return text;
    }
  }
  return null;
}
"""

REGISTRY_JS = r"""
const has = (k) => Boolean($env[k] && String($env[k]).trim());
function entry(provider, model_id, capabilities, strength, cost_rank, extra) {
  const envKey = provider === 'groq' ? 'GROQ_API_KEY' : provider === 'ollama' ? 'OLLAMA_API_KEY' : 'OPENROUTER_API_KEY';
  return Object.assign({
    provider, model_id,
    credential_name: 'env:' + envKey,
    capabilities, strength, cost_rank,
    context_limit: null, supports_tools: null,
    status: has(envKey) ? 'available' : 'unavailable'
  }, extra || {});
}
// Only models of providers that are actually configured can be available.
// Claude/GPT/DeepSeek direct APIs are NOT assumed: they appear only via
// OpenRouter, and only when OPENROUTER_API_KEY is set.
const registry = [
  entry('groq', 'openai/gpt-oss-120b', ['reasoning', 'planning', 'architecture', 'review', 'research', 'general', 'coding'], 3, 1, { context_limit: 131072, supports_tools: true }),
  entry('groq', 'openai/gpt-oss-20b', ['reasoning', 'planning', 'general', 'coding', 'writing', 'testing', 'fast', 'extraction'], 2, 1, { context_limit: 131072, supports_tools: true }),
  entry('ollama', 'gpt-oss:120b', ['reasoning', 'planning', 'architecture', 'review', 'general'], 3, 2, { supports_tools: true }),
  entry('ollama', 'qwen3-coder:480b', ['coding', 'testing', 'debugging'], 3, 2, { supports_tools: true }),
  entry('ollama', 'deepseek-v3.1:671b', ['reasoning', 'review', 'research', 'architecture'], 3, 3, {}),
  entry('ollama', 'gpt-oss:20b', ['general', 'fast', 'writing', 'extraction'], 2, 2, { supports_tools: true }),
  entry('openrouter', 'anthropic/claude-sonnet-4.5', ['coding', 'reasoning', 'architecture', 'review', 'writing', 'testing'], 3, 3, {}),
  entry('openrouter', 'openai/gpt-5', ['reasoning', 'coding', 'planning', 'architecture', 'review', 'research', 'general'], 3, 3, {}),
  entry('openrouter', 'deepseek/deepseek-r1', ['reasoning', 'review', 'research'], 3, 2, {})
];
const available = registry.filter(m => m.status === 'available');
const body = $input.first().json.body || {};
const projectId = 'proj-' + Date.now() + '-' + Math.floor(Math.random() * 100000);
const sd = $getWorkflowStaticData('global');
sd.project_id = projectId;
sd.requirement = body.requirement || '';
sd.domain_hint = body.domain || [];
sd.expected_outputs = body.expected_outputs || [];
sd.constraints = body.constraints || [];
sd.documents = body.documents || [];
// Optional per-role agent assignments sent by MindFlow (AI Factory page):
// body.agents = { "AI Leader": {name, provider, model, system_prompt}, ... }.
// An assignment applies only when its provider is known AND that provider's
// key exists in the n8n environment; otherwise it is reported as ignored so
// the caller sees why their agent did not run. Only the PRESENCE of the
// provider env key is checked here — key values never enter the workflow.
const ROLE_NAMES = ['AI Leader', 'AI Planner', 'AI Architect', 'AI Developer', 'AI Tester', 'AI Reviewer', 'AI Researcher'];
const PROVIDER_ENV = { groq: 'GROQ_API_KEY', ollama: 'OLLAMA_API_KEY', openrouter: 'OPENROUTER_API_KEY' };
const rawAgents = (body.agents && typeof body.agents === 'object' && !Array.isArray(body.agents)) ? body.agents : {};
const overrides = {};
const overridesIgnored = [];
for (const role of ROLE_NAMES) {
  const a = rawAgents[role];
  if (!a || typeof a !== 'object') continue;
  const provider = String(a.provider || '').toLowerCase();
  const model = String(a.model || '').trim();
  const agentName = String(a.name || role).slice(0, 120);
  if (!PROVIDER_ENV[provider] || !model) {
    overridesIgnored.push({ role, agent_name: agentName, reason: 'invalid_provider_or_model' });
    continue;
  }
  if (!has(PROVIDER_ENV[provider])) {
    overridesIgnored.push({ role, agent_name: agentName, reason: 'provider_not_configured_in_n8n_env:' + PROVIDER_ENV[provider] });
    continue;
  }
  overrides[role] = {
    agent_name: agentName, provider, model,
    system_prompt: typeof a.system_prompt === 'string' ? a.system_prompt.slice(0, 8000) : ''
  };
}
sd.agent_overrides = overrides;
sd.agent_overrides_ignored = overridesIgnored;
sd.registry = registry;
sd.results = [];
sd.review = null;
sd.revision_rounds = 0;
sd.started_ms = Date.now();
return [{ json: {
  project_id: projectId,
  requirement: sd.requirement,
  domain_hint: sd.domain_hint,
  expected_outputs: sd.expected_outputs,
  constraints: sd.constraints,
  documents: sd.documents,
  has_available_model: available.length > 0,
  available_models: available
} }];
"""

PREPARE_LEADER_JS = PROVIDERS_JS + r"""
function rankModels(models, cap, complexity) {
  return models.filter(m => m.capabilities.includes(cap)).slice().sort((a, b) =>
    complexity === 'low'
      ? (a.cost_rank - b.cost_rank) || (a.strength - b.strength)
      : (b.strength - a.strength) || (a.cost_rank - b.cost_rank));
}
const input = $input.first().json;
const available = input.available_models || [];
let pick = rankModels(available, 'planning', 'high')[0]
  || rankModels(available, 'reasoning', 'high')[0]
  || rankModels(available, 'general', 'high')[0]
  || available[0];
if (!pick) return [{ json: { has_available_model: false, project_id: input.project_id } }];
const sdPre = $getWorkflowStaticData('global');
const leaderOverride = (sdPre.agent_overrides || {})['AI Leader'] || null;
if (leaderOverride) {
  pick = { provider: leaderOverride.provider, model_id: leaderOverride.model, capabilities: [], strength: 3, cost_rank: 1 };
}
const promptParts = [
  'You are the AI Leader and AI Planner of a 7-role AI team. Roles: AI Leader, AI Planner, AI Architect, AI Developer, AI Tester, AI Reviewer, AI Researcher.',
  'Analyse the user requirement, decide its domain(s) (software, research, business, marketing, education, office, creative, mixed — do NOT force everything into a software project), and produce a task plan.',
  'Rules:',
  '- Use only roles that are needed; a role may own several tasks; never create circular dependencies.',
  '- For every task choose provider + model_id ONLY from the AVAILABLE MODELS list below; copy the ids exactly. If no available model fits a task, set its model_selection to null and its status to "needs_configuration".',
  '- Prefer strong coding models for complex code, strong reasoning models for planning/architecture/review, fast cheap models for simple extraction/formatting tasks.',
  '- The Reviewer should use a different model than the Developer when the list allows it.',
  'Respond with ONLY this JSON (no markdown, no commentary):',
  '{"project_id":"' + input.project_id + '","project_summary":"...","domain":["..."],"expected_outputs":["..."],"assumptions":[],"tasks":[{"task_id":"task-1","role":"AI Researcher","objective":"...","instructions":"...","task_type":"research|planning|architecture|coding|testing|review|writing|extraction|general","domain":["..."],"input_from":[],"depends_on":[],"model_selection":{"provider":"groq","model_id":"...","reason":"...","fallback":[]},"complexity":"low|medium|high","priority":"low|medium|high","acceptance_criteria":["..."],"output_format":"json","status":"planned"}]}',
  'AVAILABLE MODELS (registry): ' + JSON.stringify(available)
];
if (leaderOverride && leaderOverride.system_prompt) {
  promptParts.unshift('The user assigned their own MindFlow agent "' + leaderOverride.agent_name + '" to lead this team. Its instructions:\n' + leaderOverride.system_prompt);
}
const assignments = sdPre.agent_overrides || {};
const assignedRoles = Object.keys(assignments);
if (assignedRoles.length) {
  promptParts.push('FIXED AGENT ASSIGNMENTS from MindFlow (the router will honor these provider/model choices per role; plan tasks for these roles normally): ' + JSON.stringify(assignedRoles.map(r => ({ role: r, agent: assignments[r].agent_name, provider: assignments[r].provider, model: assignments[r].model }))));
}
const systemPrompt = promptParts.join('\n');
const userContent = [
  'REQUIREMENT: ' + (input.requirement || ''),
  input.domain_hint && input.domain_hint.length ? 'DOMAIN HINT: ' + JSON.stringify(input.domain_hint) : '',
  input.expected_outputs && input.expected_outputs.length ? 'EXPECTED OUTPUTS: ' + JSON.stringify(input.expected_outputs) : '',
  input.constraints && input.constraints.length ? 'CONSTRAINTS: ' + JSON.stringify(input.constraints) : '',
  input.documents && input.documents.length ? 'DOCUMENTS: ' + JSON.stringify(input.documents).slice(0, 12000) : ''
].filter(Boolean).join('\n');
const call = providerCall(pick.provider, pick.model_id, systemPrompt, userContent, 8192);
const sd = $getWorkflowStaticData('global');
sd.leader_selection = { provider: pick.provider, model_id: pick.model_id };
return [{ json: Object.assign({ project_id: input.project_id, has_available_model: true, leader_selection: sd.leader_selection }, call) }];
"""

NO_MODEL_JS = r"""
const input = $input.first().json;
const sd = $getWorkflowStaticData('global');
return [{ json: {
  project_id: input.project_id || sd.project_id || null,
  status: 'needs_configuration',
  error: 'no_available_model: no provider key is configured in the n8n environment. Set GROQ_API_KEY and/or OLLAMA_API_KEY (or OPENROUTER_API_KEY) in the .env file next to docker-compose.yml, restart n8n, and run again.',
  model_registry: sd.registry || [],
  task_results: [],
  review: null,
  final: null
} }];
"""

PARSE_PLAN_JS = EXTRACT_JS + r"""
const ROLES = ['AI Leader', 'AI Planner', 'AI Architect', 'AI Developer', 'AI Tester', 'AI Reviewer', 'AI Researcher'];
const CAP_FOR_ROLE = {
  'AI Leader': 'reasoning', 'AI Planner': 'planning', 'AI Architect': 'architecture',
  'AI Developer': 'coding', 'AI Tester': 'testing', 'AI Reviewer': 'review', 'AI Researcher': 'research'
};
function rankModels(models, cap, complexity) {
  return models.filter(m => m.capabilities.includes(cap)).slice().sort((a, b) =>
    complexity === 'low'
      ? (a.cost_rank - b.cost_rank) || (a.strength - b.strength)
      : (b.strength - a.strength) || (a.cost_rank - b.cost_rank));
}
function rankedFor(models, cap, complexity) {
  let ranked = rankModels(models, cap, complexity);
  if (!ranked.length) ranked = rankModels(models, 'general', complexity);
  return ranked;
}
function inferCap(task) {
  const tt = String(task.task_type || '').toLowerCase();
  if (/extract|classif|normal|format/.test(tt)) return 'fast';
  let cap = CAP_FOR_ROLE[task.role] || 'general';
  const dom = ((task.domain || []).join(' ') + ' ' + tt).toLowerCase();
  if (cap === 'coding' && /(marketing|content|education|business|office|writing|seo)/.test(dom) && !/(code|software|website|web|app|api|debug)/.test(dom)) return 'writing';
  return cap;
}
const item = $input.first();
const sd = $getWorkflowStaticData('global');
const available = (sd.registry || []).filter(m => m.status === 'available');
const text = responseText(item);
const plan = text ? extractJson(text) : null;
if (!plan || !Array.isArray(plan.tasks) || !plan.tasks.length) {
  sd.plan = null;
  sd.plan_error = 'leader_did_not_return_valid_plan';
  sd.skipped_roles = ROLES.map(r => ({ role: r, status: 'skipped', reason: 'plan_failed' }));
  return [{ json: { task: { task_id: 'plan', role: 'AI Leader', objective: 'Produce the team plan', status: 'failed', model_selection: null } } }];
}
const byKey = {};
for (const m of available) byKey[m.provider + '::' + m.model_id] = m;
const tasks = [];
plan.tasks.forEach((raw, i) => {
  const role = ROLES.includes(raw.role) ? raw.role : 'AI Developer';
  const task = {
    task_id: String(raw.task_id || ('task-' + (i + 1))),
    role,
    objective: String(raw.objective || ''),
    instructions: String(raw.instructions || ''),
    task_type: String(raw.task_type || ''),
    domain: Array.isArray(raw.domain) ? raw.domain : (Array.isArray(plan.domain) ? plan.domain : []),
    depends_on: Array.isArray(raw.depends_on) ? raw.depends_on.map(String) : [],
    complexity: ['low', 'medium', 'high'].includes(raw.complexity) ? raw.complexity : 'medium',
    priority: raw.priority || 'medium',
    acceptance_criteria: Array.isArray(raw.acceptance_criteria) ? raw.acceptance_criteria : [],
    output_format: raw.output_format || 'json',
    status: 'planned'
  };
  const cap = inferCap(task);
  const ranked = rankedFor(available, cap, task.complexity);
  const leaderSel = raw.model_selection || null;
  const leaderEntry = leaderSel ? byKey[leaderSel.provider + '::' + leaderSel.model_id] : null;
  const override = (sd.agent_overrides || {})[role] || null;
  if (override) {
    task.model_selection = {
      provider: override.provider, model_id: override.model,
      reason: 'mindflow_agent_assignment:' + override.agent_name,
      fallback: ranked.filter(m => !(m.provider === override.provider && m.model_id === override.model)).slice(0, 2)
        .map(m => ({ provider: m.provider, model_id: m.model_id }))
    };
  } else if (!ranked.length && !leaderEntry) {
    task.status = 'needs_configuration';
    task.model_selection = null;
    task.router_note = 'no_available_model_for_capability:' + cap;
  } else if (leaderEntry && leaderEntry.capabilities.includes(cap)) {
    task.model_selection = {
      provider: leaderEntry.provider, model_id: leaderEntry.model_id,
      reason: leaderSel.reason || 'leader_choice_validated_by_router',
      fallback: ranked.filter(m => m.model_id !== leaderEntry.model_id).slice(0, 2)
        .map(m => ({ provider: m.provider, model_id: m.model_id }))
    };
  } else {
    const chosen = ranked[0];
    task.model_selection = {
      provider: chosen.provider, model_id: chosen.model_id,
      reason: leaderEntry
        ? 'router_reassigned: leader choice unavailable or capability mismatch for ' + cap
        : 'router_assigned: capability ' + cap + ', complexity ' + task.complexity,
      fallback: ranked.slice(1, 3).map(m => ({ provider: m.provider, model_id: m.model_id }))
    };
  }
  tasks.push(task);
});
// Topological order by depends_on (unknown deps ignored); cycle -> keep plan order.
const order = [];
const placed = new Set();
let guard = 0;
let remaining = tasks.slice();
while (remaining.length && guard++ < 50) {
  const ready = remaining.filter(t => t.depends_on.every(d => placed.has(d) || !tasks.some(x => x.task_id === d)));
  if (!ready.length) { order.push(...remaining); sd.plan_warning = 'dependency_cycle_or_unresolvable_order'; break; }
  for (const t of ready) { order.push(t); placed.add(t.task_id); }
  remaining = remaining.filter(t => !placed.has(t.task_id));
}
const usedRoles = new Set(tasks.map(t => t.role));
sd.plan = { project_id: plan.project_id || sd.project_id, project_summary: plan.project_summary || '', domain: plan.domain || [], expected_outputs: plan.expected_outputs || [], assumptions: plan.assumptions || [], tasks: order };
sd.skipped_roles = ROLES.filter(r => !usedRoles.has(r)).map(r => ({ role: r, status: 'skipped', reason: 'not_required_by_plan' }));
return order.map(t => ({ json: { task: t } }));
"""

PREPARE_TASK_JS = PROVIDERS_JS + r"""
const ROLE_PROMPTS = {
  'AI Leader': 'You are the AI Leader handling a coordination/synthesis task for the team.',
  'AI Planner': 'You are the AI Planner: decompose goals into concrete, verifiable steps with dependencies and acceptance criteria.',
  'AI Architect': 'You are the AI Architect: design the solution, structure or method that best fits the task domain — not only software.',
  'AI Developer': 'You are the AI Developer/Executor: produce the actual deliverable of the task in its domain. For software tasks write the code; for other domains produce the professional artifact itself (document, content, analysis, plan).',
  'AI Tester': 'You are the AI Tester/Validator: check the referenced work against its acceptance criteria. Never claim you ran tools or tests you did not actually run; label reasoning-based checks as such.',
  'AI Reviewer': 'You are the AI Reviewer: independently challenge correctness, completeness, consistency, risks and usability of the referenced work.',
  'AI Researcher': 'You are the AI Researcher: research from the provided context. Separate facts, inferences and assumptions; never invent sources.'
};
const RESULT_CONTRACT = 'Respond with ONLY this JSON (no markdown): {"project_id":"...","task_id":"...","role":"...","provider":"...","model_id":"...","status":"completed|failed|needs_human_input","summary":"...","deliverables":[],"evidence":[],"assumptions":[],"risks":[],"handoff":{"to_role":"...","notes":"..."},"needs_human_input":false}';
const task = $input.first().json.task;
const sd = $getWorkflowStaticData('global');
if (!task.model_selection || task.status === 'needs_configuration' || task.status === 'failed') {
  return [{ json: { skip_call: true, task } }];
}
const results = sd.results || [];
const depResults = results.filter(r => (task.depends_on || []).includes(r.task_id));
const taskOverride = (sd.agent_overrides || {})[task.role] || null;
const persona = taskOverride && taskOverride.system_prompt
  ? taskOverride.system_prompt
  : (ROLE_PROMPTS[task.role] || ROLE_PROMPTS['AI Developer']);
const systemPrompt = persona + '\n' + RESULT_CONTRACT;
const userContent = [
  'PROJECT: ' + (sd.plan ? sd.plan.project_summary || '' : '') + ' (requirement: ' + (sd.requirement || '') + ')',
  'TASK ' + task.task_id + ' — ' + task.role,
  'OBJECTIVE: ' + task.objective,
  task.instructions ? 'INSTRUCTIONS: ' + task.instructions : '',
  task.acceptance_criteria && task.acceptance_criteria.length ? 'ACCEPTANCE CRITERIA: ' + JSON.stringify(task.acceptance_criteria) : '',
  depResults.length ? 'INPUT FROM DEPENDENCY TASKS: ' + JSON.stringify(depResults.map(r => ({ task_id: r.task_id, role: r.role, summary: r.summary, deliverables: r.deliverables }))).slice(0, 8000) : '',
  'Your provider is ' + task.model_selection.provider + ' and your model_id is ' + task.model_selection.model_id + '; project_id is ' + sd.project_id + ', task_id is ' + task.task_id + ', role is ' + task.role + '.'
].filter(Boolean).join('\n');
const call = providerCall(task.model_selection.provider, task.model_selection.model_id, systemPrompt, userContent, 8192);
return [{ json: Object.assign({ skip_call: false, task, started_ms: Date.now() }, call) }];
"""

MAKE_SKIPPED_JS = r"""
const task = $input.first().json.task;
const sd = $getWorkflowStaticData('global');
const status = task.status === 'failed' ? 'failed' : 'needs_configuration';
return [{ json: { task, result: {
  project_id: sd.project_id, task_id: task.task_id, role: task.role,
  provider: task.model_selection ? task.model_selection.provider : null,
  model_id: task.model_selection ? task.model_selection.model_id : null,
  model_reason: task.router_note || null,
  status,
  summary: status === 'failed' ? 'The Leader did not return a valid plan.' : 'No available model fits this task. Configure the missing provider and re-run.',
  deliverables: [], evidence: [], assumptions: [], risks: [],
  handoff: { to_role: 'AI Leader', notes: '' },
  needs_human_input: status === 'needs_configuration',
  duration_ms: 0
} } }];
"""

PARSE_TASK_JS = EXTRACT_JS + PROVIDERS_JS + r"""
const prep = $('Prepare Task Call').first().json;
const task = prep.task;
const item = $input.first();
const text = responseText(item);
const parsed = text ? extractJson(text) : null;
const sd = $getWorkflowStaticData('global');
function normalize(p, providerUsed, modelUsed) {
  return {
    project_id: sd.project_id, task_id: task.task_id, role: task.role,
    provider: providerUsed, model_id: modelUsed,
    model_reason: task.model_selection ? task.model_selection.reason : null,
    status: ['completed', 'failed', 'needs_human_input'].includes(p && p.status) ? p.status : 'completed',
    summary: (p && p.summary) || '',
    deliverables: (p && p.deliverables) || [],
    evidence: (p && p.evidence) || [],
    assumptions: (p && p.assumptions) || [],
    risks: (p && p.risks) || [],
    handoff: (p && p.handoff) || { to_role: 'AI Leader', notes: '' },
    needs_human_input: Boolean(p && p.needs_human_input),
    duration_ms: Date.now() - (prep.started_ms || Date.now())
  };
}
if (parsed) {
  return [{ json: { task, result: normalize(parsed, task.model_selection.provider, task.model_selection.model_id) } }];
}
const fb = task.model_selection && Array.isArray(task.model_selection.fallback) ? task.model_selection.fallback[0] : null;
if (fb && PROVIDERS[fb.provider] && ($env[PROVIDERS[fb.provider].env_key] || '')) {
  const retryPrep = $('Prepare Task Call').first().json;
  const messages = retryPrep.provider_body.messages;
  const call = providerCall(fb.provider, fb.model_id, messages[0].content, messages[1].content, 8192);
  return [{ json: Object.assign({ task, needs_fallback: true, first_error: 'provider_error_or_invalid_output' }, call) }];
}
return [{ json: { task, result: {
  project_id: sd.project_id, task_id: task.task_id, role: task.role,
  provider: task.model_selection.provider, model_id: task.model_selection.model_id,
  model_reason: task.model_selection.reason,
  status: 'failed', summary: 'Provider error or the model did not return valid JSON, and no fallback model is available.',
  deliverables: [], evidence: [], assumptions: [], risks: [],
  handoff: { to_role: 'AI Leader', notes: '' }, needs_human_input: false,
  duration_ms: Date.now() - (prep.started_ms || Date.now())
} } }];
"""

PARSE_FALLBACK_JS = EXTRACT_JS + r"""
const prep = $('Parse Task Result').first().json;
const task = prep.task;
const item = $input.first();
const text = responseText(item);
const parsed = text ? extractJson(text) : null;
const sd = $getWorkflowStaticData('global');
const fb = task.model_selection.fallback[0];
return [{ json: { task, result: {
  project_id: sd.project_id, task_id: task.task_id, role: task.role,
  provider: fb.provider, model_id: fb.model_id,
  model_reason: (task.model_selection.reason || '') + ' [fallback used after primary model failed]',
  status: parsed ? (['completed', 'failed', 'needs_human_input'].includes(parsed.status) ? parsed.status : 'completed') : 'failed',
  summary: parsed ? (parsed.summary || '') : 'Fallback model also failed or returned invalid output.',
  deliverables: parsed ? (parsed.deliverables || []) : [],
  evidence: parsed ? (parsed.evidence || []) : [],
  assumptions: parsed ? (parsed.assumptions || []) : [],
  risks: parsed ? (parsed.risks || []) : [],
  handoff: parsed ? (parsed.handoff || { to_role: 'AI Leader', notes: '' }) : { to_role: 'AI Leader', notes: '' },
  needs_human_input: parsed ? Boolean(parsed.needs_human_input) : false,
  duration_ms: 0
} } }];
"""

RECORD_JS = r"""
const input = $input.first().json;
const sd = $getWorkflowStaticData('global');
sd.results = sd.results || [];
if (input.result) sd.results.push(input.result);
return [{ json: {} }];
"""

PREPARE_REVIEW_JS = PROVIDERS_JS + r"""
function rankModels(models, cap) {
  return models.filter(m => m.capabilities.includes(cap)).slice()
    .sort((a, b) => (b.strength - a.strength) || (a.cost_rank - b.cost_rank));
}
const sd = $getWorkflowStaticData('global');
const available = (sd.registry || []).filter(m => m.status === 'available');
const results = sd.results || [];
const completed = results.filter(r => r.status === 'completed');
if (!completed.length) {
  sd.review = { status: 'needs_configuration', score: 0, issues: ['no_task_completed'], missing_requirements: [], contradictions: [], unsupported_claims: [], required_revisions: [], final_notes: ['No task completed, so there is nothing to review.'] };
  return [{ json: { skip_review: true } }];
}
// Prefer a reviewer model different from the most used executor model.
const freq = {};
for (const r of completed) { const k = r.provider + '::' + r.model_id; freq[k] = (freq[k] || 0) + 1; }
const dominant = Object.keys(freq).sort((a, b) => freq[b] - freq[a])[0];
let ranked = rankModels(available, 'review');
const different = ranked.filter(m => (m.provider + '::' + m.model_id) !== dominant);
if (different.length) ranked = different;
const pick = ranked[0] || rankModels(available, 'reasoning')[0] || available[0];
if (!pick) { sd.review = null; return [{ json: { skip_review: true } }]; }
const reviewerOverride = (sd.agent_overrides || {})['AI Reviewer'] || null;
const reviewerPick = reviewerOverride
  ? { provider: reviewerOverride.provider, model_id: reviewerOverride.model }
  : pick;
sd.reviewer_selection = { provider: reviewerPick.provider, model_id: reviewerPick.model_id };
const reviewerPersona = reviewerOverride && reviewerOverride.system_prompt ? reviewerOverride.system_prompt + '\n' : '';
const systemPrompt = reviewerPersona + [
  'You are the AI Reviewer performing the final independent review of an AI team project.',
  'Check every task result against the plan and its acceptance criteria. Be strict but fair.',
  'Respond with ONLY this JSON (no markdown): {"status":"approved|changes_requested","score":0,"issues":[],"missing_requirements":[],"contradictions":[],"unsupported_claims":[],"required_revisions":[],"final_notes":[]}',
  'score is 0-100. In required_revisions list the task_id values that must be redone (exact ids from the plan). Approve only when acceptance criteria are met and no serious issue remains.'
].join('\n');
const userContent = [
  'PROJECT: ' + (sd.plan ? sd.plan.project_summary || '' : '') + ' (requirement: ' + (sd.requirement || '') + ')',
  'PLAN: ' + JSON.stringify(sd.plan).slice(0, 6000),
  'TASK RESULTS: ' + JSON.stringify(results).slice(0, 14000),
  'Revision round so far: ' + (sd.revision_rounds || 0) + ' of max 2.'
].join('\n');
const call = providerCall(reviewerPick.provider, reviewerPick.model_id, systemPrompt, userContent, 4096);
return [{ json: Object.assign({ skip_review: false }, call) }];
"""

PARSE_REVIEW_JS = EXTRACT_JS + r"""
const item = $input.first();
const sd = $getWorkflowStaticData('global');
const text = responseText(item);
const review = text ? extractJson(text) : null;
if (!review || !review.status) {
  sd.review = { status: 'review_failed', score: 0, issues: ['reviewer_did_not_return_valid_json'], missing_requirements: [], contradictions: [], unsupported_claims: [], required_revisions: [], final_notes: [] };
  return [{ json: { needs_revision: false } }];
}
sd.review = review;
const rounds = sd.revision_rounds || 0;
const wanted = Array.isArray(review.required_revisions) ? review.required_revisions.map(String) : [];
const planTasks = sd.plan && Array.isArray(sd.plan.tasks) ? sd.plan.tasks : [];
const targets = planTasks.filter(t => wanted.includes(t.task_id));
if (review.status !== 'approved' && rounds < 2 && targets.length) {
  sd.revision_rounds = rounds + 1;
  sd.revision_targets = targets.map(t => t.task_id);
  return targets.map(t => ({ json: { task_id: t.task_id, needs_revision: true } }));
}
return [{ json: { needs_revision: false } }];
"""

PREPARE_REVISION_JS = PROVIDERS_JS + r"""
const taskId = $input.first().json.task_id;
const sd = $getWorkflowStaticData('global');
const task = (sd.plan.tasks || []).find(t => t.task_id === taskId);
const previous = (sd.results || []).find(r => r.task_id === taskId) || {};
const review = sd.review || {};
if (!task || !task.model_selection) return [{ json: { task_id: taskId, skip_call: true } }];
const revisionOverride = (sd.agent_overrides || {})[task.role] || null;
const revisionPersona = revisionOverride && revisionOverride.system_prompt ? revisionOverride.system_prompt + '\n' : '';
const systemPrompt = revisionPersona + 'You are the ' + task.role + ' revising your earlier work after an independent review. Fix every listed issue; keep what was already correct. Respond with ONLY this JSON (no markdown): {"project_id":"...","task_id":"...","role":"...","provider":"...","model_id":"...","status":"completed|failed|needs_human_input","summary":"...","deliverables":[],"evidence":[],"assumptions":[],"risks":[],"handoff":{"to_role":"AI Reviewer","notes":"..."},"needs_human_input":false}';
const userContent = [
  'TASK ' + task.task_id + ' — ' + task.role,
  'OBJECTIVE: ' + task.objective,
  task.instructions ? 'INSTRUCTIONS: ' + task.instructions : '',
  task.acceptance_criteria && task.acceptance_criteria.length ? 'ACCEPTANCE CRITERIA: ' + JSON.stringify(task.acceptance_criteria) : '',
  'YOUR PREVIOUS RESULT: ' + JSON.stringify(previous).slice(0, 6000),
  'REVIEW ISSUES TO FIX: ' + JSON.stringify({ issues: review.issues || [], missing_requirements: review.missing_requirements || [], contradictions: review.contradictions || [], unsupported_claims: review.unsupported_claims || [], final_notes: review.final_notes || [] }).slice(0, 4000),
  'Your provider is ' + task.model_selection.provider + ' and your model_id is ' + task.model_selection.model_id + '; project_id is ' + sd.project_id + ', task_id is ' + task.task_id + ', role is ' + task.role + '.'
].filter(Boolean).join('\n');
const call = providerCall(task.model_selection.provider, task.model_selection.model_id, systemPrompt, userContent, 8192);
return [{ json: Object.assign({ task_id: taskId, task, skip_call: false, started_ms: Date.now() }, call) }];
"""

PARSE_REVISION_JS = EXTRACT_JS + r"""
const prep = $('Prepare Revision Call').first().json;
const task = prep.task;
const sd = $getWorkflowStaticData('global');
if (!task) return [{ json: {} }];
const item = $input.first();
const text = responseText(item);
const parsed = text ? extractJson(text) : null;
const result = {
  project_id: sd.project_id, task_id: task.task_id, role: task.role,
  provider: task.model_selection.provider, model_id: task.model_selection.model_id,
  model_reason: (task.model_selection.reason || '') + ' [revision round ' + (sd.revision_rounds || 1) + ']',
  status: parsed ? (['completed', 'failed', 'needs_human_input'].includes(parsed.status) ? parsed.status : 'completed') : 'failed',
  summary: parsed ? (parsed.summary || '') : 'Revision call failed or returned invalid output; previous result kept.',
  deliverables: parsed ? (parsed.deliverables || []) : ((sd.results || []).find(r => r.task_id === task.task_id) || {}).deliverables || [],
  evidence: parsed ? (parsed.evidence || []) : [],
  assumptions: parsed ? (parsed.assumptions || []) : [],
  risks: parsed ? (parsed.risks || []) : [],
  handoff: parsed ? (parsed.handoff || { to_role: 'AI Reviewer', notes: '' }) : { to_role: 'AI Reviewer', notes: '' },
  needs_human_input: parsed ? Boolean(parsed.needs_human_input) : false,
  duration_ms: Date.now() - (prep.started_ms || Date.now()),
  revised: true
};
sd.results = (sd.results || []).filter(r => r.task_id !== task.task_id);
sd.results.push(result);
return [{ json: {} }];
"""

PREPARE_FINALIZE_JS = PROVIDERS_JS + r"""
function rankModels(models, cap) {
  return models.filter(m => m.capabilities.includes(cap)).slice()
    .sort((a, b) => (b.strength - a.strength) || (a.cost_rank - b.cost_rank));
}
const sd = $getWorkflowStaticData('global');
const available = (sd.registry || []).filter(m => m.status === 'available');
let pick = rankModels(available, 'reasoning')[0] || available[0];
const leaderOverride = (sd.agent_overrides || {})['AI Leader'] || null;
if (leaderOverride) pick = { provider: leaderOverride.provider, model_id: leaderOverride.model };
if (!pick) return [{ json: { skip_call: true } }];
const systemPrompt = [
  ...(leaderOverride && leaderOverride.system_prompt ? [leaderOverride.system_prompt] : []),
  'You are the AI Leader delivering the final synthesis of an AI team project.',
  'Write in the same language as the requirement.',
  'Respond with ONLY this JSON (no markdown): {"summary":"...","deliverables":[],"open_questions":[],"notes":[]}'
].join('\n');
const userContent = [
  'REQUIREMENT: ' + (sd.requirement || ''),
  'PLAN SUMMARY: ' + (sd.plan ? sd.plan.project_summary || '' : ''),
  'TASK RESULTS: ' + JSON.stringify(sd.results || []).slice(0, 14000),
  'FINAL REVIEW: ' + JSON.stringify(sd.review || {})
].join('\n');
const call = providerCall(pick.provider, pick.model_id, systemPrompt, userContent, 4096);
return [{ json: Object.assign({ skip_call: false }, call) }];
"""

BUILD_FINAL_JS = EXTRACT_JS + r"""
const sd = $getWorkflowStaticData('global');
let final = null;
const item = $input.first();
if (item && item.json && !item.json.skip_call) {
  const text = responseText(item);
  final = text ? extractJson(text) : null;
}
const results = sd.results || [];
const review = sd.review || null;
let status = 'completed';
if (!sd.plan) status = 'failed';
else if (results.some(r => r.status === 'needs_configuration')) status = 'needs_configuration';
else if (review && review.status === 'changes_requested') status = 'completed_with_issues';
else if (results.some(r => r.status === 'failed')) status = 'completed_with_issues';
return [{ json: {
  project_id: sd.project_id,
  status,
  domain: sd.plan ? sd.plan.domain || [] : [],
  plan: sd.plan || null,
  plan_error: sd.plan_error || null,
  model_registry: (sd.registry || []).filter(m => m.status === 'available'),
  leader_selection: sd.leader_selection || null,
  agent_assignments: Object.entries(sd.agent_overrides || {}).map(([role, o]) => ({ role, agent_name: o.agent_name, provider: o.provider, model: o.model })),
  agent_assignments_ignored: sd.agent_overrides_ignored || [],
  reviewer_selection: sd.reviewer_selection || null,
  task_results: results,
  skipped_roles: sd.skipped_roles || [],
  review,
  revision_rounds: sd.revision_rounds || 0,
  final,
  duration_ms: Date.now() - (sd.started_ms || Date.now())
} }];
"""


def workflow_seven_agent_routing():
    wf = {"name": "AI Factory — 7-Agent Dynamic Model Routing",
          "nodes": [], "connections": {},
          "settings": {"saveDataErrorExecution": "all", "saveDataSuccessExecution": "all",
                       "saveManualExecutions": True, "executionOrder": "v1"},
          "staticData": None, "pinData": {}}
    add = wf["nodes"].append
    add(sticky("## 7-Agent Dynamic Model Routing\n"
               "Implements `ai-7-agent-dynamic-model-routing.md`: 7 roles (Leader, Planner, Architect, "
               "Developer/Executor, Tester, Reviewer, Researcher) with **per-task model routing**.\n\n"
               "**Model Capability Registry** marks a model `available` only when its provider key exists "
               "in the n8n environment (`GROQ_API_KEY` / `OLLAMA_API_KEY` / `OPENROUTER_API_KEY`, set in the "
               ".env file next to docker-compose.yml). Keys never appear in this JSON. Claude/GPT/DeepSeek "
               "are reachable only through OpenRouter and only when its key is set.\n\n"
               "POST `/webhook/ai-team/start` with `{requirement, domain?, expected_outputs?, constraints?, documents?}`. "
               "Optional `agents` maps a role name to a MindFlow agent `{name, provider, model, system_prompt}` "
               "(sent by the MindFlow AI Factory page): the router honors that agent's provider/model and system "
               "prompt for the role when the provider is configured in the n8n env, and reports the assignment "
               "(or why it was ignored) in the final package. "
               "Tasks run sequentially in dependency order; the review gate allows at most 2 revision rounds. "
               "Run one execution at a time (run state uses workflow static data).", -80, 640, 900, 300))
    add(node("Team Webhook", "n8n-nodes-base.webhook", 2,
             {"httpMethod": "POST", "path": "ai-team/start", "responseMode": "responseNode",
              "options": {}}, 0, 300, webhookId=str(uuid.uuid4())))
    add(code("Model Capability Registry", REGISTRY_JS, 260, 300))
    add(code("Prepare Leader Plan Call", PREPARE_LEADER_JS, 520, 300))
    add(if_node("Has Available Model", "json.has_available_model", 780, 300))
    add(code("Build Needs-Configuration Package", NO_MODEL_JS, 1040, 560))
    add(http("Leader Plan Call", 1040, 220))
    add(code("Parse Plan + Model Router", PARSE_PLAN_JS, 1300, 220))
    add(node("Task Loop", "n8n-nodes-base.splitInBatches", 3,
             {"batchSize": 1, "options": {}}, 1560, 220))
    add(code("Prepare Task Call", PREPARE_TASK_JS, 1820, 60))
    add(if_node("Skip Provider Call", "json.skip_call", 2080, 60))
    add(code("Make Skipped Result", MAKE_SKIPPED_JS, 2340, -60))
    add(http("Task Provider Call", 2340, 160))
    add(code("Parse Task Result", PARSE_TASK_JS, 2600, 160))
    add(if_node("Use Fallback Model", "json.needs_fallback", 2860, 160))
    add(http("Task Fallback Call", 3120, 160))
    add(code("Parse Fallback Result", PARSE_FALLBACK_JS, 3380, 160))
    add(code("Record Result", RECORD_JS, 3640, 160))
    add(code("Prepare Review Call", PREPARE_REVIEW_JS, 1820, 460))
    add(if_node("Skip Review", "json.skip_review", 2080, 460))
    add(http("Review Call", 2340, 460))
    add(code("Parse Review", PARSE_REVIEW_JS, 2600, 460))
    add(if_node("Needs Revision", "json.needs_revision", 2860, 460))
    add(node("Revision Loop", "n8n-nodes-base.splitInBatches", 3,
             {"batchSize": 1, "options": {}}, 3120, 640))
    add(code("Prepare Revision Call", PREPARE_REVISION_JS, 3380, 780))
    add(http("Revision Call", 3640, 780))
    add(code("Parse Revision Result", PARSE_REVISION_JS, 3900, 780))
    add(code("Prepare Finalize Call", PREPARE_FINALIZE_JS, 3120, 300))
    add(http("Leader Finalize Call", 3380, 300))
    add(code("Build Final Package", BUILD_FINAL_JS, 3640, 300))
    add(node("Respond to Webhook", "n8n-nodes-base.respondToWebhook", 1.1,
             {"respondWith": "json", "responseBody": "={{ $json }}", "options": {}}, 3900, 300))

    chain(wf, "Team Webhook", "Model Capability Registry", "Prepare Leader Plan Call",
          "Has Available Model")
    connect(wf, "Has Available Model", "Leader Plan Call", output_index=0)
    connect(wf, "Has Available Model", "Build Needs-Configuration Package", output_index=1)
    chain(wf, "Leader Plan Call", "Parse Plan + Model Router", "Task Loop")
    # SplitInBatches outputs: [0] = done, [1] = loop batch
    connect(wf, "Task Loop", "Prepare Review Call", output_index=0)
    connect(wf, "Task Loop", "Prepare Task Call", output_index=1)
    chain(wf, "Prepare Task Call", "Skip Provider Call")
    connect(wf, "Skip Provider Call", "Make Skipped Result", output_index=0)
    connect(wf, "Skip Provider Call", "Task Provider Call", output_index=1)
    chain(wf, "Make Skipped Result", "Record Result")
    chain(wf, "Task Provider Call", "Parse Task Result", "Use Fallback Model")
    connect(wf, "Use Fallback Model", "Task Fallback Call", output_index=0)
    connect(wf, "Use Fallback Model", "Record Result", output_index=1)
    chain(wf, "Task Fallback Call", "Parse Fallback Result", "Record Result")
    connect(wf, "Record Result", "Task Loop")
    chain(wf, "Prepare Review Call", "Skip Review")
    connect(wf, "Skip Review", "Review Call", output_index=1)
    connect(wf, "Skip Review", "Prepare Finalize Call", output_index=0)
    chain(wf, "Review Call", "Parse Review", "Needs Revision")
    connect(wf, "Needs Revision", "Revision Loop", output_index=0)
    connect(wf, "Needs Revision", "Prepare Finalize Call", output_index=1)
    connect(wf, "Revision Loop", "Prepare Review Call", output_index=0)
    connect(wf, "Revision Loop", "Prepare Revision Call", output_index=1)
    chain(wf, "Prepare Revision Call", "Revision Call", "Parse Revision Result")
    connect(wf, "Parse Revision Result", "Revision Loop")
    chain(wf, "Prepare Finalize Call", "Leader Finalize Call", "Build Final Package",
          "Respond to Webhook")
    connect(wf, "Build Needs-Configuration Package", "Respond to Webhook")
    return wf


def main():
    os.makedirs(OUT, exist_ok=True)
    wf = workflow_seven_agent_routing()
    path = os.path.join(OUT, "07-seven-agent-dynamic-routing.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(wf, f, ensure_ascii=False, indent=2)
    print(f"wrote {os.path.basename(path)}: {len(wf['nodes'])} nodes")


if __name__ == "__main__":
    main()
