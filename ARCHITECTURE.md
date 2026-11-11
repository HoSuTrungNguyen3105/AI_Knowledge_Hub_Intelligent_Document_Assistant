# AI Knowledge Hub — Thiết kế và lộ trình

## 1. Phân tích phạm vi

Đặc tả yêu cầu sản phẩm full-stack có dữ liệu thật, không phải UI demo. Triển khai lần lượt sáu phase; mỗi phase phải chạy kiểm tra trước khi chuyển tiếp. Bản đầu tiên tập trung Phase 1: hạ tầng, đăng ký/đăng nhập/đăng xuất, quản lý phiên và dashboard. Không dựng các nút upload/chat/agent giả hoạt động.

Ràng buộc: Next.js App Router dùng JavaScript/JSX; backend Python 3.12+; PostgreSQL và pgvector; Alembic quản lý schema; API key chỉ ở backend. Dữ liệu mọi tài nguyên được lọc theo chủ sở hữu ở backend, không chỉ ẩn ở giao diện.

## 2. Kiến trúc

```text
Browser
  → Next.js :3000 (App Router, Tailwind, Zustand, Axios)
    → /api/v1/* (same-origin rewrite)
      → FastAPI :8000
        → API/Pydantic → services → repositories/SQLAlchemy
          → PostgreSQL :5432 + pgvector
          → providers OpenAI/Gemini (Phase 4)
          → xử lý tài liệu/RAG (Phase 2–3)
          → bộ công cụ agent đã đăng ký (Phase 5)
```

Frontend: `app` chỉ tổ chức route; component hiển thị; hooks điều phối truy vấn; services gọi API; Zustand giữ người dùng hiện tại, không lưu JWT vào localStorage. Các trang Knowledge, Chat, Agents, Notes, Settings chưa triển khai sẽ nêu đúng phase thay vì giả dữ liệu.

Backend: request/response ở `schemas`; route trong `api/v1`; logic xác thực trong `services`; truy vấn dữ liệu trong `repositories`; model trong `models`; cấu hình/security/database trong `core`. Phase 1 dùng SQLAlchemy đồng bộ và route đồng bộ để FastAPI chạy I/O DB trong thread pool. Streaming/provider async được bổ sung ở phase tương ứng.

JWT access có thời hạn 15 phút. Refresh token là chuỗi ngẫu nhiên 256 bit, lưu SHA-256 ở DB, thời hạn 7 ngày; xoay token mỗi lần refresh. Cookie HttpOnly, SameSite=Lax; Secure khi triển khai HTTPS. Access JWT liên kết session để logout vô hiệu hóa cả access token. Các request thay đổi trạng thái có cookie phải có Origin nằm trong allowlist nhằm chống CSRF. Frontend chỉ thử refresh một lần và gom các refresh đồng thời.

Rate limit Phase 1 là in-memory, dùng một backend worker. Khi scale nhiều worker/replica phải thay bằng bộ đếm dùng chung (Redis/gateway). Không tin trực tiếp X-Forwarded-For từ client.

## 3. Schema dữ liệu

Tất cả ID dùng UUID; timestamps UTC. Foreign key có chính sách xóa rõ ràng. Các tài nguyên cấp cao có `user_id` được index. Tuyệt đối không trả password hash, token hash hoặc API key qua API.

| Bảng | Cột chính / quan hệ | Giai đoạn |
|---|---|---|
| users | id, email unique, name, password_hash, created_at | 1 |
| refresh_tokens | id (session id), user_id → users, token_hash unique, expires_at, revoked_at, created_at | 1 |
| knowledge_bases | id, user_id → users, name, description, created_at, updated_at | Schema nền ở 1; CRUD ở 2 |
| documents | id, user_id → users, knowledge_base_id → knowledge_bases, original_filename, file_size, mime_type, storage_path, status, chunk_count, error_message, created_at | Schema nền ở 1; xử lý ở 2 |
| conversations | id, user_id → users, knowledge_base_id nullable, title, provider, model, created_at, updated_at | Schema nền ở 1; chat ở 3–4 |
| ai_requests | id, user_id → users, provider, model, status, created_at | Schema nền ở 1; ghi usage ở 3–5 |
| activity_logs | id, user_id → users, action, description, created_at | 1 |
| document_chunks | id, document_id → documents, chunk_index, content, page_number nullable, metadata JSONB, embedding vector, embedding_provider/model/version | 2–3 |
| messages | id, conversation_id → conversations, role, content, citations JSONB, status, created_at | 3–4 |
| notes | id, user_id → users, title, content, created_at, updated_at | 5 |
| agent_executions | id, user_id → users, prompt, provider, model, status, result, steps, created_at | 5 |
| tool_executions | id, agent_execution_id → agent_executions, tool_name, arguments JSONB, result JSONB, status, duration_ms, created_at | 5 |
| user_settings | user_id unique, provider, model, temperature, embedding_provider/model, chunk_size/overlap, top_k, encrypted_api_keys | 6 |

pgvector extension được bật trong migration PostgreSQL đầu tiên. Cột vector và index HNSW được thêm ở Phase 3 khi xác định embedding model/dimension. Không trộn vector từ hai model hoặc dimension khác nhau. Đổi embedding model yêu cầu re-index, không âm thầm tìm kiếm trên vector cũ.

## 4. Hợp đồng API

Prefix `/api/v1`. JSON lỗi chuẩn của FastAPI: `{ "detail": "..." }`, validation dùng HTTP 422. Response không chứa bí mật. ID là chuỗi UUID; thời gian ISO 8601.

### Phase 1 — triển khai ngay

| Method + path | Request | Response |
|---|---|---|
| GET /health | Không | `{status:"ok"}`; 503 nếu DB chưa sẵn sàng |
| POST /auth/register | `{name,email,password}` | 201: `{user:{id,name,email,created_at}}` + cookies |
| POST /auth/login | `{email,password}` | 200: `{user:{...}}` + cookies |
| POST /auth/refresh | Cookie refresh | 200: `{user:{...}}` + cookies mới |
| POST /auth/logout | Cookie phiên | 204 + xóa cookies, revoke session |
| GET /auth/me | Cookie access | `{id,name,email,created_at}` |
| GET /dashboard | Cookie access | `{total_documents,total_knowledge_bases,total_conversations,ai_requests_usage,recent_activity:[{id,action,description,created_at}]}` |

Email chuẩn hóa lowercase; password 10–128 ký tự; name 1–100 ký tự. Đăng ký tự tạo phiên. Sai email/mật khẩu trả cùng thông báo 401. Email trùng trả 409. Auth có rate limit trả 429 + Retry-After. Dashboard chỉ aggregate dữ liệu của user đang đăng nhập; tài khoản mới có số đếm bằng 0 từ DB và hoạt động đăng ký thật.

### Các phase tiếp theo — chưa có endpoint giả

- Phase 2: CRUD `/knowledge-bases`; upload multipart `/documents/upload` với `knowledge_base_id`, `file`; list/detail/delete/status theo đặc tả. Status: queued → processing → ready/failed; giới hạn kích thước và kiểm tra signature/MIME, tên file không dùng làm đường dẫn lưu trữ.
- Phase 3–4: CRUD `/chat/conversations`, PATCH rename, messages thường/stream; body `{content,provider,model,temperature,knowledge_base_id,rag_enabled}`. SSE gồm `token`, `sources`, `done`, `error`; stop dùng AbortController và hủy tác vụ provider; regenerate giữ tính nhất quán lịch sử.
- Phase 4: `/ai/providers`, `/ai/generate`, `/ai/embeddings`; structured output được validate bằng Pydantic, không chỉ parse JSON không kiểm tra.
- Phase 5: `/ai/agent/run`, logs theo execution, CRUD `/notes`. Confirmation dùng mã xác nhận ràng buộc user/execution/arguments, không để model tự cấp quyền.
- Phase 6: GET/PATCH `/settings`; API key chỉ nhận lúc ghi, đọc lại chỉ `configured: true/false`; mã hóa backend bằng khóa riêng từ môi trường, không trả ciphertext ra browser.

Các route có tài nguyên ID phải kiểm tra ownership trong truy vấn DB và trả 404 cho tài nguyên của user khác. Phân trang và metadata filtering được bổ sung với CRUD, không tải toàn bộ nội dung lên frontend.

## 5. RAG pipeline

1. Xác thực user/knowledge base, kiểm tra dung lượng, extension + MIME + nội dung và lưu file bằng tên nội bộ.
2. Job xử lý có trạng thái bền vững: trích PDF theo trang, DOCX theo đoạn, TXT/Markdown UTF-8; giới hạn số trang/kích thước giải nén, báo rõ PDF scan cần OCR.
3. Normalize khoảng trắng, chunk có overlap cấu hình; giữ filename, page và vị trí chunk.
4. Provider embedding tạo vector; lưu cùng model/version/dimension vào pgvector. Retry có giới hạn, tránh ghi trùng.
5. Câu hỏi → embedding cùng model → similarity search có filter `user_id`, knowledge base, metadata → top-K.
6. Ngữ cảnh coi là dữ liệu không đáng tin, không phải chỉ dẫn hệ thống. LLM chỉ trả lời dựa trên các trích đoạn khi bật RAG; không đủ dữ liệu phải nói rõ.
7. Trả đáp án kèm citation ID/filename/page/score do backend gắn với kết quả truy xuất, không tin citation model bịa ra.

Không truy xuất đủ ngữ cảnh thì không giả câu trả lời có căn cứ. Kiểm thử bằng tài liệu nhỏ có đáp án biết trước, câu hỏi ngoài tài liệu và dữ liệu của hai người dùng.

## 6. AI Agent

Input + user context → provider adapter nhận schema tool → tool call thật → allowlist → validate Pydantic → ownership/confirmation → execute → lưu log → gửi observation cho model → lặp tối đa N bước → final response.

Năm tool: `search_knowledge_base`, `summarize_document` (short/detailed), `calculator` (AST allowlist và giới hạn độ phức tạp, không eval), `create_note`, `search_conversation_history`. Không cho model chạy shell/code tùy ý. Tool result có cấu trúc, giới hạn độ dài, không chứa API key. Tool lỗi được log và trả observation an toàn. Provider-specific adapter xử lý khác biệt OpenAI/Gemini, không giả định hai API giống nhau.

## 7. Kế hoạch theo phase

- Phase 1: khởi tạo frontend/backend, PostgreSQL/pgvector/Alembic, Docker Compose; xác thực và dashboard thật; kiểm thử auth, cô lập dữ liệu và production build.
- Phase 2: CRUD knowledge base, upload, parser, job xử lý, chunks và trạng thái; kiểm thử file sai loại/quá lớn/khác chủ sở hữu.
- Phase 3: embedding, similarity search, RAG, citation; kiểm thử truy xuất và trường hợp không đủ thông tin.
- Phase 4: adapters OpenAI/Gemini, streaming, structured outputs và chat hoàn chỉnh; live test cần API key do người dùng tự cấu hình.
- Phase 5: agent/tool calling, notes, tool logs và confirmation; kiểm thử từng tool, step limit và payload không hợp lệ.
- Phase 6: settings hoàn chỉnh, UX/error/loading states, kiểm thử end-to-end, hardening, hướng dẫn deploy.

Không đánh dấu các phase 2–6 hoàn thành chỉ vì đã thiết kế schema. Kết quả kiểm thử và giới hạn môi trường của Phase 1 được ghi trong README sau khi chạy thực tế.
