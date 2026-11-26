import { api } from "./api";

// Collaboration rooms (NEXORA Module 03): rooms on multi_chats with
// member Agents and @mention replies.
export const collabService = {
  async listRooms(signal) {
    const { data } = await api.get("/ai/collab/rooms", { signal });
    return data.rooms;
  },
  async createRoom(payload, signal) {
    const { data } = await api.post("/ai/collab/rooms", payload, { signal });
    return data;
  },
  async getRoom(id, signal) {
    const { data } = await api.get(`/ai/collab/rooms/${id}`, { signal });
    return data;
  },
  async patchRoom(id, payload, signal) {
    const { data } = await api.patch(`/ai/collab/rooms/${id}`, payload, { signal });
    return data;
  },
  async deleteRoom(id) {
    await api.delete(`/ai/collab/rooms/${id}`);
  },
  async roomUsage(roomId, signal) {
    const { data } = await api.get(`/ai/collab/rooms/${roomId}/usage`, { signal });
    return data;
  },
  async listMessages(roomId, signal) {
    const { data } = await api.get(`/ai/collab/rooms/${roomId}/messages`, { signal });
    return data.messages;
  },
  async postMessage(roomId, payload, signal) {
    const { data } = await api.post(`/ai/collab/rooms/${roomId}/messages`, payload, { signal });
    return data.messages;
  },
  async postMessageFull(roomId, payload, signal) {
    const { data } = await api.post(`/ai/collab/rooms/${roomId}/messages`, payload, { signal });
    return data;
  },
  async listRuns(roomId, signal) {
    const { data } = await api.get(`/ai/collab/rooms/${roomId}/runs`, { signal });
    return data.runs;
  },
  async getRun(runId, signal) {
    const { data } = await api.get(`/ai/collab/runs/${runId}`, { signal });
    return data;
  },
  async cancelRun(runId, signal) {
    const { data } = await api.post(`/ai/collab/runs/${runId}/cancel`, {}, { signal });
    return data;
  },
  async retryRun(runId, signal) {
    const { data } = await api.post(`/ai/collab/runs/${runId}/retry`, {}, { signal });
    return data;
  },
  async summarize(roomId, agentId, signal) {
    const { data } = await api.post(
      `/ai/collab/rooms/${roomId}/summarize`,
      { agent_id: agentId || null },
      { signal }
    );
    return data;
  },
  async exportRoom(roomId, formats, runId, signal) {
    const { data } = await api.post(
      `/ai/collab/rooms/${roomId}/export`,
      { formats: formats || ["md", "json", "zip"], run_id: runId || null },
      { signal }
    );
    return data.artifacts;
  },
  async listArtifacts(roomId, signal) {
    const { data } = await api.get(`/ai/collab/rooms/${roomId}/artifacts`, { signal });
    return data.artifacts;
  },
  async downloadArtifact(artifactId) {
    const { data } = await api.get(`/ai/collab/artifacts/${artifactId}/download`, {
      responseType: "blob",
    });
    return data;
  },
  async deleteArtifact(artifactId) {
    await api.delete(`/ai/collab/artifacts/${artifactId}`);
  },
};

export function getCollabError(error) {
  const code = error?.response?.data?.detail?.code;
  if (code === "collab_room_not_found") return "Không tìm thấy phòng hợp tác.";
  if (code === "collab_agent_not_member") return "Agent được nhắc tới không phải thành viên của phòng.";
  if (code === "collab_message_not_found") return "Không tìm thấy tin nhắn được trả lời trong phòng này.";
  if (code === "collab_moderator_not_member") return "Moderator phải là thành viên của phòng.";
  if (code === "collab_run_not_found") return "Không tìm thấy lượt chạy này.";
  if (code === "collab_nothing_to_retry") return "Lượt chạy này không có tác vụ lỗi nào để chạy lại.";
  if (code === "collab_no_agents") return "Phòng chưa có Agent thành viên nào.";
  if (code === "collab_artifact_not_found") return "Không tìm thấy file kết quả này.";
  if (code === "agent_not_found") return "Có Agent không thuộc về bạn.";
  return error?.response?.data?.detail?.message || "Đã xảy ra lỗi. Vui lòng thử lại.";
}
