# AI Collaboration Room — Báo cáo triển khai

Báo cáo cho bản nâng cấp **Phòng hợp tác** (`/collab`) theo đặc tả
`MindFlow-AI-Collaboration-Room-Update.md`. Triển khai qua 4 PR xếp
chồng, merge theo thứ tự: **#67 → #68 → #69 → #70**.

## 1. Tóm tắt thay đổi

| Đợt | PR | Nội dung |
| --- | --- | --- |
| 1 | #67 | Context Builder: Agent được nhắc sau đọc được kết quả Agent trước; `sequence`, reply link, `context_message_ids`; ngân sách token của phòng |
| 2 | #68 | Runs & tasks (`collab_runs`, `collab_tasks`), chế độ Tự động có điều phối + loop guard, Moderator tổng hợp, cancel/retry, cài đặt phòng |
| 3 | #69 | Artifacts (`collab_artifacts`): xuất FINAL-REPORT.md, transcript, results.json, gói ZIP có manifest + checksum, tải có kiểm quyền |
| 4 | #70 | Giao diện `/collab`: cài đặt phòng, reply/phản biện, panel lượt chạy, panel file kết quả |

## 2. Nguyên nhân gốc của lỗi cũ (có bằng chứng trong code)

1. **Agent không thấy kết quả của Agent khác**: `post_message` cũ đóng
   băng transcript **một lần trước vòng lặp mention** và dùng chung cho
   mọi Agent. Trong cùng một post nhắc nhiều Agent, Agent thứ hai không
   bao giờ nhận được câu trả lời Agent thứ nhất vừa lưu vào DB.
2. **Cắt transcript sai đầu**: `"\n".join(lines)[:12000]` giữ phần CŨ
   nhất và cắt mất kết quả MỚI nhất khi phòng dài.
3. **Ngân sách token**: lượt chạy dùng mặc định 8000 byte của Agent
   Studio trong khi transcript cho phép tới 12.000 ký tự (tiếng Việt
   ≈ 30 KB UTF-8) → phòng hơi dài là mọi lượt gọi chết
   `agent_budget_exceeded`.
4. Không có sequence/reply/context tracking nên không truy vết được
   Agent đã nhận dữ liệu nào.

Cách khắc phục (đợt 1): context được **truy vấn lại từ DB ngay trước
từng Agent**, gắn nhãn `[#sequence] Tên (provider/model)`, cắt giữ
phần mới nhất, mỗi câu trả lời lưu `context_message_ids` +
`reply_to_message_id` + provider/model tại thời điểm trả lời; ngân
sách phòng `COLLAB_TOKEN_BUDGET = 32768` (bằng Discussion).

## 3. Kiến trúc trước và sau

Trước: `multi_chats` + `collab_messages`, mention → chạy Agent bằng
transcript đóng băng, không run/task/artifact, lỗi chỉ là một mã code
trên tin nhắn rỗng.

Sau: thêm `collab_runs` (mode, trạng thái, turn_count, token, lý do
dừng, final_message_id) và `collab_tasks` (agent, assigned_by, trạng
thái, attempt, output_message_id); Orchestrator trong
`CollabService._auto_discussion` chọn Agent bằng router từ khoá vai
trò xác định, dừng theo: Agent kết luận (`[KẾT LUẬN]`), trùng nội
dung, hết lượt, người dùng hủy, hết Agent phù hợp; Moderator tổng hợp
4 phần (xác nhận / đề xuất / bất đồng / rủi ro cần quyết).
`collab_artifacts` lưu file kết quả kèm SHA-256.

## 4. Luồng Agent-to-Agent đã xác minh ra sao

Test `test_second_mentioned_agent_sees_first_reply` (kịch bản
**ARCH-RESULT-739** của đặc tả): một post nhắc Agent A (model-a) rồi
Agent B (model-b). Mock provider cho A trả "Kiến trúc đề xuất:
ARCH-RESULT-739". Test khẳng định: prompt gửi cho B **chứa chuỗi
ARCH-RESULT-739**, `context_message_ids` của tin B chứa id tin của A,
và B trả lời dựa trên chuỗi đó. Test run tự động khẳng định Reviewer
đọc được nội dung Architect và Moderator tổng hợp ở cuối.

## 5. Kiểm thử

Backend: `tests/test_collab.py` — 8 test cũ giữ nguyên, thêm 9 test:
ARCH-RESULT-739, reply-to, ngân sách transcript dài, run/task của
lượt directed, run tự động + Moderator, retry task lỗi, summarize,
export + ZIP manifest/checksum, cách ly artifact theo chủ sở hữu.
Chạy: `python -m pytest -q tests/test_collab.py` +
`python -m ruff check app tests` (trên máy dev, theo quy trình repo).
Frontend: `npm run build`.

## 6. Provider — trạng thái thật

Gateway hiện có (registry + adapter + connection test + key mã hoá
theo user) được tái sử dụng nguyên trạng: OpenAI, Gemini, Groq,
Ollama đang hoạt động. **Anthropic, DeepSeek và Custom API vẫn ở trạng
thái `implemented=False` trong registry** — chưa có adapter, không
tuyên bố đã tích hợp; đây là phần còn lại của Phase 1 trong đặc tả,
làm thành đợt riêng khi cần. Lỗi `PROVIDER_REQUEST_REJECTED` phía
Ollama: mã lỗi nay được hiện rõ trên từng tin kèm nội dung trả dở và
nút chạy lại, nhưng **nguyên nhân gốc phía Ollama chưa kết luận được**
(backend không nhận được lý do từ upstream; cần một lệnh curl bằng
key thật ở máy dev để đọc JSON lỗi — xem ghi chú trong PR #53/#64).

## 7. Hạn chế còn lại

- Chạy đồng bộ trong request (như phần còn lại của hệ thống), chưa
  có SSE streaming cho phòng; cancel chỉ có hiệu lực giữa các lượt
  của run tự động.
- Router chế độ Tự động là từ khoá xác định theo tên Agent, chưa
  phải LLM-planner.
- Artifact lưu trong MongoDB (text/base64) — phù hợp gói phòng chat;
  phòng rất lớn nên chuyển object storage ở đợt sau.
- Xuất PDF/DOCX/XLSX chưa làm; hiện có .md/.json/.zip theo đặc tả
  tối thiểu.

## 8. Cấu hình và chạy

Không cần biến môi trường mới. API key provider vẫn nhập ở trang
Providers (mã hoá theo user). Sau khi merge đủ 4 PR: restart backend
(index mới tự tạo lúc khởi động), `npm run build` cho frontend. Thứ
tự merge bắt buộc: #67 → #68 → #69 → #70 (mỗi PR merge xong, đổi base
PR kế tiếp về `main`).
