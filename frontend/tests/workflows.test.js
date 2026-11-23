// @vitest-environment jsdom
import { afterEach, describe, expect, it } from "vitest";
import MockAdapter from "axios-mock-adapter";
import { api } from "../services/api";
import { teamsService, workflowsService } from "../services/workflows";
import { agentStatus, progressOf, roleMeta, stepperOf } from "../utils/workflows";

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
