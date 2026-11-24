# HƯỚNG DẪN DÙNG — n8n AI Agent Factory (bản tích hợp trong repo MindFlow)

Thư mục `n8n-ai-factory/` này là hệ thống 10 AI Agent chạy bằng n8n, nằm
**độc lập** với backend/frontend MindFlow: nó có Docker Compose, database
MongoDB và service thực thi riêng. MindFlow không bị ảnh hưởng gì khi
bạn chạy hay tắt hệ thống này.

Luồng hoạt động: bạn nhập yêu cầu → Project Manager chia việc → các Agent
phân tích/thiết kế → Developer sinh code → Integration đối chiếu → QA chạy
build thật trong Docker sandbox + Reviewer duyệt (chưa đạt thì trả về đúng
Agent sửa, tối đa 2 vòng) → đóng gói ZIP cho bạn tải.

---

## Bước 1 — Lấy code về máy

```powershell
cd F:\Clone\clone-digotal_3\AI_Application\AI_Knowledge_Hub_Intelligent_Document_Assistant
git pull
cd n8n-ai-factory
```

Mở **Docker Desktop** và đợi nó chạy xong (icon cá voi đứng yên).

## Bước 2 — Tạo file .env và đưa 2 key Groq/Ollama vào (QUAN TRỌNG)

```powershell
Copy-Item .env.example .env
notepad .env
```

Trong file `.env` vừa tạo, điền:

1. `MONGODB_URI` + `MONGODB_DATABASE`: chuỗi kết nối **MongoDB Atlas**
   của bạn (cùng cluster với MindFlow — lấy trong Atlas: Connect →
   Drivers) và tên database `mindflow_ai`. **URI chứa mật khẩu database
   nên file `.env` này tuyệt đối không được commit.** Xem dữ liệu: mở
   Atlas trên web (Data Explorer) hoặc MongoDB Compass bằng chính URI đó.
2. `HOST_WORKSPACES_DIR`: đường dẫn tuyệt đối của thư mục workspaces trên
   máy bạn. Nếu repo nằm ở
   `F:\Clone\clone-digotal_3\AI_Application\AI_Knowledge_Hub_Intelligent_Document_Assistant`
   thì điền (dùng dấu `/`):
   ```
   HOST_WORKSPACES_DIR=F:/Clone/clone-digotal_3/AI_Application/AI_Knowledge_Hub_Intelligent_Document_Assistant/n8n-ai-factory/ces-data/workspaces
   ```
3. `GROQ_API_KEY` và `OLLAMA_API_KEY`: mở file **`backend\.env` ở gốc repo
   MindFlow** (file bạn đang dùng cho backend), copy đúng 2 giá trị đó dán
   sang. Đây là cách "kết hợp key vào hệ thống n8n": workflow JSON chỉ
   chứa **tên biến** (`GROQ_API_KEY` / `OLLAMA_API_KEY`), lúc chạy n8n tự
   lấy giá trị từ file `.env` này.

> ⚠️ **Ba điều tuyệt đối về key:**
> - Repo này là **PUBLIC** — file `.env` chứa key thật **không bao giờ
>   được commit**. Trước mỗi lần commit bất cứ thứ gì, chạy `git status`:
>   nếu thấy `.env` của thư mục này xuất hiện trong danh sách sẽ commit
>   thì DỪNG LẠI và xoá nó khỏi staging ngay.
> - Không dán key vào file JSON workflow, không gửi key qua chat.
> - `GROQ_API_KEY` đang dùng chung với MindFlow production — lộ key này là
>   AI của MindFlow cũng ngừng hoạt động theo. Key Ollama nếu là key dùng
>   thử từng dán qua chat trước đây thì nên vào ollama.com thu hồi và tạo
>   key mới rồi mới điền vào đây.

## Bước 3 — Khởi động

```powershell
docker compose up -d --build
docker compose ps
```

Lần đầu build vài phút. Đạt khi `n8n` và
`code-exec-service` đều Up. Kiểm tra nhanh: mở http://localhost:8080/health
thấy `{"status":"ok"...}` là service thực thi đã sống.

## Bước 4 — Thiết lập n8n (làm 1 lần)

1. Mở http://localhost:5678 → tạo tài khoản owner (chỉ dùng local).
2. **Không cần tạo credential nào trong n8n** — khoá provider đã nằm ở
   `.env` (Bước 2), còn dữ liệu do service thực thi tự ghi vào MongoDB.
   (Các workflow cũ dùng Postgres đã được thay toàn bộ; nếu n8n của bạn
   còn import bản workflow cũ từ trước thì xoá đi và import lại bản mới.)
3. Import workflow: menu **Workflows → ⋯ → Import from File**, import lần
   lượt 6 file trong thư mục `n8n-ai-factory\workflows\`. Mở từng workflow,
   bấm **Save** rồi gạt **Active**.
   **Phải Active cả 6 workflow** — thiếu một cái là hệ thống gọi tới sẽ 404.

## Bước 5 — Chạy thử (ví dụ website bán giày sneaker)

1. Mở Dashboard http://localhost:8080.
2. Nhà cung cấp để mặc định **Groq** (model tự điền `openai/gpt-oss-120b` /
   `openai/gpt-oss-20b` — đúng dòng model MindFlow của bạn đang chạy tốt).
3. Chế độ **A — Full Website**, dán yêu cầu:

   > Xây dựng website bán giày sneaker bằng React + Vite + Tailwind CSS:
   > trang chủ (hero, sản phẩm nổi bật), trang danh sách sản phẩm có lọc
   > theo hãng và giá, trang chi tiết sản phẩm, giỏ hàng lưu localStorage,
   > trang thanh toán mô phỏng, trang liên hệ. Tối thiểu 12 sản phẩm.
   > Giao diện hiện đại, responsive.

4. Bấm **Bắt đầu chạy 10 Agent**. Dashboard tự cập nhật mỗi 5 giây: Agent
   nào đang chạy/xong/lỗi, tốn bao nhiêu token, QA đạt chưa. Một lượt chạy
   mất vài phút đến vài chục phút.
5. Xong sẽ có nút **Tải file ZIP**. Tải về, giải nén, chạy thử:
   ```powershell
   npm install
   npm run dev
   ```
   Trạng thái `COMPLETED_WITH_ISSUES` = hết 2 vòng sửa mà QA vẫn còn issue
   (danh sách issue hiện trên Dashboard) — không phải lỗi hệ thống.

Hoặc chạy bằng lệnh (webhook chỉ trả lời khi toàn bộ pipeline xong):

```powershell
curl -X POST http://localhost:5678/webhook/ai-factory/start -H "Content-Type: application/json" -d "{\"mode\":\"full\",\"requirement\":\"Xây dựng website bán giày sneaker...\"}"
```

## Bước 6 — Đổi provider / model / chế độ

- **Đổi provider**: ô "Nhà cung cấp AI" trên Dashboard (Groq / Ollama
  Cloud / OpenRouter) — model từng Agent tự đổi theo. Muốn đổi mặc định
  luôn: mở workflow **AI Factory — Agent Execution** → node **Resolve
  Agent Config**, sửa `DEFAULT_PROVIDER` và bảng `models` của từng Agent.
- **Chế độ B (Module)**: chọn ở Dashboard + điền tên module (ví dụ
  Authentication) — PM chỉ gọi các Agent cần cho module đó.
- **Chế độ C (Project có sẵn)**: chọn ở Dashboard + đính kèm file ZIP
  source — Agent phân tích cây file thật và chỉ sửa đúng file trong phạm
  vi yêu cầu.
- **Sửa .env xong** (thêm/đổi key) phải chạy lại `docker compose up -d`
  trong thư mục này để n8n nhận giá trị mới.


## Bước 7 — Workflow 7 Agent tự chọn model (Dynamic Model Routing)

Ngoài 6 workflow ở trên, thư mục `workflows\` còn có
**`07-seven-agent-dynamic-routing.json`**: đội đúng 7 role (Leader,
Planner, Architect, Developer, Tester, Reviewer, Researcher) xử lý đa
lĩnh vực — không chỉ code, còn nghiên cứu, marketing, giáo dục, báo cáo…
Điểm khác biệt: **không khoá cứng một model cho mọi role** — hệ thống tự
chọn model theo từng task.

Cách dùng:

1. Import thêm file `07-seven-agent-dynamic-routing.json` vào n8n (như
   Bước 4), bấm **Save** và gạt **Active**. Workflow này không cần
   credential nào cả — chỉ cần key provider trong file `.env`
   (`GROQ_API_KEY` / `OLLAMA_API_KEY` đã điền ở Bước 2 là chạy được ngay).
2. Gửi yêu cầu (PowerShell):

   ```powershell
   curl -X POST http://localhost:5678/webhook/ai-team/start -H "Content-Type: application/json" -d "{\"requirement\":\"Lập kế hoạch marketing 3 tháng cho ứng dụng học tiếng Anh trẻ em\",\"domain\":[\"marketing\"]}"
   ```

   Webhook trả lời khi cả đội chạy xong (vài phút). Kết quả JSON gồm:
   `plan` (từng task có `model_selection` ghi rõ provider/model/**lý do
   chọn**), `task_results`, `skipped_roles` (role không cần chạy, kèm lý
   do), `review` của Reviewer, `revision_rounds` (số vòng sửa, tối đa 2)
   và `final` — bản tổng hợp cuối của Leader.
3. Muốn xem hệ thống đã chọn model thế nào: mở execution trong n8n →
   node **Parse Plan + Model Router** để xem từng task được gán model
   nào; node **Model Capability Registry** cho thấy model nào đang
   `available` (chỉ model của provider có key trong `.env` mới available).

Provider/model **chạy ngay** với `.env` hiện tại của bạn: Groq
(`openai/gpt-oss-120b`, `openai/gpt-oss-20b`) và Ollama Cloud
(`gpt-oss:120b`, `gpt-oss:20b`, `qwen3-coder:480b`, `deepseek-v3.1:671b`).
**Cần cấu hình thêm** nếu muốn dùng: Claude / GPT-5 / DeepSeek-R1 qua
OpenRouter — thêm `OPENROUTER_API_KEY` vào `.env` rồi
`docker compose up -d` lại; trước đó các model này hiện `unavailable`
trong registry và router sẽ không bao giờ chọn chúng. Không có key nào
nằm trong file JSON workflow.

Lưu ý: chạy **một lượt tại một thời điểm** cho workflow này (trạng thái
lượt chạy lưu trong static data của workflow); task chạy tuần tự theo
thứ tự phụ thuộc.

## Bước 8 — Chạy đội Agent ngay trong MindFlow (trang AI Factory)

Sau khi đã import bản mới nhất của workflow 07 và bấm Publish/Active:

1. Mở MindFlow → mục **Agents → AI Factory** (đường dẫn `/agents/factory`).
2. Trang này tự liệt kê các Agent bạn **đã tạo trong MindFlow** và tự gán
   vào đúng vai trò theo tên (AI Leader → vai trò Leader, AI Developer →
   Developer…). Bạn đổi Agent cho từng vai trò tuỳ ý, hoặc để trống một
   vai trò để n8n tự chọn model từ registry của nó.
3. Nhập yêu cầu → bấm **Chạy đội Agent qua n8n**. MindFlow gửi yêu cầu
   kèm provider/model/system prompt của từng Agent đã gán sang webhook
   của workflow 07; kết quả (kế hoạch, từng nhiệm vụ, đánh giá Reviewer,
   bản tổng hợp cuối) hiện ngay trên trang. Một lượt chạy mất vài phút.

Điều kiện: n8n đang chạy (`docker compose up -d`) và backend MindFlow với
tới được n8n ở `http://localhost:5678` (mặc định; đổi bằng biến môi trường
`N8N_WEBHOOK_BASE_URL` trong `backend/.env` nếu bạn chạy n8n ở nơi khác).
Provider của Agent được gán cũng phải có key trong `.env` của n8n — nếu
chưa có, trang kết quả sẽ ghi rõ vai trò đó bị bỏ qua vì
`provider_not_configured_in_n8n_env`.

## Lỗi thường gặp

| Hiện tượng | Nguyên nhân & cách xử lý |
|---|---|
| Agent báo `missing_env_key` | `.env` chưa có key của provider đang chọn, hoặc chưa `docker compose up -d` lại sau khi sửa `.env` |
| Webhook 404 | Chưa Active đủ 6 workflow, hoặc gọi sai path |
| Dashboard báo `database_unavailable` / workflow lỗi ở node `(CES)` | Chưa điền `MONGODB_URI` trong `.env`, mật khẩu trong URI sai, hoặc Atlas chưa cho IP máy bạn vào (Atlas → Network Access). Xem thêm `docker compose logs code-exec-service` |
| Bước build báo `HOST_WORKSPACES_DIR is not configured` | Chưa điền biến này ở Bước 2, hoặc đường dẫn sai |
| Agent báo `model_did_not_return_valid_json` | Model đó không tuân thủ JSON — đổi model cho Agent đó trên Dashboard/node Resolve Agent Config. Lượt lỗi vẫn lưu trong collection `agent_runs` (MongoDB) để xem lại |
| Chạy lâu bất thường | Xem n8n → Executions để biết đang kẹt ở node nào; xem Dashboard hoặc collection `agent_runs` trong MongoDB để biết Agent nào đang chạy |
| Trang AI Factory (MindFlow) báo không kết nối được n8n | n8n chưa chạy (`docker compose up -d`), workflow 07 chưa Publish/Active, hoặc backend MindFlow không tới được `localhost:5678` (kiểm tra `N8N_WEBHOOK_BASE_URL` trong `backend/.env`) |

Chi tiết kiến trúc, API của Code Execution Service và các giới hạn an
toàn: xem **README.md** trong thư mục này.
