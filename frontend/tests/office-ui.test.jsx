// @vitest-environment jsdom
// Office simulation view + quick agent rename. Fixtures are local test data.
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import MockAdapter from "axios-mock-adapter";
import { api } from "../services/api";
import { AgentOffice } from "../components/workflows/agent-office";
import { RenameAgentDialog } from "../components/agents/rename-agent";

const mock = new MockAdapter(api);
afterEach(() => { cleanup(); mock.reset(); });

const team = {
  id: "t1",
  members: [
    { agent_id: "a1", agent_name: "AI Leader", role: "coordinator" },
    { agent_id: "a2", agent_name: "AI Developer", role: "developer" },
  ],
};
const workflow = { id: "w1", title: "WF", goal: "Xây website", status: "running" };
const tasks = [
  { id: "k1", title: "Developer: WF", assigned_agent_id: "a2", status: "in_progress" },
  { id: "k2", title: "Leader: WF", assigned_agent_id: "a1", status: "completed" },
];
const messages = [
  { id: "m1", from_agent_id: "a1", to_agent_id: "a2", content: "Đã giao việc cho Developer.", message_type: "TASK_ASSIGNMENT", status: "delivered", created_at: "2026-11-23T05:00:00Z" },
];

describe("AgentOffice simulation view", () => {
  it("renders agents at desks with real task and chat data", () => {
    render(<AgentOffice workflow={workflow} team={team} tasks={tasks} messages={messages} onRenameAgent={vi.fn()} />);
    expect(screen.getByText("Xây website")).toBeTruthy();
    expect(screen.getAllByText("AI Leader").length).toBeGreaterThan(0);
    expect(screen.getAllByText("AI Developer").length).toBeGreaterThan(0);
    // The working agent's bubble and the task rail both show the real
    // in-progress task title.
    expect(screen.getAllByText(/Developer: WF/).length).toBeGreaterThan(1);
    // Task rail shows the real task with the office progress mapping.
    expect(screen.getByText("55%")).toBeTruthy();
    // Team chat rail shows the real message.
    expect(screen.getByText(/Đã giao việc cho Developer/)).toBeTruthy();
  });

  it("asks the parent to rename when a nameplate is clicked", () => {
    const onRenameAgent = vi.fn();
    render(<AgentOffice workflow={workflow} team={team} tasks={tasks} messages={messages} onRenameAgent={onRenameAgent} />);
    fireEvent.click(screen.getByRole("button", { name: /Đổi tên AI Developer/ }));
    expect(onRenameAgent).toHaveBeenCalledWith(expect.objectContaining({ agent_id: "a2" }));
  });
});

describe("RenameAgentDialog", () => {
  it("patches only the name and reports the updated agent", async () => {
    mock.onPatch("/ai/agents/a2").reply((config) => {
      const body = JSON.parse(config.data);
      expect(body).toEqual({ name: "Siêu Dev" });
      return [200, { id: "a2", name: "Siêu Dev" }];
    });
    const onRenamed = vi.fn();
    render(<RenameAgentDialog agent={{ id: "a2", name: "AI Developer" }} onClose={vi.fn()} onRenamed={onRenamed} />);
    const input = screen.getByLabelText("Tên mới");
    fireEvent.change(input, { target: { value: "Siêu Dev" } });
    fireEvent.click(screen.getByRole("button", { name: /Lưu tên mới/ }));
    await waitFor(() => expect(onRenamed).toHaveBeenCalledWith(expect.objectContaining({ name: "Siêu Dev" })));
  });
});
