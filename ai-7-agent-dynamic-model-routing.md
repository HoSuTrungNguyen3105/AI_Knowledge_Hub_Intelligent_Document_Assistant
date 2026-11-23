# AI Multi-Agent Team – 7 vai trò, tự chọn model theo nhiệm vụ

## 1. Mục tiêu

Hãy kiểm tra và nâng cấp workflow n8n hiện tại thành hệ thống **7 AI role** có khả năng tự phân tích yêu cầu, tự chia việc, tự chọn model phù hợp cho từng task và phối hợp để tạo ra kết quả hoàn chỉnh.

Hệ thống phải xử lý đa lĩnh vực, không giới hạn ở code:
- Lập trình, thiết kế phần mềm, debug, review, kiểm thử.
- Nghiên cứu, phân tích tài liệu, tổng hợp thông tin.
- Kinh doanh, chiến lược, phân tích thị trường và đối thủ.
- Marketing, SEO, nội dung và truyền thông.
- Giáo dục, bài giảng, kế hoạch dạy học và tài liệu.
- Văn phòng: báo cáo, email, quy trình, bảng tính, slide.
- Sáng tạo, lập kế hoạch, phân tích và các công việc hỗn hợp.

Người dùng chỉ đưa yêu cầu. AI Leader điều phối toàn bộ hệ thống.

## 2. Bảy AI role bắt buộc

Giữ 7 vai trò logic sau, nhưng **không khóa cứng model cho từng role**. Model được lựa chọn lại theo loại công việc, độ khó, chi phí, độ trễ và khả năng truy cập provider.

| Role | Trách nhiệm |
|---|---|
| **AI Leader** | Tiếp nhận yêu cầu, xác định mục tiêu, điều phối, phân công, xử lý xung đột và tổng hợp kết quả cuối |
| **AI Planner** | Phân rã mục tiêu thành task, xác định dependency, thứ tự và tiêu chí nghiệm thu |
| **AI Architect** | Thiết kế giải pháp, cấu trúc, phương pháp hoặc kiến trúc phù hợp lĩnh vực |
| **AI Developer / Executor** | Thực hiện task được giao; với code thì viết/chỉnh code, với lĩnh vực khác thì tạo sản phẩm chuyên môn tương ứng |
| **AI Tester / Validator** | Kiểm tra đầu ra theo tiêu chí; chạy test khi có công cụ phù hợp, không giả vờ đã chạy |
| **AI Reviewer** | Phản biện độc lập, kiểm tra tính đúng, đủ, nhất quán, rủi ro và khả năng sử dụng |
| **AI Researcher** | Nghiên cứu, tìm căn cứ, đọc tài liệu được cung cấp hoặc dùng công cụ tìm kiếm nếu workflow có quyền |

Các role có thể phối hợp lặp lại nhiều vòng. Ví dụ, AI Researcher cung cấp thông tin cho Planner; Architect bàn giao thiết kế cho Developer; Tester gửi lỗi về Developer; Reviewer đánh giá bản sửa; Leader quyết định hoàn tất.

**Không được biến mọi yêu cầu thành dự án phần mềm.** Tên Developer/Executor mang nghĩa người thực thi công việc chuyên môn, không chỉ viết code.

## 3. Hiện trạng model cần xử lý

Workflow hiện đang cấu hình cả 7 role cùng dùng:

```text
groq / openai/gpt-oss-20b
```

Đây chỉ là cấu hình hiện tại, không phải lựa chọn tối ưu cố định.

Hãy kiểm tra workflow, credentials và provider đã có trước khi sửa. Mục tiêu là chuyển từ cấu hình một model dùng cho tất cả sang **model routing tự động theo từng task**.

## 4. Yêu cầu tự động lựa chọn model

### 4.1. Nguyên tắc

- AI Leader/Model Router phải đánh giá task trước khi chọn model.
- Chọn model theo năng lực phù hợp với task, không chọn chỉ dựa trên tên thương hiệu.
- Có thể chọn Claude, GPT, DeepSeek, Groq-hosted models, Ollama local models hoặc provider khác **chỉ khi provider đó đã được cấu hình và có credentials/endpoint hợp lệ**.
- Không mặc định rằng dự án đã có API Claude, OpenAI hoặc DeepSeek.
- Không tự tạo API key, không yêu cầu lộ API key trong prompt, không ghi token vào Code node, log hay file JSON.
- Không tự ý xóa hoặc ghi đè credentials đang hoạt động.
- Nếu provider/model chưa được kết nối, đánh dấu `unavailable` và không định tuyến đến đó.
- Không tự đổi model ID theo phỏng đoán. Phải lấy từ danh sách model đã cấu hình hoặc danh sách model được provider hỗ trợ.
- Tách biệt model routing với credentials: credential được quản lý trong n8n Credentials, không nhúng vào workflow JSON.
- Với n8n Cloud, không gọi Ollama qua `localhost` hoặc `host.docker.internal` trên máy cá nhân. Chỉ dùng endpoint từ xa đã cấu hình, có HTTPS và bảo vệ xác thực phù hợp.

### 4.2. Bản đồ năng lực để tham khảo

Đây là hướng dẫn phân loại, **không phải danh sách model được đảm bảo đang có sẵn**:

| Loại nhiệm vụ | Năng lực/model family nên ưu tiên |
|---|---|
| Code phức tạp, sửa lỗi khó, refactor nhiều file | Claude dòng coding mạnh, GPT dòng coding/reasoning mạnh, DeepSeek dòng coder/reasoner mạnh |
| Thiết kế kiến trúc, phân tích hệ thống | Model reasoning mạnh, cửa sổ ngữ cảnh đủ lớn |
| Lập kế hoạch, phân rã task | Model reasoning tốt, tuân thủ JSON ổn định |
| Viết code thông thường | Model coding có chất lượng tốt, tốc độ/chi phí hợp lý |
| Sinh test, debug, phân tích lỗi | Model coding/reasoning tốt |
| Review, phản biện, kiểm tra logic | Model mạnh và độc lập với model tạo đầu ra nếu có thể |
| Nghiên cứu, tổng hợp tài liệu | Model có khả năng đọc ngữ cảnh dài; kết hợp search/retrieval nếu được cấp |
| Viết nội dung, email, báo cáo | Model ngôn ngữ tốt, chi phí hợp lý |
| Phân loại, trích xuất, chuẩn hóa dữ liệu | Model nhỏ/nhanh như Ollama nếu đáp ứng chất lượng |

Khi dự án có nhiều lựa chọn thực tế, hãy chọn model tốt nhất trong số model đã kết nối. Nếu không có model coding chuyên dụng, dùng model reasoning/coding tốt nhất đang khả dụng và ghi rõ đó là lựa chọn thay thế.

### 4.3. Chính sách định tuyến

Tạo một bước **Model Capability Registry** và **Model Router**:

1. Đọc danh sách provider, model ID và credential reference hiện có.
2. Gắn metadata cho từng model: provider, model ID, nhóm năng lực, context limit nếu biết, hỗ trợ tool/function calling nếu biết, trạng thái khả dụng và mức chi phí/tốc độ nếu có dữ liệu.
3. Phân tích task: `domain`, `task_type`, `complexity`, `risk`, `context_size`, `needs_tools`, `needs_json`.
4. Chọn model phù hợp nhất trong danh sách khả dụng.
5. Ghi lại lý do chọn model.
6. Nếu model lỗi, retry có giới hạn; sau đó fallback sang model tương đương đang khả dụng.
7. Nếu không có model phù hợp, dừng task với `needs_configuration` thay vì giả vờ hoàn thành.

Không gọi API thử hàng loạt model trong mỗi execution nếu việc đó tốn chi phí. Ưu tiên registry cấu hình sẵn và health check có giới hạn.

## 5. Cách AI Leader phân công 7 role

Không bắt buộc cả 7 role phải gọi model cho mọi yêu cầu nếu một role không cần thiết. Tuy nhiên, workflow phải giữ đủ 7 role và phải có cơ chế ghi trạng thái `skipped` cùng lý do cho role không cần chạy. Với yêu cầu lớn, phức tạp hoặc đa lĩnh vực, hãy huy động đủ 7 role.

AI Leader tạo task có:
- Mục tiêu cụ thể.
- Phạm vi và việc không thuộc phạm vi.
- Đầu vào.
- Đầu ra bắt buộc.
- Tiêu chí nghiệm thu.
- Dependency.
- Độ ưu tiên.
- Model/provider được chọn và lý do.
- Timeout/retry.

Task độc lập chạy song song; task phụ thuộc chạy sau khi nhận đủ đầu vào.

## 6. Ví dụ tự chọn model theo loại công việc

### Ví dụ A – Xây dựng ứng dụng web
- Leader: model reasoning tốt để điều phối.
- Planner: model reasoning tốt, xuất JSON ổn định.
- Architect: model reasoning/coding mạnh.
- Developer: model coding mạnh nhất đang kết nối (ưu tiên Claude/GPT/DeepSeek coding nếu có).
- Tester: model coding/reasoning phù hợp để tạo và phân tích test.
- Reviewer: model reasoning mạnh, tốt nhất khác model Developer nếu có.
- Researcher: model đọc tài liệu tốt; dùng công cụ tìm kiếm nếu workflow có.

### Ví dụ B – Lập kế hoạch marketing
- Leader: model reasoning.
- Planner: model lập kế hoạch.
- Architect: chuyên gia cấu trúc chiến dịch.
- Developer/Executor: model viết nội dung và deliverable marketing.
- Tester/Validator: kiểm tra thông điệp, tính nhất quán và tiêu chí chiến dịch.
- Reviewer: phản biện chiến lược và rủi ro.
- Researcher: nghiên cứu thị trường/khách hàng/đối thủ từ nguồn được phép.

### Ví dụ C – Soạn báo cáo hoặc bài thuyết trình
Bảy role tự đổi nhiệm vụ tương ứng: điều phối, lập dàn ý, thiết kế cấu trúc, soạn nội dung, kiểm tra dữ liệu/định dạng, biên tập độc lập và nghiên cứu căn cứ.

## 7. Quy trình phối hợp

1. **Intake:** nhận yêu cầu, đầu ra mong muốn, ràng buộc và tài liệu.
2. **Research:** thu thập căn cứ cần thiết; phân biệt dữ kiện, suy luận và giả định.
3. **Planning:** Leader + Planner chia task, dependency và tiêu chí nghiệm thu.
4. **Routing:** Model Router chọn model phù hợp cho từng task.
5. **Execution:** Architect và Developer/Executor tạo giải pháp, sản phẩm hoặc nội dung.
6. **Validation:** Tester kiểm tra từng đầu ra.
7. **Review:** Reviewer phản biện độc lập.
8. **Revision:** task lỗi quay lại đúng role phụ trách; tối đa 2 vòng sửa mặc định.
9. **Finalization:** Leader tổng hợp, ghi trạng thái và bàn giao.

Agent phải trao đổi qua dữ liệu có cấu trúc trong workflow, không chỉ dựa vào hội thoại ngầm. Mọi bàn giao phải chứa `project_id`, `task_id`, `from_role`, `to_role`, `summary`, `artifacts`, `open_questions` và `status`.

## 8. JSON contract – Model Registry

```json
{
  "available_models": [
    {
      "provider": "groq",
      "model_id": "openai/gpt-oss-20b",
      "credential_name": "Tên credential trong n8n, không phải secret",
      "capabilities": ["reasoning", "general"],
      "status": "available"
    }
  ]
}
```

Chỉ đưa vào registry những model thực sự được cấu hình. Không đưa API key vào JSON.

## 9. JSON contract – Kế hoạch của Leader/Planner

```json
{
  "project_id": "project-unique-id",
  "project_summary": "Mục tiêu tổng thể",
  "domain": ["software", "research"],
  "expected_outputs": ["Sản phẩm A", "Báo cáo B"],
  "assumptions": [],
  "tasks": [
    {
      "task_id": "task-1",
      "role": "AI Researcher",
      "objective": "Mục tiêu cụ thể",
      "instructions": "Hướng dẫn thực hiện",
      "input_from": [],
      "depends_on": [],
      "model_selection": {
        "provider": "groq",
        "model_id": "openai/gpt-oss-20b",
        "reason": "Model hiện có phù hợp với task",
        "fallback": []
      },
      "complexity": "medium",
      "priority": "high",
      "acceptance_criteria": [],
      "output_format": "json",
      "status": "planned"
    }
  ]
}
```

Quy tắc:
- Một project có thể có nhiều task; không ép mọi yêu cầu thành cùng một sơ đồ.
- Mỗi role có thể có một hoặc nhiều task khi thực sự cần.
- Không tạo dependency vòng tròn.
- Model ID phải có trong registry và trạng thái khả dụng.
- Nếu thiếu provider/model, ghi `needs_configuration`.

## 10. JSON contract – Kết quả mỗi role

```json
{
  "project_id": "project-unique-id",
  "task_id": "task-1",
  "role": "AI Developer",
  "provider": "groq",
  "model_id": "openai/gpt-oss-20b",
  "status": "completed",
  "summary": "Tóm tắt",
  "deliverables": [],
  "evidence": [],
  "assumptions": [],
  "risks": [],
  "handoff": {
    "to_role": "AI Tester",
    "notes": "Các điểm cần kiểm tra"
  },
  "needs_human_input": false
}
```

## 11. JSON contract – Review

```json
{
  "status": "approved",
  "score": 0,
  "issues": [],
  "missing_requirements": [],
  "contradictions": [],
  "unsupported_claims": [],
  "required_revisions": [],
  "final_notes": []
}
```

Chỉ duyệt khi đạt tiêu chí nghiệm thu và không còn lỗi nghiêm trọng.

## 12. Yêu cầu chỉnh sửa workflow n8n hiện tại

Trước khi sửa:
1. Đọc workflow JSON hiện tại và kiểm tra toàn bộ node/connection.
2. Kiểm tra bảy role đang dùng `groq / openai/gpt-oss-20b`.
3. Kiểm tra các credentials/provider thực tế đang tồn tại trong n8n.
4. Phân biệt provider đã kết nối với provider mới chỉ là ý tưởng.

Khi sửa:
- Giữ nguyên 7 role logic.
- Thêm Model Capability Registry và Model Router.
- Cho phép mỗi role/task dùng model khác nhau.
- Ưu tiên model coding mạnh cho task code; model reasoning cho lập kế hoạch/kiến trúc/review; model nhanh/nhẹ cho task đơn giản.
- Có thể dùng Claude, GPT, DeepSeek hoặc model khác khi đã có credentials và endpoint.
- Nếu chưa có credentials, tạo danh sách cấu hình còn thiếu và hướng dẫn người dùng kết nối; không tự tạo hoặc giả lập credentials.
- Giữ nguyên credential reference, không xuất secret vào workflow JSON.
- Không thêm node/provider chưa được người dùng cho phép nếu nó phát sinh chi phí hoặc cần tài khoản mới.
- Dùng Switch/IF để route theo provider/model.
- Xử lý lỗi, timeout, retry, fallback, rate limit và output không hợp lệ.
- Không để Merge chờ vô hạn nếu một nhánh thất bại.
- Lưu model đã chọn, lý do chọn, trạng thái và thời gian thực thi của từng task.
- Có thể xuất workflow JSON để import lại; kiểm tra JSON parse được, node connections hợp lệ và không có credential secret trước khi bàn giao.

## 13. Prompt giao việc cho AI đang chỉnh dự án

> Hãy đọc toàn bộ tài liệu này và kiểm tra workflow n8n hiện tại. Hiện có 7 role: AI Leader, AI Planner, AI Architect, AI Developer, AI Tester, AI Reviewer và AI Researcher; cả 7 đang dùng `groq / openai/gpt-oss-20b`. Hãy nâng cấp thành hệ thống tự phân tích task và tự chọn model phù hợp cho từng role/task. Không khóa tất cả vào một model. Với code phức tạp, ưu tiên model coding mạnh như Claude, GPT coding hoặc DeepSeek coder/reasoner nếu provider đó đã được kết nối. Với lập kế hoạch, kiến trúc và review, chọn model reasoning phù hợp. Với task nhẹ, có thể chọn model nhanh/nhẹ hoặc Ollama nếu đủ năng lực. Hãy kiểm tra credentials và model thực tế trước khi định tuyến; không giả định Claude/OpenAI/DeepSeek đã có API key. Không tự tạo, tiết lộ hoặc ghi đè API key. Nếu cần provider mới, báo rõ tên credential cần người dùng tự kết nối trong n8n. Giữ nguyên bảy role, cho phép các role trao đổi và bàn giao kết quả, chạy song song khi độc lập, kiểm thử và review trước khi tổng hợp. Hệ thống phải hỗ trợ nhiều lĩnh vực, không chỉ code. Sau khi chỉnh sửa, xuất file JSON workflow hoàn chỉnh để import vào n8n và báo rõ provider/model nào hoạt động ngay, provider/model nào cần cấu hình thêm.
