import { getErrorMessage } from "../services/api";
import { formatCount } from "./format";

const chatErrorLabels = {
  conversation_not_found: "Không tìm thấy hội thoại. Có thể nó đã bị xóa.",
  model_not_chat_capable: "Model này không hỗ trợ trò chuyện. Hãy chọn model khác.",
  model_not_synced: "Hãy đồng bộ model của provider trong Cài đặt AI trước khi trò chuyện.",
  provider_disabled: "Provider đang tắt. Hãy bật lại trong Cài đặt AI.",
  credentials_missing: "Bạn chưa lưu API key cho provider này. Hãy vào Cài đặt AI.",
  empty_message: "Tin nhắn trống. Hãy nhập nội dung trước khi gửi.",
  generation_failed: "Provider trả về phản hồi không hợp lệ. Không có nội dung nào được tạo.",
  provider_authentication_failed: "Provider từ chối API key. Hãy kiểm tra key trong Cài đặt AI.",
  provider_rate_limited: "Provider đang giới hạn yêu cầu. Vui lòng chờ rồi thử lại.",
  provider_timeout: "Provider phản hồi quá lâu. Hãy thử lại sau.",
  provider_unavailable: "Chưa kết nối được provider. Kiểm tra mạng rồi thử lại.",
  encryption_unavailable: "Backend chưa có khóa mã hóa hợp lệ. Hãy cấu hình CREDENTIAL_ENCRYPTION_KEY.",
  invalid_provider_configuration: "Thông tin hội thoại chưa hợp lệ. Hãy kiểm tra provider, model và giới hạn.",
};

// Map a backend error code to fixed Vietnamese copy. Never echo upstream text.
export function getChatError(error) {
  const code = error?.response?.data?.detail?.code;
  if (code && Object.hasOwn(chatErrorLabels, code)) return chatErrorLabels[code];
  const status = error?.response?.status;
  if (status === 401) return "Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.";
  if (status === 409) return "Cấu hình hội thoại không còn phù hợp. Hãy tải lại hoặc kiểm tra Cài đặt AI.";
  if (status === 422) return "Thông tin chưa hợp lệ. Hãy kiểm tra nội dung và cấu hình hội thoại.";
  return getErrorMessage(error);
}

// The SSE error event carries a fixed backend code; map it to the same copy.
export function chatErrorFromEvent(data) {
  const code = data?.code;
  if (code && Object.hasOwn(chatErrorLabels, code)) return chatErrorLabels[code];
  return "Quá trình tạo nội dung gặp lỗi. Vui lòng thử lại.";
}

export function formatTokens(value) {
  return value === null || value === undefined ? "—" : formatCount(value);
}

export function formatLatency(ms) {
  if (ms === null || ms === undefined) return "";
  return ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`;
}

export const messageStatusLabels = {
  success: "Hoàn tất",
  stopped: "Đã dừng",
  error: "Lỗi",
};