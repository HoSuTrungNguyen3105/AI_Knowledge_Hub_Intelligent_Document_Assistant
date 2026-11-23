# HƯỚNG DẪN DÙNG — n8n AI Agent Factory (bản tích hợp trong repo MindFlow)

Thư mục `n8n-ai-factory/` này là hệ thống 10 AI Agent chạy bằng n8n, nằm
**độc lập** với backend/frontend MindFlow: nó có Docker Compose, database
PostgreSQL và service thực thi riêng. MindFlow không bị ảnh hưởng gì khi
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

1. `POSTGRES_PASSWORD`: đặt một mật khẩu tuỳ ý.
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

Lần đầu build vài phút. Đạt khi `postgres` healthy, `n8n` và
`code-exec-service` đều Up. Kiểm tra nhanh: mở http://localhost:8080/health
thấy `{"status":"ok"...}` là service thực thi đã sống.

## Bước 4 — Thiết lập n8n (làm 1 lần)

1. Mở http://localhost:5678 → tạo tài khoản owner (chỉ dùng local).
2. Tạo credential **Postgres**: menu **Credentials → New → Postgres**, đặt
   tên đúng **`AI Factory Postgres`**, Host `postgres`, Port `5432`,
   Database `ai_factory`, User `aifactory`, Password = mật khẩu bạn đặt ở
   Bước 2. (Không cần tạo credential cho Groq/Ollama nữa — key đã nằm ở
   `.env`.)
3. Import workflow: menu **Workflows → ⋯ → Import from File**, import lần
   lượt 6 file trong thư mục `n8n-ai-factory\workflows\`. Mở từng workflow,
   kiểm tra các node Postgres đã gắn credential `AI Factory Postgres`
   (chưa gắn thì chọn lại theo tên), bấm **Save** rồi gạt **Active**.
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

## Lỗi thường gặp

| Hiện tượng | Nguyên nhân & cách xử lý |
|---|---|
| Agent báo `missing_env_key` | `.env` chưa có key của provider đang chọn, hoặc chưa `docker compose up -d` lại sau khi sửa `.env` |
| Webhook 404 | Chưa Active đủ 6 workflow, hoặc gọi sai path |
| Node Postgres báo credential lỗi | Tên credential phải đúng `AI Factory Postgres`; chọn lại trong node rồi Save |
| Bước build báo `HOST_WORKSPACES_DIR is not configured` | Chưa điền biến này ở Bước 2, hoặc đường dẫn sai |
| Agent báo `model_did_not_return_valid_json` | Model đó không tuân thủ JSON — đổi model cho Agent đó trên Dashboard/node Resolve Agent Config. Lượt lỗi vẫn lưu trong bảng `agent_runs` để xem lại |
| Chạy lâu bất thường | Xem n8n → Executions để biết đang kẹt ở node nào; xem Dashboard/`agent_runs` để biết Agent nào đang chạy |

Chi tiết kiến trúc, API của Code Execution Service và các giới hạn an
toàn: xem **README.md** trong thư mục này.
