# MindFlow: Tính năng Phân tích dự án và Đề xuất đội ngũ (Người + AI)

## 1. Câu hỏi ban đầu

Có thể để AI phân tích một dự án, rồi đề xuất nhân viên và AI phù hợp để thực hiện không? Nếu chọn người thì add người, nếu chọn AI thì add AI.

**Kết luận: Có, làm được, và nên làm.** Tính năng này có giá trị doanh nghiệp hơn việc chỉ xây nhiều AI agent nói chuyện với nhau, và có thể phát triển thành sản phẩm thực tế, không chỉ là demo cho phỏng vấn.

Ý tưởng cốt lõi: một dự án có thể được thực hiện bởi nhân viên, AI, hoặc kết hợp cả hai. Người và AI đều được coi là "nguồn lực" (resource) trong cùng một hệ thống.

---

## 2. Luồng hoạt động đề xuất

Ví dụ dự án: *Xây dựng website thương mại điện tử bằng Next.js, có quản lý sản phẩm, thanh toán, đơn hàng và dashboard quản trị.*

| Bước | Tên | Mô tả |
|------|-----|-------|
| 1 | Project Analysis AI | Phân tích tài liệu, yêu cầu, công nghệ, độ phức tạp, deadline, rủi ro |
| 2 | Team Recommendation AI | Phân tích danh sách nhân viên và AI hiện có để tìm nguồn lực phù hợp cho từng công việc |
| 3 | Resource Allocation | Quản lý chọn nhân viên hoặc AI cho từng nhiệm vụ |
| 4 | Human Approval | Quản lý duyệt đội ngũ và bắt đầu dự án |

**Ví dụ đề xuất phân công (dữ liệu minh họa):**

| Công việc | Người | AI |
|-----------|-------|----|
| Frontend Development | Nguyễn Văn A (React, Next.js, 4 năm kinh nghiệm) | Claude Code (coding, refactoring, component) |
| Backend Development | Trần Văn B (Node.js, PostgreSQL, API) | Codex (code generation, debugging) |
| QA & Testing | Lê Văn C (QA, test case, regression) | Playwright Agent (UI automation, E2E) |

Một nhiệm vụ có thể giao cho: một nhân viên, một AI agent, nhân viên + AI phối hợp, hoặc nhiều AI agent chuyên môn khác nhau. Không nhất thiết mỗi task phải có cả người và AI.

---

## 3. Màn hình Workforce Management

Một màn hình riêng với hai tab: **Nhân viên** và **AI Agents**.

**Khi thêm nhân viên, lưu hồ sơ năng lực:**

- Kỹ năng, công nghệ
- Kinh nghiệm thực tế
- Vai trò chuyên môn
- Số giờ có thể làm việc
- Dự án đang tham gia
- Mức độ sẵn sàng

**Khi thêm AI, lưu:**

- Nhà cung cấp và model
- Chuyên môn hoặc vai trò
- Tools và quyền được phép sử dụng
- Chi phí, giới hạn token
- Khả năng xử lý tác vụ
- Trạng thái kết nối và hiệu suất đánh giá

> **Lưu ý:** Claude Code, Codex hay OpenCode không chỉ là model. Chúng có thể là runtime/coding agent riêng. MindFlow cần tích hợp runtime hoặc API tương ứng, không phải chỉ thêm tên AI vào danh sách.

---

## 4. Điều làm tính năng thực sự thông minh

Không để AI chỉ dựa vào tên kỹ năng để chọn người. Ví dụ hai nhân viên đều biết React, nhưng:

- Nhân viên A đang có 3 dự án.
- Nhân viên B đang rảnh và đã làm dự án tương tự.
- AI Agent C tạo component nhanh nhưng không được phép truy cập dữ liệu thanh toán.

MindFlow phải đánh giá đồng thời:

1. Năng lực chuyên môn
2. Kinh nghiệm thực tế
3. Khối lượng công việc hiện tại
4. Thời gian có thể hoàn thành
5. Chi phí
6. Quyền truy cập và mức độ rủi ro
7. Lịch sử chất lượng công việc

Sau đó AI đưa ra phương án phân công kèm giải thích lý do. Quản lý có quyền thay đổi trước khi xác nhận.

---

## 5. Lộ trình triển khai (từ tài liệu gốc)

| Giai đoạn | Chức năng |
|-----------|-----------|
| 1 | Workforce: Add Employee / Add AI |
| 2 | Skill & Capability Profile |
| 3 | Project Analysis AI |
| 4 | Team Recommendation AI |
| 5 | Task Allocation & Approval |
| 6 | Theo dõi hiệu suất người và AI |

**Tóm lược giá trị cốt lõi:** AI hiểu dự án → hiểu năng lực nguồn lực → đề xuất đội ngũ phù hợp → con người phê duyệt → người và AI cùng thực hiện → hệ thống đo lường kết quả.

---

## 6. Đề xuất bổ sung để triển khai thực tế

1. **Một model dữ liệu chung cho người và AI.** Bảng `Resource` có `type` (human hoặc ai), các trường chung (kỹ năng, mức sẵn sàng, chi phí) và trường riêng (số giờ làm việc cho người; giới hạn token, quyền tool cho AI). Thuật toán đề xuất chạy trên một danh sách duy nhất; "add người" và "add AI" chỉ là hai form nhập khác nhau.
2. **Tách chấm điểm khỏi giải thích.** Tính điểm phù hợp bằng quy tắc hoặc công thức có trọng số (kỹ năng, tải việc, chi phí, rủi ro), để LLM chỉ giải thích lý do. Dễ kiểm soát và debug hơn.
3. **Ràng buộc cứng cho AI.** AI không được chạm dữ liệu thanh toán thì phải bị loại khỏi task đó, không chỉ bị trừ điểm.
4. **Lưu lịch sử kết quả từng task** (đạt hay không, thời gian, số lần sửa) để các lần đề xuất sau chính xác hơn.
5. **Tích hợp runtime là phần khó nhất.** Với bản demo, bắt đầu bằng AI agent giả lập hoặc gọi API model, sau đó mới tích hợp coding agent thật.

**Thứ tự MVP gợi ý:** Workforce (add người/AI) → hồ sơ năng lực → phân tích dự án thành task → đề xuất phân công kèm lý do → duyệt và giao. Theo dõi hiệu suất để sau.

---

## 7. Đánh giá khả thi với website hiện tại

**Trang:** `https://ai-knowledge-hub-intelligent-document-cmfu.onrender.com/agents/workflows`

**Giới hạn của lần kiểm tra:** Trang là ứng dụng render phía trình duyệt và yêu cầu đăng nhập. Công cụ đọc web chỉ thấy dòng "Đang kiểm tra phiên đăng nhập…", không đăng nhập được, nên **chưa xem được giao diện, dữ liệu hay code thật**.

**Những gì thấy được từ phần công khai:**

- Ứng dụng tên MindFlow AI, mô tả là không gian AI cá nhân để kết nối provider, model và tri thức.
- Có route `/agents/workflows`, cho thấy đã có khái niệm agent và workflow.
- Đang chạy trên Render.

**Nhận định (có điều kiện):** Nếu phần provider, model, agent và workflow đã chạy được, tính năng Workforce là khả thi và nên xây tiếp trên nền hiện có, không cần làm lại.

**Có thể tái sử dụng:**

- Phần kết nối provider/model → trở thành "AI resource" trong Workforce.
- Phần agent/workflow → nơi thực thi task sau khi quản lý duyệt.

**Cần xây mới:**

1. Bảng nguồn lực dùng chung cho người và AI, kèm hồ sơ năng lực.
2. Bước phân tích dự án thành task (gọi LLM, trả về JSON có cấu trúc).
3. Bước chấm điểm và đề xuất phân công kèm lý do.
4. Màn hình duyệt và chỉnh sửa trước khi giao.

**Lưu ý hạ tầng:** Nếu dùng gói miễn phí của Render, service sẽ ngủ sau thời gian không dùng, lần mở đầu sẽ chậm, ảnh hưởng độ mượt khi demo hoặc phỏng vấn.

**Bảo mật:** Không chia sẻ mật khẩu trong chat. Nên đổi mật khẩu tài khoản đã gửi và dùng tài khoản demo riêng khi cần chia sẻ.

---

## 9. Lưu dữ liệu bằng MongoDB

Giữ nguyên ngôn ngữ và stack đang dùng, chỉ thêm các collection sau:

| Collection | Vai trò |
|------------|---------|
| `resources` | Nhân viên và AI chung một collection, phân biệt bằng `type` (`human` / `ai`) |
| `projects` | Thông tin dự án và trạng thái duyệt |
| `project_analyses` | Kết quả AI phân tích dự án (danh sách task, nhúng trong document) |
| `allocations` | Phương án phân công đề xuất, chỉnh sửa, duyệt (kèm `score`, `reason`) |
| `task_results` | Lịch sử kết quả từng task, dùng cho theo dõi hiệu suất |
| `agent_events` | Biên nhận các sự kiện agent mà n8n đã nhận (mục 11) |

**Ví dụ `resources` (AI):**

```json
{
  "type": "ai",
  "name": "Claude Code",
  "role": "Coding Agent",
  "skills": [{ "name": "Refactoring", "level": 4 }],
  "availability": { "status": "connected" },
  "costPerHour": 2,
  "ai": {
    "provider": "anthropic",
    "model": "...",
    "runtime": "coding-agent",
    "allowedTools": ["fs", "git"],
    "deniedScopes": ["payment-data"],
    "tokenLimitPerTask": 200000
  }
}
```

**Index nên tạo:**

- `resources`: `{ type: 1, "availability.status": 1 }`, `{ "skills.name": 1 }`
- `allocations`: `{ projectId: 1, status: 1 }`
- `task_results`: `{ resourceId: 1, completedAt: -1 }`

**Lưu ý:** validate JSON do LLM trả trước khi ghi; kiểm tra ràng buộc cứng (`deniedScopes`) trong code; không lưu API key thô trong `resources`.

---

## 10. Vai trò của n8n

**Nên giao cho n8n:** nhận webhook, gọi LLM phân tích dự án, chạy task cho AI agent sau khi duyệt, kết nối công cụ ngoài (GitHub, email), gửi thông báo.

**Nên giữ trong backend MindFlow:** chấm điểm và đề xuất phân công, ràng buộc cứng/phân quyền, giao diện duyệt, dữ liệu gốc trong Mongo.

```
MindFlow UI -> MindFlow Backend (Mongo, chấm điểm, phân quyền)
                    | webhook
                    v
                  n8n -> LLM / agent / công cụ ngoài
                    | callback
                    v
             MindFlow Backend (ghi task_results)
```

**Cần lưu ý:** giấy phép n8n (Sustainable Use License) nếu bán thương mại; chạy coding agent thật cần môi trường riêng; Render gói miễn phí sẽ ngủ nên webhook có thể chậm hoặc timeout.

---

## 11. Thêm agent ở trang `/agents` và xác nhận n8n nhận đúng

File workflow đi kèm: `n8n-agent-created-workflow.json`.

### 11.1 Hợp đồng gửi nhận

Khi người dùng bấm thêm agent, backend MindFlow gửi:

- **Method:** `POST`
- **URL:** Production URL của webhook, dạng `https://<n8n-host>/webhook/mindflow-agent-created`
- **Header:** `x-mindflow-secret: <chuỗi bí mật>` (tên header phải trùng với credential Header Auth trong n8n)
- **Body:**

```json
{
  "event": "agent.created",
  "sentAt": "2026-11-24T10:00:00.000Z",
  "agent": {
    "id": "665f1c...",
    "name": "Claude Code",
    "type": "ai",
    "provider": "anthropic",
    "model": "...",
    "role": "Coding Agent",
    "skills": [{ "name": "Refactoring", "level": 4 }],
    "allowedTools": ["fs", "git"],
    "deniedScopes": ["payment-data"],
    "tokenLimitPerTask": 200000,
    "status": "connected"
  }
}
```

Không gửi API key của provider trong body. Workflow cũng bỏ qua các trường nhạy cảm nếu backend gửi nhầm.

### 11.2 Workflow làm gì

1. **Webhook** nhận POST, kiểm tra header bí mật (sai thì n8n tự từ chối 403).
2. **Validate & Normalize** kiểm tra `event`, `agent.id`, `name`, `provider`, `model`; chuẩn hóa dữ liệu, gắn `receivedAt` và `executionId`.
3. **Is Valid?** đúng thì ghi biên nhận vào collection `agent_events`, rồi trả **200**; sai thì trả **400** kèm danh sách lỗi.
4. Nếu có lỗi hệ thống (ví dụ Mongo mất kết nối), n8n trả **5xx** để backend biết mà thử lại.

Phản hồi thành công:

```json
{
  "received": true,
  "agentId": "665f1c...",
  "event": "agent.created",
  "executionId": "1234",
  "receivedAt": "2026-11-24T10:00:01.000Z"
}
```

### 11.3 Cách backend biết n8n nhận đúng

Backend chỉ coi là thành công khi **cả hai** điều kiện đúng: HTTP 200 và `received === true` và `agentId` trong phản hồi trùng agent vừa gửi. Sau đó lưu trạng thái đồng bộ ngay trên document agent:

```json
"n8nSync": {
  "status": "synced",
  "lastAttemptAt": "Date",
  "executionId": "1234",
  "error": null
}
```

`status` có thể là `pending`, `synced`, `failed`. Nên đặt timeout ngắn (vài giây) và thử lại tối đa 2-3 lần. Dùng `agent.id` làm khóa chống trùng để gửi lại không tạo bản ghi lệch ý nghĩa.

### 11.4 Cách kiểm thử

1. Trong n8n, import file `n8n-agent-created-workflow.json`.
2. Mở node Webhook, tạo credential **Header Auth** (tên header `x-mindflow-secret`, giá trị là chuỗi bí mật). Chọn credential MongoDB cho node `Save Receipt to MongoDB`.
3. Bấm **Listen for test event**, rồi gọi **Test URL** (`/webhook-test/mindflow-agent-created`):

```bash
curl -i -X POST "https://<n8n-host>/webhook-test/mindflow-agent-created" \
  -H "Content-Type: application/json" \
  -H "x-mindflow-secret: <chuỗi bí mật>" \
  -d '{"event":"agent.created","sentAt":"2026-11-24T10:00:00.000Z","agent":{"id":"test-1","name":"Test Agent","provider":"anthropic","model":"test","role":"Coding Agent"}}'
```

4. Kết quả mong đợi: 200 và JSON có `received: true`; node hiện dữ liệu trong n8n; collection `agent_events` có thêm một document.
5. Thử gọi thiếu `agent.name` thì phải ra 400; gọi sai header bí mật thì phải ra 403.
6. Khi đạt, bấm **Activate** workflow và đổi sang **Production URL** (`/webhook/...`) trong cấu hình backend. Test URL chỉ hoạt động khi đang bấm Listen.
7. Thêm một agent thật ở trang `/agents`, kiểm tra tab **Executions** trong n8n và trường `n8nSync` trong Mongo.

### 11.5 Lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp |
|-------------|------------------------|
| 404 | Workflow chưa Activate nhưng gọi Production URL, hoặc dùng Test URL khi chưa Listen |
| 403 | Sai tên hoặc giá trị header bí mật |
| 400 | Thiếu trường bắt buộc trong `agent` |
| Timeout | n8n hoặc backend trên Render đang ngủ; tăng timeout, thử lại |
| URL webhook sai host | Tự host n8n sau proxy mà chưa đặt biến môi trường `WEBHOOK_URL` |
| Không có dữ liệu trong Mongo | Credential MongoDB chưa chọn, hoặc sai tên database |

### 11.6 Việc còn mở

- Chưa xem được code trang `/agents` (cần đăng nhập), nên phần gọi webhook phía backend chưa viết. Cần biết ngôn ngữ và framework backend đang dùng.
- File workflow chưa được import thử trực tiếp trên n8n của bạn. Nếu import báo lỗi ở node nào (nhất là node MongoDB, vì tên tham số có thể khác giữa các phiên bản n8n), hãy gửi lại thông báo lỗi để chỉnh.
