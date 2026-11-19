import { getCompareError } from "./compare";

const errors = {
  agent_not_found: "Không tìm thấy Agent trong tài khoản của bạn. Có thể Agent đã bị xóa.",
  execution_not_found: "Không tìm thấy lượt thực thi. Hãy tải lại lịch sử.",
  invalid_agent_tools: "Công cụ không thuộc danh sách khả dụng. Hãy kiểm tra lựa chọn công cụ.",
  agent_budget_exceeded: "Đã đạt ngân sách 8000 đơn vị ước lượng bảo thủ. Hãy chia nhỏ yêu cầu; đây không phải số token tính phí.",
  agent_step_limit: "Đã đạt giới hạn 6 bước. Hãy chia nhỏ yêu cầu.",
  agent_timeout: "Đã đạt giới hạn thời gian 120 giây. Hãy thử yêu cầu ngắn hơn.",
  tool_timeout: "Công cụ phản hồi quá lâu. Xem trace và thử lại.",
  tool_failed: "Công cụ thực thi thất bại. Xem mã lỗi trong trace.",
  tool_not_available: "Công cụ chưa khả dụng trong giai đoạn này. Hãy bỏ chọn công cụ đó.",
  tool_not_allowed: "Agent không được phép sử dụng công cụ này.",
  unknown_tool: "Công cụ không có trong danh sách được phép.",
  model_not_tool_capable: "Model không hỗ trợ function calling. Hãy bỏ chọn công cụ hoặc đổi model.",
  provider_not_tool_capable: "Provider không hỗ trợ function calling. Hãy bỏ chọn công cụ hoặc đổi provider.",
  function_calling_not_supported: "Provider hoặc model không hỗ trợ function calling. Hãy bỏ chọn công cụ.",
  step_limit_exceeded: "Đã đạt giới hạn 6 bước. Hãy chia nhỏ yêu cầu.",
  token_budget_exceeded: "Đã đạt ngân sách 8000 đơn vị ước lượng bảo thủ. Hãy chia nhỏ yêu cầu; đây không phải số token tính phí.",
  execution_timeout: "Đã đạt giới hạn thời gian 120 giây. Hãy thử yêu cầu ngắn hơn.",
  execution_stopped: "Lượt thực thi đã được dừng.",
  tool_execution_failed: "Công cụ thực thi thất bại. Xem mã lỗi trong trace.",
  invalid_tool_arguments: "Tham số công cụ không hợp lệ.",
};

export function agentErrorFromEvent(data) {
  if (Object.hasOwn(errors, data?.code)) return errors[data.code];
  return getCompareError({ response: { status: 500, data: { detail: { code: data?.code } } } });
}

export function getAgentError(error) {
  const code = error?.response?.data?.detail?.code;
  if (Object.hasOwn(errors, code)) return errors[code];
  if (error?.response?.status === 404) return "Không tìm thấy dữ liệu trong tài khoản của bạn. Hãy tải lại.";
  if (error?.response?.status === 409) return "Cấu hình Agent không còn phù hợp. Hãy tải lại hoặc kiểm tra Cài đặt AI.";
  if (error?.response?.status === 422) return "Thông tin Agent chưa hợp lệ. Hãy kiểm tra tên, prompt, model và công cụ.";
  return getCompareError(error ?? {});
}

// Explicit false anywhere blocks tools. Unknown is allowed, not advertised as verified.
export function toolCapability(provider, model) {
  const values = [provider?.function_calling, provider?.capabilities?.function_calling,
    model?.capabilities?.function_calling, model?.capabilities?.tools];
  if (values.includes(false)) return false;
  return values.includes(true) ? true : null;
}

export const executionStatusLabels = { running: "Đang chạy", success: "Hoàn tất", error: "Lỗi", stopped: "Đã dừng" };

export function traceValue(value) {
  if (value === null || value === undefined) return "—";
  return typeof value === "string" ? value : JSON.stringify(value, null, 2);
}

// Step traces are canonical. tool_executions is a duplicated server audit and is
// deliberately not rendered. Repeated events update calls by id rather than append.
export function applyExecutionEvent(execution, event) {
  if (event.event === "execution" || event.event === "done") {
    return { ...execution, ...event.data.execution, steps: event.data.execution.steps ?? execution?.steps ?? [] };
  }
  if (!execution) return execution;
  const data = event.data;
  if (event.event === "execution_error") return { ...execution, status: "error", error_code: data.code };
  if (!["step_delta", "tool_call", "tool_result", "step_done"].includes(event.event)) return execution;
  const index = event.event === "step_done" ? data.step.index : data.step_index;
  const steps = [...(execution.steps ?? [])];
  const position = steps.findIndex((step) => step.index === index);
  const previous = position === -1 ? { index, content: "", tool_calls: [] } : steps[position];
  let step = previous;
  if (event.event === "step_delta") step = { ...previous, content: (previous.content ?? "") + (data.text ?? "") };
  else if (event.event === "step_done") step = { ...previous, ...data.step, tool_calls: data.step.tool_calls ?? previous.tool_calls };
  else {
    const calls = [...(previous.tool_calls ?? [])];
    const callIndex = calls.findIndex((call) => call.id === data.tool_call.id);
    if (callIndex === -1) calls.push(data.tool_call);
    else calls[callIndex] = { ...calls[callIndex], ...data.tool_call };
    step = { ...previous, tool_calls: calls };
  }
  if (position === -1) steps.push(step);
  else steps[position] = step;
  return { ...execution, steps: steps.sort((a, b) => a.index - b.index), step_count: steps.length };
}
