# MindFlow AI — Thiết kế và lộ trình tích hợp

## Cập nhật theo update_features.md

### Hiện trạng và quyết định

Đã rà soát source handwritten frontend/backend, schemas, tests, scripts và cấu hình; loại trừ secrets, thư viện và build output. Baseline hiện tại (sau Phase 3): 237 backend tests + 68 frontend tests đạt; Ruff/ESLint đạt. Backend đã chuyển sang MongoDB (motor async) thay PostgreSQL/SQLAlchemy/Alembic; Docker vẫn chưa được cài trên máy.

| Hạng mục | Hiện trạng | Phương án |
|---|---|---|
| Frontend | Next.js 16.4.6, React 19.3.1, JSX, Tailwind 4, Axios, Zustand | Giữ nguyên framework, layout, refresh client, loading/error/toast; thêm trang Settings thật |
| Backend | FastAPI 0.162.4, Pydantic 2.14.3, motor 3.6 (MongoDB async) | Mở rộng API → service → repository async; adapter không nằm trong endpoint |
| Database | MongoDB (Atlas/local), 9 collections ứng dụng | Thêm collections `user_provider_credentials`, `ai_models` + unique index; giữ nguyên 7 collections cũ, không tạo lại conversations/documents |
| Authentication | JWT gắn session, refresh rotation, cookie HttpOnly, CSRF Origin, owner filtering | Giữ nguyên issuer, cookie và logic auth; dùng CurrentUser cho API mới |
| AI Integration | Chưa có | Registry capabilities + adapter OpenAI/Gemini/Groq; Claude/DeepSeek/Ollama đánh dấu chưa tích hợp |
| API | /api/v1; Next same-origin rewrite | Thêm /ai/providers và endpoints cấu hình/model/test kết nối |

### Đợt triển khai hiện tại: Foundation bổ sung + Phase 2

Bổ sung nền tảng provider và quản lý kết nối trước, không triển khai tất cả module cùng lúc. Module Chat/Compare/Agent được ưu tiên tiếp theo; không chuyển sang knowledge/RAG trước ba module này.

- Provider registry là metadata cố định trong backend, không cần bảng `ai_providers` chỉ để lặp lại 6 định nghĩa trong mã. Không có danh sách model giả/hardcode: model được đồng bộ từ API thật theo key của từng user.
- Thêm collection `user_provider_credentials`: id, user_id, provider, encrypted_api_key, enabled, default_model, connection_status, last_checked_at, models_synced_at, last_error_code, revision, timestamps; unique index (user_id, provider).
- Thêm collection `ai_models`: id, credential_id (xóa theo credential ở tầng ứng dụng, MongoDB không có FK cascade), model_id, display_name, description, capabilities JSON, input/output token limits, capability_source; unique index (credential_id, model_id). Model catalog gắn credential vì quyền truy cập có thể khác giữa người dùng.
- Giữ nguyên 7 collections cũ; tái sử dụng `ActivityLog` nếu ghi hoạt động cấu hình. Không tăng AIRequest count cho việc chỉ liệt kê model và không tự tạo token/cost usage.
- API key mã hóa bằng Fernet với `CREDENTIAL_ENCRYPTION_KEY` độc lập JWT secret. Payload mã hóa gắn user/provider để chống tráo ciphertext giữa tài khoản. Không trả key, ciphertext, prefix/suffix key hoặc upstream response thô về browser/log.
- Thiếu encryption key: auth/dashboard vẫn chạy; API quản lý báo chưa sẵn sàng, không lưu plaintext hoặc suy ra key từ JWT. Script init_env chỉ thêm key khi chưa có, không tự thay key đã dùng.
- Endpoint provider cố định HTTPS; không nhận base URL tùy ý, không bật adapter Ollama khi chưa có chính sách SSRF. HTTP timeout, giới hạn trang/model/response; không follow redirect mang credentials.
- Kiểm tra kết nối bằng API chỉ đọc danh sách model; không gửi nội dung người dùng, không gọi generation tính phí. Trạng thái connected chỉ xác nhận model listing, **không bảo đảm mọi model có quyền generation/quota**.
- Đồng bộ thất bại giữ cache trước đó nhưng đánh dấu error và ngày sync cũ. Thay key xóa cache/default model và đưa về untested. Revision ngăn kết quả request cũ ghi đè credential vừa được thay/xóa.
- Capabilities dùng true/false/unknown, không suy đoán mọi model hỗ trợ chat/stream/tools. OpenAI /models không cung cấp capabilities nên để unknown; Gemini dùng supportedGenerationMethods, không coi function calling hoặc streaming có mặt khi metadata không nói rõ.

### Hợp đồng API bổ sung

Tất cả endpoint cần CurrentUser, trả Cache-Control: no-store và không có trường bí mật trong response.

| Endpoint | Hợp đồng |
|---|---|
| GET /ai/providers | `{encryption_ready, providers:[{id,name,implemented,configured,enabled,connection_status,default_model,model_count,last_checked_at,models_synced_at,last_error_code}]}` |
| PATCH /ai/providers/{provider} | Body chỉ gồm `api_key?`, `enabled?`, `default_model?`; trả metadata provider; key mới reset model cache |
| POST /ai/providers/{provider}/test | Dùng key đã lưu; sync model list thật; trả `{provider,model_count,scope:"model_listing"}` |
| GET /ai/providers/{provider}/models | `{provider,models:[{id,display_name,description,capabilities,input_token_limit,output_token_limit,capability_source}],synced_at}`; chỉ đọc cache thuộc user |
| DELETE /ai/providers/{provider} | 204; xóa credential và model cache của user, không xóa hội thoại hoặc dữ liệu khác |

Lỗi provider dùng `{detail:{code,message}}` đã làm sạch. Provider trả 401 không được chuyển thành auth 401 của ứng dụng để tránh kích hoạt refresh session vô nghĩa. Không coi danh sách model rỗng là lỗi kết nối nếu upstream trả thành công hợp lệ.

### Các file tạo, sửa và giữ nguyên

- Tạo: `backend/app/services/ai/{base_provider,registry,openai_provider,gemini_provider,ai_factory}.py`, `backend/app/core/credential_vault.py`, `backend/app/models/providers.py`, `backend/app/repositories/providers.py`, `backend/app/services/providers.py`, `backend/app/schemas/providers.py`, `backend/app/api/v1/providers.py`, provider/security tests.
- Sửa tối thiểu backend: model exports; Settings thêm encryption key; main đăng ký router và hỗ trợ PATCH/DELETE CORS; middleware no-store cho API AI; requirements thêm cryptography/httpx. Không nâng framework.
- Tạo frontend: route `/settings`, provider settings components, hook và service, confirm dialog dùng lại được, tests cho transport/validation.
- Sửa tối thiểu frontend: navigation Settings từ placeholder sang trang thật; nhãn MindFlow AI và lộ trình theo đặc tả mới; CSS dành riêng Settings. Không viết lại auth, dashboard data flow, Axios refresh hoặc session store.
- Sửa hỗ trợ: `.env.example`, `scripts/init_env.py`, test harness encryption config, README hướng dẫn key/migration/test, tài liệu này.
- Giữ nguyên: `plan_create_web.md`, `update_features.md`, API auth/contracts, cookie names/issuer, password hashing, 7 collections domain cũ và tài liệu/dữ liệu người dùng. Không commit/push/deploy.

### Lộ trình thay thế lộ trình cũ

1. Foundation: tái sử dụng auth/dashboard/database; bổ sung provider architecture.
2. Multi-AI Integration: OpenAI/Gemini/Groq, credentials mã hóa, model sync/default, bật/tắt và test connection (đợt này).
3. Multi-model Chat: tái sử dụng conversations; thêm messages, adapters generation/stream với capability checks, history/system prompt/temperature/token limits.
4. Compare AI: chạy song song độc lập lỗi, synthesis theo lựa chọn user, usage/cost có nguồn giá và nhãn ước tính.
5. Agent Studio/Execution: agent CRUD, tools allowlist, quyền, timeout/step/token budget và logs.
6. File Intelligence/RAG/Memory: parse file, embedding/vector search, citations, memory tự nguyện và có thể xóa/tắt.
7. Research/Workflow: search service cấu hình, nguồn được kiểm chứng, workflow execution.
8. Production: live provider tests, MongoDB/Docker integration, security/performance/observability/deployment.

Mỗi đợt chạy hồi quy auth/dashboard, unit/API tests, frontend build/lint và kiểm tra UI. Thiếu API key/provider quota hoặc MongoDB/Docker phải ghi rõ, không dùng mock trong ứng dụng và không gọi đó là live verification. Chat/Compare/Agent chưa được coi là đã triển khai chỉ vì có registry/route placeholder.

### Nguồn hợp đồng provider đã đối chiếu

- OpenAI Models API: https://developers.openai.com/api/reference/resources/models/methods/list — `GET https://api.openai.com/v1/models`, Bearer auth, response `{object:"list",data:[{id,object,created,owned_by,...}]}`; không có capability flags.
- Groq Models API (OpenAI-compatible): https://console.groq.com/docs/api-reference#models-list — `GET https://api.groq.com/openai/v1/models`, Bearer auth, response `{object:"list",data:[{id,object,created,owned_by,output_modalities,...}]}`. Adapter Groq kế thừa adapter OpenAI (endpoint cố định) và override `_provider_model`: đánh dấu `chat=false` khi `output_modalities` không chứa `text` (whisper→transcription, orpheus→speech) hoặc id thuộc họ `prompt-guard` (bộ phân loại, đã verify trả 400 khi stream); model chat thường vẫn để unknown vì listing không chứng minh quyền generation.
- Gemini Models API: https://aistudio.google.com/api-reference/models
- Gemini discovery đọc trực tiếp: https://generativelanguage.googleapis.com/$discovery/rest?version=v1beta — `GET /v1beta/models`, pageSize tối đa 1000, pageToken/nextPageToken, models[].supportedGenerationMethods và token limits.
- Probe không có credentials: OpenAI trả 401, Gemini trả 403. Groq đã xác minh listing bằng API key thật (11 model: 5 model chat để unknown, 6 model audio/phân loại bị đánh dấu `chat=false`); đã verify `openai/gpt-oss-20b` stream thật trả delta + usage, còn `llama-prompt-guard-2-86m` trả 400 "text classification models do not support streaming". OpenAI/Gemini chưa có key hợp lệ để live test.

### Đợt triển khai Phase 3: Multi-model Chat

Triển khai sau khi Phase 2 ổn định, ưu tiên Chat trước Compare/Agent. Tái sử dụng tối đa nền tảng hiện có; không viết lại auth/dashboard/provider, không tạo collection trùng.

Quyết định thiết kế:

- **Tái sử dụng collections sẵn có** `conversations`, `messages`, `ai_requests` (đã có trong schema nền). Không tạo bảng mới cho chat. Thêm index compound `conversations(user_id, updated_at desc)` để liệt kê theo thời gian, `messages(conversation_id, created_at)` và `messages(user_id)`; `ai_requests(user_id)` giữ nguyên. `Conversation` bổ sung `system_prompt`, `temperature`, `max_output_tokens`; `Message`/`AIRequest` mang `input_tokens`, `output_tokens`, `latency_ms`, `error_code`, `status`.
- **Generation async trên app loop**: khác với listing (đồng bộ, chạy trong thread), adapter generation (`ChatHTTP.stream`) là async generator tiêu thụ trực tiếp bởi `StreamingResponse`, nên client ngắt kết nối sẽ hủy request provider đang chạy. Endpoint cố định HTTPS, không follow redirect, bỏ qua proxy môi trường, giới hạn bytes/timeout, chỉ chấp nhận `Content-Encoding: identity`.
- **SSE contract**: event `user_message` → nhiều `delta` → `done` (hoặc `error`). Định dạng `event: <name>\ndata: <json>\n\n`. Validation/ownership/capability/credential được kiểm tra TRƯỚC khi mở stream (`prepare_send`/`prepare_regenerate`); lỗi giai đoạn này trả JSON `{detail:{code,message}}` (404/409/422), không phải SSE. Lỗi giữa stream phát event `error` và lưu assistant status `error`.
- **Capability tri-state**: chỉ chặn khi `capabilities.chat is False` rõ ràng; `unknown/null` vẫn cho phép chat. OpenAI `/models` không có capability nên để unknown; Groq dùng `output_modalities` + họ `prompt-guard` để đánh dấu model không chat là `false` (loại khỏi picker), phần còn lại để unknown. Model phải thuộc catalog đã đồng bộ của credential; provider phải implemented + configured + enabled.
- **Chống lộ key**: `SecretRedactor` quét cửa sổ trượt trên text delta đã trích xuất (bắt cả trường hợp key bị chia cắt giữa hai delta); `_sse_events` cũng quét trên data thô. Key giải mã trong backend, không trả ciphertext/plaintext về browser/log; lỗi chỉ mang mã công khai cố định.
- **Cô lập chủ sở hữu + nhất quán lịch sử**: mọi truy vấn lọc `user_id`; regenerate thay assistant cuối sau user turn cuối, giữ tính nhất quán; xóa hội thoại xóa kèm messages. Nội dung đã sinh khi hủy được lưu bền vững (`_persist_partial` shielded khi `CancelledError`) với status `stopped`. Usage token là số thật provider trả về; không tự bịa token/cost, không tăng AIRequest cho việc chỉ liệt kê.
- **Frontend**: `/chat` là route thật (loại `chat` khỏi `sections` placeholder để `[section]` không xung đột). SSE client dùng `fetch` (axios không stream được trong browser) với `credentials: include`, `AbortController`, và refresh cookie một lần khi 401 rồi retry — gương interceptor axios nhưng không sửa `services/api.js` dùng chung. Hook dẫn xuất trạng thái loading trong render (không setState đồng bộ trong effect) để đạt rule `react-hooks/set-state-in-effect`. Markdown render bằng `react-markdown` + `remark-gfm`, KHÔNG bật raw HTML nên output model không inject markup.

Hợp đồng API chat (prefix `/api/v1/ai/chat`, cần CurrentUser, `Cache-Control: no-store`):

| Endpoint | Hợp đồng |
|---|---|
| GET `/conversations` | `{conversations:[ConversationSummary]}` |
| POST `/conversations` | `{provider,model,title?,system_prompt?,temperature?(0–2),max_output_tokens?(1–8192)}` extra=forbid → 201 |
| GET `/conversations/{id}` | `ConversationDetail` = summary + `messages:[MessageOut]` |
| PATCH `/conversations/{id}` | ≥1 trường `title?/system_prompt?/temperature?/max_output_tokens?`; không đổi provider/model; title không null |
| DELETE `/conversations/{id}` | 204; xóa hội thoại + messages |
| POST `/conversations/{id}/messages` | `{content}` (1–32000, strip) → `text/event-stream` |
| POST `/conversations/{id}/regenerate` | không body → `text/event-stream`, thay assistant cuối |

`MessageOut`: `{id,role,content,status,model,input_tokens,output_tokens,latency_ms,error_code,created_at}`. Mã lỗi: `conversation_not_found`(404), `model_not_chat_capable`/`model_not_synced`/`provider_disabled`/`credentials_missing`(409), `empty_message`/`invalid_provider_configuration`(422), `generation_failed`/`provider_unavailable`(502), `provider_authentication_failed`(400), `provider_rate_limited`(429), `provider_timeout`(504), `encryption_unavailable`(503).

Các file tạo, sửa và giữ nguyên (Phase 3):

- Tạo backend: `app/services/ai/{chat,chat_types}.py` (ChatHTTP, SecretRedactor, ChatRequest/ChatEvent), `app/services/chat.py` (ChatService + PreparedChat), `app/repositories/chat.py`, `app/schemas/chat.py`, `app/api/v1/chat.py`; tests `tests/test_chat.py`, `tests/test_chat_adapters.py`.
- Sửa tối thiểu backend: `openai_provider.py`/`gemini_provider.py` thêm `stream_chat` + redactor; `groq_provider.py` kế thừa OpenAI (chỉ khác endpoint); `models/entities.py` bổ sung trường conversation/message/ai_request; `core/database.py` thêm index chat; `main.py` đăng ký router chat + exception handler cho `/api/v1/ai`; `tests/test_security.py` thêm 4 route chat vào danh sách OpenAPI. Không nâng framework, không đổi auth/cookie.
- Tạo frontend: `services/chat.js`, `utils/chat.js`, `hooks/use-chat.js`, `hooks/use-chat-providers.js`, `components/chat/*` (markdown, message-item, message-list, composer, conversation-list, config-editor, setup-panel, conversation-view, chat-workspace), route `app/(workspace)/chat/{page.jsx,chat.css}`, tests `tests/chat.test.js`, `tests/chat-ui.test.jsx`.
- Sửa tối thiểu frontend: `utils/navigation.js` (bỏ `chat` khỏi sections), `components/app-shell.jsx` (nav `/chat` thật), `utils/app-config.js` (stage Phase 3), `tests/format.test.js` (sections còn 4). Không viết lại auth/dashboard/provider UI, Axios refresh hay session store.
- Giữ nguyên: `plan_create_web.md`, `update_features.md`, API auth/provider contracts, cookie names/issuer, password hashing, collections domain cũ và dữ liệu người dùng. Không commit/push/deploy.

Kiểm chứng Phase 3: backend **237 tests** + Ruff đạt; frontend **68 tests** + ESLint đạt + Next build thành công. Groq **live chat** stream nhận delta `"OK"` + usage thật (76/41), không lộ key. Geometry offline (iframe 360/390/768/1440, đo bằng số, không chụp ảnh): không tràn ngang ở document/`.page-content`/`.chat-layout` cho cả conversation view lẫn setup panel. Chưa live test OpenAI/Gemini (chưa có key hợp lệ); chưa build Docker; xác nhận thiết bị thật dành cho người dùng.

---

## Thiết kế ban đầu AI Knowledge Hub (giữ để tham chiếu)

Phần dưới mô tả baseline PostgreSQL/pgvector ban đầu (giữ để tham chiếu lịch sử). Stack hiện hành đã chuyển sang MongoDB async (motor); thứ tự phase hiện hành là phần cập nhật ở trên. Các bảng, pgvector và Alembic bên dưới không còn là stack đang chạy.

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
