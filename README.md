# MindFlow AI

Mở rộng AI Knowledge Hub theo `update_features.md`, giữ nền tảng trong `plan_create_web.md` và triển khai từng giai đoạn. **Bản hiện tại: Foundation + Phase 2 — quản lý provider/model OpenAI và Gemini.**

## Đã triển khai

- Frontend Next.js App Router **JavaScript/JSX**, Tailwind CSS, Axios, Zustand và Lucide.
- Backend FastAPI, SQLAlchemy, Pydantic, Alembic; schema nền trên PostgreSQL + pgvector.
- Đăng ký, đăng nhập, đăng xuất, profile; JWT access, refresh token xoay vòng, cookie HttpOnly; thu hồi session khi logout.
- Dashboard lấy số tài liệu, kho kiến thức, hội thoại, yêu cầu AI và hoạt động từ DB của người dùng hiện tại. Tài khoản mới có số đếm bằng 0, không seed dữ liệu demo.
- Giao diện desktop/mobile; trạng thái loading, lỗi, toast và route cần đăng nhập.
- Docker Compose tách frontend, backend và database; script tạo bí mật local ngẫu nhiên.
- Trang `/settings`: lưu/thay/xóa API key theo từng người dùng, bật/tắt provider, kiểm tra kết nối, đồng bộ model thật và chọn model mặc định.
- Adapter OpenAI/Gemini gọi API danh sách model; API key mã hóa Fernet trong DB, không trả lại browser. Capabilities chưa xác minh được hiển thị là “Chưa xác định”.
- Migration `0002_provider_management` chỉ thêm hai bảng `user_provider_credentials`, `ai_models`; giữ nguyên bảy bảng cũ, cookie và cơ chế xác thực.

**Chưa triển khai:** tạo nội dung AI, chat/streaming, Compare/synthesis, agent/tool calling, files/RAG/memory/research/workflows và ghi chú. Claude, DeepSeek, Ollama chỉ có trong registry, chưa nhận key hoặc gọi API. Các trang tương ứng ghi rõ lộ trình, không giả lập kết quả. Không cần API key AI để đăng nhập và dùng dashboard.

Phân tích hiện trạng, danh sách file tạo/sửa/giữ nguyên, schema và API contracts: [ARCHITECTURE.md](ARCHITECTURE.md).

## 1. Chạy bằng Docker Desktop — khuyến nghị

Yêu cầu: Docker Desktop chạy Linux containers + Docker Compose; Python để tạo `.env` (hoặc tự copy `.env.example` và thay mọi `CHANGE_ME` bằng giá trị ngẫu nhiên). Trên Windows, cài [Docker Desktop](https://docs.docker.com/desktop/setup/install/windows-install/) và khởi động trước.

Mở terminal tại thư mục chứa README:

```sh
python scripts/init_env.py
docker compose up --build -d
docker compose ps
```

Script **không ghi đè** `.env` đã tồn tại. Không gửi nội dung `.env` lên Git, chat hoặc ảnh chụp. Sau khi các container healthy:

- Web: http://localhost:3000
- Swagger API: http://localhost:8000/docs
- OpenAPI JSON: http://localhost:8000/openapi.json
- DB readiness: http://localhost:8000/api/v1/health

Tạo tài khoản tại `/register`, sau đó vào dashboard. Không có tài khoản hoặc mật khẩu mặc định.

Backend tự chạy `alembic upgrade head` trước khi phục vụ request. Migration đầu bật extension `vector` trong PostgreSQL. Volume `postgres_data` giữ DB qua lần restart. Cổng PostgreSQL/backend/frontend trong Compose chỉ bind localhost.

Xem log hoặc dừng (giữ dữ liệu):

```sh
docker compose logs --tail=100 backend frontend
docker compose down
```

Không dùng `docker compose down -v` trừ khi bạn chủ động muốn xóa toàn bộ dữ liệu database.

## 2. Chạy frontend/backend trực tiếp để phát triển

Yêu cầu: Node.js 22 LTS, Python 3.12+, PostgreSQL 16 có pgvector. Có thể chỉ chạy database bằng `docker compose up -d db`; nếu không có Docker, tự cài PostgreSQL **kèm pgvector**, tạo user/database khớp `.env`.

### Bước A — cấu hình

```sh
python scripts/init_env.py
```

`DATABASE_URL` mặc định trỏ `localhost:5432`. Nếu DB ngoài máy, sửa URL theo kết nối của bạn. Mật khẩu có ký tự đặc biệt phải URL-encode; mật khẩu do script sinh là hex nên không cần bước này.

### Bước B — backend (PowerShell trên Windows)

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload --no-proxy-headers
```

Linux/macOS: thay `.\.venv\Scripts\python.exe` bằng `.venv/bin/python`. Backend tự đọc `.env` ở thư mục gốc; không dùng SQLite như database production.

### Bước C — frontend (terminal khác)

```sh
cd frontend
npm ci
npm run dev
```

Truy cập http://localhost:3000. Browser chỉ gọi cùng origin `/api/v1`; Next rewrite đến `http://127.0.0.1:8000`. Để đổi backend, đặt biến server-side `BACKEND_URL` trước khi chạy/build Next.js. Không dùng biến `NEXT_PUBLIC_` cho bí mật.

## 3. Kiểm thử

Backend từ `backend/`:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Frontend từ `frontend/`:

```sh
npm test
npm run lint
npm run build
```

Unit/API tests backend dùng SQLite biệt lập để chạy không cần server DB. Đây **không phải** bằng chứng PostgreSQL/pgvector, migration online hoặc Docker runtime đã chạy. Kiểm thử frontend dùng HTTP mock ở lớp transport để kiểm tra refresh/retry; ứng dụng thực không dùng các mock này.

Smoke test thủ công sau khi Compose khởi động:

1. `/register`: tạo tài khoản A, kiểm tra tự đăng nhập và dashboard có hoạt động đăng ký.
2. Tải lại trang để kiểm tra phiên cookie; mở DevTools không được thấy JWT trong localStorage hoặc `document.cookie`.
3. Đăng xuất rồi mở `/dashboard`: phải quay về login.
4. Sai mật khẩu phải hiện lỗi, không refresh vô hạn. Đăng ký email trùng phải hiện lỗi.
5. Tạo tài khoản B: hoạt động của A không xuất hiện. Các số đếm tài khoản mới bằng 0.
6. Các mục chưa triển khai phải ghi rõ phase, không báo upload/chat thành công.
7. Kiểm tra layout ở chiều rộng 360px, 390px, 768px và desktop; menu mobile mở/đóng bằng bàn phím và cảm ứng.

### Kết quả kiểm chứng của lần triển khai

- Backend: **62 tests passed**, Ruff đạt, `pip check` không có dependency hỏng. Một cảnh báo deprecation upstream về Starlette/httpx, không làm test thất bại.
- Frontend: **15 tests passed** (refresh/retry, lỗi an toàn, helper và lộ trình); ESLint không lỗi/cảnh báo; production build Next.js thành công.
- Smoke test HTTP qua **Next.js rewrite → FastAPI → SQLite tạm** đạt: health, register, profile, dashboard, refresh rotation, logout, login. Không mock API trong smoke test này.
- Trình duyệt: đăng ký/đăng nhập/đăng xuất, sai mật khẩu, xác nhận mật khẩu không khớp, protected-route redirect; cookie không đọc được bằng JavaScript; menu mobile giữ focus và đóng bằng Escape.
- Đo DOM của login/register/dashboard bằng iframe kích thước cố định 360/390/768/1440px: không tràn ngang. Chưa xác nhận trực quan trên thiết bị thật.
- Compose YAML được parse; migration PostgreSQL upgrade/downgrade compile offline. **Chưa chạy Docker image, PostgreSQL/pgvector thật hoặc migration online**, do máy không có Docker/PostgreSQL. Không đánh đồng SQLite tests với PostgreSQL integration tests.
- `npm audit --omit=dev --registry=https://registry.npmjs.org`: 0 vulnerabilities tại thời điểm kiểm tra; không phải bảo đảm toàn bộ ứng dụng không có lỗ hổng.

Chạy lại HTTP smoke test sau khi khởi động ứng dụng:

```sh
python scripts/smoke_http.py --base-url http://localhost:3000
```

Lệnh này tạo **một tài khoản kiểm thử thật** trong DB đang kết nối, không tự xóa tài khoản. Không dùng trên DB production nếu không muốn thêm dữ liệu kiểm thử.

Nếu chưa có PostgreSQL, có thể kiểm tra riêng luồng HTTP bằng harness được đánh dấu rõ ràng (không dùng cho phát triển dữ liệu thật/deploy):

```powershell
# Terminal 1, từ thư mục gốc; cần .env và backend/.venv đã được tạo
.\backend\.venv\Scripts\python.exe scripts/serve_test_backend.py --allow-test-database
# Terminal 2
cd frontend
npm run dev
# Terminal 3, từ thư mục gốc
python scripts/smoke_http.py
```

Harness chỉ bind 127.0.0.1, dùng database SQLite tạm, giới hạn rate được nâng cho kiểm thử; dừng bằng Ctrl+C. Không có seed user/tài liệu; dữ liệu có thể mất khi dừng. Cấu hình ứng dụng chính vẫn **chỉ chấp nhận PostgreSQL**.

## 4. Hợp đồng xác thực

API prefix `/api/v1`. Payload đăng ký `{name,email,password}`, đăng nhập `{email,password}`. Thành công trả `{user:{id,name,email,created_at}}` và đặt cookies. `/auth/me` trả trực tiếp object user. `/auth/logout` trả 204.

- `kh_access`: JWT 15 phút, HttpOnly, path `/api/v1`, ràng buộc một session còn hiệu lực.
- `kh_refresh`: chuỗi ngẫu nhiên, HttpOnly, path `/api/v1/auth`; DB chỉ lưu hash, xoay token khi refresh.
- `POST /auth/refresh` dùng cookie, không nhận JWT từ JavaScript. Axios chỉ retry một lần và gộp refresh đồng thời.
- Request POST/PATCH/DELETE có cookie cần header `Origin` hợp lệ. Khi dùng curl/Postman với cookie jar, thêm `Origin: http://localhost:3000`. CORS không thay thế CSRF.
- Với HTTPS, đặt `COOKIE_SECURE=true`. Local HTTP dùng false. Hai host `localhost` và `127.0.0.1` có cookie riêng, nên dùng nhất quán một host.

Các tính năng chưa có endpoint sẽ trả 404, không trả dữ liệu demo. Full API schemas/validation được FastAPI xuất ở `/docs`.

## 5. Triển khai trên server

Đây là nền tảng Phase 1, **chưa phải toàn bộ sản phẩm AI hoàn thiện**. Trước khi mở public:

1. Dùng VM/server có Docker; đặt `.env` riêng bằng secret mới, tuyệt đối không đưa secrets vào image/repository.
2. Đặt `COOKIE_SECURE=true`, `CORS_ORIGINS=["https://ten-mien-cua-ban"]`; cấu hình HTTPS reverse proxy đến frontend localhost:3000. Không mở PostgreSQL hoặc backend trực tiếp ra Internet.
3. Giữ API dưới cùng origin `/api/v1`. Nếu thay đích backend trong Next rewrite phải build lại frontend.
4. Chạy một backend worker với rate limiter hiện tại. Muốn nhiều worker/replica phải chuyển rate limit sang Redis/gateway và cấu hình trusted proxy chính xác; không tin X-Forwarded-For tùy ý.
5. Backup database trước migration; kiểm tra restore định kỳ. Dùng account migration có quyền tạo extension, account runtime tối thiểu khi harden production.
6. Chạy build/test và smoke test trên PostgreSQL thật. Cấu hình log, giám sát lỗi và dung lượng; không log cookie/password/API key.
7. Bổ sung email verification, password reset và quản trị session trước khi sử dụng public quy mô lớn; chưa thuộc Phase 1 này.

Các API key AI sẽ được cấu hình ở backend ở các phase sau; không tự điền key vào frontend.

## 6. Lộ trình tiếp theo

| Phase | Nội dung | Trạng thái |
|---|---|---|
| 1 | Hạ tầng, auth, dashboard | Đã triển khai; còn xác minh runtime PostgreSQL/Docker |
| 2 | Knowledge base, upload, text extraction, chunks | Chưa triển khai |
| 3 | Embeddings, pgvector search, RAG, citations | Chưa triển khai |
| 4 | OpenAI/Gemini adapters, chat, streaming, structured output | Chưa triển khai |
| 5 | Agent, 5 tools, tool calling, logs, notes | Chưa triển khai |
| 6 | Settings, hoàn thiện UX, integration tests, hardening | Chưa triển khai |

Bản đặc tả gốc được giữ nguyên. Không tự động commit, push hoặc deploy.
