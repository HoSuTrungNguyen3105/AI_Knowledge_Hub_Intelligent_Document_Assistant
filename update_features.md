# TASK: XÂY DỰNG AI TOKEN & API USAGE ANALYTICS CHO MINDFLOW

## 1. Mục tiêu

Xây dựng module **AI Usage & Cost Analytics** trong MindFlow để theo dõi toàn bộ mức sử dụng API của các nhà cung cấp AI.

Các nhà cung cấp cần hỗ trợ:

- OpenAI
- Anthropic Claude
- Google Gemini
- DeepSeek
- Groq
- Custom OpenAI-compatible API

Mục tiêu là giúp người quản trị biết:

- Đã sử dụng bao nhiêu token?
- Input Token và Output Token là bao nhiêu?
- Đã tiêu tốn bao nhiêu tiền cho API?
- Model nào đang được sử dụng nhiều nhất?
- AI Agent nào tiêu tốn nhiều token nhất?
- Workflow nào tiêu tốn nhiều chi phí nhất?
- Chi phí theo ngày, tuần, tháng.
- Nhà cung cấp nào đang được sử dụng nhiều nhất?

**Lưu ý:** Đây là module phân tích dữ liệu sử dụng API, không phải hệ thống thay thế LLM Gateway hiện tại.

---

## 2. Yêu cầu bắt buộc trước khi code

Trước tiên, hãy kiểm tra toàn bộ codebase MindFlow để xác định:

1. Cấu trúc LLM Gateway hiện tại.
2. Các provider đã tích hợp.
3. Các service gọi API AI.
4. Cách xử lý streaming.
5. Cấu trúc database hiện tại.
6. Cách quản lý API Key.
7. Agent Studio và Agent Conversations.
8. Workflow Automation và hệ thống Execution Logs.
9. Các module Dashboard và quản lý người dùng.

Sau khi kiểm tra, lập bảng:

| Chức năng | Đã có | Cần bổ sung |
|---|---|---|
| LLM Gateway | Kiểm tra code | |
| Provider Management | Kiểm tra code | |
| Token Tracking | Kiểm tra code | |
| Cost Calculation | Kiểm tra code | |
| Usage Dashboard | Kiểm tra code | |
| Agent Usage Tracking | Kiểm tra code | |
| Workflow Usage Tracking | Kiểm tra code | |

Không được tạo thêm hệ thống trùng với các chức năng đã tồn tại.

---

## 3. Thiết kế giao diện

Tạo một khu vực mới có tên:

**AI Usage & Analytics**

Có thể đặt trong khu vực Settings / AI Providers / Usage hoặc vị trí phù hợp với kiến trúc giao diện hiện tại.

### 3.1. Overview Dashboard

Hiển thị các thống kê:

- Total Tokens
- Input Tokens
- Output Tokens
- Total Estimated Cost
- Total API Requests
- Average Cost per Request

Có bộ lọc:

- Hôm nay
- 7 ngày
- 30 ngày
- Tháng này
- Tháng trước
- Tùy chỉnh thời gian

Các số liệu phải lấy từ database thực tế, không dùng dữ liệu mock trong production.

### 3.2. Biểu đồ sử dụng Token

Tạo biểu đồ thể hiện:

- Input Tokens theo thời gian.
- Output Tokens theo thời gian.
- Total Tokens theo thời gian.
- Chi phí API theo ngày.

Cho phép chuyển đổi giữa các chế độ xem.

### 3.3. Provider Usage

Hiển thị mức sử dụng theo nhà cung cấp:

| Provider | Requests | Input Tokens | Output Tokens | Estimated Cost |
|---|---:|---:|---:|---:|
| OpenAI | | | | |
| Claude | | | | |
| Gemini | | | | |
| DeepSeek | | | | |
| Groq | | | | |

Có thể nhấn vào từng Provider để xem chi tiết.

### 3.4. Model Usage

Thống kê theo từng model:

- Model Name
- Provider
- Total Requests
- Input Tokens
- Output Tokens
- Total Tokens
- Estimated Cost
- Average Latency

Cho phép sắp xếp theo:

- Token sử dụng nhiều nhất.
- Chi phí cao nhất.
- Request nhiều nhất.
- Latency cao nhất.

### 3.5. Agent Usage

Thống kê mức tiêu thụ của từng AI Agent:

- Agent Name
- Provider
- Model
- Total Requests
- Total Tokens
- Estimated Cost
- Success Rate

Mục đích: biết Agent nào đang tiêu tốn nhiều tài nguyên nhất.

### 3.6. Workflow Usage

Thống kê chi phí của từng workflow:

- Workflow Name
- Execution Count
- AI Requests
- Total Tokens
- Estimated Cost
- Average Execution Time

Đặc biệt phải phân biệt chi phí AI API với chi phí hạ tầng hoặc chi phí dịch vụ bên ngoài.

### 3.7. Usage History

Tạo bảng lịch sử từng lần gọi AI:

| Thông tin | Mô tả |
|---|---|
| Time | Thời gian gọi API |
| Provider | Nhà cung cấp |
| Model | Model được sử dụng |
| Agent | Agent thực hiện |
| Workflow | Workflow liên quan |
| Input Tokens | Token đầu vào |
| Output Tokens | Token đầu ra |
| Total Tokens | Tổng token |
| Cost | Chi phí ước tính |
| Latency | Thời gian phản hồi |
| Status | Thành công / Thất bại |

Yêu cầu:

- Tìm kiếm.
- Lọc theo Provider.
- Lọc theo Model.
- Lọc theo Agent.
- Lọc theo thời gian.
- Phân trang.
- Xuất CSV.

Không lưu toàn bộ nội dung prompt và response nếu không thực sự cần thiết. Ưu tiên lưu metadata và usage.

---

## 4. Backend Architecture

Tận dụng LLM Gateway hiện tại để ghi nhận usage sau mỗi lần gọi API.

Luồng đề xuất:

User Request
→ LLM Gateway
→ Provider Adapter
→ AI Provider
→ Response
→ Extract Usage Metadata
→ Calculate Cost
→ Save Usage Record
→ Analytics Dashboard

Không tạo một service gọi API AI mới.

### 4.1. Usage Tracking Service

Tạo hoặc mở rộng service phù hợp với kiến trúc hiện tại.

Các nhiệm vụ:

- Nhận usage metadata từ provider.
- Chuẩn hóa dữ liệu.
- Ghi nhận token.
- Tính chi phí.
- Gắn thông tin Agent.
- Gắn thông tin Workflow.
- Ghi nhận trạng thái request.
- Tổng hợp dữ liệu thống kê.

### 4.2. Chuẩn hóa Usage Metadata

Thiết kế cấu trúc dữ liệu thống nhất:

```json
{
  "provider": "openai",
  "model": "gpt-model",
  "inputTokens": 1200,
  "outputTokens": 450,
  "totalTokens": 1650,
  "cachedInputTokens": 0,
  "reasoningTokens": 0,
  "estimatedCost": 0,
  "currency": "USD",
  "latencyMs": 2400,
  "status": "success",
  "agentId": null,
  "workflowId": null,
  "conversationId": null,
  "userId": null,
  "createdAt": "ISO_DATE"
}
```

Đây là schema minh họa. Hãy điều chỉnh theo cấu trúc database hiện tại.

Không phải provider nào cũng trả về đầy đủ các trường. Những trường không có dữ liệu phải được xử lý đúng, không tự tạo số liệu.

### 4.3. Database

Kiểm tra database hiện tại trước khi tạo collection mới.

Nếu đang sử dụng MongoDB, có thể bổ sung collection:

**ai_usage_logs**

Các trường đề xuất:

- userId
- provider
- model
- inputTokens
- outputTokens
- totalTokens
- cachedInputTokens
- reasoningTokens
- estimatedCost
- currency
- latencyMs
- status
- agentId
- workflowId
- conversationId
- requestId
- createdAt

Tạo index phù hợp cho:

- userId + createdAt
- provider + createdAt
- model + createdAt
- agentId + createdAt
- workflowId + createdAt

Không lưu API Key dạng plaintext.

Không lưu dữ liệu usage trùng lặp nếu đã có hệ thống logging phù hợp.

---

## 5. Tính toán chi phí API

Đây là phần rất quan trọng.

Không được sử dụng một mức giá chung cho tất cả model.

Xây dựng cơ chế quản lý bảng giá:

**AI Model Pricing**

Mỗi model cần có:

- Provider
- Model ID
- Input Price per 1M Tokens
- Output Price per 1M Tokens
- Cached Input Price nếu có
- Effective Date
- Currency
- Pricing Version

Công thức cơ bản:

```text
Input Cost = Input Tokens / 1,000,000 * Input Price

Output Cost = Output Tokens / 1,000,000 * Output Price

Estimated Cost = Input Cost + Output Cost
```

Đối với model có cached tokens, reasoning tokens hoặc các loại token tính phí riêng, phải áp dụng đúng quy tắc giá của provider.

Yêu cầu:

1. Có thể cập nhật bảng giá mà không phải sửa code.
2. Không ghi đè bảng giá cũ đã sử dụng để tính lịch sử.
3. Mỗi usage record cần lưu pricing version hoặc đơn giá áp dụng.
4. Phân biệt Estimated Cost và Actual Provider Billing.
5. Không tuyên bố số liệu ước tính là hóa đơn thực tế.
6. Có thể hiển thị chi phí bằng USD và quy đổi VND nếu có tỷ giá hợp lệ.

---

## 6. Xử lý Streaming

Kiểm tra tất cả các provider đang hỗ trợ streaming.

Yêu cầu:

- Thu thập usage metadata từ response cuối cùng.
- Đối với OpenAI, xử lý đúng cơ chế include_usage khi dùng Chat Completions streaming.
- Đối với các provider khác, tuân thủ định dạng streaming riêng.
- Không ghi nhận token nhiều lần khi nhận nhiều chunk.
- Có cơ chế xử lý khi stream bị ngắt giữa chừng.
- Phân biệt request thành công, thất bại và bị hủy.
- Không tự ước lượng token nếu provider không cung cấp usage, trừ khi có cơ chế tính riêng được đánh dấu rõ là estimated.

---

## 7. API Endpoints

Kiểm tra quy ước API hiện tại trước khi triển khai.

Các endpoint đề xuất:

```http
GET /api/ai-usage/overview
GET /api/ai-usage/timeseries
GET /api/ai-usage/providers
GET /api/ai-usage/models
GET /api/ai-usage/agents
GET /api/ai-usage/workflows
GET /api/ai-usage/history
GET /api/ai-usage/export
GET /api/ai-usage/pricing
PUT /api/ai-usage/pricing/:id
```

Các API cần hỗ trợ:

- Date range.
- Provider filter.
- Model filter.
- Agent filter.
- Workflow filter.
- Pagination.
- Sorting.

Phải kiểm tra quyền truy cập để người dùng không xem được usage của người dùng khác.

---

## 8. Quản lý ngân sách và cảnh báo

Bổ sung chức năng quản lý ngân sách:

- Đặt giới hạn chi phí theo tháng.
- Đặt giới hạn theo Provider.
- Đặt giới hạn theo Agent.
- Cảnh báo khi đạt 50%, 80%, 100%.
- Hiển thị phần ngân sách còn lại.

Ví dụ:

```text
Monthly Budget: $50

Current Usage: $35

Remaining: $15

Usage: 70%
```

Có thể tích hợp thông báo vào hệ thống Notification hiện tại.

Lưu ý: Cảnh báo ngân sách không đồng nghĩa với việc tự động ngắt API. Chỉ bổ sung cơ chế chặn request khi người quản trị chủ động bật giới hạn cứng và hệ thống đã xử lý an toàn.

---

## 9. Giao diện và trải nghiệm người dùng

Yêu cầu UI:

- Đồng bộ hoàn toàn với design system hiện tại của MindFlow.
- Responsive Desktop / Tablet / Mobile.
- Không tạo giao diện tách biệt khỏi hệ thống.
- Biểu đồ dễ đọc.
- Có loading state.
- Có empty state.
- Có error state.
- Có tooltip giải thích Token và Cost.
- Có khả năng cập nhật dữ liệu.
- Không sử dụng dữ liệu giả để hiển thị như dữ liệu thật.

Ưu tiên giao diện chuyên nghiệp, gọn, dễ quan sát.

Không nhồi quá nhiều biểu đồ vào cùng một màn hình.

---

## 10. Bảo mật và tối ưu

- Chỉ người có quyền phù hợp mới được xem thống kê tổng thể.
- Người dùng thông thường chỉ xem dữ liệu của chính mình.
- Không trả API Key về frontend.
- Không lưu prompt và response đầy đủ nếu không cần thiết.
- Không cho phép người dùng sửa usage logs.
- Chống ghi nhận trùng request.
- Có requestId để đối soát.
- Tối ưu aggregate query.
- Phân trang lịch sử.
- Có thể dùng cache cho dashboard.
- Không gọi API provider liên tục chỉ để cập nhật dashboard.

---

## 11. Testing

Phải kiểm tra:

1. Gọi OpenAI API và ghi nhận token.
2. Gọi Claude API và ghi nhận token.
3. Gọi Gemini API và ghi nhận token.
4. Gọi DeepSeek API và ghi nhận token.
5. Gọi API qua streaming.
6. Request thất bại.
7. Request bị hủy.
8. Request thiếu usage metadata.
9. Tính toán chi phí theo đúng model.
10. Lọc thống kê theo ngày.
11. Thống kê theo Agent.
12. Thống kê theo Workflow.
13. Phân quyền dữ liệu người dùng.
14. Xuất CSV.
15. Kiểm tra không ghi nhận usage trùng lặp.

Đối chiếu một số request thực tế với dashboard của provider để kiểm tra độ chính xác.

---

## 12. Kế hoạch triển khai

### Phase 1: Audit và Usage Tracking
- Kiểm tra LLM Gateway.
- Xác định nơi nhận usage metadata.
- Chuẩn hóa dữ liệu.
- Lưu usage logs.
- Xử lý streaming.

### Phase 2: Cost Calculation
- Xây dựng model pricing.
- Tính toán chi phí.
- Lưu lịch sử giá.
- Kiểm tra tính chính xác.

### Phase 3: Analytics Dashboard
- Overview.
- Provider Usage.
- Model Usage.
- Token Charts.
- Usage History.

### Phase 4: Agent & Workflow Analytics
- Thống kê theo Agent.
- Thống kê theo Workflow.
- Phân tích chi phí từng tác vụ.

### Phase 5: Budget & Notifications
- Quản lý ngân sách.
- Cảnh báo chi phí.
- Tích hợp Notification.

---

## 13. Yêu cầu bàn giao

Sau khi hoàn thành, cần cung cấp:

1. Source code frontend.
2. Source code backend.
3. Database schema.
4. API documentation.
5. Tài liệu kiến trúc.
6. Danh sách file mới và file đã chỉnh sửa.
7. Danh sách chức năng hoàn thành.
8. Báo cáo test.
9. Những vấn đề còn tồn tại.
10. Hướng dẫn cấu hình và triển khai.

Xuất toàn bộ báo cáo kỹ thuật thành file Markdown và Word.

Nếu có nhiều file tài liệu, đóng gói thành ZIP.

---

## 14. Nguyên tắc quan trọng

- Không xây lại LLM Gateway.
- Không xây lại Provider Management.
- Không tạo một hệ thống API Key riêng.
- Không thay đổi kiến trúc hiện tại nếu không cần thiết.
- Không phá vỡ các chức năng Chat, Agent, Streaming và Workflow hiện có.
- Không sử dụng dữ liệu mock trong môi trường production.
- Không tuyên bố đã tích hợp nếu chưa có request thực tế.
- Ưu tiên tái sử dụng service, database và component hiện tại.
- Chia nhỏ công việc theo từng phase.
- Sau mỗi phase phải kiểm tra build, test và regression.

**Mục tiêu cuối cùng:**

MindFlow phải có một hệ thống theo dõi AI Usage tập trung, giúp quản trị viên biết chính xác lượng token được provider báo cáo, ước tính chi phí, theo dõi từng model, Agent và Workflow, đồng thời kiểm soát ngân sách API.

Hãy bắt đầu bằng việc audit codebase và đề xuất phương án tích hợp trước khi chỉnh sửa code. Không tự ý xây toàn bộ module mới khi chưa xác định những phần đã có.