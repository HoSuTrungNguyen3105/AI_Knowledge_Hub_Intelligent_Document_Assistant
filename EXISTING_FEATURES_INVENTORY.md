# EXISTING FEATURES INVENTORY — Đối chiếu MindFlow AI với 17 module NEXORA

> Trạng thái: **Đầy đủ** = dùng được ngay cho NEXORA · **Một phần** = có nền thật, cần bổ sung ·
> **Chưa có** = chưa tồn tại trong code. Đối chiếu trên `main` sau PR #20, 2026-11-24.

## Bảng tổng hợp

| Module NEXORA | Trạng thái | Phần đã có (tái sử dụng) | Phần còn thiếu |
|---|---|---|---|
| 01 Executive Dashboard | Một phần | `/dashboard` đếm tài liệu/KB/hội thoại/AI request/hoạt động từ DB thật; `ai_requests` có usage + latency; `agent_tasks`/`agent_workflows` có trạng thái | Thẻ tổng quan doanh nghiệp (workspaces, approvals…), analytics: tỉ lệ hoàn thành/thất bại, chi phí theo thời gian, phân bổ model, hoạt động gần đây hợp nhất |
| 02 Workspace Management | **Chưa có** | Cô lập dữ liệu theo `user_id` (tương đương workspace cá nhân 1 người) | Collection workspaces/members, vai trò, chuyển đổi workspace, cài đặt workspace, giới hạn dùng |
| 03 AI Collaboration Workspace | Một phần | Chat 1-1 với model (`/chat`, streaming SSE, lịch sử bền vững); `multi_chats` (chat nhiều model); workspace Phase 6 hiển thị tin nhắn Agent-Agent thật (Communication Center), Task Board, timeline | Phòng chat người + nhiều Agent với @mention, chọn team trong composer, panel phải (tiến độ/token), ghim/tìm kiếm/lưu trữ hội thoại nhóm |
| 04 AI Agent Management | **Đầy đủ (gần)** | CRUD, nhân bản, provider/model đã đồng bộ, system prompt, temperature, max tokens, tools allowlist (calculator/datetime/data_analyzer), lịch sử thực thi + trace tool, ngân sách 6 bước/120s/8000 token | Kích hoạt/vô hiệu hoá (activate/deactivate), giới hạn chi phí riêng từng Agent, health status tổng hợp |
| 05 Agent Team Management | **Đầy đủ (gần)** | Tạo/sửa/xoá team, gán vai trò Coordinator/Planner/Architect/Developer/Tester/Reviewer/Researcher, chọn Coordinator, trang Teams riêng; 3 đội mẫu tương ứng Engineering/Research/Operations tạo được ngay bằng Agent sẵn có | Team budget, execution strategy cấu hình được, team performance |
| 06 AI Task Management | Một phần | Task sinh từ workflow có trạng thái (queued/in_progress/completed/failed + cột Failed), phụ thuộc theo thứ tự vai trò, vòng review `REVISION_REQUEST`, Task Board trong workspace, huỷ được | Task độc lập ngoài workflow (tạo tay, gán người/Agent), priority/deadline/labels/subtasks/comments, các trạng thái `waiting_for_input`/`waiting_for_approval`/`under_review` đầy đủ |
| 07 AI Orchestration Engine | **Đầy đủ (lõi)** | Phân rã theo vai trò, gán việc tuần tự, handoff qua message store, review loop tối đa 2 lần sửa, retry (gồm nhịp riêng cho rate-limit), timeout 600s, ngân sách token theo usage thật, pause/resume/cancel, trạng thái bền vững, execution id theo workflow | Chạy song song cho task độc lập, conditional routing, checkpoint giữa chừng chi tiết hơn; LangGraph **không cần** ở giai đoạn này (xem quyết định trong Implementation Plan) |
| 08 Enterprise Knowledge Hub | **Chưa có (gần như)** | Collection `knowledge_bases` + `documents` + index; hội thoại gắn được `knowledge_base_id`; dashboard đếm tài liệu | Upload + validation, parser (PDF/DOCX/TXT/MD…), chunking, embedding, vector store, retrieval + citation, phân quyền tài liệu cho Agent, bật 2 tool tri thức đang tắt |
| 09 Workflow Automation (n8n) | Một phần | Bộ `n8n-ai-factory` (8 workflow: orchestrator, thực thi Agent, chạy song song, sinh code, QA/review, đóng ZIP, WF07 dynamic routing, WF08 bản tin theo lịch); cầu nối MindFlow ↔ n8n bất đồng bộ (callback token riêng, idempotent, timeout, huỷ run); dashboard factory tĩnh | Ánh xạ sang bộ WF01–WF10 của đặc tả (GitHub Issue Analysis, Approval Notification, Usage Reporting…), trang Workflow Center trong MindFlow liệt kê workflow n8n + lịch sử execution, webhook cho sự kiện từ GitHub |
| 10 Human Approval Center | **Chưa có** | Workflow có trạng thái chờ (`waiting`) + resume — điểm neo kỹ thuật để gắn phê duyệt | Collection approvals, inbox, approve/reject/request-changes kèm bình luận + lịch sử, chính sách "hành động nào cần duyệt" |
| 11 LLM Evaluation Center | **Chưa có** | `/compare` chạy 2–4 model song song + synthesis, lưu usage/latency/chi phí ước tính — nền cho Model Comparison | Dataset/test case, evaluation runs, scorecard (accuracy, success rate, citation validity…), regression, báo cáo |
| 12 Model & Provider Management | **Đầy đủ (gần)** | Danh sách provider, nhập key mã hoá Fernet theo user, test kết nối (liệt kê model thật), đồng bộ model, model mặc định, bật/tắt; ghi nhận model thực dùng trong từng execution | Claude adapter (registry có nhưng chưa implemented), fallback model khi provider lỗi, cấu hình giá theo model |
| 13 Tool & Integration Management | Một phần | Tools của Agent có allowlist + gán theo Agent + log thực thi tool (`tool_executions`); tích hợp n8n đã chạy thật; GitHub qua connector ngoài app | Trang Integrations trong app (trạng thái Connected/Disconnected/Error thật), GitHub/GitLab integration trong app, kiểm tra kết nối theo integration |
| 14 Observability & Audit | Một phần | `activity_logs` theo user; `agent_executions` + `tool_executions` có trace; `agent_workflow_events` timeline; dashboard factory; health endpoint | Trang quan sát hợp nhất (execution list/detail xuyên module), audit log cho approval/credential/permission changes, biểu đồ chi phí theo ngày/Agent/model, health của n8n/provider trên một màn hình |
| 15 Notification Center | **Chưa có** | Sự kiện nền đã có (workflow xong/thất bại, run n8n xong) nhưng chưa phát thành thông báo; WF08 gửi Telegram tuỳ chọn | Collection notifications, inbox trong app + đánh dấu đã đọc, tuỳ chọn kênh (Telegram qua n8n đã có sẵn đường) |
| 16 Search Center | **Chưa có** | Tìm kiếm cục bộ trong vài trang (lịch sử chat…) | Global search xuyên hội thoại/task/agent/tài liệu/workflow, tôn trọng quyền |
| 17 Settings & Administration | Một phần | Trang Providers (cấu hình provider theo user); profile + đổi mật khẩu qua auth API; giới hạn hệ thống trong Settings backend | Vai trò/quản trị thành viên (phụ thuộc Module 02), tuỳ chọn thông báo, theme/ngôn ngữ, trang quản trị hệ thống |

## Các tính năng ngoài danh mục module nhưng đã có và phải giữ

- **Xuất ZIP website** từ workflow (2 chế độ tĩnh/source project, kiểm tra an toàn đường dẫn,
  giới hạn kích thước, tự sửa `index.html` ở gốc) + tuỳ chọn thiết kế (palette/phong cách).
- **AI Factory qua n8n bằng chính Agent của MindFlow** (gán vai trò theo Agent thật, async +
  callback + huỷ run) và **WF08** bản tin nghiên cứu theo lịch kèm Telegram tuỳ chọn.
- **Trang Workflows hợp nhất** (PR #20): 2 tab MindFlow/n8n, nút Run/Resume/Pause/Cancel ngay
  trên thẻ danh sách ở cả hai phía.
- **Mô phỏng văn phòng** (agent-office) và avatar robot trong trang chi tiết workflow.
- Kỷ luật dữ liệu: chi phí luôn là **ước tính** có nhãn, token chỉ tính từ usage provider xác nhận,
  lỗi provider hiển thị đúng mã thật (không che thành lỗi chung).

## Kết luận

Trong 17 module: **3 module gần đầy đủ** (04, 05, 12), **1 module có lõi đầy đủ** (07),
**8 module có một phần**, **5 module chưa có** (02, 08, 10, 11, 15, 16 — thực tế là 6 nếu tách
riêng Search). Thứ tự xây dựng hợp lý không phải theo số module mà theo phụ thuộc nền tảng:
Workspace (02) → Seed/Dashboard (Part 5 + 01) → Approval (10) → Knowledge (08) → Evaluation (11)
→ Observability/Search/Notifications (14/16/15). Chi tiết ở `NEXORA_IMPLEMENTATION_PLAN.md`.
