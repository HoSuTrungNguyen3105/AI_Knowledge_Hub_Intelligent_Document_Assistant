# MindFlow AI — Phase 6: Multi-Agent Collaboration & Communication

## 1. Mục tiêu

Mở rộng **dự án MindFlow AI hiện tại** bằng chức năng Multi-Agent Collaboration: nhiều AI Agent có thể giao tiếp hai chiều, nhận/giao nhiệm vụ, trao đổi kết quả, phản biện, yêu cầu sửa đổi và phối hợp hoàn thành một mục tiêu chung.

Đây là **phần mở rộng trên nền tảng đã có**, không phải dự án mới.

### Nguyên tắc bắt buộc

- Đọc README.md và `ARCHITECTURE.md` trước khi sửa code.
- Giữ nguyên kiến trúc, quy ước code, xác thực, phân quyền và giao diện hiện tại.
- Không tạo lại các chức năng đã có trong Phase 1–5.
- Không thay Next.js bằng React/Vite.
- Không thay FastAPI bằng Node.js/Express.
- Không thay MongoDB bằng Google Sheets hoặc PostgreSQL.
- Không tạo hệ thống Agent độc lập tách khỏi AI Agent Studio hiện có.
- Tái sử dụng provider adapters, model registry, streaming SSE, Agent CRUD, function calling, execution history và tool audit hiện tại.
- Không dùng dữ liệu giả để mô phỏng Agent đang giao tiếp.
- Triển khai tăng dần, giữ tương thích ngược và không làm hỏng các route/API hiện có.

## 2. Hiện trạng dự án cần giữ nguyên

Theo README hiện tại, MindFlow AI đã có:

### Frontend
- Next.js App Router, JavaScript/JSX.
- Tailwind CSS, Axios, Zustand, Lucide.
- Các trang `/settings`, `/chat`, `/compare`, `/agents`.
- Đăng nhập và route bảo vệ bằng cơ chế xác thực hiện tại.
- Streaming SSE cho Chat, Compare và Agent Execution.

### Backend
- FastAPI async, Pydantic, Motor (MongoDB async).
- API prefix `/api/v1`.
- Provider adapters cho OpenAI, Gemini và Groq.
- API key của từng người dùng được mã hóa Fernet trong MongoDB; không trả key về browser.
- JWT access/refresh qua HttpOnly cookies.
- Phân quyền dữ liệu theo user hiện tại.
- Các collections đang có, cần tái sử dụng khi phù hợp:
  - `agents`
  - `agent_executions`
  - `tool_executions`
  - `user_provider_credentials`
  - `ai_models`
  - `conversations`
  - `messages`
  - `ai_requests`
  - `comparisons`
- Agent hiện đã có system prompt, provider/model, temperature, giới hạn token, tools allowlist và lịch sử chạy.
- Tool hiện có: Calculator, DateTime, Data Analyzer.
- Agent Execution hiện là từng lần chạy độc lập; chưa có memory dài hạn và chưa có cơ chế nhiều Agent phối hợp trong cùng một workflow.

**Không được giả định có những subsystem chưa được README xác nhận.** Nếu code thực tế khác README, kiểm tra code và `ARCHITECTURE.md`, sau đó báo rõ khác biệt trước khi thay đổi.

## 3. Phạm vi Phase 6

Xây dựng các chức năng sau:

1. Tạo một nhóm Agent (Agent Team) từ các Agent đã tồn tại trong `/agents`.
2. Tạo một workflow/project run với mục tiêu chung.
3. Có một Coordinator/Leader điều phối các Agent trong nhóm.
4. Agent gửi tin nhắn cho Agent khác thông qua Backend.
5. Agent có thể giao nhiệm vụ, đặt câu hỏi, phản hồi, bàn giao và yêu cầu sửa đổi.
6. Agent nhận được đúng context và lịch sử liên quan đến nhiệm vụ của mình.
7. Lưu toàn bộ message, task, trạng thái và execution trace trong MongoDB.
8. Giao diện hiển thị trao đổi và tiến độ gần realtime.
9. Có thể dừng, tiếp tục hoặc xem lại workflow.
10. Giới hạn vòng lặp, thời gian, số lần gọi model và ngân sách token.

Không yêu cầu Agent tự do nói chuyện vô hạn. Orchestrator phải kiểm soát lượt, điều kiện chuyển tiếp và kết thúc workflow.

## 4. Kiến trúc mở rộng

Giữ nguyên Next.js → FastAPI → MongoDB và bổ sung lớp điều phối Multi-Agent.

```text
Next.js Frontend
    |
    | Existing auth cookies / API / SSE
    v
FastAPI Backend
    |
    +-- Existing Provider Adapters
    |      +-- OpenAI
    |      +-- Gemini
    |      +-- Groq
    |
    +-- Existing Agent Service
    |      +-- Agent configuration
    |      +-- System prompt
    |      +-- Tool allowlist
    |      +-- Model selection
    |
    +-- NEW Multi-Agent Orchestrator
    |      +-- Workflow Manager
    |      +-- Agent Team Manager
    |      +-- Task Manager
    |      +-- Message Manager
    |      +-- Context Builder
    |      +-- Execution Coordinator
    |      +-- Loop / Budget Guard
    |
    v
MongoDB
    +-- Existing collections
    +-- agent_teams
    +-- agent_workflows
    +-- agent_tasks
    +-- agent_messages
    +-- agent_workflow_events
```

### Quy tắc giao tiếp

- Agent không gọi trực tiếp API của Agent khác.
- Agent không truy cập MongoDB trực tiếp.
- Mọi message/task phải đi qua Message Manager và Orchestrator.
- Orchestrator xác định Agent nhận, kiểm tra quyền, dựng context, gọi provider adapter và lưu kết quả.
- Khi Agent hoàn tất, Orchestrator quyết định Agent tiếp theo dựa trên workflow state và kết quả thực tế.
- Dùng chung provider adapters hiện có; không viết một lớp gọi Groq/OpenAI/Gemini thứ hai.
- Dùng chung cơ chế mã hóa credential và xác thực hiện có.

## 5. Cách Agent giao tiếp qua lại

### 5.1. Message là dữ liệu được lưu bền vững

Mỗi message cần có tối thiểu:

```json
{
  "id": "message_id",
  "workflow_id": "workflow_id",
  "task_id": "task_id",
  "from_agent_id": "agent_id_or_user",
  "to_agent_id": "agent_id_or_coordinator",
  "message_type": "TASK_ASSIGNMENT",
  "content": "Hãy lập kế hoạch triển khai chức năng đăng nhập.",
  "context_refs": [],
  "status": "PENDING",
  "created_at": "ISO-8601",
  "processed_at": null
}
```

Các `message_type` tối thiểu:

- `USER_REQUEST`
- `TASK_ASSIGNMENT`
- `MESSAGE`
- `QUESTION`
- `RESPONSE`
- `HANDOFF`
- `TASK_COMPLETED`
- `TASK_FAILED`
- `REVIEW_REQUEST`
- `REVISION_REQUEST`
- `APPROVAL`
- `WORKFLOW_UPDATE`

Các trạng thái message:

- `PENDING`
- `PROCESSING`
- `DELIVERED`
- `COMPLETED`
- `FAILED`

Không dùng message status để thay thế task/workflow status.

### 5.2. Ví dụ hội thoại thực tế

Người dùng yêu cầu: “Phân tích và đề xuất cách bổ sung chức năng Knowledge Base vào MindFlow AI.”

1. User gửi yêu cầu tạo workflow.
2. Coordinator giao Planner lập kế hoạch.
3. Planner gửi câu hỏi cho Architect để xác định ảnh hưởng đến kiến trúc hiện tại.
4. Architect đọc thông tin dự án được cung cấp, phản hồi Planner.
5. Planner tổng hợp kế hoạch và gửi Coordinator.
6. Coordinator giao Researcher nghiên cứu các lựa chọn nếu có công cụ nghiên cứu khả dụng.
7. Coordinator giao Reviewer đánh giá kế hoạch.
8. Reviewer có thể gửi `REVISION_REQUEST` cho Planner.
9. Planner cập nhật và gửi lại.
10. Coordinator tổng hợp kết quả cuối cùng cho người dùng.

Đây phải là các lượt gọi model thực tế, với nội dung message được lưu và có trace. Không tạo sẵn chuỗi hội thoại minh họa để giả vờ Agent đang làm việc.

### 5.3. Context cho từng Agent

Mỗi lần gọi Agent cần tạo context có chọn lọc:

- System prompt và cấu hình Agent.
- Mục tiêu workflow.
- Task hiện tại và task phụ thuộc.
- Message liên quan trực tiếp đến Agent.
- Kết quả của Agent tiền nhiệm cần thiết.
- Các giới hạn và định dạng output.

Không gửi toàn bộ lịch sử của tất cả Agent vào mọi lần gọi model. Phải giới hạn context để giảm token và tránh lộ dữ liệu không liên quan.

## 6. Vai trò Agent

Không bắt buộc tạo cứng một bộ Agent mới. Ưu tiên chọn các Agent đã được người dùng tạo trong `/agents` và gán vai trò trong Team.

Vai trò gợi ý:

| Role | Trách nhiệm |
|---|---|
| Coordinator / Leader | Điều phối workflow, giao việc, quyết định bước tiếp theo, tổng hợp |
| Planner | Chia mục tiêu thành task và xác định phụ thuộc |
| Architect | Phân tích kiến trúc, thiết kế giải pháp |
| Developer | Thực hiện nhiệm vụ lập trình/phân tích kỹ thuật trong phạm vi được cấp |
| Tester | Kiểm tra và báo lỗi |
| Reviewer | Phản biện, đánh giá, phê duyệt hoặc yêu cầu sửa |
| Researcher | Nghiên cứu khi có công cụ/dữ liệu phù hợp |

Mỗi Agent trong Team phải tham chiếu một Agent configuration đã tồn tại, bao gồm provider, model, system prompt, temperature và tools được phép.

Nếu Agent bị xóa hoặc provider/model không còn khả dụng, workflow phải báo lỗi rõ ràng; không tự thay bằng model giả hoặc Agent khác mà không thông báo.

## 7. MongoDB data design

Trước khi tạo collection mới, kiểm tra `ARCHITECTURE.md` và schema thực tế để tránh trùng dữ liệu. Dùng các collection mới sau nếu chưa có cấu trúc tương đương.

### 7.1. `agent_teams`

Lưu nhóm Agent theo user:

- `_id`
- `user_id`
- `name`
- `description`
- `coordinator_agent_id`
- `members`: danh sách `{agent_id, role, enabled}`
- `created_at`
- `updated_at`

### 7.2. `agent_workflows`

Lưu lần chạy phối hợp:

- `_id`
- `user_id`
- `team_id`
- `title`
- `goal`
- `status`: `queued | running | waiting | completed | failed | cancelled`
- `current_step`
- `max_steps`
- `budget`
- `usage`
- `final_result`
- `error_code`
- `created_at`
- `updated_at`
- `completed_at`

### 7.3. `agent_tasks`

Lưu công việc được giao:

- `_id`
- `user_id`
- `workflow_id`
- `parent_task_id`
- `title`
- `description`
- `assigned_agent_id`
- `created_by_agent_id`
- `depends_on`
- `status`: `pending | in_progress | review | completed | failed | cancelled`
- `priority`
- `result`
- `revision_count`
- `created_at`
- `updated_at`

### 7.4. `agent_messages`

Lưu giao tiếp giữa Agent:

- `_id`
- `user_id`
- `workflow_id`
- `task_id`
- `from_agent_id`
- `to_agent_id`
- `message_type`
- `content`
- `context_refs`
- `status`
- `created_at`
- `processed_at`
- `error_code`

### 7.5. `agent_workflow_events`

Lưu event phục vụ timeline/audit:

- `_id`
- `user_id`
- `workflow_id`
- `event_type`
- `actor_id`
- `payload`
- `created_at`

### 7.6. Index và ownership

Tạo index phù hợp, tối thiểu:
- `agent_teams`: `{user_id, updated_at}`
- `agent_workflows`: `{user_id, created_at}`, `{team_id, status}`
- `agent_tasks`: `{workflow_id, status}`, `{assigned_agent_id, status}`
- `agent_messages`: `{workflow_id, created_at}`, `{to_agent_id, status}`
- `agent_workflow_events`: `{workflow_id, created_at}`

Mọi truy vấn phải giới hạn theo `user_id` lấy từ authenticated request, không tin `user_id` do frontend gửi lên. Tạo index theo cách idempotent phù hợp cơ chế khởi động hiện tại; không dùng SQL migration/Alembic.

## 8. API đề xuất

Giữ prefix `/api/v1`, router conventions và response/error format hiện tại. Tất cả endpoint cần đăng nhập, kiểm tra ownership, `Cache-Control: no-store`, CSRF Origin protection và rate limit theo quy tắc đang áp dụng.

### Teams

- `GET /api/v1/ai/agent-teams`
- `POST /api/v1/ai/agent-teams`
- `GET /api/v1/ai/agent-teams/{team_id}`
- `PATCH /api/v1/ai/agent-teams/{team_id}`
- `DELETE /api/v1/ai/agent-teams/{team_id}`

### Workflows

- `GET /api/v1/ai/agent-workflows`
- `POST /api/v1/ai/agent-workflows`
- `GET /api/v1/ai/agent-workflows/{workflow_id}`
- `POST /api/v1/ai/agent-workflows/{workflow_id}/start`
- `POST /api/v1/ai/agent-workflows/{workflow_id}/pause`
- `POST /api/v1/ai/agent-workflows/{workflow_id}/resume`
- `POST /api/v1/ai/agent-workflows/{workflow_id}/cancel`
- `GET /api/v1/ai/agent-workflows/{workflow_id}/messages`
- `GET /api/v1/ai/agent-workflows/{workflow_id}/tasks`
- `GET /api/v1/ai/agent-workflows/{workflow_id}/events`

Có thể điều chỉnh endpoint theo convention đang có sau khi kiểm tra source code. Không tạo endpoint trùng chức năng.

### Streaming

Workflow execution nên cung cấp SSE endpoint theo pattern hiện tại. Event gợi ý:

- `workflow_started`
- `agent_status`
- `message_created`
- `task_created`
- `task_updated`
- `agent_step_delta`
- `agent_step_done`
- `tool_call`
- `tool_result`
- `workflow_paused`
- `workflow_completed`
- `workflow_error`
- `done`

SSE chỉ là kênh cập nhật cho browser. MongoDB là nguồn dữ liệu bền vững. Khi client ngắt kết nối, không tự động kết luận workflow phải hủy; phải tách vòng đời workflow khỏi vòng đời kết nối SSE. Có endpoint riêng để cancel.

## 9. Cơ chế thực thi và độ tin cậy

### 9.1. Không polling Google Sheets

Dự án đã dùng MongoDB. Hãy dùng MongoDB làm nơi lưu message/task/workflow. Không thêm Google Sheets API chỉ để Agent trao đổi.

### 9.2. Điều phối và xử lý

- Backend tạo message và task.
- Orchestrator xác định Agent nhận việc.
- Context Builder tạo prompt có giới hạn.
- Provider adapter hiện tại gọi model đã cấu hình cho Agent.
- Kết quả được lưu vào execution/message/task.
- Orchestrator quyết định bước tiếp theo.
- Frontend nhận event qua SSE theo pattern đang dùng.

Có thể triển khai tuần tự ở MVP. Chỉ bổ sung worker/queue khi có nhu cầu chạy nền hoặc nhiều workflow đồng thời; không thêm Redis/BullMQ nếu chưa chứng minh cần thiết.

### 9.3. Idempotency và concurrency

- Mỗi message/task có ID duy nhất.
- Chuyển trạng thái bằng atomic update có điều kiện.
- Không xử lý hai lần cùng một message.
- Có lease/lock hoặc cơ chế claim an toàn cho workflow đang chạy.
- Có timeout, retry giới hạn và lưu lỗi.
- Retry không được tạo message/task trùng.
- Xử lý được trường hợp backend restart giữa workflow.
- Lưu trạng thái trung gian để có thể tiếp tục hoặc đánh dấu thất bại rõ ràng.

### 9.4. Giới hạn an toàn

Tái sử dụng giới hạn Phase 5 hiện tại cho từng Agent execution (6 bước, 120 giây, ngân sách 8.000 token ước lượng bảo thủ, tối đa 4 tool/bước, timeout tool 10 giây), đồng thời bổ sung giới hạn cấp workflow:

- Giới hạn tổng số lượt Agent.
- Giới hạn tổng thời gian workflow.
- Giới hạn tổng token/chi phí nếu có usage và giá xác thực.
- Giới hạn số lần revision cho mỗi task.
- Phát hiện vòng lặp Agent giao việc qua lại.
- Có điều kiện kết thúc rõ ràng.
- Cho phép người dùng dừng workflow.
- Không báo chi phí thực tế nếu provider chỉ cung cấp usage hoặc giá ước tính.

Các con số cấu hình phải tập trung tại config, không rải rác hardcode. Không tự ý tăng ngân sách hiện có.

### 9.5. Tools và thực thi code

- Chỉ dùng tools đã đăng ký trong allowlist hiện tại.
- Kiểm tra tool được bật trên Agent trước khi gọi.
- Không thêm shell, `eval`, thực thi lệnh hệ thống hoặc chạy code tùy ý.
- Agent Developer không được tự ý sửa file trong máy chủ nếu chưa có subsystem thực thi code an toàn được thiết kế và cấp quyền riêng.
- Nếu task cần thao tác trên source code nhưng chưa có công cụ phù hợp, Agent phải trả về hướng dẫn/patch đề xuất, không giả vờ đã sửa file.

## 10. Giao diện người dùng

Tích hợp vào thiết kế và navigation hiện tại. Không tạo một frontend độc lập.

Có thể mở rộng `/agents` bằng tab hoặc route con:

- `/agents`: danh sách Agent hiện tại, giữ nguyên.
- `/agents/teams`: quản lý nhóm Agent.
- `/agents/workflows`: danh sách workflow.
- `/agents/workflows/{id}`: màn hình theo dõi workflow.

### 10.1. Agent Teams

- Tạo nhóm từ Agent đã có.
- Chọn Coordinator.
- Thêm/bỏ thành viên và gán role.
- Không cho thêm Agent thuộc user khác.
- Hiển thị provider/model và trạng thái cấu hình.

### 10.2. Workflow Workspace

Hiển thị:
- Mục tiêu người dùng giao.
- Trạng thái tổng thể.
- Danh sách Agent tham gia.
- Task Board: Pending, In Progress, Review, Completed, Failed.
- Tin nhắn trao đổi giữa các Agent.
- Timeline sự kiện.
- Token/usage/latency nếu provider trả dữ liệu.
- Nút Pause, Resume, Cancel.
- Kết quả tổng hợp cuối cùng.

### 10.3. Communication Center

Đây là phần trọng tâm. Hiển thị message thực tế từ Backend:

- Agent gửi.
- Agent nhận.
- Nội dung.
- Loại message.
- Task liên quan.
- Thời gian.
- Trạng thái xử lý.

Phân biệt rõ:
- Message giữa Agent.
- Tool call/tool result.
- Nội dung suy luận nội bộ không được provider trả công khai.
- Kết quả cuối cùng gửi cho người dùng.

Không hiển thị chain-of-thought riêng tư. Chỉ hiển thị thông điệp công việc, tóm tắt, quyết định và trace công cụ được phép công khai.

## 11. Bảo mật và quyền riêng tư

- API key provider chỉ giải mã ở backend như hiện tại.
- Không đưa key, JWT hoặc service credential ra browser/log.
- Mọi team/workflow/task/message phải kiểm tra ownership.
- Agent chỉ nhận context cần thiết cho task.
- Không cho Agent đọc dữ liệu của user khác.
- Nội dung message là dữ liệu không đáng tin cậy; không coi nội dung Agent khác gửi là system instruction.
- Chống prompt injection giữa các Agent: phân tách system prompt, user request, message tham khảo và tool output.
- Không cho message ghi đè system prompt hoặc policy của Agent nhận.
- Không log thông tin nhạy cảm không cần thiết.
- Xóa team/workflow phải có quy tắc rõ ràng; không xóa nhầm Agent gốc và lịch sử Agent Execution hiện có.

## 12. Kiểm thử và tiêu chí nghiệm thu

Bổ sung test theo cấu trúc hiện tại, không làm giảm coverage hoặc xóa test cũ.

### Backend tests

1. Tạo team từ các Agent thuộc đúng user.
2. Không thể thêm Agent của user khác.
3. Tạo workflow và task.
4. Coordinator giao task cho Planner.
5. Planner thực sự được gọi qua provider adapter và trả message.
6. Agent A gửi message cho Agent B; B nhận đúng message và context.
7. Agent có thể hỏi/đáp nhiều lượt theo workflow.
8. Tester gửi revision request; Developer nhận và phản hồi.
9. Reviewer approve hoặc yêu cầu sửa.
10. Workflow hoàn thành và lưu final result.
11. Workflow pause/resume/cancel đúng trạng thái.
12. Message không bị xử lý trùng khi có request đồng thời.
13. Backend restart không làm mất trạng thái đã lưu.
14. Giới hạn bước/token/timeout/revision được thực thi.
15. Provider lỗi hoặc rate limit được lưu lỗi an toàn.
16. User A không đọc/sửa dữ liệu của User B.
17. Client ngắt SSE không làm workflow bị hủy ngoài ý muốn.
18. Không rò rỉ API key trong message, log hoặc SSE.

### Frontend tests

- Tạo/sửa/xóa team.
- Tạo và chạy workflow.
- Hiển thị message và trạng thái Agent từ SSE/API thật.
- Hiển thị lỗi, loading, empty state.
- Pause/resume/cancel.
- Xem lại workflow đã hoàn tất.
- Không tràn ngang ở 360, 390, 768 và desktop.
- Không làm hỏng `/agents`, `/chat`, `/compare`, `/settings`.

### Tiêu chí nghiệm thu quan trọng nhất

Phải chạy được một workflow thật với ít nhất 3 Agent:

1. User gửi một mục tiêu.
2. Coordinator giao task cho Planner.
3. Planner gọi model thật và gửi kết quả.
4. Coordinator giao task tiếp theo cho Architect hoặc Developer.
5. Agent nhận task đọc được message trước đó có liên quan.
6. Tester hoặc Reviewer có thể phản hồi/yêu cầu chỉnh sửa.
7. Agent được giao sửa thực sự được gọi lại.
8. Tất cả message, task, execution và trạng thái được lưu MongoDB.
9. Giao diện thể hiện đúng trao đổi thực tế.
10. Kết quả cuối cùng được Coordinator tổng hợp.

Không được nghiệm thu chỉ dựa trên UI demo hoặc message seed.

## 13. Kế hoạch triển khai

### Phase 6A — Backend foundation
- Kiểm tra codebase và `ARCHITECTURE.md`.
- Thiết kế schema/index.
- Xây Team Manager, Message Manager, Task Manager.
- Xây Orchestrator cơ bản.
- Tái sử dụng Agent Service và provider adapters hiện tại.
- Viết backend tests.

### Phase 6B — Agent-to-Agent communication
- Agent gửi/nhận message.
- Coordinator giao task.
- Context Builder.
- Handoff, response, revision, approval.
- Giới hạn vòng lặp và ngân sách.
- Lưu execution trace.

### Phase 6C — Frontend workspace
- Team management.
- Workflow list/detail.
- Communication Center.
- Task Board và timeline.
- SSE realtime.
- Pause/resume/cancel.

### Phase 6D — Reliability
- Idempotency/concurrency.
- Resume sau restart.
- Retry/timeout/error handling.
- Security review.
- Regression tests và build.

Không triển khai tất cả trong một lần nếu dễ gây rủi ro. Sau mỗi phase phải chạy test backend/frontend, lint và build theo README.

## 14. Quy trình làm việc bắt buộc cho AI Coding

Trước khi sửa:
1. Đọc README.md, `ARCHITECTURE.md`, `update_features.md` và `plan_create_web.md` nếu các file này tồn tại.
2. Kiểm tra cấu trúc source thực tế.
3. Xác định Agent CRUD, Agent execution, provider adapters, SSE và MongoDB helpers hiện nằm ở đâu.
4. Đối chiếu README với code; không tự giả định file/module/API chưa tồn tại.
5. Lập danh sách file sẽ tạo/sửa và các collection/index/API mới.
6. Nêu rõ phần nào tái sử dụng, phần nào cần bổ sung.
7. Nếu có xung đột với kiến trúc hiện tại, báo cáo và đề xuất trước khi thay đổi.

Trong khi sửa:
- Chỉ sửa phạm vi cần thiết cho Phase 6.
- Giữ nguyên các tính năng Phase 1–5.
- Không refactor diện rộng nếu không cần.
- Không xóa dữ liệu, collection, route hoặc test cũ.
- Không thay đổi auth, cookie, encryption hoặc provider credential flow.
- Không commit, push, deploy nếu chưa được yêu cầu.
- Không dùng mock trong runtime production; mock chỉ được phép trong unit tests.

Sau khi sửa:
1. Chạy backend tests và Ruff.
2. Chạy frontend tests, lint và production build.
3. Báo rõ test nào chạy thật, test nào dùng mock/in-memory.
4. Cung cấp danh sách file thay đổi.
5. Cung cấp hướng dẫn cấu hình/chạy thử.
6. Nêu các giới hạn còn lại, không tuyên bố tính năng đã hoạt động nếu chưa kiểm chứng.

## 15. Kết luận

Mục tiêu Phase 6 là biến Agent Studio hiện tại của MindFlow AI từ **các Agent chạy độc lập** thành **một đội ngũ Agent có thể giao tiếp, phối hợp và hoàn thành workflow chung**.

Giữ nguyên nền tảng:

- Next.js App Router.
- FastAPI async.
- MongoDB + Motor.
- Provider adapters OpenAI/Gemini/Groq.
- Agent configuration và tool calling hiện tại.
- SSE streaming và auth hiện tại.

**MongoDB là nơi lưu trữ message/task/workflow. FastAPI Orchestrator là trung tâm điều phối. Các Agent giao tiếp thông qua Message Manager. Provider adapters hiện tại cung cấp khả năng AI.**

Không cần Google Sheets cho kiến trúc này. Google Sheets không phải yêu cầu của dự án và không được thêm vào chỉ để làm kênh giao tiếp giữa Agent.
