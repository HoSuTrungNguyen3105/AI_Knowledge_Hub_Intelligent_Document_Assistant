# AI Agent Factory — 10 AI Agent phối hợp qua n8n

Hệ thống tự động hoá bằng **n8n**: 10 AI Agent (Project Manager, Business Analyst,
UI/UX Designer, Frontend Architect, Frontend Developer, Backend Architect,
Backend Developer, Integration Agent, QA Engineer, Code Reviewer) phối hợp
xây dựng website/module phần mềm qua **OpenRouter**, sinh code thật, chạy
build/test trong **Docker sandbox** riêng, có vòng QA → sửa lỗi → review lại,
và đóng gói **ZIP** để tải xuống. Trạng thái mọi Agent được lưu vào
**PostgreSQL** và theo dõi qua Dashboard đi kèm.

```
Người dùng ──► Dashboard (:8080) ──► n8n Main Orchestrator (:5678)
                                          │
        ┌──────────────┬──────────────────┼──────────────────┐
        ▼              ▼                  ▼                  ▼
  Agent Execution  Parallel Exec.   Code Generation    QA & Review ──► ZIP Packaging
  (OpenRouter)     (chạy song song)      │                  │
                                          ▼                  ▼
                              Code Execution Service (Docker sandbox:
                              ghi file, npm install/lint/test/build, ZIP)
                                          │
                                     PostgreSQL (projects, tasks,
                                     agent_runs, artifacts, qa_reviews)
```

## 1. Yêu cầu

- Docker + Docker Compose (máy bạn kiểm soát — service thực thi cần quyền
  Docker daemon để tạo sandbox, xem mục Bảo mật).
- Một API key **OpenRouter** (https://openrouter.ai/keys).
- n8n mục tiêu: **1.x** (đã kiểm theo format export của n8n 1.x; xem mục
  "Giới hạn trung thực" ở cuối).

## 2. Cài đặt

```bash
cp .env.example .env
```

Mở `.env` và đặt:

- `POSTGRES_PASSWORD`: mật khẩu tuỳ ý.
- `HOST_WORKSPACES_DIR`: **đường dẫn tuyệt đối trên máy host** của thư mục
  `ces-data/workspaces` trong thư mục dự án này. Ví dụ Windows:
  `C:/ai-agent-factory/ces-data/workspaces`; macOS/Linux:
  `/home/you/ai-agent-factory/ces-data/workspaces`. Bắt buộc ở chế độ sandbox
  Docker để container sandbox mount đúng file mà service đã ghi.

Khởi động:

```bash
docker compose up -d --build
docker compose ps        # postgres healthy, n8n và code-exec-service up
```

- n8n: http://localhost:5678 (lần đầu tạo tài khoản owner).
- Dashboard: http://localhost:8080

## 3. Khoá API và credential (bắt buộc đọc)

**Khoá provider (Groq / Ollama / OpenRouter) KHÔNG nằm trong workflow JSON.**
Workflow Agent Execution đọc khoá từ biến môi trường của n8n lúc chạy:
`GROQ_API_KEY`, `OLLAMA_API_KEY`, `OPENROUTER_API_KEY` — đặt chúng trong
file `.env` cạnh `docker-compose.yml` (xem `.env.example`). Vì vậy JSON
workflow an toàn để commit/public; file `.env` thật thì **tuyệt đối không
commit** (repo này là PUBLIC — lộ khoá là mất khoá).

Provider mặc định của bản tích hợp này là **Groq** (model
`openai/gpt-oss-120b` / `openai/gpt-oss-20b` — đúng dòng model MindFlow
đang chạy). Đổi provider/model: trên Dashboard (ô chọn nhà cung cấp + model
từng Agent), hoặc trong node **Resolve Agent Config** của workflow Agent
Execution (`DEFAULT_PROVIDER` và bảng `models` của từng Agent), hoặc ghi đè
theo từng lần chạy bằng trường `providers` / `models` của request.

Credential n8n duy nhất còn cần tạo (tham chiếu theo tên, sai tên là node
báo lỗi ngay):

- **AI Factory Postgres** — loại *Postgres*: Host `postgres`, Port `5432`,
  Database / User / Password đúng các giá trị `POSTGRES_DB / POSTGRES_USER /
  POSTGRES_PASSWORD` trong `.env`.

Sau khi import (mục 4), mở từng workflow kiểm tra các node Postgres đã gắn
đúng credential trên; nếu n8n báo credential chưa chọn thì chọn lại theo
tên rồi lưu. Hướng dẫn từng bước bằng tiếng Việt: xem **HUONG-DAN.md**.

## 4. Import workflow vào n8n

Trong n8n: **Workflows → ⋯ → Import from File**, import lần lượt 6 file trong
thư mục `workflows/` (thứ tự không quan trọng vì các workflow gọi nhau qua
webhook, không qua ID):

| File | Vai trò | Webhook |
|---|---|---|
| `01-main-orchestrator.json` | Điều phối toàn bộ pipeline + vòng sửa lỗi | `POST /webhook/ai-factory/start` |
| `02-agent-execution.json` | Chạy 1 Agent qua OpenRouter, lưu run vào DB | `POST /webhook/ai-factory/agent-execute` |
| `03-parallel-agent-execution.json` | Chạy nhiều Agent song song, gộp kết quả | `POST /webhook/ai-factory/parallel` |
| `04-code-generation.json` | Dev Agent sinh code → Integration → lưu file vào CES | `POST /webhook/ai-factory/codegen` |
| `05-qa-and-review.json` | Build/test trong sandbox + QA + Reviewer | `POST /webhook/ai-factory/qa-review` |
| `06-zip-packaging.json` | Đóng gói ZIP + cập nhật link tải | `POST /webhook/ai-factory/package` |
| `07-seven-agent-dynamic-routing.json` | Đội 7 role tự chọn model theo task (mục 11) | `POST /webhook/ai-team/start` |

Sau đó **Activate cả 6 workflow** (webhook production chỉ hoạt động khi
workflow đang active).

Đổi model/prompt cho từng Agent: mở workflow **Agent Execution** → node
**Resolve Agent Config** — mọi Agent, model mặc định và system prompt đều ở
đó. Model cũng ghi đè được theo từng lần chạy qua trường `models` của request
hoặc ngay trên Dashboard.

Model mặc định theo OpenRouter (bảng dưới). Khi dùng Groq, mặc định là `openai/gpt-oss-120b` (riêng 2 Developer là `openai/gpt-oss-20b`); khi dùng Ollama Cloud là `gpt-oss:120b` (Developer: `qwen3-coder:480b`, QA: `deepseek-v3.1:671b`) — toàn bộ nằm trong node Resolve Agent Config và trên Dashboard:

| Agent | Model mặc định |
|---|---|
| Project Manager | `anthropic/claude-sonnet-4.5` |
| Business Analyst | `openai/gpt-5` |
| UI/UX Designer | `google/gemini-2.5-pro` |
| Frontend Architect | `anthropic/claude-sonnet-4.5` |
| Frontend Developer | `qwen/qwen3-coder` |
| Backend Architect | `openai/gpt-5` |
| Backend Developer | `qwen/qwen3-coder` |
| Integration Agent | `anthropic/claude-sonnet-4.5` |
| QA Engineer | `deepseek/deepseek-r1` |
| Code Reviewer | `anthropic/claude-sonnet-4.5` |

## 5. Cách các Agent phối hợp (không chạy độc lập)

Mọi trao đổi đi qua Main Orchestrator theo đúng đồ thị phụ thuộc:

1. **Project Manager** nhận yêu cầu → trả kế hoạch JSON: danh sách task,
   `agents_needed`, thứ tự/phụ thuộc. Task được ghi vào bảng `tasks`.
2. **Business Analyst ∥ UI/UX Designer** chạy **song song** (Workflow 3).
3. **Frontend Architect ∥ Backend Architect** chạy song song, nhận output
   của BA/UX làm context.
4. **Code Generation**: Frontend Developer ∥ Backend Developer sinh file →
   **Integration Agent** đối chiếu API contract, sửa file xung đột → file
   cuối được ghi vào workspace của Code Execution Service, ghi `artifacts`.
5. **QA & Review**: CES chạy `npm install/lint/test/build` trong sandbox →
   QA Engineer + Code Reviewer phán quyết. Chưa đạt → Orchestrator gửi issue
   về **đúng Agent phụ trách** sửa (tối đa 2 vòng sửa), rồi QA lại.
6. Đạt (hoặc hết vòng sửa — trạng thái `COMPLETED_WITH_ISSUES` ghi rõ, không
   giả vờ đạt) → đóng gói ZIP.

Mọi Agent dùng **một schema JSON thống nhất**:
`{task_id, project_id, agent_id, task_description, input_context, output,
status, error, artifacts}` — và mỗi lượt chạy đều lưu vào `agent_runs` kèm
model, token usage, chi phí (nếu OpenRouter trả về), thời gian chạy, lỗi và
số lần thử (trạng thái PENDING / RUNNING / COMPLETED / FAILED / RETRYING ở
tầng dữ liệu; node gọi OpenRouter tự retry 2 lần khi lỗi mạng/5xx).

## 6. Ba chế độ sử dụng

Gửi `POST http://localhost:5678/webhook/ai-factory/start`:

**Mode A — Full Website** (mặc định khi `mode: "full"`): cả 10 Agent.

```json
{ "mode": "full",
  "requirement": "Xây dựng website bán giày sneaker bằng React + Vite + Tailwind…" }
```

**Mode B — Specific Module**: PM quyết định chỉ gọi các Agent cần cho module.

```json
{ "mode": "module", "module_name": "Authentication",
  "requirement": "Module đăng nhập/đăng ký JWT cho hệ thống hiện tại…" }
```

**Mode C — Existing Project**: gửi kèm ZIP source hiện có (base64). CES giải
nén vào workspace (chặn path traversal, giới hạn số file/dung lượng), PM nhận
cây file thật và chỉ lên kế hoạch thay đổi tối thiểu; file ngoài phạm vi
không bị đụng vào — Developer chỉ trả về file cần sửa/thêm, CES ghi đè đúng
các file đó.

```json
{ "mode": "existing", "requirement": "Thêm trang cài đặt tài khoản…",
  "existing_zip_base64": "<base64 của file .zip>" }
```

## 7. Ví dụ chạy thử (đầu → cuối)

1. Mở Dashboard http://localhost:8080, chọn chế độ **A — Full Website**, nhập:

   > Xây dựng website bán giày sneaker bằng React + Vite + Tailwind CSS:
   > trang chủ (hero, sản phẩm nổi bật), trang danh sách sản phẩm có lọc theo
   > hãng và giá, trang chi tiết sản phẩm, giỏ hàng lưu localStorage, trang
   > thanh toán mô phỏng và trang liên hệ. Tối thiểu 12 sản phẩm. Giao diện
   > hiện đại, responsive.

2. Bấm **Bắt đầu chạy 10 Agent**. Dashboard tự phát hiện project mới và cập
   nhật mỗi 5 giây: trạng thái từng Agent, token/chi phí, lượt QA.
3. Hoặc chạy bằng curl:

   ```bash
   curl -X POST http://localhost:5678/webhook/ai-factory/start \
     -H 'Content-Type: application/json' \
     -d '{"mode":"full","requirement":"Xây dựng website bán giày sneaker bằng React + Vite + Tailwind: trang chủ, danh sách sản phẩm có lọc, chi tiết, giỏ hàng localStorage, thanh toán mô phỏng, liên hệ. Tối thiểu 12 sản phẩm."}'
   ```

   Webhook chỉ trả lời khi **toàn bộ pipeline xong** (vài phút đến vài chục
   phút tuỳ model) — response gồm `project_id`, `status`, `download_url` và
   tóm tắt QA. Trong lúc chờ, theo dõi ở Dashboard hoặc
   `GET http://localhost:8080/api/projects/<project_id>`.
4. Tải ZIP ở `download_url` (hoặc nút **Tải file ZIP** trên Dashboard), giải
   nén, chạy thử:

   ```bash
   npm install
   npm run dev     # xem website
   npm run build   # kiểm tra build
   ```

## 8. Code Execution Service — API & an toàn

| Endpoint | Việc |
|---|---|
| `POST /projects` `{project_id}` | Tạo workspace |
| `POST /projects/:id/files` `{files:[{path,content}]}` | Ghi file (chặn `..`, đường dẫn tuyệt đối, file ẩn nguy hiểm; giới hạn 200 file/lượt, 1MB/file, 20MB/lượt) |
| `GET /projects/:id/files` | Cây file hiện tại |
| `POST /projects/:id/import` `{zip_base64}` | Giải nén project có sẵn (tối đa 500 entries / 50MB) |
| `POST /projects/:id/run` `{steps}` | Chạy install/lint/test/build trong sandbox |
| `POST /projects/:id/package` | Đóng ZIP (luôn loại `node_modules`, `.git`, `.env*`) |
| `GET /projects/:id/download` | Tải ZIP |
| `GET /api/projects`, `GET /api/projects/:id` | Trạng thái cho Dashboard (đọc PostgreSQL) |

Sandbox Docker cho mỗi bước chạy: container dùng một lần từ image
`node:20-alpine`, `--memory 1g --cpus 2 --pids-limit 256`, timeout 300s,
**không mount secret nào**, **tắt network** cho lint/test/build (chỉ bước
install được ra mạng để tải package từ npm registry). Mỗi project một thư
mục riêng — service không cho truy cập chéo project khác.

> ⚠️ Để spawn sandbox, CES được mount `/var/run/docker.sock` — tương đương
> quyền Docker daemon trên host. Chỉ chạy hệ thống này trên máy bạn kiểm
> soát. Chế độ `SANDBOX_MODE=local` chạy code AI **không có cô lập** — chỉ
> dùng khi phát triển và hiểu rõ rủi ro.


## 11. Workflow 07 — 7 Agent tự chọn model theo task (Dynamic Model Routing)

Theo đặc tả `ai-7-agent-dynamic-model-routing.md`: một workflow độc lập
(không cần Postgres/Dashboard) với đúng **7 role logic** — AI Leader,
AI Planner, AI Architect, AI Developer/Executor, AI Tester/Validator,
AI Reviewer, AI Researcher — xử lý **đa lĩnh vực** (phần mềm, nghiên cứu,
kinh doanh, marketing, giáo dục, văn phòng, sáng tạo), không ép mọi yêu
cầu thành dự án code.

Cách hoạt động:

1. **Model Capability Registry**: danh sách model kèm năng lực
   (reasoning/planning/architecture/coding/testing/review/research/
   writing/fast), độ mạnh, mức chi phí. Một model chỉ `available` khi key
   của provider tương ứng có trong môi trường n8n (`GROQ_API_KEY` /
   `OLLAMA_API_KEY` / `OPENROUTER_API_KEY` trong `.env`). Claude/GPT/
   DeepSeek bản quyền riêng **không được giả định đã có** — chúng chỉ vào
   registry qua OpenRouter và chỉ available khi `OPENROUTER_API_KEY` đã đặt.
2. **Leader lập kế hoạch** theo contract của đặc tả (task có role,
   depends_on, acceptance_criteria, model_selection...).
3. **Model Router** kiểm chứng lựa chọn của Leader với registry: model
   không tồn tại/không available/sai năng lực thì router gán lại theo
   capability + độ phức tạp, kèm lý do và danh sách fallback. Không có
   model nào phù hợp → task mang trạng thái `needs_configuration`, không
   giả vờ hoàn thành.
4. **Thực thi** từng task theo thứ tự dependency (kết quả task trước được
   truyền cho task phụ thuộc), lỗi provider thì thử 1 lần + chuyển
   fallback. Role nào kế hoạch không cần sẽ xuất hiện trong kết quả với
   trạng thái `skipped` kèm lý do.
5. **Review gate**: Reviewer độc lập chấm theo contract review của đặc
   tả, ưu tiên model khác model đã thực thi nhiều nhất; chưa đạt thì các
   task bị nêu tên chạy lại (tối đa **2 vòng sửa**), sau đó Leader tổng
   hợp kết quả cuối.

Gọi thử:

```bash
curl -X POST http://localhost:5678/webhook/ai-team/start \
  -H "Content-Type: application/json" \
  -d '{"requirement":"Lập kế hoạch marketing 3 tháng cho ứng dụng học tiếng Anh trẻ em","domain":["marketing"]}'
```

Kết quả trả về gồm `plan` (kèm model_selection + lý do cho từng task),
`task_results` (contract kết quả từng role, có provider/model/thời gian
chạy), `skipped_roles`, `review`, `revision_rounds` và `final` của Leader.

Giới hạn của workflow này: các task chạy **tuần tự** theo thứ tự dependency
(chưa chạy song song trong cùng một workflow để giữ việc import/đọc hiểu
đơn giản); trạng thái vòng chạy lưu ở static data của workflow nên chỉ
chạy **một execution tại một thời điểm**. Sinh lại JSON sau khi sửa:
`python3 tools/build_workflow_07.py` rồi import lại.

## 9. Xử lý sự cố

- **`missing_env_key`**: file `.env` cạnh docker-compose chưa có khoá của provider đang chọn, hoặc đã sửa `.env` mà chưa `docker compose up -d` lại để n8n nhận biến mới.
- **Webhook 404**: workflow chưa Active, hoặc sai path — kiểm tra cả 6
  workflow đã bật.
- **Node Postgres/OpenRouter báo credential lỗi**: tên credential phải đúng
  `AI Factory Postgres` và `OpenRouter API`; chọn lại credential trong node
  rồi lưu workflow.
- **Lỗi `HOST_WORKSPACES_DIR is not configured`** ở bước build: đặt biến này
  trong `.env` (đường dẫn host tuyệt đối) rồi `docker compose up -d` lại.
- **Agent trả `model_did_not_return_valid_json`**: model đó không tuân thủ
  JSON — đổi model cho Agent đó trong node Resolve Agent Config hoặc qua
  Dashboard. Lượt chạy lỗi vẫn được lưu đầy đủ trong `agent_runs`.
- **Chạy lâu**: bình thường — 10 Agent + build. Xem tiến độ ở Dashboard hoặc
  bảng `agent_runs`; n8n Executions cho thấy node đang chạy.

## 10. Giới hạn trung thực

- Bộ workflow được **sinh bằng code và kiểm tra cấu trúc + cú pháp toàn bộ
  Code node bằng script** (`tools/validate_workflows.py`), service kiểm tra
  cú pháp bằng Node — nhưng **chưa được chạy thử trên một n8n/OpenRouter
  thật trong môi trường soạn thảo này**. Lần chạy đầu tiên của bạn là lần
  kiểm chứng thật: nếu node nào lỗi cấu hình, n8n báo rõ tại node đó.
- Kết quả build/test là thật theo nghĩa: CES **thực sự chạy** npm trong
  sandbox và QA dựa trên log thật đó. Hệ thống không bao giờ tự tuyên bố
  build thành công khi sandbox trả lỗi — trường hợp hết 2 vòng sửa mà vẫn
  chưa đạt, project đóng với trạng thái `COMPLETED_WITH_ISSUES` kèm danh
  sách issue còn lại.
- Frontend do Developer Agent sinh là một project Vite độc lập; backend (nếu
  có) nằm trong thư mục `server/` của cùng project và chạy riêng theo ghi
  chú của Backend Developer — CES chỉ build frontend ở bước `build`.
- Dashboard là bản MVP một file tĩnh do CES phục vụ: đủ form 3 chế độ, chọn
  model từng Agent, theo dõi 10 Agent, QA, log và tải ZIP — đúng phạm vi
  quản lý cần thiết, không phải một SPA riêng.
