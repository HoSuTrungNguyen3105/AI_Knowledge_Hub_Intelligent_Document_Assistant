# DATABASE IMPACT ANALYSIS — Mở rộng MongoDB hiện tại cho NEXORA AI

> Nguyên tắc (theo đặc tả Part 6 và quy ước dự án): giữ nguyên MongoDB, giữ nguyên schema đang
> chạy, **không tạo collection một cách máy móc** khi đã có cấu trúc tương đương, không migration
> phá huỷ, không xoá dữ liệu người dùng. Mọi thay đổi dưới đây đều là **thêm mới** (collection mới
> hoặc field tuỳ chọn) và tương thích ngược.

## 1. Hiện trạng: 23 collections đang dùng

Khai báo qua `init_indexes()` (`backend/app/core/database.py`) và các service. Mọi collection
nghiệp vụ đều owner-scoped bằng `user_id` (UUID), có `created_at`/`updated_at`.

| Nhóm | Collections | Dùng cho |
|---|---|---|
| Tài khoản | `users`, `refresh_tokens` | Auth, session xoay vòng |
| Provider | `user_provider_credentials`, `ai_models` | Key mã hoá Fernet theo user, catalog model đã đồng bộ |
| Chat | `conversations`, `multi_chats`, `messages`, `ai_requests` | Chat 1-1/nhiều model, usage + latency thật |
| So sánh | `comparisons` | Compare 2–4 model + synthesis |
| Agent | `agents`, `agent_executions`, `tool_executions` | Agent Studio Phase 5 + audit tool |
| Multi-agent | `agent_teams`, `agent_workflows`, `agent_tasks`, `agent_messages`, `agent_workflow_events`, `agent_workflow_files` | Phase 6 + artifact ZIP |
| Tri thức | `knowledge_bases`, `documents` | Mới ở mức khai báo/đếm — chưa có pipeline xử lý |
| Hệ thống | `activity_logs`, `n8n_factory_runs` | Nhật ký hoạt động cá nhân; lượt chạy AI Factory (PR #19) |

**Nhận định:** cấu trúc hiện tại đã gần với bảng thiết kế logic ở Part 6 của đặc tả
(`agent_teams` ≈ `agent_teams`, `agent_tasks` ≈ `tasks`, `agent_workflows` ≈ `workflow_executions`…).
Không đổi tên collection đang chạy — ánh xạ khái niệm thay vì đổi schema.

## 2. Thay đổi đề xuất

### 2.1. Collection MỚI (chỉ khi module tương ứng được triển khai)

| Collection | Module | Nội dung chính | Index đề xuất |
|---|---|---|---|
| `workspaces` | 02 | id, owner_id, name, description, avatar?, settings (AI config, usage limits), is_demo, timestamps | `owner_id`; `(owner_id, name)` |
| `workspace_members` | 02 | id, workspace_id, user_id, role (owner/admin/leader/employee/operator/viewer), invited_by, timestamps | unique `(workspace_id, user_id)`; `user_id` |
| `approvals` | 10 | id, user_id (người quyết), workspace_id?, source_type (workflow/factory_run/action), source_id, title, detail, status (pending/approved/rejected/changes_requested), comment, decided_by, decided_at, deadline?, timestamps | `(user_id, status, created_at -1)`; `(source_type, source_id)` |
| `notifications` | 15 | id, user_id, type, title, body, link, read_at, source refs, timestamps | `(user_id, read_at, created_at -1)` |
| `evaluation_datasets` | 11 | id, user_id, name, description, cases[{prompt, expected?, rubric}], timestamps | `user_id` |
| `evaluation_runs` | 11 | id, user_id, dataset_id, targets[{provider, model, agent_id?}], status, summary (avg score, success rate, total tokens/cost est), timestamps | `(user_id, created_at -1)`; `dataset_id` |
| `evaluation_results` | 11 | id, run_id, case_index, target, output, score, metrics (latency, tokens, cost est), judge (model/rule), error?, timestamps | `(run_id, case_index)` |
| `seed_registry` | Part 5 | key (duy nhất, vd `nexora_demo_v1`), version, applied_at, counts | unique `key` |
| `document_chunks` | 08 (khi làm RAG) | id, document_id, user_id, knowledge_base_id, index, text, page?, embedding (mảng số), embedding_model, timestamps | `document_id`; `knowledge_base_id` |

### 2.2. Field BỔ SUNG trên collection sẵn có (đều tuỳ chọn, mặc định vắng = hành vi cũ)

| Collection | Field mới | Lý do |
|---|---|---|
| `agents`, `agent_teams`, `agent_workflows`, `conversations`, `knowledge_bases` | `workspace_id` (nullable) | Gắn dữ liệu vào workspace theo từng đợt (strangler), không ép migrate toàn bộ một lần |
| `agents`, `agent_teams`, `conversations`, `documents`, `agent_workflows`, `approvals`, `evaluation_datasets` | `is_demo` (bool, mặc định false/vắng) | Phân biệt dữ liệu seed với dữ liệu thật theo Part 5 §1.5; dashboard loại trừ demo khỏi số liệu "thật" |
| `documents` | `status` (uploaded/processing/ready/failed), `error_code`, `chunk_count`, `file_type`, `size_bytes` | Pipeline xử lý tài liệu của Module 08 có trạng thái bền vững |
| `agent_tasks` | `priority`, `deadline` (nullable) | Module 06 khi mở rộng task độc lập |
| `agent_workflows` | `requires_approval` (bool) | Cổng phê duyệt trước khi chốt kết quả (Module 10) — trạng thái chờ đã có sẵn (`waiting`) |
| `activity_logs` | `workspace_id` (nullable) | Audit theo workspace khi Module 02/14 triển khai |

### 2.3. Cấu hình (không phải dữ liệu)

- `Settings` thêm `app_env: str = "development"` (nhận `development | demo | production`) —
  điều kiện bắt buộc để Seed Data chỉ chạy ở dev/demo theo Part 5 §1.1.
- Không thêm biến bí mật mới ở giai đoạn nền tảng. Claude API (nếu làm) dùng đúng cơ chế
  credential mã hoá theo user hiện có — không có key trong code/env chung.

## 3. Những thứ KHÔNG thay đổi

- Không đổi tên/xoá collection hiện có; không đổi kiểu `_id` (UUID), không đổi cơ chế index lúc
  khởi động (`init_indexes` chỉ **thêm** index mới).
- Không chuyển MongoDB sang PostgreSQL, không thêm ORM/migration framework.
- Không lưu secret dạng plaintext ở bất kỳ collection mới nào (credential tiếp tục qua Fernet).
- Không ghi chain-of-thought riêng tư vào audit/activity logs (giữ quy ước hiện tại: chỉ lưu
  nội dung giao việc, kết quả, sự kiện được phép công khai).

## 4. Chiến lược Workspace không phá dữ liệu hiện tại (điểm rủi ro lớn nhất)

Toàn bộ truy vấn hiện tại lọc theo `user_id`. Cách làm an toàn theo từng bước:

1. Tạo `workspaces`/`workspace_members`; mỗi user tự có **workspace cá nhân mặc định**
   (tạo lười khi cần, idempotent) với role `owner`.
2. Giai đoạn đầu, API workspace chỉ quản lý workspace + thành viên + vai trò; dữ liệu nghiệp vụ
   vẫn owner-scoped như cũ (workspace cá nhân 1-1 với user nên hành vi không đổi).
3. Các entity mới tạo sau đó mới ghi thêm `workspace_id`; truy vấn lọc theo workspace **chỉ bật**
   cho từng module khi module đó đã sẵn sàng, kèm mặc định "workspace hiện tại của user".
4. Mời thành viên/chia sẻ dữ liệu thật giữa nhiều user là bước riêng, làm sau cùng khi đã có
   kiểm thử cô lập hai chiều — không gộp vào đợt nền tảng.

## 5. Seed Data — tác động dữ liệu

- Chỉ ghi khi `app_env ∈ {development, demo}` và có bản ghi `seed_registry` chưa tồn tại
  (idempotent, chạy lại an toàn kể cả khi lỗi giữa chừng — mỗi bước seed kiểm tra tồn tại theo
  khoá tự nhiên: tên + chủ sở hữu + `is_demo: true`).
- Chỉ seed cho **tài khoản được chỉ định** (ví dụ tài khoản demo) hoặc khi user chưa có dữ liệu
  tương ứng — không bao giờ ghi đè/bổ sung vào dữ liệu thật đã có của user khác; mọi bản ghi seed
  mang `is_demo: true` để dashboard và người dùng nhận diện, và có đường xoá riêng chỉ chạm vào
  bản ghi demo.
- Nội dung seed bám Part 5 §1.3 nhưng rút gọn theo thực tế: workspace demo, 7 Agent mẫu (đã có
  cơ chế "Tạo bộ 7 Agent mẫu" từ PR #2 — tái sử dụng), 3 team mẫu, vài workflow/task ở nhiều
  trạng thái, approvals mẫu, notifications mẫu. **Không** seed số liệu execution giả vào
  `ai_requests`/`agent_executions` (giữ kỷ luật số liệu thật của dự án); lịch sử demo nếu cần
  thì nằm trong chính các bản ghi demo có nhãn, không trộn vào thống kê thật.

## 6. Index & hiệu năng

- Bổ sung index trong `init_indexes()` cho các collection mới (mục 2.1) và compound
  `(user_id, status)` cho `approvals`, `(workspace_id, created_at -1)` khi workspace bật lọc.
- Tìm kiếm vector cho RAG: MongoDB local (docker mongo:7) **không có** Atlas Vector Search.
  Quyết định để ở Phase 4 của kế hoạch: hoặc dùng Atlas (đang dùng cho factory) với
  `$vectorSearch`, hoặc tính cosine trong backend trên tập chunk đã lọc theo user/KB
  (đủ cho quy mô tài liệu cá nhân, chậm hơn khi dữ liệu lớn) — không quyết định vội ở Phase 0.
