# MindFlow AI

Mở rộng AI Knowledge Hub theo `update_features.md`, giữ nền tảng trong `plan_create_web.md` và triển khai từng giai đoạn. **Bản hiện tại: Foundation + Phase 2 — quản lý provider/model OpenAI, Gemini và Groq.**

## Đã triển khai

- Frontend Next.js App Router **JavaScript/JSX**, Tailwind CSS, Axios, Zustand và Lucide.
- Backend FastAPI **async**, Pydantic, **motor (MongoDB async)**. Dữ liệu lưu trong MongoDB (Atlas hoặc local); index được tạo tự động khi khởi động, không dùng Alembic/SQL migration.
- Đăng ký, đăng nhập, đăng xuất, profile; JWT access, refresh token xoay vòng, cookie HttpOnly; thu hồi session khi logout.
- Dashboard lấy số tài liệu, kho kiến thức, hội thoại, yêu cầu AI và hoạt động từ DB của người dùng hiện tại. Tài khoản mới có số đếm bằng 0, không seed dữ liệu demo.
- Giao diện desktop/mobile; trạng thái loading, lỗi, toast và route cần đăng nhập.
- Docker Compose tách frontend, backend và MongoDB; script tạo bí mật local ngẫu nhiên.
- Trang `/settings`: lưu/thay/xóa API key theo từng người dùng, bật/tắt provider, kiểm tra kết nối, đồng bộ model thật và chọn model mặc định.
- Adapter OpenAI/Gemini/Groq gọi API danh sách model; API key mã hóa Fernet trong DB, không trả lại browser. Capabilities chưa xác minh được hiển thị là “Chưa xác định”. Groq dùng chuẩn OpenAI (`https://api.groq.com/openai/v1/models`).
- Hai collections mới `user_provider_credentials`, `ai_models` (unique index theo user/provider và credential/model); giữ nguyên bảy collections cũ, cookie và cơ chế xác thực.

**Chưa triển khai:** tạo nội dung AI, chat/streaming, Compare/synthesis, agent/tool calling, files/RAG/memory/research/workflows và ghi chú. Claude, DeepSeek, Ollama chỉ có trong registry, chưa nhận key hoặc gọi API. Các trang tương ứng ghi rõ lộ trình, không giả lập kết quả. Không cần API key AI để đăng nhập và dùng dashboard.

Phân tích hiện trạng, danh sách file tạo/sửa/giữ nguyên, schema và API contracts: [ARCHITECTURE.md](ARCHITECTURE.md).

## 1. Chạy bằng Docker Desktop — khuyến nghị

Yêu cầu: Docker Desktop chạy Linux containers + Docker Compose; Python để tạo `backend/.env` (hoặc tự copy `.env.example` vào `backend/.env` và thay mọi `CHANGE_ME` bằng giá trị ngẫu nhiên). Trên Windows, cài [Docker Desktop](https://docs.docker.com/desktop/setup/install/windows-install/) và khởi động trước.

Mở terminal tại thư mục chứa README:

```sh
python scripts/init_env.py
docker compose up --build -d
docker compose ps
```

Script **không ghi đè** `backend/.env` đã tồn tại. Không gửi nội dung `.env` lên Git, chat hoặc ảnh chụp. Sau khi các container healthy:

- Web: http://localhost:3000
- Swagger API: http://localhost:8000/docs
- OpenAPI JSON: http://localhost:8000/openapi.json
- DB readiness: http://localhost:8000/api/v1/health

Tạo tài khoản tại `/register`, sau đó vào dashboard. Không có tài khoản hoặc mật khẩu mặc định.

Compose chạy MongoDB (`mongo:7`) không xác thực, chỉ bind localhost, dùng cho phát triển cục bộ. Backend kết nối `mongodb://db:27017`; index được tạo khi backend khởi động. Volume `mongo_data` giữ DB qua lần restart. Cổng MongoDB/backend/frontend trong Compose chỉ bind localhost.

Xem log hoặc dừng (giữ dữ liệu):

```sh
docker compose logs --tail=100 backend frontend
docker compose down
```

Không dùng `docker compose down -v` trừ khi bạn chủ động muốn xóa toàn bộ dữ liệu database.

## 2. Chạy frontend/backend trực tiếp để phát triển

Yêu cầu: Node.js 22 LTS, Python 3.12+, và một MongoDB server (local hoặc MongoDB Atlas). Có thể chỉ chạy database bằng `docker compose up -d db`; nếu không có Docker, cài MongoDB local hoặc dùng Atlas (chuỗi `mongodb+srv://...`).

### Bước A — cấu hình

```sh
python scripts/init_env.py
```

Lệnh tạo `backend/.env` từ `.env.example` với `JWT_SECRET` và `CREDENTIAL_ENCRYPTION_KEY` ngẫu nhiên. `MONGODB_URI` mặc định trỏ `mongodb://localhost:27017`, `MONGODB_DATABASE=mindflow_ai`. Nếu dùng Atlas hoặc DB ngoài máy, sửa `MONGODB_URI` trong `backend/.env` theo kết nối của bạn (giữ nguyên `CREDENTIAL_ENCRYPTION_KEY` đã sinh). Mật khẩu/ký tự đặc biệt trong URI phải URL-encode.

**Quan trọng:** `CREDENTIAL_ENCRYPTION_KEY` là khóa Fernet độc lập, dùng để mã hóa API key provider trong DB. Phải backup khóa này cùng database; mất khóa = không giải mã được key đã lưu. Không xoay khóa bằng cách chạy lại script (script giữ khóa cũ).

### Bước B — backend (PowerShell trên Windows)

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload --no-proxy-headers
```

Linux/macOS: thay `.\.venv\Scripts\python.exe` bằng `.venv/bin/python`. Backend tự đọc `backend/.env` và tạo index MongoDB khi khởi động; không có bước migration riêng.

### Bước C — frontend (terminal khác)

```sh
cd frontend
npm ci
npm run dev
```

Truy cập http://localhost:3000. Browser chỉ gọi cùng origin `/api/v1`; Next rewrite đến `http://127.0.0.1:8000`. Để đổi backend, đặt biến server-side `BACKEND_URL` trước khi chạy/build Next.js. Không dùng biến `NEXT_PUBLIC_` cho bí mật.

### Bước D — cấu hình provider (tùy chọn, cần API key thật)

Vào `/settings` sau khi đăng nhập: chọn OpenAI, Gemini hoặc Groq, dán API key (chỉ gửi lên backend, mã hóa trước khi lưu), bấm kiểm tra kết nối để đồng bộ danh sách model thật, rồi chọn model mặc định. Có thể bật/tắt hoặc xóa key bất kỳ lúc nào. Không có key vẫn đăng nhập và dùng dashboard bình thường.

## 3. Kiểm thử

Backend từ `backend/`:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
```

Frontend từ `frontend/`:

```sh
npm test
npm run lint
npm run build
```

Unit/API tests backend dùng **mongomock-motor** (MongoDB in-memory) để chạy hoàn toàn offline, không cần server DB hay mạng. Đây **không phải** bằng chứng MongoDB/Atlas thật hoặc Docker runtime đã chạy. Kiểm thử frontend dùng HTTP mock ở lớp transport để kiểm tra refresh/retry và UI provider; ứng dụng thực không dùng các mock này.

Smoke test thủ công sau khi ứng dụng khởi động:

1. `/register`: tạo tài khoản A, kiểm tra tự đăng nhập và dashboard có hoạt động đăng ký.
2. Tải lại trang để kiểm tra phiên cookie; mở DevTools không được thấy JWT trong localStorage hoặc `document.cookie`.
3. Đăng xuất rồi mở `/dashboard`: phải quay về login.
4. Sai mật khẩu phải hiện lỗi, không refresh vô hạn. Đăng ký email trùng phải hiện lỗi.
5. Tạo tài khoản B: hoạt động của A không xuất hiện. Các số đếm tài khoản mới bằng 0.
6. `/settings`: lưu key → trạng thái “đã cấu hình/chưa kiểm tra”; kiểm tra kết nối với key sai phải báo lỗi an toàn, không lộ key; xóa key phải có hộp thoại xác nhận.
7. Các mục chưa triển khai phải ghi rõ phase, không báo upload/chat thành công.
8. Kiểm tra layout ở chiều rộng 360px, 390px, 768px và desktop; menu mobile mở/đóng bằng bàn phím và cảm ứng.

### Kết quả kiểm chứng của lần triển khai

- Backend: **173 tests passed**, Ruff đạt, `pip check` không có dependency hỏng. Một cảnh báo deprecation upstream về Starlette/httpx, không làm test thất bại.
- Frontend: **31 tests passed** (refresh/retry, lỗi an toàn, helper, lộ trình và UI provider); ESLint không lỗi/cảnh báo; production build Next.js thành công.
- Script: `scripts/test_init_env.py` **3 tests passed** (giữ bí mật cũ, không xoay khóa, thay placeholder).
- Smoke test HTTP qua **harness MongoDB in-memory (mongomock) → FastAPI** đạt: health, register, profile, dashboard, refresh rotation, logout, login. Không mock API trong smoke test này; đây là stack thật nhưng DB là in-memory, không phải MongoDB server.
- Smoke test HTTP trên **MongoDB Atlas thật** (backend dev của người dùng) đạt: register 201, lưu key 200 (mã hóa, untested), kiểm tra kết nối trả **400 `provider_authentication_failed`** với key thử không hợp lệ (lỗi có cấu trúc, an toàn, không phải 500 — chứng minh đường adapter async hoạt động), models 200 (rỗng), delete 204, logout 204. **Đây không phải live success**: không có API key provider hợp lệ nên chưa đồng bộ được model thật.
- **Groq live success:** adapter Groq gọi `GET https://api.groq.com/openai/v1/models` bằng key người dùng cung cấp, trả **11 model thật** (vd `openai/gpt-oss-120b`, `qwen/qwen3.8-27b`, `whisper-large-v3`), capabilities `unknown`. Chỉ đọc danh sách model, không generation; key không hardcode trong source và không lưu lại sau kiểm chứng.
- Tài khoản kiểm thử đã tạo trong DB dev (không tự xóa): `smoke-http-fix@example.com`, `smoke-proxy-c29c3a71@example.com`, `prov-smoke-5917a5c1@example.com`. Tài khoản do harness tạo chỉ tồn tại in-memory và mất khi dừng.
- **Chưa kiểm chứng:** build/chạy Docker image (máy không có Docker); đồng bộ model thật bằng API key hợp lệ cho OpenAI/Gemini (Groq đã live); xác nhận trực quan trên thiết bị thật. Không đánh đồng mongomock tests với MongoDB integration tests.

Chạy lại HTTP smoke test sau khi khởi động ứng dụng:

```sh
python scripts/smoke_http.py --base-url http://localhost:3000
```

Lệnh này tạo **một tài khoản kiểm thử thật** trong DB đang kết nối, không tự xóa tài khoản. Không dùng trên DB production nếu không muốn thêm dữ liệu kiểm thử.

Nếu chưa có MongoDB server, có thể kiểm tra riêng luồng HTTP bằng harness in-memory được đánh dấu rõ ràng (không dùng cho phát triển dữ liệu thật/deploy; cần dev deps `mongomock-motor`):

```powershell
# Terminal 1, từ thư mục gốc; cần backend/.venv đã cài requirements-dev.txt
.\backend\.venv\Scripts\python.exe scripts/serve_test_backend.py --allow-test-database
# Terminal 2
cd frontend
npm run dev
# Terminal 3, từ thư mục gốc
python scripts/smoke_http.py
```

Harness chỉ bind 127.0.0.1, dùng MongoDB in-memory, giới hạn rate được nâng cho kiểm thử; dừng bằng Ctrl+C. Không có seed user/tài liệu; dữ liệu mất khi dừng. Cấu hình ứng dụng chính vẫn kết nối MongoDB thật qua `MONGODB_URI`.

## 4. Hợp đồng xác thực

API prefix `/api/v1`. Payload đăng ký `{name,email,password}`, đăng nhập `{email,password}`. Thành công trả `{user:{id,name,email,created_at}}` và đặt cookies. `/auth/me` trả trực tiếp object user. `/auth/logout` trả 204.

- `kh_access`: JWT 15 phút, HttpOnly, path `/api/v1`, ràng buộc một session còn hiệu lực.
- `kh_refresh`: chuỗi ngẫu nhiên, HttpOnly, path `/api/v1/auth`; DB chỉ lưu hash, xoay token khi refresh.
- `POST /auth/refresh` dùng cookie, không nhận JWT từ JavaScript. Axios chỉ retry một lần và gộp refresh đồng thời.
- Request POST/PATCH/DELETE có cookie cần header `Origin` hợp lệ. Khi dùng curl/Postman với cookie jar, thêm `Origin: http://localhost:3000`. CORS không thay thế CSRF.
- Với HTTPS, đặt `COOKIE_SECURE=true`. Local HTTP dùng false. Hai host `localhost` và `127.0.0.1` có cookie riêng, nên dùng nhất quán một host.

Các tính năng chưa có endpoint sẽ trả 404, không trả dữ liệu demo. Full API schemas/validation được FastAPI xuất ở `/docs`.

### Hợp đồng provider (Phase 2)

Tất cả endpoint cần đăng nhập, trả `Cache-Control: no-store` và không có trường bí mật.

| Endpoint | Hợp đồng |
|---|---|
| GET `/ai/providers` | `{encryption_ready, providers:[{id,name,implemented,configured,enabled,connection_status,default_model,model_count,...}]}` |
| PATCH `/ai/providers/{provider}` | Body chỉ gồm `api_key?`, `enabled?`, `default_model?`; key mới reset model cache |
| POST `/ai/providers/{provider}/test` | Dùng key đã lưu; sync model list thật; trả `{provider,model_count,scope:"model_listing"}` |
| GET `/ai/providers/{provider}/models` | `{provider,models:[...],synced_at}`; chỉ đọc cache thuộc user |
| DELETE `/ai/providers/{provider}` | 204; xóa credential và model cache của user |

Lỗi provider dùng `{detail:{code,message}}` đã làm sạch. Provider trả 401 không chuyển thành auth 401 của ứng dụng. “Connected” chỉ xác nhận model listing, không bảo đảm mọi model có quyền generation/quota.

## 5. Triển khai trên server

Đây là nền tảng Foundation + Phase 2, **chưa phải toàn bộ sản phẩm AI hoàn thiện**. Trước khi mở public:

1. Dùng VM/server có Docker; đặt `backend/.env` riêng bằng secret mới, tuyệt đối không đưa secrets vào image/repository.
2. Đặt `COOKIE_SECURE=true`, `CORS_ORIGINS=["https://ten-mien-cua-ban"]`; cấu hình HTTPS reverse proxy đến frontend localhost:3000. Không mở MongoDB hoặc backend trực tiếp ra Internet.
3. Dùng MongoDB có xác thực (Atlas hoặc self-host bật auth) cho production; Compose mặc định không auth chỉ dành cho dev cục bộ. Backup database **và** `CREDENTIAL_ENCRYPTION_KEY` định kỳ; kiểm tra restore.
4. Giữ API dưới cùng origin `/api/v1`. Nếu thay đích backend trong Next rewrite phải build lại frontend.
5. Chạy một backend worker với rate limiter hiện tại. Muốn nhiều worker/replica phải chuyển rate limit sang Redis/gateway và cấu hình trusted proxy chính xác; không tin X-Forwarded-For tùy ý.
6. Chạy build/test và smoke test trên MongoDB thật. Cấu hình log, giám sát lỗi và dung lượng; không log cookie/password/API key.
7. Bổ sung email verification, password reset và quản trị session trước khi sử dụng public quy mô lớn; chưa thuộc phase này.

API key provider do từng người dùng nhập ở `/settings`, mã hóa ở backend; không điền key vào frontend hoặc biến `NEXT_PUBLIC_`.

## 6. Lộ trình tiếp theo

Ưu tiên theo `update_features.md`: Chat → Compare → Agent trước, các module knowledge/RAG/memory triển khai sau.

| Phase | Nội dung | Trạng thái |
|---|---|---|
| 1 | Hạ tầng, auth, dashboard (MongoDB) | Đã triển khai |
| 2 | Provider OpenAI/Gemini/Groq, key mã hóa, model sync/default, bật/tắt, test connection | Đã triển khai; Groq đã live test (11 model), OpenAI/Gemini chưa live test |
| 3 | Multi-model Chat: messages, generation/stream, capability checks, history | Chưa triển khai |
| 4 | Compare AI: chạy song song, synthesis, usage/cost ước tính vs thực tế | Chưa triển khai |
| 5 | Agent Studio/Execution: tools allowlist, quyền, budget, logs | Chưa triển khai |
| 6 | File Intelligence/RAG/Memory, Research/Workflow | Chưa triển khai |
| 7 | Production: live provider tests, MongoDB/Docker integration, hardening | Chưa triển khai |

Bản đặc tả gốc được giữ nguyên. Không tự động commit, push hoặc deploy.