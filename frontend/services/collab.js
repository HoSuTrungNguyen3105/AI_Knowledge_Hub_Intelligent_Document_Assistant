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
  async listMessages(roomId, signal) {
    const { data } = await api.get(`/ai/collab/rooms/${roomId}/messages`, { signal });
    return data.messages;
  },
  async postMessage(roomId, payload, signal) {
    const { data } = await api.post(`/ai/collab/rooms/${roomId}/messages`, payload, { signal });
    return data.messages;
  },
};

export function getCollabError(error) {
  const code = error?.response?.data?.detail?.code;
  if (code === "collab_room_not_found") return "Không tìm thấy phòng hợp tác.";
  if (code === "collab_agent_not_member") return "Agent được nhắc tới không phải thành viên của phòng.";
  if (code === "collab_message_not_found") return "Không tìm thấy tin nhắn được trả lời trong phòng này.";
  if (code === "agent_not_found") return "Có Agent không thuộc về bạn.";
  return error?.response?.data?.detail?.message || "Đã xảy ra lỗi. Vui lòng thử lại.";
}
