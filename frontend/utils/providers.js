import { getErrorMessage } from "../services/api";

const errorLabels = {
  credentials_missing: "Bạn chưa lưu API key cho provider này.",
  encryption_unavailable: "Backend chưa có khóa mã hóa hợp lệ. Hãy cấu hình CREDENTIAL_ENCRYPTION_KEY.",
  credentials_unreadable: "Không giải mã được API key đã lưu. Kiểm tra khóa mã hóa của backend hoặc lưu lại API key.",
  provider_authentication_failed: "Provider từ chối API key. Hãy kiểm tra key và quyền truy cập của tài khoản.",
  provider_rate_limited: "Provider đang giới hạn yêu cầu. Vui lòng chờ rồi kiểm tra lại.",
  provider_timeout: "Provider phản hồi quá lâu. Cấu hình cũ vẫn được giữ; hãy thử lại sau.",
  provider_unavailable: "Chưa kết nối được provider. Kiểm tra mạng và tình trạng dịch vụ rồi thử lại.",
  invalid_provider_response: "Phản hồi của provider không hợp lệ. Không có model nào được đồng bộ từ phản hồi này.",
  provider_not_implemented: "Provider này chưa được tích hợp trong phiên bản hiện tại.",
  configuration_changed: "Cấu hình đã thay đổi trong lúc kiểm tra. Vui lòng tải lại và thử lại.",
  invalid_default_model: "Model mặc định phải thuộc danh sách đã đồng bộ của provider này.",
  chat_not_supported: "Model này không hỗ trợ tạo nội dung chat (theo metadata của provider).",
  provider_disabled: "Provider đang tắt. Bật lại provider để dùng model của nó.",
};

export function getProviderError(error) {
  const code = error.response?.data?.detail?.code;
  if (Object.hasOwn(errorLabels, code)) return errorLabels[code];
  if (error.response?.status === 422) return "Cấu hình chưa hợp lệ. Kiểm tra API key và model đã chọn.";
  if (error.response?.status === 409) return "Cấu hình không còn phù hợp. Hãy đồng bộ model hoặc tải lại trang.";
  return getErrorMessage(error);
}

// Persistent explanation for a stored failed check, so the reason survives after
// the transient toast disappears (metadata already carries last_error_code).
export function providerFailureReason(code) {
  if (code && Object.hasOwn(errorLabels, code)) return errorLabels[code];
  return "Lần kiểm tra gần nhất chưa thành công.";
}

export function validateApiKey(value) {
  const key = value.trim();
  if (!key) return "Vui lòng nhập API key.";
  if (!/^[!-~]{8,4096}$/.test(key)) return "API key cần từ 8 đến 4096 ký tự ASCII, không có khoảng trắng hoặc xuống dòng.";
  return "";
}

// Providers whose keys only work with a paid-up account: a perfectly valid
// key still fails until the account holds balance/credit (DeepSeek answers
// 402 Insufficient Balance). The key section shows this note so the user
// checks billing first instead of debugging a "broken" key.
const paidProviderNotes = {
  deepseek:
    "DeepSeek là provider trả phí — key chỉ dùng được khi tài khoản còn số dư. Hãy kiểm tra và nạp tiền tại platform.deepseek.com trước khi dùng; hết số dư thì API sẽ báo lỗi dù key đúng.",
  anthropic:
    "Claude (Anthropic) là provider trả phí — key chỉ dùng được khi tài khoản còn tín dụng. Hãy kiểm tra và nạp tiền trong Anthropic Console (console.anthropic.com) trước khi dùng.",
};

export function paidProviderNote(provider) {
  return paidProviderNotes[provider?.id] ?? null;
}

export function providerStatus(provider) {
  if (!provider.implemented) return { label: "Sắp tích hợp", tone: "neutral" };
  if (!provider.configured) return { label: "Chưa kết nối", tone: "neutral" };
  if (provider.connection_status === "error") return { label: "Kiểm tra thất bại", tone: "error" };
  if (provider.connection_status === "connected") return { label: "Đã xác minh danh sách model", tone: "success" };
  return { label: "Chưa kiểm tra", tone: "pending" };
}

export function capabilityLabel(value) {
  return value === true ? "Có" : value === false ? "Không" : "Chưa xác định";
}

export function filterModels(models, query) {
  const needle = query.trim().toLowerCase();
  return models.filter((model) => `${model.id} ${model.display_name || ""}`.toLowerCase().includes(needle));
}
