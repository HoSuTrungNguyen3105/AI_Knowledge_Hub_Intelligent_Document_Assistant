import { getErrorMessage } from "../services/api";

const compareErrorLabels = {
  comparison_not_found: "Không tìm thấy phép so sánh. Có thể nó đã bị xóa.",
  invalid_comparison_targets: "Cần chọn từ 2 đến 4 model khác nhau để so sánh.",
  no_successful_runs: "Chưa có câu trả lời thành công nào để tổng hợp. Hãy chạy so sánh trước.",
  model_not_chat_capable: "Model này không hỗ trợ trò chuyện. Hãy chọn model khác.",
  model_not_synced: "Hãy đồng bộ model của provider trong Cài đặt AI trước khi so sánh.",
  provider_disabled: "Provider đang tắt. Hãy bật lại trong Cài đặt AI.",
  credentials_missing: "Bạn chưa lưu API key cho provider này. Hãy vào Cài đặt AI.",
  provider_not_implemented: "Provider này chưa được tích hợp trong phiên bản hiện tại.",
  generation_failed: "Provider trả về phản hồi không hợp lệ. Không có nội dung nào được tạo.",
  model_tools_unsupported: "Model không hỗ trợ gọi công cụ (tool calling). Hãy đổi sang model hỗ trợ tool calling.",
  provider_request_rejected: "Provider từ chối yêu cầu tạo nội dung (400). Hãy kiểm tra model và cấu hình rồi thử lại.",
  provider_authentication_failed: "Provider từ chối API key. Hãy kiểm tra key trong Cài đặt AI.",
  provider_rate_limited: "Provider đang giới hạn yêu cầu. Vui lòng chờ rồi thử lại.",
  provider_timeout: "Provider phản hồi quá lâu. Hãy thử lại sau.",
  provider_unavailable: "Chưa kết nối được provider. Kiểm tra mạng rồi thử lại.",
  encryption_unavailable: "Backend chưa có khóa mã hóa hợp lệ. Hãy cấu hình CREDENTIAL_ENCRYPTION_KEY.",
};

// Map a backend error code to fixed Vietnamese copy. Never echo upstream text.
export function getCompareError(error) {
  const code = error?.response?.data?.detail?.code;
  if (code && Object.hasOwn(compareErrorLabels, code)) return compareErrorLabels[code];
  const status = error?.response?.status;
  if (status === 401) return "Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.";
  if (status === 409) return "Cấu hình so sánh không còn phù hợp. Hãy tải lại hoặc kiểm tra Cài đặt AI.";
  if (status === 422) return "Thông tin chưa hợp lệ. Hãy kiểm tra prompt và các model đã chọn.";
  return getErrorMessage(error);
}

// The SSE error event carries a fixed backend code; map it to the same copy.
export function compareErrorFromEvent(data) {
  const code = data?.code;
  if (code && Object.hasOwn(compareErrorLabels, code)) return compareErrorLabels[code];
  return "Quá trình tạo nội dung gặp lỗi. Vui lòng thử lại.";
}

// Estimated USD only — never a provider-confirmed charge. Null when the model has
// no published pricing or the provider returned no token usage.
export function formatCost(value) {
  if (value === null || value === undefined) return "—";
  const amount = Number(value);
  if (!Number.isFinite(amount)) return "—";
  return `$${amount < 0.01 ? amount.toFixed(6) : amount.toFixed(4)}`;
}

export const runStatusLabels = {
  pending: "Chưa chạy",
  running: "Đang chạy",
  success: "Hoàn tất",
  stopped: "Đã dừng",
  error: "Lỗi",
};