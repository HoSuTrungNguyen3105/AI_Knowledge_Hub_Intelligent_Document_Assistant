# MindFlow AI

Mở rộng AI Knowledge Hub theo `update_features.md`, giữ nền tảng trong `plan_create_web.md` và triển khai từng giai đoạn. **Bản hiện tại: Foundation + Phase 2–5 — Multi-model Chat, Multi-AI Comparison và AI Agent Studio/Execution với tool calling thật.**

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
- **Phase 3 — Multi-model Chat** tại `/chat`: tạo hội thoại theo provider/model đã cấu hình, gửi/nhận tin nhắn **streaming SSE**, lưu lịch sử, đổi tên/xóa hội thoại, tạo lại câu trả lời, sao chép, Markdown + code block, system prompt và temperature/giới hạn token riêng từng hội thoại.
- Chat tái sử dụng collections `conversations`, `messages`, `ai_requests` sẵn có (không tạo bảng trùng); thêm index compound phục vụ liệt kê hội thoại và truy vấn tin nhắn. Mỗi lượt ghi usage token thật từ provider và độ trễ; không tự bịa token/cost.
- Adapter generation async cho OpenAI/Gemini/Groq chạy trên event loop của app, hủy khi client ngắt kết nối; chỉ chặn model khi capability `chat` là `false` rõ ràng (`unknown` vẫn cho phép). API key giải mã trong backend, không trả về browser; nội dung sinh ra được quét để không lộ key kể cả khi key bị chia cắt giữa nhiều delta.
- Trang `/chat` chỉ hiện provider đã `implemented + configured + enabled` và model đã đồng bộ hỗ trợ chat; chưa có provider sẵn sàng thì dẫn sang `/settings`, không dùng model/kết quả giả lập.
- **Phase 4 — Multi-AI Comparison** tại `/compare`: gửi cùng một câu hỏi tới **2–4 model khác nhau** (có thể khác provider), chạy **song song độc lập**; mỗi model một cột hiển thị provider, model, nội dung trả lời (Markdown), trạng thái thành công/lỗi/dừng, độ trễ, token vào/ra và **chi phí ước tính** (khi provider có dữ liệu giá). Một model lỗi **không** làm hỏng cả phép so sánh — các cột khác vẫn chạy và lưu kết quả.
- **AI Synthesis (tùy chọn):** chọn một provider/model đã đồng bộ để tổng hợp các câu trả lời thành công thành một đáp án chung; chỉ chạy khi có ít nhất một câu trả lời thành công. Synthesis cũng stream và lưu lại kèm phép so sánh.
- So sánh lưu trong collection mới `comparisons` (mỗi user chỉ thấy dữ liệu của mình); đổi tên ngầm theo prompt, xóa có xác nhận. Chi phí luôn gắn nhãn **ước tính** (`≈`), phân biệt với chi phí thực tế provider xác nhận; không tự bịa token/giá. Groq công bố giá per-token nên cột Groq có ước tính; provider không công bố giá thì hiển thị `—`.

- **Phase 5 — AI Agents** tại `/agents`: tạo, chỉnh sửa, nhân bản và xóa Agent; cấu hình provider/model đã đồng bộ, system prompt, temperature, token ra và tools. Avatar dùng chữ viết tắt của tên, chưa có upload ảnh.
- Agent gọi **Calculator, DateTime và Data Analyzer** qua function calling: backend kiểm tra tool được bật + schema tham số, chạy tool thật và trả observation cho AI xử lý tiếp. Không có `eval`, shell hoặc lệnh hệ thống tùy ý.
- Vòng lặp giới hạn **6 bước, 120 giây, ngân sách 8.000 token theo ước lượng bảo thủ**, tối đa 4 tool/bước, timeout tool 10 giây. Ngân sách tính cả context gửi lại và output; vẫn chặn khi provider không trả usage. Số token hiển thị/chi phí ước tính chỉ dùng usage provider xác nhận, không dùng ước lượng an toàn này để tính phí.
- Lịch sử lần chạy + trace từng bước/tool lưu theo user trong `agents`, `agent_executions`, `tool_executions`; xóa Agent xóa kèm lịch sử/tool audit. Mỗi lần chạy độc lập, không tự đưa lịch sử vào memory. Key tiếp tục mã hóa, chỉ xử lý ở backend.

- **Phase 6 — Multi-Agent Collaboration** tại `/agents/teams` và `/agents/workflows`: tạo nhóm (Team) từ các Agent đã có, gán vai trò Coordinator/Planner/Architect/Developer/Tester/Reviewer/Researcher và chọn một Coordinator thuộc nhóm; tạo workflow với mục tiêu chung rồi chạy phối hợp thật — Coordinator giao task lần lượt cho từng Agent qua Orchestrator ở backend, mỗi lượt gọi model thật bằng đúng cơ chế chạy Agent của Phase 5 (provider adapter + tool allowlist + ngân sách từng lượt), Agent sau đọc kết quả liên quan của Agent trước qua Context Builder, Reviewer/Tester có thể gửi yêu cầu sửa (`REVISION_REQUEST`) để Agent trước chạy lại trong giới hạn số lần sửa. Mọi message/task/event được lưu bền vững trong 5 collections mới `agent_teams`, `agent_workflows`, `agent_tasks`, `agent_messages`, `agent_workflow_events`; màn hình workspace hiển thị Agent cards theo vai trò, Task Board, Communication Center (tin nhắn thật), tiến độ và timeline, cập nhật qua SSE; có Pause (trạng thái `waiting`)/Resume/Cancel. Giới hạn cấp workflow nằm trong cấu hình backend (tối đa 12 lượt Agent, timeout 600 giây, tối đa 2 lần sửa/task) và không tăng ngân sách Phase 5. Chạy nền tách khỏi kết nối SSE — ngắt trình duyệt không hủy workflow. Cách dùng: tạo Agent ở `/agents` → tạo nhóm ở `/agents/teams` → tạo workflow ở `/agents/workflows` → mở workspace và bấm **Run Workflow**.
- **Xuất ZIP website (Phase 6, bổ sung):** khi tạo workflow, chọn **Sản phẩm đầu ra → Website — xuất ZIP**. Sau khi các Agent xong việc, Agent Developer (hoặc Coordinator nếu nhóm không có Developer) được gọi thêm một lượt để xuất toàn bộ sản phẩm theo định dạng file blocks, theo **hai chế độ**: (1) **website tĩnh** — HTML/CSS/JS thuần, chạy độc lập bằng cách mở `index.html`; (2) **source project** — khi mục tiêu yêu cầu framework (React/Vite/Tailwind…), Agent xuất toàn bộ source project (`package.json`, file cấu hình, `src/...`, README) và ZIP được nhận diện là project khi có `package.json`. Backend trích xuất + kiểm tra an toàn (chặn path traversal, chỉ nhận đuôi file text an toàn gồm cả `jsx/ts/tsx`, giới hạn 50 file / 256 KB mỗi file / 2 MB tổng — cấu hình trong Settings), lưu vào collection `agent_workflow_files` và ghi `artifact_status` trên workflow. Mở workspace: mục **Sản phẩm — Website (ZIP)** ghi rõ loại sản phẩm, liệt kê file và có nút **Tải ZIP** (ZIP dựng trong bộ nhớ, kèm `HUONG-DAN.md` do hệ thống sinh: chế độ project hướng dẫn `npm install` / `npm run dev` / `npm run build`). **Lưu ý trung thực:** server không chạy npm/build thử — source project được đóng gói từ kết quả Agent, người dùng tự chạy các lệnh trên để kiểm tra build. Nếu Agent không trả file hợp lệ, workflow chữ vẫn hoàn thành nhưng artifact bị đánh dấu `failed` kèm mã lỗi rõ ràng — không có ZIP giả. Workflow dạng **Văn bản** (mặc định) và các workflow đã tạo trước đây không xuất ZIP.
- **Thứ tự vai trò + chịu lỗi (Phase 6, bổ sung):** Orchestrator chạy Agent theo **vai trò hiệu dụng** — role cụ thể đã lưu trong nhóm được ưu tiên; member nào còn để role chung "member" sẽ được suy vai trò từ tên Agent (AI Planner → Planner, AI Reviewer → Reviewer...). Nhóm sản xuất (Planner → Architect → Researcher → Developer) luôn chạy trước, Tester/Reviewer chỉ đánh giá **sau khi sản phẩm đã có**; nhóm cũ tạo tay với mọi role là "member" vẫn chạy đúng thứ tự, không cần tạo lại nhóm. Nếu một Agent lỗi provider tạm thời, hệ thống tự thử lại 1 lần; vẫn lỗi thì chỉ task của Agent đó bị đánh dấu Failed (hiện rõ ở cột **Failed** của Task Board) và workflow chạy tiếp với các Agent còn lại — workflow chỉ thất bại khi mọi Agent đều lỗi. Nếu bước tổng hợp cuối của Coordinator lỗi nhưng nhóm đã có kết quả, kết quả thật gần nhất được dùng làm kết quả cuối để không mất công cả nhóm.
- **Tạo workflow — tiêu đề vs mục tiêu:** ô **Tiêu đề** chỉ chứa tên ngắn (tối đa 200 ký tự, có bộ đếm trên form); **toàn bộ yêu cầu chi tiết phải nhập ở ô Mục tiêu chung**. Nếu dữ liệu tạo workflow/nhóm không hợp lệ, API trả mã `validation_error` kèm danh sách trường đã làm sạch (không chứa giá trị đã gửi) để giao diện chỉ rõ trường lỗi, thay cho mã chung chung trước đây.

**Chưa triển khai:** files/RAG/memory và ghi chú. Document Search, Knowledge Search, Text Summarizer, Web Search hiển thị chưa khả dụng cho đến khi có subsystem tương ứng ở Phase 6–7; backend từ chối chạy. Claude, DeepSeek, Ollama chỉ có trong registry, chưa nhận key hoặc gọi API. Không cần API key AI để đăng nhập và dùng dashboard.

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

### Bước E — trò chuyện với model (Phase 3, cần provider đã cấu hình)

Sau khi đã lưu key, bật provider và đồng bộ model ở Bước D, mở `/chat`:

1. Bấm **Hội thoại mới**, chọn provider và model (chỉ model đã đồng bộ, hỗ trợ chat mới hiện). Có thể đặt tên, system prompt, temperature (0–2) và giới hạn token ra (1–8192); để trống để dùng mặc định của provider.
2. Gửi tin nhắn: câu trả lời chạy **streaming** từng phần. Bấm **Dừng** để ngắt giữa chừng (nội dung đã sinh vẫn được lưu, đánh dấu “Đã dừng”).
3. Mỗi hội thoại lưu lịch sử riêng cho tài khoản của bạn; đổi tên, chỉnh cấu hình, **Tạo lại** câu trả lời cuối hoặc sao chép nội dung. Xóa hội thoại sẽ xóa toàn bộ tin nhắn của nó (có hộp thoại xác nhận).
4. Nếu provider/model chưa sẵn sàng, trang sẽ báo lỗi an toàn và dẫn về `/settings`; không có kết quả giả lập. Chi phí/token hiển thị là số thật provider trả về, không phải ước tính.

Stream dùng cùng origin `/api/v1/ai/chat/...` với cookie HttpOnly; trình duyệt nhận `text/event-stream`. Không lưu JWT/API key trong localStorage.

### Bước F — so sánh nhiều model (Phase 4, cần provider đã cấu hình)

Sau Bước D (đã lưu key, bật provider, đồng bộ model), mở `/compare`:

1. Bấm **So sánh mới**, chọn provider + model rồi **Thêm model vào so sánh**; lặp lại để có **2–4 model khác nhau** (có thể trộn nhiều provider). Nhập **Câu hỏi chung**; tùy chọn đặt tên, system prompt, temperature (0–2) và giới hạn token ra (1–8192). Bấm **Tạo phép so sánh**.
2. Bấm **Chạy so sánh**: các cột chạy **song song**, nội dung stream từng phần. Một model lỗi chỉ đánh dấu cột đó, các cột còn lại vẫn hoàn tất. Bấm **Dừng** để ngắt; nội dung đã sinh vẫn được lưu (đánh dấu “Đã dừng”). **Chạy lại** để chạy lại toàn bộ.
3. Mỗi cột hiển thị trạng thái, token vào/ra, độ trễ và **chi phí ước tính** (`≈ $…`, chỉ khi provider công bố giá; nếu không có giá thì `—`). Đây là **ước tính**, không phải khoản phí provider xác nhận.
4. **AI Synthesis (tùy chọn):** chọn provider/model tổng hợp rồi bấm **Tổng hợp câu trả lời** để gộp các đáp án thành công thành một câu trả lời chung (cũng stream, lưu kèm phép so sánh). Chỉ khả dụng khi có ít nhất một câu trả lời thành công.
5. Mỗi phép so sánh lưu riêng theo tài khoản; đổi tên/xóa (có xác nhận). Nếu provider/model chưa sẵn sàng, trang báo lỗi an toàn và dẫn về `/settings`, không có kết quả giả lập.

Stream dùng cùng origin `/api/v1/ai/compare/...` với cookie HttpOnly (`text/event-stream`). API key chỉ giải mã ở backend, không trả về browser.

### Bước G — tạo và chạy Agent (Phase 5)

Sau Bước D, mở `/agents`:

1. Tạo Agent, đặt tên và chọn provider/model đã đồng bộ. Nhập system prompt nếu cần; bật các tool muốn cho Agent sử dụng. Model có capability `tools=false` không được chạy tools; capability chưa xác định phải được kiểm chứng bằng lần chạy thực tế, không bảo đảm từ model listing.
2. Lưu Agent rồi gửi yêu cầu, ví dụ: “Dùng Calculator tính 17 × 23 + 5”, “Dùng DateTime lấy giờ UTC+7”, hoặc “Dùng Data Analyzer tính trung bình của 10, 20, 30, 40”. Trace hiển thị lời gọi và kết quả tool, sau đó là câu trả lời cuối.
3. Có thể dừng khi đang stream, xem lại lịch sử, chỉnh sửa/nhân bản Agent hoặc xóa có xác nhận. Câu hỏi, câu trả lời và tham số/kết quả tool được lưu trong lịch sử của tài khoản; không gửi thông tin nhạy cảm nếu chưa muốn lưu. Chưa có memory dài hạn hay Knowledge Base.
4. Nếu chạm giới hạn bước/token/timeout, lần chạy được lưu với trạng thái lỗi và mã nguyên nhân. Ngân sách ước lượng bảo thủ có thể từ chối prompt dài trước khi gọi provider. Token/chi phí hiển thị không phải số đo của bộ giới hạn này; chi phí luôn là ước tính từ giá công bố.

Không cần cài thư viện hay đổi DB cho Phase 5. Backend `--reload` tự nạp code mới; nếu đang chạy không có reload, khởi động lại backend và frontend. Index mới được tạo idempotent khi backend khởi động; không xóa/chuyển đổi collections cũ.

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
7. `/chat` (cần provider đã cấu hình + đồng bộ model): tạo hội thoại, gửi tin nhắn thấy streaming, dừng giữa chừng vẫn lưu nội dung, tạo lại/sao chép/đổi tên/xóa hoạt động; tài khoản B không thấy hội thoại của A. Chưa cấu hình provider thì trang dẫn sang `/settings`, không có kết quả giả.
8. `/compare` (cần provider đã cấu hình + đồng bộ model): tạo phép so sánh 2–4 model, chạy song song thấy nhiều cột stream; cố tình chọn một model không chat được để xác nhận cột đó lỗi nhưng các cột khác vẫn hoàn tất; tổng hợp (synthesis) chạy khi có ≥1 câu trả lời thành công; token/độ trễ/ước tính chi phí hiển thị đúng nhãn; tài khoản B không thấy phép so sánh của A.
9. `/agents`: tạo/sửa/nhân bản/xóa Agent, gọi ba tool đang khả dụng, thấy trace và câu trả lời stream, dừng/lưu lịch sử; tài khoản B không thấy Agent/lịch sử của A. Tool chưa triển khai không chọn/chạy được.
10. Các mục chưa triển khai (Knowledge/RAG, Memory, Notes, tools phụ thuộc Phase 6–7) ghi rõ lộ trình, không báo thành công giả.
11. Kiểm tra layout ở chiều rộng 360px, 390px, 768px và desktop; menu mobile mở/đóng bằng bàn phím và cảm ứng; chat, compare và agents không tràn ngang.

### Kết quả kiểm chứng của lần triển khai

- Backend: **360 tests passed** (thêm tool/function-calling/Agent CRUD, ownership, budget, timeout, cancellation, audit, Gemini signed parallel replay, BSON guard và usage không đầy đủ), Ruff đạt, `pip check` không có dependency hỏng. Một cảnh báo deprecation upstream về Starlette/httpx, không làm test thất bại.
- Frontend: **161 tests passed** (61 tests Agent mới, gồm API/SSE, helpers, hook identity/revision/cancellation, editor/run/history/capability và confirmations; hồi quy auth/provider/chat/compare); ESLint không lỗi/cảnh báo; production build Next.js thành công (`/chat`, `/compare`, `/agents` là route thật, `[section]` chỉ sinh `/knowledge`, `/notes` — không xung đột).
- Script: `scripts/test_init_env.py` **3 tests passed** (giữ bí mật cũ, không xoay khóa, thay placeholder).
- Smoke test HTTP qua **harness MongoDB in-memory (mongomock) → FastAPI** đạt: health, register, profile, dashboard, refresh rotation, logout, login. Không mock API trong smoke test này; đây là stack thật nhưng DB là in-memory, không phải MongoDB server.
- Smoke test HTTP trên **MongoDB Atlas thật** (backend dev của người dùng) đạt: register 201, lưu key 200 (mã hóa, untested), kiểm tra kết nối trả **400 `provider_authentication_failed`** với key thử không hợp lệ (lỗi có cấu trúc, an toàn, không phải 500 — chứng minh đường adapter async hoạt động), models 200 (rỗng), delete 204, logout 204. **Đây không phải live success**: không có API key provider hợp lệ nên chưa đồng bộ được model thật.
- **Groq live success:** adapter Groq gọi `GET https://api.groq.com/openai/v1/models` bằng key người dùng cung cấp, trả **11 model thật** (vd `openai/gpt-oss-120b`, `qwen/qwen3.8-27b`, `whisper-large-v3`), capabilities `unknown`. Chỉ đọc danh sách model, không generation; key không hardcode trong source và không lưu lại sau kiểm chứng.
- **Groq chat live success (Phase 3):** adapter generation gọi `POST https://api.groq.com/openai/v1/chat/completions` (stream) với model `openai/gpt-oss-20b`, nhận delta nội dung `"OK"` và usage thật (input 76 / output 41 token). Adapter chỉ lấy `delta.content`, bỏ qua `reasoning_content` của model suy luận; key không xuất hiện trong nội dung sinh ra. Key chỉ đọc lúc chạy để kiểm chứng, không hardcode/lưu/commit.
- **Geometry offline (Phase 3):** harness iframe cố định 360/390/768/1440px nhúng đúng `globals.css` + `chat.css` và DOM chat thật; đo bằng số (không chụp ảnh): `scrollWidth === clientWidth` ở cả document, `.page-content` và `.chat-layout` cho cả màn hình hội thoại lẫn setup panel → không tràn ngang; bảng Markdown rộng và code block dài cuộn nội bộ đúng thiết kế.
- **Groq compare live success (Phase 4):** chạy đúng đường adapter mà `CompareService` dùng (không ghi DB, key chỉ đọc lúc chạy, không in ra). Catalog 11 model (5 chat / 6 non-chat). Hai model chat `openai/gpt-oss-safeguard-20b` và `qwen/qwen3.8-27b` cùng trả lời `"4"` với usage thật (92/63 và 29/2 token) và **chi phí ước tính** từ giá per-token Groq (≈ $0.0000258 và ≈ $0.0000312). `whisper-large-v3` (non-chat) trả `generation_failed` đúng như mong đợi. **Cô lập lỗi:** 2 thành công + 1 thất bại trong cùng phép so sánh — một model lỗi KHÔNG hủy các model khác. **Synthesis** gộp các đáp án thành công, trả `"4"` (145/122 token). Key không hardcode/lưu/commit.
- **Geometry offline (Phase 4):** harness Node + iframe cố định 1440/1200/1000/760/380px nhúng đúng `globals.css` + `chat.css` + `compare.css` và DOM compare thật (2/3/4 cột + synthesis + setup, kèm bảng Markdown/code block dài); đo bằng số (không chụp ảnh): `docOverflow = 0`, `worst = 0`, `clip = 0` ở mọi chiều rộng và mọi biến thể → không tràn ngang, không phần tử nào vượt viewport, không container nào cắt nội dung; `.run-columns` tự xuống hàng ở màn hẹp.
- **Groq Agent live success (Phase 5):** HTTP thật qua FastAPI → MongoDB Atlas, model `openai/gpt-oss-20b`; cả ba lần chạy success trong 2 bước: Calculator `17*23+5` → `396` (input 743/output 72 token), DateTime UTC+7 → thời gian ISO hợp lệ (817/92), Data Analyzer `[10,20,30,40]` → count `4`, mean `25` (796/112). GET execution đã lưu khớp stream ở cả ba trường hợp; SSE không chứa key. Key chỉ đọc lúc kiểm thử từ nguồn người dùng cho phép, gửi qua API cấu hình và mã hóa như ứng dụng hiện hành; không hardcode/in/lưu key vào source. Tài khoản tạm và toàn bộ dữ liệu thuộc đúng tài khoản này đã được dọn sau kiểm chứng, không xóa dữ liệu người dùng cũ.
- **Hồi quy Agent offline:** signed replay Gemini giữ đúng ID/thought signature, gom các function responses song song; opaque metadata không xuất hiện trong SSE/history. Tham số không lưu được BSON bị từ chối an toàn; hủy wrapper/đúng lúc finalizer ghi vẫn lưu terminal một lần. Usage thiếu ở bất kỳ bước nào không được báo thành tổng đầy đủ hoặc cost đầy đủ. Đây là contract tests, không phải Gemini live.
- **Geometry offline (Phase 5):** Node + headless Chrome đo DOM JSX/CSS Agent thật trong iframe cố định 360/390/768/1000/1440px (không chụp ảnh), gồm 14 Agent tên dài, model 512 ký tự, editor, trace JSON, bảng Markdown/code dài, lịch sử/lỗi. Sau khi sửa `min-width:0`, mỗi mục danh sách còn 180–215px; document overflow ngang **0px** ở mọi khung; provider/model lịch sử xuống dòng trong khung; JSON/code/bảng cuộn nội bộ. Nhãn danh sách và select đóng được cắt bằng ellipsis theo thiết kế.
- Tài khoản kiểm thử cũ đã tạo trong DB dev (không tự xóa): `smoke-http-fix@example.com`, `smoke-proxy-c29c3a71@example.com`, `prov-smoke-5917a5c1@example.com`. Tài khoản do harness tạo chỉ tồn tại in-memory và mất khi dừng.
- **Chưa kiểm chứng:** build/chạy Docker image (máy không có Docker); đồng bộ model thật và chat/compare/agent live bằng API key hợp lệ cho OpenAI/Gemini (Groq đã live listing, chat, compare/synthesis và ba Agent tools); xác nhận trực quan trên thiết bị thật của người dùng. Không đánh đồng mongomock tests với MongoDB integration tests.

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

### Hợp đồng chat (Phase 3)

Tất cả endpoint cần đăng nhập, prefix `/api/v1/ai/chat`, trả `Cache-Control: no-store`, lọc theo chủ sở hữu và không có trường bí mật.

| Endpoint | Hợp đồng |
|---|---|
| GET `/conversations` | `{conversations:[{id,title,provider,model,system_prompt,temperature,max_output_tokens,created_at,updated_at}]}` |
| POST `/conversations` | Body `{provider,model,title?,system_prompt?,temperature?,max_output_tokens?}` (extra=forbid); 201 + summary. Provider phải implemented + configured + enabled, model phải đã đồng bộ |
| GET `/conversations/{id}` | `{...summary, messages:[{id,role,content,status,model,input_tokens,output_tokens,latency_ms,error_code,created_at}]}` |
| PATCH `/conversations/{id}` | Body ≥1 trường `title?/system_prompt?/temperature?/max_output_tokens?`; không đổi provider/model; title không được null |
| DELETE `/conversations/{id}` | 204; xóa hội thoại và toàn bộ tin nhắn của nó |
| POST `/conversations/{id}/messages` | Body `{content}` (1–32000 ký tự, strip); trả `text/event-stream` |
| POST `/conversations/{id}/regenerate` | Không body; thay câu trả lời assistant cuối bằng lượt sinh mới, trả `text/event-stream` |

SSE gồm các event: `user_message` (tin nhắn user đã lưu), `delta` (`{text}` từng phần), `done` (`{message}` assistant hoàn chỉnh kèm usage), `error` (`{code,message}` đã làm sạch). Định dạng `event: <name>\ndata: <json>\n\n`. Lỗi trước khi stream (validation, ownership, capability, credential) trả JSON `{detail:{code,message}}` với HTTP tương ứng (404/409/422), không phải SSE. Client ngắt kết nối → tác vụ provider bị hủy, nội dung đã sinh được lưu với status `stopped`.

Mã lỗi chat: `conversation_not_found` (404), `model_not_chat_capable`/`model_not_synced`/`provider_disabled`/`credentials_missing` (409), `empty_message`/`invalid_provider_configuration` (422), `generation_failed`/`provider_unavailable` (502), `provider_authentication_failed` (400), `provider_rate_limited` (429), `provider_timeout` (504), `encryption_unavailable` (503). CSRF Origin và rate limit áp dụng như các API AI khác.

### Hợp đồng compare (Phase 4)

Tất cả endpoint cần đăng nhập, prefix `/api/v1/ai/compare`, trả `Cache-Control: no-store`, lọc theo chủ sở hữu và không có trường bí mật.

| Endpoint | Hợp đồng |
|---|---|
| GET `/comparisons` | `{comparisons:[{id,title,targets:[{provider,model}],has_synthesis,created_at,updated_at}]}` |
| POST `/comparisons` | Body `{prompt(1–32000,strip),targets:[{provider,model}](2–4 phần tử khác nhau),title?,system_prompt?(≤8000),temperature?(0–2),max_output_tokens?(1–8192)}`; 201 + detail. Mỗi target phải implemented + configured + enabled, model đã đồng bộ và không bị chặn chat |
| GET `/comparisons/{id}` | `{id,title,prompt,system_prompt,temperature,max_output_tokens,runs:[RunOut],synthesis:SynthesisOut|null,created_at,updated_at}` |
| DELETE `/comparisons/{id}` | 204; xóa phép so sánh của user |
| POST `/comparisons/{id}/execute` | Không body; chạy song song tất cả target, trả `text/event-stream` |
| POST `/comparisons/{id}/synthesize` | Body `{provider,model}`; tổng hợp các run thành công, trả `text/event-stream` |

`RunOut`: `{id,provider,model,status(pending|success|stopped|error),content,input_tokens,output_tokens,latency_ms,error_code,estimated_cost}`. `SynthesisOut` cùng dạng (một provider/model). `estimated_cost` là **ước tính** từ giá per-token provider công bố (Groq có; provider không công bố giá thì `null`), không phải khoản phí provider xác nhận.

SSE execute gồm: `comparison` (detail ban đầu), nhiều `run_delta` (`{run_id,text}`), `run_done`/`run_error` (`{run}` hoàn chỉnh), `done` (detail cuối). SSE synthesize gồm: `synthesis_delta` (`{text}`), `synthesis_done` (`{synthesis}`), `synthesis_error` (`{code,message}`), `done`. Định dạng `event: <name>\ndata: <json>\n\n`. **Một run lỗi phát `run_error` rồi các run khác vẫn tiếp tục** — không hủy cả phép so sánh. Lỗi trước khi stream (validation, ownership, target, credential) trả JSON `{detail:{code,message}}` (404/409/422), không phải SSE. Client ngắt kết nối → các tác vụ provider bị hủy, nội dung đã sinh được lưu với status `stopped`.

Mã lỗi compare bổ sung: `comparison_not_found` (404), `invalid_comparison_targets` (422), `no_successful_runs` (409 — synthesis cần ≥1 run thành công); dùng chung các mã provider/chat ở trên. CSRF Origin và rate limit áp dụng như các API AI khác.

### Hợp đồng agents (Phase 5)

Prefix `/api/v1/ai/agents`; mọi endpoint cần đăng nhập, `Cache-Control: no-store`, lọc chủ sở hữu. Không có endpoint thực thi tool tùy ý.

| Endpoint | Hợp đồng |
|---|---|
| GET `/tools` | `{tools:[{name,description,parameters,available,phase}]}`; metadata registry cố định |
| GET/POST đường gốc | `{agents:[AgentSummary]}` / tạo `{name,provider,model,description?,system_prompt?,temperature?,max_output_tokens?,tools?}` → 201 + detail |
| GET/PATCH/DELETE `/{id}` | Đọc/sửa cấu hình hoặc xóa Agent + executions/tool audit; trường name/provider/model/tools không được null |
| POST `/{id}/duplicate` | 201 + bản sao cấu hình, không sao chép lịch sử |
| POST `/{id}/run` | `{prompt}` → SSE; kiểm tra credential/model/capability và budget trước stream |
| GET `/{id}/executions` | `{executions:[ExecutionSummary]}` |
| GET/DELETE `/{id}/executions/{execution_id}` | Detail gồm content, steps, usage, latency, error_code, estimated_cost, tool_executions / xóa run + audit |

SSE: `execution` (`{execution}`) → `step_delta` (`{step_index,text}`), `tool_call`/`tool_result` (`{step_index,tool_call}`), `step_done` (`{step}`) → `done` (`{execution}`). Lỗi runtime phát `execution_error` (`{code,message}`) trước `done` có trạng thái lỗi. Tool lỗi trả observation an toàn cho model, không thực thi ngoài allowlist. Dừng/ngắt stream lưu phần đã sinh với `stopped`.

Execution trả snapshot `provider`/`model`, prompt/content, status, steps, input/output token nullable, latency/error và tool audit. Tổng input/output chỉ hiện khi tất cả bước đã gọi đều có usage phía tương ứng; nếu thiếu một phía thì cost ước tính null, không tính phí từ số token ước lượng bảo thủ. Thought signature/metadata replay riêng của Gemini không trả cho frontend hoặc lưu vào trace công khai.

Mã lỗi bổ sung: `agent_not_found`/`execution_not_found` (404), `invalid_agent_tools` (422), `model_not_tool_capable`/`agent_step_limit`/`agent_budget_exceeded` (409), `agent_timeout` (504). Dùng lại các mã provider/chat hiện có; CSRF Origin/rate limit áp dụng như trước.

## 5. Triển khai trên server

Đây là nền tảng Foundation + Phase 2–5 (Chat, Compare, Agent Studio/Execution), **chưa phải toàn bộ sản phẩm AI hoàn thiện**. Trước khi mở public:

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
| 3 | Multi-model Chat: messages, generation/stream SSE, capability checks, history, system prompt/temperature/token limits | Đã triển khai; Groq đã live chat (stream + usage), OpenAI/Gemini chưa live test |
| 4 | Compare AI: chạy song song độc lập lỗi, synthesis tùy chọn, usage/độ trễ, cost ước tính (có nhãn) vs thực tế | Đã triển khai; Groq đã live compare + isolation + synthesis + pricing, OpenAI/Gemini chưa live test |
| 5 | Agent Studio/Execution: tools allowlist, quyền, budget, logs | Đã triển khai; Groq live gọi 3 tools và lưu lịch sử trên MongoDB Atlas; OpenAI/Gemini chỉ contract tests, chưa live |
| 6 | File Intelligence/RAG/Memory, Research/Workflow | Chưa triển khai |
| 7 | Production: live provider tests, MongoDB/Docker integration, hardening | Chưa triển khai |

Bản đặc tả gốc được giữ nguyên. Không tự động commit, push hoặc deploy.