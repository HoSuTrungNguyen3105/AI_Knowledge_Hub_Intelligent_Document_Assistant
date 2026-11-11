import axios from "axios";

const options = { baseURL: "/api/v1", withCredentials: true, timeout: 20000 };
export const api = axios.create(options);
export const refreshClient = axios.create(options);
let refreshing = null;

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const request = error.config;
    if (error.response?.status !== 401 || !request || request.skipAuthRefresh || request._retry) {
      return Promise.reject(error);
    }
    request._retry = true;
    if (!refreshing) {
      refreshing = refreshClient.post("/auth/refresh").finally(() => { refreshing = null; });
    }
    try {
      await refreshing;
      return await api(request);
    } catch (refreshError) {
      if ([401, 403].includes(refreshError.response?.status) && typeof window !== "undefined") {
        window.dispatchEvent(new Event("session-expired"));
      }
      return Promise.reject(refreshError);
    }
  },
);

export function getErrorMessage(error) {
  const status = error.response?.status;
  if (status === 429) return "Bạn thao tác hơi nhanh. Vui lòng thử lại sau một phút.";
  if (status === 409) return "Email này đã được đăng ký. Bạn có thể đăng nhập.";
  if (status === 401) return "Email hoặc mật khẩu chưa đúng, hoặc phiên đăng nhập đã hết hạn.";
  if (status === 403) return "Yêu cầu bị từ chối. Hãy mở ứng dụng bằng địa chỉ đã cấu hình.";
  if (status === 422) return "Thông tin chưa hợp lệ. Hãy kiểm tra email, tên và độ dài mật khẩu.";
  if (status >= 500) return "Máy chủ chưa sẵn sàng. Vui lòng kiểm tra backend và cơ sở dữ liệu.";
  if (!error.response) return "Không kết nối được máy chủ. Hãy kiểm tra kết nối và backend.";
  return "Không thể hoàn tất thao tác. Vui lòng thử lại.";
}
