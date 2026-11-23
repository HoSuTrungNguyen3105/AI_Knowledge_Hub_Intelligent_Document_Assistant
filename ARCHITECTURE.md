# MindFlow AI — Thiết kế và lộ trình tích hợp

## Cập nhật theo update_features.md

### Hiện trạng và quyết định

Đã rà soát source handwritten frontend/backend, schemas, tests, scripts và cấu hình; loại trừ secrets, thư viện và build output. Baseline hiện tại (sau Phase 5): 360 backend tests + 161 frontend tests đạt; Ruff/ESLint đạt; Next build thành công. Backend đã chuyển sang MongoDB (motor async) thay PostgreSQL/SQLAlchemy/Alembic; Docker vẫn chưa được cài trên máy.

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
4. Compare AI: chạy song song độc lập lỗi, synthesis theo lựa chọn user, usage/cost có nguồn giá và nhãn ước tính (đã triển khai — xem mục Phase 4 bên dưới).
5. Agent Studio/Execution: agent CRUD, tools allowlist, quyền, timeout/step/token budget và logs (đã triển khai — xem mục Phase 5 bên dưới).
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

### Đợt triển khai Phase 4: Multi-AI Comparison

Triển khai sau khi Phase 3 ổn định, ưu tiên Compare trước Agent. Tái sử dụng tối đa nền tảng provider/chat hiện có; không viết lại auth/dashboard/provider/chat, không tạo collection trùng.

Quyết định thiết kế:

- **Collection mới `comparisons`** (không dùng lại `conversations` vì một phép so sánh có nhiều run song song + một synthesis, khác cấu trúc hội thoại tuần tự). `Comparison` mang `user_id`, `title`, `prompt`, `system_prompt`, `temperature`, `max_output_tokens`, `runs`, `synthesis`, timestamps. Thêm index compound `comparisons(user_id, updated_at desc)` để liệt kê theo thời gian; mọi truy vấn lọc `user_id`.
- **`runs` là map keyed by id, không phải array**: `runs: dict[str, ComparisonRun]`. Lý do: mongomock (test offline) KHÔNG implement `array_filters`, nên cập nhật từng run dùng dotted `$set` `runs.{run_id}.{key}` thay vì positional array. API vẫn xuất `runs` dạng LIST (`ComparisonDetail.runs`) để frontend render cột; repository/service iterate `.values()`. Mỗi `ComparisonRun`/`ComparisonSynthesis` mang `status(pending|success|stopped|error)`, `content`, `input_tokens`, `output_tokens`, `latency_ms`, `error_code`, `estimated_cost`.
- **Chạy song song độc lập lỗi**: `CompareService.stream_prepared` spawn một `asyncio.create_task(run_one)` mỗi target, dùng chung `asyncio.Queue`; vòng lặp chính `while finished < len(tasks)` tiêu thụ event. Một run lỗi chỉ phát `run_error` cho run đó, các run khác vẫn chạy và lưu kết quả. `run_one` có try/except phòng thủ quanh `_persist_run` để LUÔN phát một event terminal (`run_done`/`run_error`) kể cả khi persist lỗi. Client ngắt kết nối → `CancelledError` cancel + gather tất cả task; nội dung đã sinh lưu với status `stopped`.
- **Chi phí ước tính có nguồn giá, gắn nhãn rõ**: `_estimate_cost(model, in, out)` cộng `price * token` cho từng phía có giá, else `None`. Groq công bố giá per-token USD (string) trong `/models` → `GroqProvider._provider_model` capture `input_price_per_token`/`output_price_per_token` (helper `_price` parse an toàn, loại giá âm). Provider không công bố giá (OpenAI) → `estimated_cost = null`, frontend hiện `—`. Frontend luôn prefix `≈` và title ghi rõ đây là ước tính, không phải khoản phí provider xác nhận. Không tự bịa token/giá.
- **Capability + cô lập chủ sở hữu**: mỗi target qua `_require_target` (provider implemented + configured + enabled, model đã đồng bộ, chỉ chặn khi `capabilities.chat is False`). Synthesis chỉ chạy khi có ≥1 run `success` (`no_successful_runs` 409). Tái sử dụng `ChatHTTP.stream` + `SecretRedactor` của Phase 3 nên key không lộ kể cả khi bị chia cắt giữa nhiều delta; lỗi chỉ mang mã công khai cố định.
- **SSE contract**: execute → `comparison` (detail đầu) → nhiều `run_delta`/`run_done`/`run_error` → `done`. synthesize → `synthesis_delta`/`synthesis_done`/`synthesis_error` → `done`. Validation/ownership/target/credential kiểm tra TRƯỚC khi mở stream (`prepare_execute`/`prepare_synthesize`); lỗi giai đoạn này trả JSON `{detail:{code,message}}` (404/409/422), không phải SSE.
- **Frontend**: `/compare` là route thật (loại `compare` khỏi `sections` placeholder để `[section]` không xung đột; sections còn 3: knowledge/agents/notes). Tái sử dụng `streamChat` (fetch SSE + AbortController + refresh 401 một lần) của Phase 3, KHÔNG sửa `services/api.js`/`services/chat.js` dùng chung. Hook `use-compare` dẫn xuất loading trong render (không setState đồng bộ trong effect) để đạt rule `react-hooks/set-state-in-effect`; `runText` accumulate delta theo run_id, xóa khi run terminal. `.run-columns` dùng `repeat(auto-fit, minmax(min(100%, 280px), 1fr))` → 2/3/4 cột tự xuống hàng ở màn hẹp. Markdown render bằng `react-markdown` + `remark-gfm`, KHÔNG bật raw HTML. UI phẳng theo design system hiện có (không gradient/glow), tái sử dụng class `.conversation-list`/`.conversation-item`/`.message-flag`/`.setup-panel`.

Hợp đồng API compare (prefix `/api/v1/ai/compare`, cần CurrentUser, `Cache-Control: no-store`):

| Endpoint | Hợp đồng |
|---|---|
| GET `/comparisons` | `{comparisons:[ComparisonSummary]}` (summary có `targets:[{provider,model}]`, `has_synthesis`) |
| POST `/comparisons` | `{prompt(1–32000,strip),targets:[{provider,model}](2–4 khác nhau),title?,system_prompt?(≤8000),temperature?(0–2),max_output_tokens?(1–8192)}` → 201 + detail |
| GET `/comparisons/{id}` | `ComparisonDetail` = `{...,runs:[RunOut],synthesis:SynthesisOut|null}` |
| DELETE `/comparisons/{id}` | 204; xóa phép so sánh của user |
| POST `/comparisons/{id}/execute` | không body → `text/event-stream`, chạy song song |
| POST `/comparisons/{id}/synthesize` | `{provider,model}` → `text/event-stream`, tổng hợp run thành công |

`RunOut`/`SynthesisOut`: `{id,provider,model,status,content,input_tokens,output_tokens,latency_ms,error_code,estimated_cost}`. Mã lỗi mới: `comparison_not_found`(404), `invalid_comparison_targets`(422), `no_successful_runs`(409); dùng chung mã provider/chat của Phase 2–3.

Các file tạo, sửa và giữ nguyên (Phase 4):

- Tạo backend: `app/services/compare.py` (CompareService + PreparedRun/PreparedCompare/PreparedSynthesis), `app/repositories/compare.py`, `app/schemas/compare.py`, `app/api/v1/compare.py`; tests `tests/test_compare.py` (13 tests).
- Sửa tối thiểu backend: `models/entities.py` thêm `Comparison`/`ComparisonRun`/`ComparisonSynthesis` (`runs` là dict); `core/database.py` thêm index `comparisons`; `services/ai/base_provider.py` thêm 3 mã lỗi compare; `services/ai/openai_provider.py` thêm `OpenAIPricing` + `output_modalities`/`pricing` vào `OpenAIModel`; `services/ai/groq_provider.py` thêm `_price` + capture giá + đánh dấu non-chat; `main.py` đăng ký router compare; `tests/test_security.py` thêm 4 route compare vào allowlist OpenAPI. Không nâng framework, không đổi auth/cookie/chat.
- Tạo frontend: `services/compare.js`, `utils/compare.js`, `hooks/use-compare.js`, `components/compare/*` (compare-workspace, comparison-list, compare-setup, run-column, synthesis-panel, comparison-view), route `app/(workspace)/compare/{page.jsx,compare.css}`, tests `tests/compare.test.js` (11) + `tests/compare-ui.test.jsx` (17).
- Sửa tối thiểu frontend: `utils/navigation.js` (bỏ `compare` khỏi sections), `components/app-shell.jsx` (nav `/compare` thật, icon Columns2), `tests/format.test.js` (sections còn 3). Không viết lại auth/dashboard/provider/chat UI, Axios refresh hay session store.
- Giữ nguyên: `plan_create_web.md`, `update_features.md`, API auth/provider/chat contracts, cookie names/issuer, password hashing, collections domain cũ và dữ liệu người dùng. Không commit/push/deploy.

Kiểm chứng Phase 4: backend **251 tests** + Ruff đạt; frontend **100 tests** + ESLint đạt + Next build thành công (`/compare` route tĩnh, `[section]` chỉ sinh knowledge/agents/notes). Groq **live compare** (đúng đường adapter CompareService dùng, không ghi DB, key không in ra): 2 model chat trả `"4"` + usage thật + chi phí ước tính từ giá Groq; 1 model non-chat (`whisper-large-v3`) `generation_failed`; **cô lập lỗi** 2 thành công + 1 thất bại không hủy nhau; **synthesis** gộp đáp án thành công trả `"4"`. Geometry offline (Node + iframe 1440/1200/1000/760/380, đo bằng số, không chụp ảnh): `docOverflow/worst/clip = 0` ở mọi chiều rộng và biến thể 2/3/4 cột + setup. Chưa live test OpenAI/Gemini (chưa có key hợp lệ); chưa build Docker; xác nhận thiết bị thật dành cho người dùng.

### Đợt triển khai Phase 5: Agent Studio và Execution

Triển khai Agent sau Chat/Compare, chưa chuyển sang Phase 6. Giữ Next.js/JSX, FastAPI async và MongoDB/motor; tái sử dụng provider credentials mã hóa, model catalog, `ChatHTTP`, cookie/CSRF/rate limiter, `ai_requests`, Markdown và SSE client.

Quyết định thiết kế:

- **Studio:** CRUD/nhân bản Agent theo user, cấu hình name/description/system prompt/provider/model/temperature/token ra/tools. Nhân bản chỉ sao chép cấu hình. Avatar là chữ viết tắt; upload ảnh, Knowledge Base và memory chưa khả dụng. Mỗi lượt chạy độc lập, không đưa lịch sử vào context của lượt sau.
- **Dữ liệu:** thêm ba collections `agents`, `agent_executions`, `tool_executions`, không trùng collection domain đang chạy. Execution lưu snapshot provider/model, prompt, trạng thái, content, steps, usage và cost ước tính; mỗi bước chứa tool trace. Audit tool độc lập phục vụ xem lại. Mọi truy vấn lọc `user_id`; endpoint nested kiểm tra cả `agent_id`. Xóa execution xóa audit; xóa Agent xóa lịch sử/audit. Index bổ sung trong `core/database.py` được áp dụng idempotent khi khởi động theo cơ chế MongoDB hiện hành; không xóa dữ liệu hay thêm Alembic/SQL migration. Không tạo collection `agent_tools` chỉ để lặp metadata registry cố định.
- **Tools có quyền rõ ràng:** Calculator (AST giới hạn, không `eval`), DateTime (now/diff với UTC offset cố định), Data Analyzer (thống kê mô tả trên dãy số hữu hạn). Agent chỉ dùng tool đã bật; backend validate Pydantic `extra=forbid`, giới hạn kích thước/kết quả, từ chối tool lạ hoặc chưa khả dụng. Document Search/Knowledge Search/Text Summarizer/Web Search là deferred metadata, không gọi giả. Không đọc file người dùng, truy cập mạng, tạo note hay thực thi code/shell tùy ý từ tool.
- **Function calling:** OpenAI/Groq nhận function schemas, tích lũy fragment thành lời gọi hoàn chỉnh và replay assistant/tool turns. Gemini dùng `functionDeclarations`, `functionCall` và `functionResponse`; kết quả song song gom thành một Content theo thứ tự. Provider call ID/thought signature được giữ nguyên trên đúng Part khi replay, chỉ trong backend; không đưa opaque metadata vào API trace/audit. Capabilities tri-state: `chat=false` chặn chat, `tools=false` chặn Agent có tools; unknown chỉ cho phép thử thật, không bảo đảm hỗ trợ.
- **Giới hạn:** tối đa 6 bước model, deadline 120 giây, 4 tool được thực thi mỗi bước, timeout tool 10 giây, 16 tool calls nhận tối đa từ một lượt sinh. Ngân sách 8.000 đơn vị ước lượng bảo thủ dùng UTF-8 bytes + framing, bao gồm system/context/tools/replay metadata và output; context gửi lại được tính lại mỗi bước. Giới hạn vẫn hoạt động khi provider không trả usage, không dùng ước lượng này làm số token hóa đơn. Tool chạy trong thread chỉ với tính toán giới hạn; timeout không phải sandbox cho code tùy ý.
- **Persistence khi dừng:** SSE wrapper đóng inner generator rõ ràng; cleanup/finalizer chạy trong task shielded để hủy request không làm lịch sử kẹt `running`. Phần text/trace đã nhận lưu `stopped`; hủy đúng lúc finalizer đang ghi không chạy finalizer lần hai. Tham số JSON không encode được BSON (số nguyên ngoài int64, key chứa NUL, v.v.) được thay bằng marker từ chối trước SSE/audit và trả observation `tool_invalid_arguments`, không làm hỏng lưu terminal.
- **Usage/cost trung thực:** bước nào thiếu usage thì giữ null cho bước đó. Tổng input/output chỉ hiện nếu mọi bước đã gọi đều cung cấp phía tương ứng; số 0 thật được giữ nguyên. Thiếu một phía hoặc không có giá công bố → cost ước tính null, không dùng tổng một phần như toàn bộ chi phí. Ghi một `ai_requests` aggregate cho mỗi execution.
- **Frontend:** `/agents` là route thật, không còn placeholder `[section]`; editor, run view, step/tool trace, final Markdown, stop, history detail/delete và confirm dialogs dùng lại design system phẳng. Hook bảo vệ session/identity/revision, hủy request khi đổi Agent/unmount và bỏ event cũ. Thông báo rõ prompt/trace được lưu vào lịch sử; KB/Memory/tools giai đoạn sau bị vô hiệu hóa.

Hợp đồng API (prefix `/api/v1/ai/agents`, cần đăng nhập, no-store):

| Endpoint | Hợp đồng |
|---|---|
| GET `/tools` | `{tools:[{name,description,parameters,available,phase}]}` |
| GET/POST đường gốc | Danh sách Agent / `{name,provider,model,description?,system_prompt?,temperature?,max_output_tokens?,tools?}` → 201 + detail |
| GET/PATCH/DELETE `/{agent_id}` | Đọc/sửa cấu hình / xóa kèm lịch sử và audit |
| POST `/{agent_id}/duplicate` | 201 + bản sao cấu hình, không sao chép history |
| POST `/{agent_id}/run` | `{prompt}` → SSE; validation/ownership/capability/budget kiểm tra trước stream |
| GET `/{agent_id}/executions` | `{executions:[ExecutionSummary]}` |
| GET/DELETE `/{agent_id}/executions/{execution_id}` | Detail với steps/tool audit/usage / xóa run + audit |

SSE: `execution` → `step_delta`, `tool_call`, `tool_result`, `step_done` → `done`; runtime lỗi phát `execution_error` rồi `done` có trạng thái lỗi. Tool lỗi thành observation an toàn để model có thể tiếp tục. Mã lỗi bổ sung: `agent_not_found`/`execution_not_found` (404), `invalid_agent_tools` (422), `model_not_tool_capable`/`agent_step_limit`/`agent_budget_exceeded` (409), `agent_timeout` (504); dùng lại mã provider/chat và chính sách key/CSRF hiện hành.

Các file tạo/sửa/giữ nguyên:

- Backend mới: `app/services/ai/tools.py`, `app/{schemas,repositories,services,api/v1}/agents.py`, tests tools/agent persistence/API. Backend mở rộng: `models/entities.py` + exports, `core/database.py`, `main.py`, `services/ai/{chat_types,base_provider,openai_provider,gemini_provider}.py`, tests adapter/security. Groq kế thừa OpenAI, không thêm transport trùng.
- Frontend mới: `services/agents.js`, `utils/agents.js`, `hooks/use-agents.js`, `components/agents/*`, `app/(workspace)/agents/{page.jsx,agents.css}`, ba test files agents. Sửa nhỏ navigation/app-shell/dashboard/app-config và `use-chat-providers` (initial provider/revision để editor dùng lại đúng model picker).
- Giữ nguyên auth/cookie/refresh, dashboard API, provider credential logic, luồng Chat/Compare, công nghệ/dependencies, đặc tả gốc, collections và dữ liệu cũ. Chỉ cập nhật nhãn lộ trình ở Chat/auth để không còn nói Agent chưa triển khai. Không commit/push/deploy.

Kiểm chứng Phase 5: backend **360 tests** + Ruff + `pip check` đạt; frontend **161 tests** (61 tests Agent mới) + ESLint + production build đạt, `/agents` là route tĩnh và `[section]` chỉ còn knowledge/notes. Groq **live HTTP → FastAPI → MongoDB Atlas** với `openai/gpt-oss-20b`: Calculator `17*23+5` → `396` (743/72 token), DateTime UTC+7 → ISO hợp lệ (817/92), Data Analyzer `[10,20,30,40]` → mean `25` (796/112); cả ba success trong 2 bước và GET lịch sử khớp stream. Key chỉ đọc lúc kiểm thử, mã hóa qua API hiện hành, không xuất hiện trong SSE/source/log; tài khoản tạm và dữ liệu của riêng tài khoản này được dọn sau kiểm chứng. OpenAI/Gemini mới kiểm chứng hợp đồng offline, chưa live; Docker chưa có trên máy. Geometry offline 360/390/768/1000/1440px: overflow ngang document 0px, danh sách Agent dài không còn giãn rộng, trace/code/bảng cuộn nội bộ; xác nhận trên thiết bị thật dành cho người dùng.

Nguồn hợp đồng replay Gemini: [Function calling](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/multimodal/function-calling), [Thought signatures](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/thought-signatures). Đây là bằng chứng định dạng API, không phải live verification bằng key Gemini.

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


### Đợt triển khai Phase 6: Multi-Agent Collaboration

Mở rộng Agent Studio từ các Agent chạy độc lập thành nhóm Agent phối hợp trong một workflow chung, giữ nguyên Next.js → FastAPI → MongoDB, auth/cookie/Fernet và provider adapters hiện có; không thêm Redis/queue/Google Sheets.

Quyết định thiết kế:

- **5 collections mới** (index tạo idempotent lúc khởi động như các collection cũ, mọi truy vấn lọc `user_id` từ phiên đăng nhập): `agent_teams` (nhóm + `coordinator_agent_id` + members `{agent_id, role, enabled}`), `agent_workflows` (goal, status `queued|running|waiting|completed|failed|cancelled`, `current_step`, `max_steps`, `budget`, `usage`, `final_result`, lease `lease_owner`/`lease_expires_at`), `agent_tasks` (status `pending|in_progress|review|completed|failed|cancelled`, `revision_count`), `agent_messages` (đủ 12 `message_type` theo đặc tả, status `PENDING|PROCESSING|DELIVERED|COMPLETED|FAILED` tách khỏi task/workflow status), `agent_workflow_events` (timeline/audit). Xóa team không xóa Agent gốc; xóa workflow xóa kèm task/message/event của chính nó.
- **Orchestrator tuần tự (MVP)** trong `app/services/workflows.py`: Coordinator giao `TASK_ASSIGNMENT` cho từng member theo thứ tự vai trò Planner → Architect → Researcher → Developer → Tester → Reviewer; mỗi lượt tái sử dụng nguyên vẹn `AgentService.prepare_run/stream_prepared` của Phase 5 nên provider adapter, tool allowlist và ngân sách 6 bước/120s/8.000 token ước lượng cho từng lượt được giữ nguyên. Reviewer/Tester trả nội dung chứa `REVISION_REQUEST` thì Agent của task hoàn thành gần nhất được gọi lại (tối đa `workflow_max_revisions_per_task`, mặc định 2). Cuối cùng Coordinator được gọi để tổng hợp `final_result`. Giới hạn cấp workflow tập trung trong `Settings` (`workflow_max_agent_turns=12`, `workflow_timeout_seconds=600`, lease 900s), không hardcode rải rác.
- **Context Builder có chọn lọc**: prompt mỗi lượt chỉ gồm mục tiêu workflow (user request), task hiện tại và kết quả của các Agent tiền nhiệm bị cắt theo `workflow_context_chars_per_result`; phần kết quả của Agent khác được đóng khung rõ là *dữ liệu tham khảo không đáng tin, không phải chỉ dẫn hệ thống* để chống prompt injection giữa các Agent; system prompt của Agent nhận không bao giờ bị message ghi đè.
- **Độ tin cậy**: chuyển trạng thái bằng atomic conditional update; message được *claim* (`PENDING → PROCESSING`) nên không xử lý trùng; workflow được claim kèm lease — start/resume thứ hai bị từ chối `workflow_already_running`, lease hết hạn (backend restart) được thu hồi qua `waiting`. Pause dùng trạng thái `waiting` (đặc tả không có `paused`), orchestrator dừng ở biên giữa hai lượt Agent; resume tiếp tục từ các task đã `completed` (không chạy lại). Workflow chạy bằng asyncio task tách khỏi request/SSE: SSE `GET /ai/agent-workflows/{id}/stream` chỉ quan sát event đã lưu; ngắt SSE không hủy workflow, hủy chỉ qua `POST /cancel`. Lỗi provider được lưu `error_code` công khai cố định, không lộ API key trong message/log/SSE.
- **API** (prefix `/api/v1`, CurrentUser, ownership, `Cache-Control: no-store` như các router AI khác): CRUD `/ai/agent-teams`, CRUD `/ai/agent-workflows` + `start|pause|resume|cancel` + `messages|tasks|events` + `stream`. Thêm Agent của user khác vào team bị từ chối `invalid_team_members`; Coordinator không thuộc members bị từ chối `coordinator_not_in_team`.
- **Frontend**: app-shell/sidebar chuyển theme theo ảnh mẫu của user (sidebar navy `#0f172a`, accent tím `#7c3aed`, nền `#f3f5fb`, card trắng bo tròn lớn, logo não tím, ô tìm nhanh trang ở topbar và trạng thái hệ thống lấy từ `/health` thật). Trang `/agents/teams` (CRUD nhóm), `/agents/workflows` (danh sách + tạo), `/agents/workflows/{id}` (workspace 3 cột: Task Board + Project Progress, Communication Center bong bóng pastel theo vai trò, Workflow Status với vòng %, stepper Plan→Develop→Test→Review→Complete, Current Task, Recent Activity) — mọi số liệu/trạng thái đều suy từ dữ liệu API thật, không hardcode; không có ô nhập tin nhắn vì backend không có endpoint gửi tin nhắn vào workflow đang chạy. Các trang cũ chỉ đổi theme qua shell/biến CSS, không viết lại logic.
- **Kiểm chứng**: backend 371 tests (360 cũ + 11 test workflow mới: team/ownership, workflow 3+ Agent hoàn thành, Agent sau nhận kết quả Agent trước, revision, pause/resume/cancel, claim message exactly-once, provider lỗi không lộ key, giới hạn bước) + Ruff đạt; frontend 170/171 tests (1 fail có sẵn trên main ở `agents-ui.test.jsx`, không liên quan Phase 6) + ESLint đạt + Next build đạt. Chưa live test với provider thật (không có API key trong môi trường này); test dùng mock transport ở tầng HTTP trong test như các phase trước.

### Bổ sung Phase 6: Xuất ZIP website cho workflow

- **Thiết kế**: `agent_workflows` thêm `output_type` (`text` mặc định — hành vi cũ không đổi | `website_zip`) và các trường artifact `artifact_status` (`none|ready|failed`), `artifact_file_count`, `artifact_total_bytes`, `artifact_error_code`. Với `website_zip`, orchestrator chạy thêm **một lượt Agent có giới hạn** sau khi mọi task xong và trước bước tổng hợp: gọi Agent có vai trò Developer của team (không có thì Coordinator) qua đúng `AgentService` Phase 5, yêu cầu xuất sản phẩm bằng *file blocks* dạng ```` ```file:duong/dan ``` ```` theo một trong hai chế độ do parser nhận diện từ chính file trích được: **static** (website tĩnh, điểm vào `index.html`) hoặc **project** (có `package.json` — source project React/Vite/Tailwind, điểm vào là `package.json` + ít nhất một file trong `src/` hoặc `index.html`). Prompt bước artifact yêu cầu Agent đọc mục tiêu: mục tiêu nhắc framework/project thì xuất toàn bộ source project hoàn chỉnh (kèm README), không rút gọn/placeholder.
- **Bảo mật/validation** (`app/services/workflow_files.py`, module thuần dễ unit test): nội dung Agent là dữ liệu không đáng tin — chuẩn hoá path và chặn tuyệt đối traversal/path tuyệt đối/segment ẩn; allowlist đuôi text `html, css, js, mjs, cjs, jsx, ts, mts, cts, tsx, json, md, txt, svg, xml` (không binary, không đuôi thực thi); giới hạn tập trung trong `Settings` (`artifact_max_files=50`, `artifact_max_file_bytes=262144`, `artifact_max_total_bytes=2097152`); file vi phạm bị loại và ghi vào payload của event `artifact_created` (kèm `mode`); trích được 0 file → `artifact_status=failed` + `artifact_no_files`, thiếu điểm vào (cả `index.html` lẫn `package.json` hợp lệ) → `artifact_missing_entry`, lỗi provider → mã lỗi của provider — workflow chữ vẫn hoàn thành, không bao giờ giả vờ có ZIP. Không thực thi nội dung Agent ở bất kỳ đâu: **server không chạy npm/build thử**; `HUONG-DAN.md` do hệ thống sinh phân biệt hai chế độ — static: mở `index.html`; project: `npm install` → `npm run dev` → `npm run build` do người dùng tự chạy, kèm ghi chú trung thực này.
- **Lưu trữ/API**: collection mới `agent_workflow_files` (`user_id`, `workflow_id`, `path`, `content`, `size_bytes`; index `(workflow_id, path)` và `user_id`; xóa workflow xóa kèm files). Event `artifact_created`/`artifact_failed`. `GET /ai/agent-workflows/{id}/files` trả danh sách file + tổng dung lượng + trạng thái; `GET /ai/agent-workflows/{id}/download.zip` dựng ZIP trong bộ nhớ bằng `zipfile` stdlib từ files đã lưu (kèm `HUONG-DAN.md` do hệ thống sinh nếu Agent không có README, không ghi đè file Agent), `Content-Disposition` filename là slug từ tiêu đề workflow; chưa có artifact → `409 artifact_not_ready`; user khác → `404` theo ownership như mọi route workflow.
- **Frontend**: form tạo workflow thêm select **Sản phẩm đầu ra** (`utils/workflows.js: OUTPUT_TYPES`); thẻ workflow có badge `Website · ZIP` (+ trạng thái sẵn sàng); workspace thêm mục **Sản phẩm — Website (ZIP)** (chỉ hiện với workflow `website_zip`): trạng thái chờ khi đang chạy, danh sách file + dung lượng + nút **Tải ZIP** khi `ready` (tải bằng `fetch` credentials → blob → anchor, refresh 401 như SSE client), mã lỗi dịch tiếng Việt khi `failed` (`artifactErrorLabel`). Mục sản phẩm ghi rõ **loại artifact** suy từ danh sách file thật (`artifactKind`: có `package.json` → Source project, ngược lại Website tĩnh).
- **Validation khi tạo workflow/nhóm (bổ sung)**: handler `RequestValidationError` trong `main.py` có nhánh riêng cho các route chứa `/ai/agent-teams` hoặc `/ai/agent-workflows` (payload không chứa secret): trả `422` với `detail.code = validation_error` + `detail.fields` chỉ gồm `loc/msg/type` đã làm sạch — không kèm `input/ctx` hay giá trị đã gửi. Mọi route `/ai` còn lại (providers/chat/compare/agents — nơi có API key) giữ nguyên cách che thành `invalid_provider_configuration`. Form tạo workflow: ô Tiêu đề `maxLength=200` + bộ đếm + hướng dẫn để yêu cầu chi tiết ở ô Mục tiêu, validate phía client (`validateWorkflowForm`) trước khi gọi API, và `getWorkflowError` dịch `validation_error`/mã che cũ thành thông báo tiếng Việt nêu đúng trường lỗi. Giới hạn backend giữ nguyên 200 ký tự — sửa ở UX và thông báo lỗi, không nới schema.
- **Kiểm chứng**: backend 386 tests (371 cũ + 11 unit test parser/ZIP + 4 test API artifact: tạo artifact + tải ZIP mở được bằng `zipfile` và có `HUONG-DAN.md`, workflow text không có artifact/409, 0 file hợp lệ → `failed` + `artifact_no_files`, owner isolation ở cả 2 endpoint mới) + Ruff đạt; frontend 182/183 tests (thêm 5 test ZIP: service files, download blob + filename từ header, 409, formatBytes/nhãn lỗi; 1 fail duy nhất vẫn là `agents-ui.test.jsx` có sẵn trên main) + ESLint đạt + Next build đạt. Chưa live test provider thật như các đợt trước.
- **Kiểm chứng đợt validation + project ZIP**: backend **393 tests** (386 cũ + 4 unit parser mới: jsx/tsx/config được nhận, project mode không cần index.html ở root, package.json trần bị từ chối, HUONG-DAN project có lệnh npm + ghi chú chưa build thử; + 3 test API: workflow project tải ZIP chứa `package.json`/`src/App.jsx` với event `mode=project`, lỗi validation tạo workflow/nhóm trả `validation_error` + field đúng và không echo giá trị đã gửi) + Ruff đạt; frontend **188/189 tests** (thêm test validate form, dịch lỗi validation, `artifactKind`; 1 fail duy nhất vẫn là `agents-ui.test.jsx` có sẵn trên main) + ESLint đạt + Next build đạt. Chưa live test provider thật.

### Bổ sung Phase 6: Vai trò hiệu dụng + Orchestrator chịu lỗi

- **Vai trò hiệu dụng (`effective_role`)**: trước đây orchestrator sắp xếp member theo đúng `role` đã lưu; một nhóm tạo tay mà mọi member đều lưu `role="member"` sẽ chạy theo thứ tự lưu trữ thô — Agent tên "AI Reviewer" có thể chạy đầu tiên (message giao việc ghi "Please complete the member part of: ..."). Nay: role lưu trữ cụ thể (planner/architect/researcher/developer/tester/reviewer/coordinator) luôn thắng; role `"member"`/không rõ được **suy từ tên Agent** (bỏ tiền tố "AI ", khớp substring theo bảng hint dùng chung backend/frontend: review→reviewer, test/qa→tester, plan→planner, architect→architect, research→researcher, develop/code/coder/engineer→developer, lead/coordinat/manager→coordinator; không suy được → member). Thứ tự chạy bắt buộc: nhóm sản xuất planner → architect → researcher → developer → member chạy trước, nhóm kiểm định tester/reviewer **chỉ chạy sau khi mọi Agent sản xuất đã xử lý xong** bất kể vị trí lưu trong team. Member có vai trò hiệu dụng coordinator (không phải coordinator của team) chạy như planner phụ; tổng hợp cuối vẫn chỉ do coordinator của team. `create_team`/`patch_team` cũng lưu luôn role đã suy khi member gửi lên là `"member"` (form tạo nhóm ở frontend tự chọn role theo tên, user vẫn đổi tay được) — nhóm cũ lưu sai role vẫn chạy đúng nhờ suy luận ở orchestrator, không cần tạo lại. Nội dung `TASK_ASSIGNMENT` chuyển sang tiếng Việt kèm nhãn vai trò ("Hãy hoàn thành phần việc của {nhãn} cho mục tiêu: ...").
- **Chịu lỗi theo lượt**: lỗi provider tạm thời (`generation_failed`, `provider_timeout`, `provider_rate_limited`, `provider_unavailable`, `agent_timeout`) được **retry 1 lần** (backoff 2s trong `WorkflowLimits`). Vẫn lỗi: task bị đánh dấu `failed`, gửi `TASK_FAILED` (tiếng Việt, kèm tên Agent + mã lỗi), lượt đã thử vẫn được cộng vào `usage.agent_turns`, và orchestrator **chạy tiếp Agent kế tiếp** thay vì sập toàn bộ workflow. Workflow chỉ `failed` khi **mọi** member task đều failed (error_code = mã lỗi đầu tiên) hoặc cấu hình hỏng ở mức không chạy được gì. Bước tổng hợp của Coordinator lỗi nhưng đã có kết quả của nhóm → dùng kết quả thật cuối cùng làm `final_result`, workflow vẫn `completed` kèm event `workflow_synthesis_fallback`. Bước artifact (website_zip) chỉ chạy khi có ít nhất 1 task completed, và Agent tạo artifact được thử độc lập kể cả khi task chính của nó đã failed.
- **Task Board**: workspace hiển thị đủ 5 cột Pending / In Progress / Review / Completed / **Failed** (trước đây cột Failed bị cắt khỏi render nên task failed "tàng hình"), Project Progress đếm đủ completed + in_progress + review + pending + failed.
- **Kiểm chứng đợt này**: backend **401 tests** (393 cũ + 8 mới: unit suy vai trò; team legacy toàn role "member" chạy đúng thứ tự planner→developer→reviewer với assignment tiếng Việt; reviewer lưu đầu danh sách vẫn chạy sau developer; 1 Agent lỗi `generation_failed` → workflow vẫn completed + task failed + `TASK_FAILED` + đếm lượt; lỗi tạm thời thành công ở retry; mọi Agent đều lỗi → workflow failed; synthesis lỗi → completed bằng fallback + event; create_team tự suy role) + Ruff đạt; frontend **190/191 tests** (thêm test `inferRoleFromName` + progress có failed/review; 1 fail duy nhất vẫn là `agents-ui.test.jsx` có sẵn trên main) + ESLint đạt + Next build đạt. Chưa live test provider thật.

### Bổ sung: Minh bạch lỗi provider + Agent tự chạy lại khi model không hỗ trợ tools

- **Gốc lỗi (đã chứng minh bằng test live trên máy người dùng)**: model `allam-2-7b` trên Groq **không hỗ trợ tool calling** — request không kèm tools chạy thành công, request kèm tools bị Groq trả HTTP 400, còn `openai/gpt-oss-20b` kèm tools chạy thành công. Trước đây lỗi này bị che 2 lớp: `ChatHTTP.stream` ép mọi status lạ thành `generation_failed` (vứt body lỗi), và adapter bỏ qua SSE event chứa `error` — nên mọi Agent có tools đều chết với mã vô nghĩa `generation_failed`.
- **Hiện lỗi thật**: hai mã công khai mới trong `ERRORS` — `model_tools_unsupported` (400) và `provider_request_rejected` (400). `ChatHTTP.stream` nay đọc body lỗi của các status 4xx còn lại (giới hạn 8KB, chỉ giữ lại mã đã phân loại — body không bao giờ vào exception/log/response, giữ kỷ luật không lộ API key) và `classify_provider_error` (base_provider) phân loại từ `error.code/type/message` đã giới hạn độ dài: nhắc tới tool/function calling → `model_tools_unsupported`, còn lại → `provider_request_rejected`. Cả OpenAI-compatible lẫn Gemini adapter đều raise theo cùng phân loại khi gặp SSE event chứa `error` thay vì nuốt im lặng. Vì hai mã nằm trong `ERRORS`, chúng đi nguyên vẹn qua `execution.error_code` → workflow `TASK_FAILED` (không bị ép về `generation_failed`).
- **Tự chữa trong AgentService**: khi một step lỗi `model_tools_unsupported` **và** lượt chạy có tools, execution tự chạy lại step đó **không kèm tools** (tối đa 1 lần chuyển chế độ cho cả execution, các step sau cũng không tools) và phát event SSE `tools_fallback {code}` — frontend hiện tại bỏ qua event lạ này một cách an toàn (có test chốt). Agent không có tools thì giữ nguyên lỗi. Chat thường không áp dụng fallback, chỉ hiện mã lỗi rõ ràng; frontend dịch cả hai mã sang tiếng Việt trong các bảng dịch sẵn có (agents/workflows/chat/compare).

### Bổ sung: Ngân sách riêng cho workflow + tính theo usage thật + nhịp rate limit

- **Gốc lỗi (test live trên máy người dùng, workflow `ca4bf8f4` sau khi đổi 7 Agent sang `openai/gpt-oss-20b`)**: AI Planner (chạy đầu, chưa có prior) thành công; AI Leader/Architect/Developer và bước artifact chết `agent_budget_exceeded`; AI Reviewer + synthesis chết `provider_rate_limited`; Tester completed nhưng lạc đề vì Developer không có kết quả. Hai gốc: (1) `AgentLimits.token_budget=8000` dùng chung cho chat thường và workflow, và `AgentService` cộng ngân sách theo `max(token thật, ước lượng byte UTF-8)` — ngữ cảnh workflow (mục tiêu dài + prior results + system prompt tiếng Việt) bị phồng ~3 lần nên vượt 8000 trước cả khi gọi model, đồng thời trần output mặc định 2048 token/lượt không thể sinh nổi một project ở bước artifact; (2) retry của workflow lùi 2 giây cho mọi lỗi tạm thời, vô ích với cửa sổ rate limit theo phút của Groq free tier.
- **Ngân sách riêng cho workflow**: `WorkflowService._agent_service(limits)` truyền `AgentLimits` override vào `AgentService` (constructor đã nhận `limits`): lượt member/synthesis dùng `WORKFLOW_AGENT_LIMITS` = 48.000 token / deadline 240s. Lượt chat/Agent Studio thường giữ nguyên 8.000 / 120s.
- **Tính ngân sách theo usage thật**: trong `stream_prepared`, mỗi step cộng **số usage provider đã báo** (`step_input`/`step_output`) khi có; chỉ phía nào provider không báo mới trừ theo ước lượng byte của phía đó. `_request_budget` giữ vai trò chốt chặn pre-flight (từ chối prompt vượt ngân sách trước khi gửi) và số trừ dự phòng — tính chất "vẫn chặn khi provider không trả usage" không đổi. Docstring của `_request_budget` đã cập nhật cho khớp.
- **Caps riêng cho artifact**: `_run_agent`/`_run_agent_resilient` nhận tham số per-run (`limits`, `max_output_tokens`) truyền xuống `prepare_run(max_output_tokens_override=...)` → `PreparedAgent.max_output_tokens_override` → trần output hiệu dụng trong `stream_prepared` là `override or agent.max_output_tokens or 2048` — không sửa record Agent đã lưu. Bước artifact dùng `ARTIFACT_AGENT_LIMITS` = 96.000 token / deadline 420s (vẫn trong timeout workflow 600s) và override output 16.384 token.
- **Nhịp rate limit**: trong `_run_agent_resilient`, `provider_rate_limited` tách khỏi nhóm tạm thời chung: thử lại tối đa `WorkflowLimits.rate_limit_retries=2` lần với backoff `rate_limit_backoff_seconds=30.0` (các mã tạm thời khác giữ 1 lần / 2 giây). Tổng thời gian chờ vẫn bị chặn bởi `asyncio.timeout` của workflow (`workflow_timeout` khi hết giờ). Hai field nằm trong `WorkflowLimits` nên test fake được `asyncio.sleep` để chốt đúng 30 giây mà không chờ thật.
- **Synthesis fallback chọn prior dài nhất**: helper `longest_prior_result` thay `prior[-1]` ở cả nhánh hết `max_steps` lẫn nhánh synthesis lỗi — kết quả cuối dự phòng là deliverable dài nhất của nhóm thay vì ghi chú review ngắn ở lượt cuối; event `workflow_synthesis_fallback` giữ nguyên.
- **Kiểm chứng đợt này**: backend **416 tests** (411 cũ + 5 mới: unit tính ngân sách ưu tiên usage thật với system prompt tiếng Việt nặng byte; workflow ngữ cảnh tiếng Việt nặng với usage thật → mọi task completed; artifact request mang `max_tokens=16384` trong khi lượt thường giữ 2048; rate limit fail 2 lần → completed ở lần 3 với đúng 2 lần sleep 30s (fake sleep) và 4 HTTP calls; synthesis lỗi → `final_result` là prior dài nhất, không phải prior cuối) + Ruff đạt. Đợt này không sửa frontend (chỉ backend + docs) nên không chạy lại frontend tests/ESLint/build. Chưa live test lại trên máy người dùng — sẽ chạy lại workflow sneaker qua Tailscale sau khi merge để xác nhận ra ZIP.
