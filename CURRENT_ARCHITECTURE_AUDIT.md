# CURRENT ARCHITECTURE AUDIT — MindFlow AI (nền tảng của NEXORA AI)

> Audit thực hiện trên source code thực tế ở `main` (sau PR #20), ngày 2026-11-24.
> Mọi khẳng định dưới đây đều đối chiếu từ code: `backend/app/main.py`, `backend/app/core/config.py`,
> `backend/app/core/database.py`, `backend/requirements.txt`, các router/service, `frontend/app/`,
> `ARCHITECTURE.md`, `README.md`. Không suy đoán từ tài liệu mô tả.

## 1. Tổng quan hệ thống

MindFlow AI hiện là một ứng dụng AI cá nhân đa người dùng (mỗi tài khoản một không gian dữ liệu riêng,
cô lập theo `user_id`), gồm: quản lý provider/model AI theo từng user, chat đa model có streaming,
so sánh nhiều model, Agent Studio (Phase 5), Multi-Agent Collaboration (Phase 6), và cầu nối sang
n8n tự host (AI Factory). Đây là nền tảng mà đặc tả NEXORA AI (`update_features.md`) yêu cầu mở rộng —
audit này xác định chính xác phần nào đã có, phần nào chưa, trước khi viết thêm code.

## 2. Công nghệ hiện tại (giữ nguyên theo yêu cầu đặc tả)

| Lớp | Công nghệ thực tế | Ghi chú |
|---|---|---|
| Frontend | Next.js App Router, React, JavaScript/JSX, Tailwind CSS, Axios, Zustand, Lucide | Không có TypeScript. Điều hướng trong `frontend/components/app-shell.jsx` |
| Backend | FastAPI (async), Pydantic v2, pydantic-settings | App factory `create_app()` trong `backend/app/main.py` |
| Database | MongoDB qua Motor (async) | Không ORM/SQL, không migration — index tạo lúc khởi động trong `init_indexes()` |
| Auth | JWT access (15 phút) trong cookie HttpOnly + refresh token xoay vòng (7 ngày, thu hồi theo family), mật khẩu Argon2 (pwdlib), kiểm tra Origin/Referer chống CSRF | `backend/app/services/auth.py`, collection `refresh_tokens` |
| Bảo mật | SecurityMiddleware + RateLimiter (API 120/phút, auth 10/phút), CORS danh sách trắng nghiêm ngặt, mã hoá Fernet cho API key của user | Key provider không bao giờ trả về browser |
| AI Providers | Adapter dùng chung chuẩn OpenAI-compatible: OpenAI, Gemini, Groq, **Ollama Cloud (đã tích hợp, PR #17)**; Anthropic Claude và DeepSeek mới có trong registry, `implemented=False` | `backend/app/services/ai/` |
| Streaming | SSE cho chat và cho quan sát workflow | Ngắt kết nối không huỷ tác vụ nền |
| n8n | Bộ `n8n-ai-factory/` trong repo: 8 workflow JSON + Code Execution Service (Node) + dashboard tĩnh; dữ liệu qua MongoDB Atlas | Thêm cầu nối MindFlow ↔ n8n (PR #18–#20) |
| Docker | `docker-compose.yml` gốc: mongo:7 + backend + frontend; compose riêng cho n8n-ai-factory | Backend bind 127.0.0.1 mặc định; chạy dev bằng script `dev-ai` trên Windows |
| Test | Backend pytest (mongomock-motor + TestClient, test offline), frontend Jest; Ruff line-length 100 | Quy trình: Muse soạn bản vá + PR, chủ dự án chạy test trên Windows |

**Không có trong dự án:** LangGraph (không có trong `requirements.txt`), hàng đợi (queue) riêng,
vector database/embedding pipeline, thư viện parse tài liệu (không có pypdf/python-docx…),
WebSocket (chỉ có SSE), TypeScript, Alembic.

## 3. Kiến trúc backend

- Router (prefix `/api/v1`): `health`, `auth`, `dashboard`, `providers`, `chat`, `compare`,
  `agents`, `workflows`, `n8n_factory` — khai trong `backend/app/main.py`.
- Phân lớp nhất quán: `api/v1/*` (HTTP) → `services/*` (nghiệp vụ) → MongoDB; schema Pydantic ở
  `app/schemas/*`; lỗi provider chuẩn hoá qua `ProviderError` + bảng `ERRORS`
  (`services/ai/base_provider.py`) và exception handler tập trung.
- Mọi truy vấn nghiệp vụ đều **owner-scoped theo `user_id`** ở tầng service (không dựa vào frontend).
- Cấu hình qua `Settings` (pydantic-settings, đọc `backend/.env`): Mongo URI/database, JWT secret,
  Fernet key, CORS, rate limit, ngân sách workflow (tối đa 12 lượt Agent, timeout 600s, tối đa
  2 lần sửa/task, lease 900s), giới hạn artifact ZIP (50 file/256KB/2MB), cấu hình cầu nối n8n
  (webhook base, callback base, timeout run 1800s). **Chưa có** biến môi trường `ENVIRONMENT`
  (development/demo/production) — đặc tả Seed Data cần biến này.
- Orchestrator Phase 6 (`services/workflows.py`): chạy nền trong tiến trình backend
  (`launch_workflow`), trạng thái bền vững trong MongoDB, chạy tuần tự theo vai trò hiệu dụng
  (Planner → Architect → Researcher → Developer → Tester/Reviewer), vòng sửa có giới hạn,
  ngân sách token tính theo usage thật của provider, có pause/resume/cancel và lease khôi phục.

## 4. Kiến trúc frontend

- Routes thật trong `frontend/app/(workspace)/`: `dashboard/`, `chat/`, `compare/`, `agents/`
  (gồm Agent Studio, `agents/teams`, `agents/workflows` — trang Workflows nay là hub 2 tab
  Workflows/AI Factory sau PR #20), `settings/` (Providers). Route `[section]/` là trang
  placeholder cho các mục chưa xây.
- Component theo miền: `components/chat`, `components/compare`, `components/agents`,
  `components/workflows`, `components/providers`; service layer ở `frontend/services/`
  (axios, baseURL `/api/v1` qua rewrite của Next, cookie auth).
- Trạng thái loading/error/empty được xử lý nhất quán; có ConfirmDialog dùng chung.

## 5. Dữ liệu (tóm tắt — chi tiết ở DATABASE_IMPACT_ANALYSIS.md)

23 collections đang dùng, nổi bật: `users`, `refresh_tokens`, `user_provider_credentials`,
`ai_models`, `conversations`, `multi_chats`, `messages`, `ai_requests`, `comparisons`, `agents`,
`agent_executions`, `tool_executions`, `agent_teams`, `agent_workflows`, `agent_tasks`,
`agent_messages`, `agent_workflow_events`, `agent_workflow_files`, `knowledge_bases`, `documents`,
`activity_logs`, `n8n_factory_runs`. Mọi collection nghiệp vụ đều có `user_id` và index tương ứng.
**Không tồn tại khái niệm workspace** ở bất kỳ tầng nào.

## 6. Điểm mạnh đang có (nền tảng NEXORA nên tận dụng)

1. Cô lập dữ liệu theo chủ sở hữu được thực thi ở backend một cách nhất quán — đúng nguyên tắc
   "không dựa vào ẩn nút ở frontend" mà đặc tả yêu cầu.
2. Provider adapter + registry + đồng bộ model thật theo key từng user, key mã hoá Fernet —
   Module 12 của NEXORA đã có phần lớn.
3. Orchestrator multi-agent chạy thật với ngân sách, timeout, giới hạn vòng sửa, hủy/tạm dừng,
   trạng thái bền vững — Module 07 đã có lõi.
4. Ghi nhận usage/latency thật từ provider (`ai_requests`, `agent_executions`) — nền cho
   Module 11/14 (đánh giá & quan sát), không phải số liệu bịa.
5. Cầu nối n8n bất đồng bộ có callback ký bằng token riêng từng run, idempotent — đúng các
   nguyên tắc tích hợp của Module 09.
6. Kỷ luật "không mock, không hiển thị dữ liệu giả như dữ liệu thật" đã là quy ước của dự án.

## 7. Khoảng trống & rủi ro chính so với đặc tả NEXORA

| # | Khoảng trống / rủi ro | Mức độ | Bằng chứng |
|---|---|---|---|
| 1 | Chưa có Workspace/RBAC: không có workspace, thành viên, vai trò; mọi dữ liệu chỉ có một chủ sở hữu duy nhất | **Cao** — ảnh hưởng gần như mọi module NEXORA | Không có collection/field workspace nào trong `init_indexes()` và schemas |
| 2 | RAG chưa hoạt động: có collection `knowledge_bases`/`documents` và dashboard đếm số tài liệu, nhưng **không có** upload/parse/chunk/embedding/retrieval, không có router tài liệu, không có thư viện parse/embedding trong requirements; hai tool `search_knowledge_base`/`summarize_document` đang bị tắt ở backend | **Cao** — Module 08 gần như phải xây mới trên nền collection sẵn có | `requirements.txt`, danh sách router trong `main.py`, README mục "Chưa triển khai" |
| 3 | Chưa có Human Approval (Module 10): workflow chỉ có pause tự động (`waiting`), không có hàng đợi phê duyệt, không có quyết định approve/reject được lưu | Trung bình | Schemas/workflows không có approval |
| 4 | Chưa có Evaluation Center (Module 11): `/compare` so sánh model theo câu hỏi tự do, nhưng không có dataset/test case/scorecard/regression | Trung bình | Router compare chỉ có CRUD + execute + synthesize |
| 5 | Chưa có Notification Center (Module 15) và Global Search (Module 16); `activity_logs` mới là nhật ký hoạt động cá nhân | Trung bình | Không có collection notifications |
| 6 | Executive Dashboard (Module 01) mới là số đếm cá nhân ở `/dashboard`, chưa có analytics (tỉ lệ hoàn thành, chi phí theo thời gian, phân bổ model…) dù dữ liệu nguồn đã có | Trung bình | `services/dashboard.py` chỉ trả counts |
| 7 | Claude chưa tích hợp (registry `implemented=False`) trong khi đặc tả nêu Claude API là provider chính | Trung bình | Registry provider |
| 8 | Tài liệu lệch thực tế: mục "Chưa triển khai" trong README nói Ollama chưa tích hợp (đã có từ PR #17) và `ARCHITECTURE.md` mục 5 còn mô tả RAG bằng pgvector/PostgreSQL của thiết kế cũ | Thấp — gây nhầm lẫn khi onboard | README.md, ARCHITECTURE.md §5 |
| 9 | Orchestrator chạy trong tiến trình backend: backend restart giữa chừng dựa vào lease + resume thủ công; chưa có hàng đợi bền vững tách rời | Thấp ở quy mô hiện tại | `launch_workflow`, `workflow_lease_seconds` |
| 10 | Chưa có cơ chế Seed Data và biến `ENVIRONMENT`; tài khoản mới bắt đầu từ 0 theo chủ đích trước đây — trái với Part 5 của đặc tả NEXORA (seed có kiểm soát cho dev/demo) | Trung bình | README "không seed dữ liệu demo"; Settings không có trường environment |

## 8. Kết luận audit

Dự án **đủ nền để mở rộng thành NEXORA theo đúng nghĩa "extend, không rebuild"**: auth, provider,
chat, agent, orchestration, n8n đều là hệ thống thật đang chạy. Ba việc nền tảng phải làm trước
mọi module nghiệp vụ mới là: (1) lớp Workspace + vai trò theo cách không phá owner-scope hiện tại,
(2) cơ chế Seed Data an toàn có cờ môi trường, (3) Executive Dashboard tính từ dữ liệu thật đã có.
Chi tiết đối chiếu từng module ở `EXISTING_FEATURES_INVENTORY.md`, tác động dữ liệu ở
`DATABASE_IMPACT_ANALYSIS.md`, lộ trình ở `NEXORA_IMPLEMENTATION_PLAN.md`.
