// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import MockAdapter from "axios-mock-adapter";
import { api } from "../services/api";
import { downloadWorkflowZip, teamsService, workflowsService } from "../services/workflows";
import {
  OUTPUT_TYPES, STARTER_AGENTS, artifactErrorLabel, createStarterSet, formatBytes,
  getWorkflowError, missingStarterAgents,
  agentStatus, progressOf, roleMeta, stepperOf,
} from "../utils/workflows";

const mock = new MockAdapter(api);
afterEach(() => mock.reset());

describe("Phase 6 REST contract", () => {
  it("unwraps team and workflow envelopes", async () => {
    mock.onGet("/ai/agent-teams").reply(200, { teams: [{ id: "t1" }] });
    mock.onGet("/ai/agent-workflows").reply(200, { workflows: [{ id: "w1" }] });
    expect(await teamsService.list()).toEqual([{ id: "t1" }]);
    expect(await workflowsService.list()).toEqual([{ id: "w1" }]);
  });
  it("creates and controls workflows through dedicated endpoints", async () => {
    mock.onPost("/ai/agent-workflows").reply(201, { id: "w1", status: "queued" });
    mock.onPost("/ai/agent-workflows/w1/start").reply(200, { id: "w1", status: "running" });
    mock.onPost("/ai/agent-workflows/w1/pause").reply(200, { id: "w1", status: "waiting" });
    mock.onPost("/ai/agent-workflows/w1/cancel").reply(200, { id: "w1", status: "cancelled" });
    expect(await workflowsService.create({ team_id: "t", title: "x", goal: "g" })).toMatchObject({ status: "queued" });
    expect(await workflowsService.start("w1")).toMatchObject({ status: "running" });
    expect(await workflowsService.pause("w1")).toMatchObject({ status: "waiting" });
    expect(await workflowsService.cancel("w1")).toMatchObject({ status: "cancelled" });
  });
  it("loads messages, tasks and events sub-resources", async () => {
    mock.onGet("/ai/agent-workflows/w1/messages").reply(200, { messages: [{ id: "m" }] });
    mock.onGet("/ai/agent-workflows/w1/tasks").reply(200, { tasks: [{ id: "k" }] });
    mock.onGet("/ai/agent-workflows/w1/events").reply(200, { events: [{ id: "e" }] });
    expect(await workflowsService.messages("w1")).toEqual([{ id: "m" }]);
    expect(await workflowsService.tasks("w1")).toEqual([{ id: "k" }]);
    expect(await workflowsService.events("w1")).toEqual([{ id: "e" }]);
  });
});

describe("Phase 6 derivations from real data", () => {
  const tasks = [
    { assigned_agent_id: "a1", title: "Planner: X", status: "completed" },
    { assigned_agent_id: "a2", title: "Developer: X", status: "in_progress" },
    { assigned_agent_id: "a3", title: "Reviewer: X", status: "pending" },
  ];
  it("computes progress counts and percent", () => {
    expect(progressOf(tasks)).toEqual({ total: 3, completed: 1, inProgress: 1, pending: 1, percent: 33 });
    expect(progressOf([]).percent).toBe(0);
  });
  it("derives agent status from its latest task", () => {
    expect(agentStatus("a2", tasks, { status: "running" }).label).toBe("Working");
    expect(agentStatus("a3", tasks, { status: "running" }).label).toBe("Waiting");
    expect(agentStatus("a1", tasks, { status: "running" }).label).toBe("Done");
  });
  it("derives the stepper from completed task roles", () => {
    const steps = stepperOf(tasks, { status: "running" });
    expect(steps.find((s) => s.key === "plan").state).toBe("done");
    expect(steps.find((s) => s.key === "develop").state).toBe("active");
    expect(steps.find((s) => s.key === "complete").state).toBe("todo");
  });
  it("maps roles to the reference palette", () => {
    expect(roleMeta("coordinator").color).toBe("#7c3aed");
    expect(roleMeta("developer").color).toBe("#ea580c");
    expect(roleMeta("unknown").label).toBe("Member");
  });
});

describe("Website ZIP artifact", () => {
  it("offers text and website_zip output types with text as the default first option", () => {
    expect(OUTPUT_TYPES.map((o) => o.value)).toEqual(["text", "website_zip"]);
  });
  it("lists artifact files through the files endpoint", async () => {
    mock.onGet("/ai/agent-workflows/w1/files").reply(200, {
      files: [{ path: "index.html", size_bytes: 42 }], total_bytes: 42, artifact_status: "ready",
    });
    const data = await workflowsService.files("w1");
    expect(data.artifact_status).toBe("ready");
    expect(data.files).toEqual([{ path: "index.html", size_bytes: 42 }]);
  });
  it("formats bytes and explains artifact failures in Vietnamese", () => {
    expect(formatBytes(500)).toBe("500 B");
    expect(formatBytes(2048)).toBe("2.0 KB");
    expect(formatBytes(3 * 1024 * 1024)).toBe("3.00 MB");
    expect(artifactErrorLabel("artifact_no_files")).toContain("không có ZIP");
    expect(artifactErrorLabel("artifact_missing_index")).toContain("index.html");
    expect(artifactErrorLabel("weird_code")).toContain("weird_code");
  });
  it("downloads the ZIP with credentials and clicks a blob anchor", async () => {
    const realCreate = document.createElement.bind(document);
    const anchor = realCreate("a");
    anchor.click = vi.fn();
    const createSpy = vi.spyOn(document, "createElement").mockImplementation((tag) => (
      tag === "a" ? anchor : realCreate(tag)
    ));
    URL.createObjectURL = vi.fn(() => "blob:zip");
    URL.revokeObjectURL = vi.fn();
    const fetchMock = vi.fn(async () => ({
      ok: true, status: 200,
      blob: async () => new Blob(["PK"], { type: "application/zip" }),
      headers: { get: () => 'attachment; filename="my-site.zip"' },
    }));
    vi.stubGlobal("fetch", fetchMock);
    try {
      const name = await downloadWorkflowZip("w1");
      expect(name).toBe("my-site.zip");
      expect(fetchMock).toHaveBeenCalledWith("/api/v1/ai/agent-workflows/w1/download.zip",
        expect.objectContaining({ credentials: "include" }));
      expect(anchor.download).toBe("my-site.zip");
      expect(anchor.click).toHaveBeenCalledTimes(1);
    } finally {
      createSpy.mockRestore();
      vi.unstubAllGlobals();
    }
  });
  it("surfaces a 409 when the artifact is not ready", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: false, status: 409, headers: { get: () => "" } })));
    try {
      await expect(downloadWorkflowZip("w1")).rejects.toMatchObject({ response: { status: 409 } });
    } finally { vi.unstubAllGlobals(); }
  });
});

describe("Teams load error reporting", () => {
  const err = (status, code) => ({ response: { status, data: { detail: code ? { code } : {} } } });
  it("explains a 404 as a stale backend that needs a restart", () => {
    expect(getWorkflowError(err(404), "fallback")).toContain("404");
    expect(getWorkflowError(err(404), "fallback")).toContain("khởi động lại backend");
  });
  it("explains 401 and 5xx with their real status", () => {
    expect(getWorkflowError(err(401), "fallback")).toContain("401");
    expect(getWorkflowError(err(503, "db_down"), "fallback")).toContain("503");
    expect(getWorkflowError(err(503, "db_down"), "fallback")).toContain("db_down");
  });
  it("keeps known detail codes readable and appends the status", () => {
    expect(getWorkflowError(err(409, "workflow_already_running"), "fallback")).toContain("Workflow đang chạy.");
    expect(getWorkflowError(err(409, "workflow_already_running"), "fallback")).toContain("409");
  });
});

describe("Starter agent set (one-click bootstrap)", () => {
  const base = { provider: "groq", model: "m1", availableToolNames: ["calculator", "datetime", "data_analyzer"] };
  it("creates all 7 agents and the starter team with Leader as coordinator", async () => {
    const createdAgents = []; const createdTeams = [];
    const result = await createStarterSet({
      ...base, existingAgents: [], existingTeams: [],
      createAgent: async (payload) => { const a = { id: `a${createdAgents.length + 1}`, ...payload }; createdAgents.push(a); return a; },
      createTeam: async (payload) => { createdTeams.push(payload); return { id: "t1", ...payload }; },
    });
    expect(createdAgents).toHaveLength(7);
    expect(createdAgents.map((a) => a.name)).toEqual(STARTER_AGENTS.map((s) => s.name));
    expect(createdAgents.every((a) => a.provider === "groq" && a.model === "m1" && a.system_prompt.length > 20)).toBe(true);
    expect(createdAgents.find((a) => a.name === "AI Developer").tools).toEqual(["calculator", "data_analyzer"]);
    expect(result.failed).toBeNull();
    expect(createdTeams).toHaveLength(1);
    expect(createdTeams[0].members).toHaveLength(7);
    expect(createdTeams[0].coordinator_agent_id).toBe(createdAgents[0].id);
    expect(createdTeams[0].members.find((m) => m.role === "coordinator").agent_id).toBe(createdAgents[0].id);
  });
  it("skips existing agents by name and never duplicates on re-click", async () => {
    const existing = STARTER_AGENTS.map((s, i) => ({ id: `x${i}`, name: s.name }));
    let agentCalls = 0; let teamCalls = 0;
    const result = await createStarterSet({
      ...base, existingAgents: existing, existingTeams: [{ id: "t", name: "Nhóm Multi-Agent" }],
      createAgent: async () => { agentCalls += 1; }, createTeam: async () => { teamCalls += 1; },
    });
    expect(agentCalls).toBe(0); expect(teamCalls).toBe(0);
    expect(result.reused).toHaveLength(7); expect(result.teamSkipped).toBe(true);
    expect(missingStarterAgents(existing)).toEqual([]);
    expect(missingStarterAgents([])).toHaveLength(7);
  });
  it("stops at the first failure and reports what was created", async () => {
    const created = [];
    const result = await createStarterSet({
      ...base, existingAgents: [], existingTeams: [],
      createAgent: async (payload) => {
        if (payload.name === "AI Architect") throw { response: { status: 409, data: { detail: {} } } };
        const a = { id: payload.name, ...payload }; created.push(a); return a;
      },
      createTeam: async () => { throw new Error("must not be called"); },
    });
    expect(created.map((a) => a.name)).toEqual(["AI Leader", "AI Planner"]);
    expect(result.failed.name).toBe("AI Architect");
    expect(result.team).toBeNull();
  });
  it("filters starter tools to the live available catalog", async () => {
    const payloads = [];
    await createStarterSet({
      provider: "groq", model: "m1", availableToolNames: ["data_analyzer"],
      existingAgents: [], existingTeams: [{ id: "t", name: "Nhóm Multi-Agent" }],
      createAgent: async (payload) => { payloads.push(payload); return { id: payload.name, ...payload }; },
      createTeam: async () => ({}),
    });
    expect(payloads.every((p) => p.tools.every((t) => t === "data_analyzer"))).toBe(true);
  });
});
