# NEXORA IMPLEMENTATION PLAN — Lộ trình mở rộng MindFlow AI thành NEXORA AI

> Căn cứ: `CURRENT_ARCHITECTURE_AUDIT.md`, `EXISTING_FEATURES_INVENTORY.md`,
> `DATABASE_IMPACT_ANALYSIS.md` (audit trên code thật, 2026-11-24) và đặc tả `update_features.md`.
> Quy ước giữ nguyên: mở rộng trên project hiện tại, không đổi ngôn ngữ/framework/database,
> không xoá chức năng đang chạy, mỗi đợt là một PR nhỏ review được trong ngày, Muse soạn bản vá +
> mở PR, chủ dự án chạy test trên Windows rồi merge (phương án 2 đã chốt).

## Quyết định kỹ thuật đã chốt trong kế hoạch này

1. **Không dùng LangGraph.** Orchestrator hiện tại (Phase 6) đã có đủ: trạng thái bền vững trong
   MongoDB, phân rã theo vai trò, handoff, review loop có giới hạn, ngân sách/timeout, pause/
   resume/cancel, lease khôi phục. Đặc tả cho phép LangGraph "nếu phù hợp" — hiện tại nó không
   thêm giá trị nào ngoài việc viết lại một hệ đang chạy. Đánh giá lại chỉ khi cần conditional
   routing/graph phức tạp thật sự.
2. **Workspace theo kiểu strangler:** thêm lớp workspace bên cạnh owner-scope hiện tại (workspace
   cá nhân mặc định 1-1 với user), bật lọc theo workspace theo từng module. Không migrate toàn
   bộ dữ liệu trong một đợt.
3. **Seed Data có kiểm soát:** chỉ ở `development`/`demo`, idempotent, có `is_demo`, không chạm
   dữ liệu thật, không seed số liệu usage/execution giả.
4. **RAG dùng lại collection sẵn có** (`knowledge_bases`, `documents`) + `document_chunks` mới;
   chọn cơ chế tìm kiếm vector ở đầu Phase 4 theo môi trường triển khai thực tế (Atlas vs local).
5. **Claude là một provider adapter mới** trong registry hiện có (không phải hệ thống riêng),
   làm ở Phase 6 cùng Evaluation hoặc sớm hơn nếu được ưu tiên.

## Phase 0 — Audit (đợt này)

- 4 tài liệu audit/kế hoạch (PR tài liệu, không sửa code).
- Sửa độ lệch tài liệu đã phát hiện: mục "Chưa triển khai" của README (Ollama đã tích hợp từ
  PR #17) và ghi chú ARCHITECTURE §5 là thiết kế cũ — làm trong PR tài liệu tiếp theo hoặc gộp
  vào PR Phase 1, không để tài liệu sai dẫn đường.

## Phase 1 — Foundation (Workspace · Seed · Executive Dashboard · Navigation)

Thứ tự trong phase: 1a → 1b → 1c → 1d, mỗi mục một PR.

**1a. Môi trường + Seed Data an toàn**
- `Settings.app_env` (mặc định `development`); service `app/services/seed.py`: seed idempotent
  theo `seed_registry`, chỉ chạy khi app_env là development/demo và được bật tường minh
  (endpoint admin `POST /ai/seed/demo` cho tài khoản hiện tại, hoặc chạy khi user chưa có Agent
  mẫu và tự bấm "Tạo bộ 7 Agent mẫu" — mở rộng cơ chế sẵn có từ PR #2).
- Seed: workspace demo (khi 1b xong), 7 Agent mẫu + 3 team mẫu (Engineering/Research/Operations)
  với `is_demo: true`; vài workflow mẫu ở trạng thái completed/failed **dạng bản ghi demo có
  nhãn**, approvals + notifications mẫu (khi 1b/Phase 2 có collection tương ứng thì bổ sung).
- Test: 8 ca theo Part 5 §1.6 (DB trống, chạy 2 lần không trùng, production không seed,
  không ghi đè dữ liệu thật…).

**1b. Workspace Management v1 (Module 02 + Part 3)**
- Backend mới: `app/schemas/workspaces.py`, `app/services/workspaces.py`,
  `app/api/v1/workspaces.py` — CRUD workspace, workspace cá nhân mặc định tạo lười, danh sách
  workspace của tôi, members (liệt kê/thêm theo email/đổi role/xoá) với kiểm tra quyền ở backend
  theo bảng vai trò rút gọn: owner/admin/leader/employee/operator/viewer.
- Frontend: trang `/workspaces` + bộ chuyển workspace trong app-shell; dữ liệu nghiệp vụ chưa
  đổi hành vi (vẫn owner-scoped).
- File sửa: `main.py` (đăng ký router), `core/database.py` (index), `app-shell.jsx`.

**1c. Executive Dashboard v1 (Module 01)**
- Backend: `GET /ai/analytics/overview` tính từ dữ liệu thật: tổng Agent đang có, workflow đang
  chạy, task hoàn thành/thất bại + tỉ lệ, token + chi phí ước tính theo `ai_requests` (7/30 ngày),
  phân bổ theo model, hoạt động gần đây hợp nhất từ `activity_logs` + workflow events. Loại trừ
  bản ghi `is_demo` khỏi số liệu thật và ghi rõ khi đang xem dữ liệu demo.
- Frontend: nâng trang `/dashboard` thêm các thẻ + biểu đồ nhẹ (không thêm thư viện chart nặng —
  dùng CSS/SVG như các trang hiện tại).

**1d. Navigation theo nhóm (Part 8.2)**
- Sắp xếp lại menu app-shell theo nhóm WORKSPACE / AI MANAGEMENT / AUTOMATION / KNOWLEDGE /
  INTELLIGENCE / ADMINISTRATION, chỉ gồm trang đã có thật (không tạo menu trỏ vào placeholder
  cho module chưa làm).

## Phase 2 — AI Collaboration + Approvals + Notifications

- **Collaboration v1 (Module 03):** mở rộng `multi_chats` thành phòng làm việc: thêm Agent của
  user làm thành viên, @mention Agent để Agent trả lời trong phòng (tái sử dụng cơ chế chạy Agent
  Phase 5), trạng thái Agent đang làm việc, dừng sinh nội dung. Panel phải (Agent tham gia +
  token của phòng) ở mức cơ bản.
- **Human Approval (Module 10):** collection `approvals`; workflow có `requires_approval` thì
  khi tới bước chốt sẽ tạo approval và chuyển `waiting`; trang `/approvals` (inbox) với
  approve/reject/request-changes + bình luận; quyết định được ghi `activity_logs`; resume workflow
  theo quyết định. Áp dụng tương tự cho run AI Factory khi cần (giai đoạn sau).
- **Notifications v1 (Module 15):** collection `notifications`; phát sinh từ sự kiện workflow
  xong/thất bại, approval mới/đã quyết, run n8n xong; chuông thông báo trong app-shell có danh
  sách + đánh dấu đã đọc. Kênh Telegram đã có qua WF08 (tuỳ chọn) — không làm email ở đợt này.

## Phase 3 — Orchestration nâng cao (Module 06/07)

- Chạy **song song** các task không phụ thuộc nhau trong orchestrator (giữ nguyên ngân sách +
  giới hạn lượt), trạng thái task bổ sung `waiting_for_input`/`under_review`, priority/deadline.
- Vai trò **Evaluator** trong bộ vai trò hiệu dụng (chấm điểm kết quả theo rubric, lưu vào
  workflow events) — cầu nối sang Phase 6.
- Task độc lập ngoài workflow (tạo tay, gán Agent, chạy như một workflow 1-task) — chỉ làm nếu
  nhu cầu sử dụng thực tế xuất hiện sau Phase 2.

## Phase 4 — Knowledge Integration (Module 08)

- Upload tài liệu (PDF/DOCX/TXT/MD/CSV trước — đúng parser có thật: pypdf, python-docx),
  trạng thái xử lý bền vững trên `documents`, chunking có overlap, embedding bằng provider đã
  cấu hình của user (model embed bị đánh dấu non-chat trong catalog hiện tại — dùng đúng chúng),
  lưu `document_chunks`.
- Bật hai tool đang tắt: `search_knowledge_base`, `summarize_document` với allowlist + phân
  quyền theo Agent (Agent chỉ đọc KB được cấp), trả lời kèm citation (filename + trang + đoạn).
- Quyết định vector search ở đầu phase: Atlas `$vectorSearch` nếu triển khai trên Atlas,
  ngược lại cosine trong backend trên chunk đã lọc (ghi rõ giới hạn quy mô).

## Phase 5 — n8n Automation mở rộng (Module 09/13)

- Trang Workflow Center trong tab AI Factory: liệt kê 8 workflow factory hiện có + trạng thái
  (dựa trên lần chạy thật gần nhất, không bịa trạng thái "Active").
- Bổ sung workflow theo đặc tả khi có nhu cầu demo thật: GitHub Issue Analysis (webhook GitHub →
  n8n → Agent phân tích → thông báo), Approval Notification (nối Module 10), Usage Reporting
  theo lịch (mở rộng WF08). Mỗi workflow chỉ đánh dấu hoàn thành khi đã chạy thử end-to-end.
- Trang Integrations v1: trạng thái thật của n8n (health qua webhook/HTTP), GitHub (qua lần
  chạy workflow), Telegram (theo cấu hình WF08).

## Phase 6 — Evaluation & Observability (Module 11/14) + Claude

- **Claude adapter** vào registry (kế thừa adapter OpenAI-compatible nếu API tương thích, hoặc
  adapter riêng cho Messages API — kiểm chứng bằng key thật của user khi làm).
- **Evaluation:** datasets + runs + results (bảng ở DATABASE_IMPACT), chạy cùng dataset trên
  nhiều model/Agent, chấm bằng rubric + model judge được cấu hình, scorecard (success rate,
  latency, token, chi phí ước tính, output validity), lưu lịch sử để so regression.
- **Observability:** trang Executions hợp nhất (agent executions + workflow + factory runs),
  trang Audit (activity_logs + quyết định approval + thay đổi credential), biểu đồ chi phí
  theo ngày/Agent/model từ `ai_requests`.

## Phase 7 — Production Readiness

- Rà soát bảo mật (quyền workspace hai chiều, tool permissions, webhook auth), index rà soát
  lại, rate limit cho endpoint nặng (evaluation/seed), kiểm thử hồi quy toàn bộ, cập nhật
  README/ARCHITECTURE cho khớp thực tế, (tuỳ chọn) global search (Module 16) nếu còn nhu cầu.

## Ánh xạ Acceptance Criteria (Part 11) → Phase

| Tiêu chí | Đạt ở |
|---|---|
| Chạy trên project hiện tại, không đổi ngôn ngữ/framework/DB, chức năng cũ còn hoạt động | Mọi phase (ràng buộc xuyên suốt) |
| Seed Data an toàn | Phase 1a |
| Tạo conversation, lưu message, ≥3 Agent tham gia, handoff, trạng thái, lịch sử, dừng được | Đã có phần lớn (Phase 5/6 cũ) + Phase 2 |
| Task: tạo/gán/trạng thái/phụ thuộc/review/kết quả | Đã có trong workflow + Phase 3 |
| RAG dùng được, citation, phân quyền | Phase 4 |
| n8n kết nối thật, ≥1 workflow chạy thật, lịch sử, xử lý lỗi, webhook auth | Đã có (PR #18–#20) + Phase 5 |
| Metrics/token/chi phí ước tính/đánh giá/báo cáo | Dữ liệu đã có + Phase 1c/6 |
| Auth, authorization, workspace isolation, tool permission, approval, không lộ credential | Đã có nền + Phase 1b/2 |

## Rủi ro chính & cách giảm thiểu

1. **Workspace chạm vào mọi truy vấn owner-scope** → strangler theo module, workspace cá nhân
   mặc định, kiểm thử cô lập hai user ở mỗi đợt bật lọc.
2. **Phạm vi đặc tả rất lớn (17 module)** → làm theo phase, mỗi phase có PR riêng và tiêu chí
   nghiệm thu riêng; không gộp nhiều module vào một PR.
3. **Chi phí/quota provider khi chạy evaluation/song song** → ngân sách theo usage thật đã có;
   evaluation giới hạn số case × số model mỗi run.
4. **RAG phụ thuộc môi trường vector search** → quyết định ở đầu Phase 4, không khoá cứng từ bây giờ.
5. **Tài liệu cũ lệch thực tế** (README/ARCHITECTURE §5) → sửa ngay từ Phase 0/1 để các đợt sau
   không đi theo thiết kế đã bỏ.
