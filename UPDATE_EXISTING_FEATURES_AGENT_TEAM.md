# TASK: NÂNG CẤP PHÂN CÔNG VAI TRÒ AGENT TEAM VÀ ĐỒNG BỘ VỚI COLLAB

## 1. MỤC TIÊU

Tôi muốn nâng cấp chức năng Agent Teams và Collaboration trong MindFlow AI.

Hai khu vực cần cập nhật:

- `/agents/teams`
- `/collab`

API hiện tại:

`/api/v1/ai/agent-teams`

Hiện trạng:
- `/agents/teams` đã có chức năng tạo và quản lý Team.
- Có thể đặt tên cho các Agent.
- Tuy nhiên, chưa có cơ chế phân công vai trò và nhiệm vụ thực sự cho từng Model.
- `/collab` chưa nhận được cấu hình phân công để biết Model nào phải đảm nhiệm công việc nào.

**Mục tiêu:** Khi tôi gán một Model vào một vai trò tại `/agents/teams`, trang `/collab` phải tự động nhận đúng cấu hình đó và sử dụng đúng Model để thực hiện đúng nhiệm vụ.

Không hardcode Model hoặc Provider.

---

## 2. NÂNG CẤP /AGENTS/TEAMS

Đây là nơi quản lý cấu hình và phân công vai trò.

### 2.1. Cấu hình từng Agent

Mỗi Agent trong Team cần có:

- Agent Name.
- Provider.
- Model.
- Role.
- Description.
- Responsibility.
- System Prompt.
- Instructions.
- Priority.
- Execution Order.
- Status.

Các trường phải được lưu vào Backend, không chỉ lưu tạm ở frontend.

### 2.2. Phân công vai trò

Tạo danh sách vai trò có thể lựa chọn:

- Leader: Điều phối và quản lý công việc.
- Planner: Phân tích yêu cầu và lập kế hoạch.
- Researcher: Nghiên cứu và thu thập thông tin.
- Architect: Thiết kế kiến trúc.
- Developer: Phát triển và viết code.
- Reviewer: Đánh giá và kiểm tra kết quả.
- Tester: Kiểm thử và tìm lỗi.
- Designer: Thiết kế giao diện.
- Custom Role: Vai trò do người dùng tự tạo.

Đây là các vai trò gợi ý, không phải các vai trò bắt buộc.

Người dùng có thể tự tạo vai trò riêng.

### 2.3. Chọn Model cho vai trò

Ví dụ một Team:

| Model | Role | Responsibility |
|---|---|---|
| Model A | Leader | Điều phối toàn bộ công việc |
| Model B | Developer | Viết và chỉnh sửa code |
| Model C | Reviewer | Review code |
| Model D | Tester | Kiểm thử |

Đây chỉ là dữ liệu ví dụ.

Người dùng phải tự chọn Provider và Model từ danh sách đã kết nối trong MindFlow.

Không mặc định GPT, Claude hay Gemini cho bất kỳ vai trò nào.

### 2.4. Cấu hình nâng cao

Cho phép người dùng:

- Thêm Agent.
- Xóa Agent.
- Đổi vai trò.
- Đổi Model.
- Đổi System Prompt.
- Thay đổi thứ tự thực thi.
- Thiết lập nhiệm vụ.
- Bật hoặc tắt Agent.
- Lưu cấu hình Team.

Có thể cho phép nhiều Agent cùng đảm nhiệm một vai trò nếu kiến trúc hỗ trợ.

Cần kiểm tra điều kiện Team có Leader trước khi chạy Collaboration. Nếu thiếu vai trò điều phối, thông báo cho người dùng thay vì tự ý gán Model.

---

## 3. NÂNG CẤP API AGENT TEAMS

API hiện tại:

`/api/v1/ai/agent-teams`

Hãy kiểm tra toàn bộ API, Schema và Database hiện có.

Nâng cấp API để lưu đầy đủ thông tin phân công.

Thông tin cần quản lý:

### Team

- id
- name
- description
- status
- agents
- created_at
- updated_at

### Agent

- id
- name
- provider_id
- model_id
- role
- description
- responsibility
- system_prompt
- instructions
- priority
- execution_order
- enabled

Đây là cấu trúc dữ liệu định hướng. Phải điều chỉnh theo Schema thực tế, không tạo trùng trường hoặc phá vỡ dữ liệu cũ.

### Yêu cầu API

- Lấy danh sách Team.
- Lấy chi tiết Team.
- Tạo Team.
- Cập nhật Team.
- Xóa Team.
- Thêm Agent vào Team.
- Cập nhật cấu hình Agent.
- Xóa Agent khỏi Team.
- Lưu vai trò và Model.
- Lấy cấu hình đầy đủ để Collaboration sử dụng.

Nếu API hiện tại đã có endpoint tương ứng thì mở rộng endpoint đó, không tạo trùng.

Đảm bảo dữ liệu sau khi lưu có thể truy xuất lại chính xác.

---

## 4. ĐỒNG BỘ VỚI /COLLAB

Đây là phần quan trọng nhất.

Khi người dùng mở `/collab` và chọn một Agent Team:

1. Frontend gọi API lấy cấu hình Team.
2. Backend trả về danh sách Agent.
3. Hệ thống đọc Provider và Model của từng Agent.
4. Hệ thống đọc vai trò và nhiệm vụ của từng Agent.
5. Orchestrator sử dụng cấu hình này để điều phối.
6. Mỗi nhiệm vụ được gửi đến đúng Agent.
7. Agent sử dụng đúng Model đã cấu hình.

**Không được tự chọn Model khác hoặc tự phân công lại vai trò nếu người dùng đã cấu hình.**

### Ví dụ thực tế

Tôi cấu hình tại `/agents/teams`:

- Model A = Leader.
- Model B = Developer.
- Model C = Reviewer.
- Model D = Tester.

Sau đó vào `/collab` và nhập:

"Hãy tạo một website quản lý bán hàng bằng React."

Luồng thực hiện phải là:

**Bước 1 – Leader**

Model A:
- Nhận yêu cầu.
- Phân tích mục tiêu.
- Chia nhỏ công việc.
- Giao nhiệm vụ cho các Agent.

**Bước 2 – Developer**

Model B:
- Nhận nhiệm vụ được giao.
- Phân tích yêu cầu kỹ thuật.
- Viết code.
- Báo cáo kết quả.

**Bước 3 – Reviewer**

Model C:
- Nhận kết quả từ Developer.
- Kiểm tra code.
- Tìm lỗi.
- Đưa ra đề xuất.
- Yêu cầu chỉnh sửa nếu cần.

**Bước 4 – Tester**

Model D:
- Nhận kết quả cần kiểm thử.
- Thực hiện hoặc đề xuất kiểm thử theo công cụ được cấp.
- Báo cáo lỗi.
- Trả kết quả cho Leader.

**Bước 5 – Leader**

Model A:
- Tổng hợp kết quả.
- Kiểm tra các nhiệm vụ đã hoàn thành.
- Báo cáo kết quả cuối cùng.

Đây là ví dụ minh họa. Luồng thực tế phải căn cứ vào vai trò và System Prompt do người dùng cấu hình.

---

## 5. ORCHESTRATOR – CƠ CHẾ ĐIỀU PHỐI

Cần có cơ chế điều phối trung tâm.

Orchestrator phải:

- Đọc cấu hình Agent Team.
- Xác định Agent chịu trách nhiệm từng nhiệm vụ.
- Gọi đúng Provider và Model.
- Truyền ngữ cảnh cần thiết.
- Nhận kết quả.
- Chuyển kết quả đến Agent tiếp theo.
- Theo dõi trạng thái.
- Xử lý lỗi.
- Tổng hợp kết quả.

Không để frontend tự quyết định Agent nào được gọi.

Backend phải là nơi thực hiện việc điều phối thực tế.

### Execution Rules

- Tôn trọng Role đã cấu hình.
- Tôn trọng Execution Order nếu được thiết lập.
- Cho phép Leader phân công Task.
- Cho phép các Agent trao đổi với nhau.
- Có thể thực hiện các Task độc lập song song nếu phù hợp.
- Có thể chuyển sang bước Review hoặc Testing.
- Có cơ chế Retry khi API lỗi.
- Có giới hạn Token và số lượt thực thi.
- Có điều kiện kết thúc phiên làm việc.

Không để các Agent trao đổi vô hạn.

---

## 6. COLLABORATION UI

Tại `/collab`, bổ sung:

### Agent Team Selector

Cho phép chọn Team đã tạo tại `/agents/teams`.

Khi chọn Team, hiển thị:

- Tên Team.
- Các Agent.
- Vai trò.
- Provider.
- Model.
- Trạng thái.

Không tạo lại cấu hình Team tại `/collab`.

Nếu muốn thay đổi phân công, điều hướng người dùng đến `/agents/teams`.

### Agent Activity

Hiển thị hoạt động thực tế:

- Agent nào đang hoạt động.
- Agent nào đang nhận nhiệm vụ.
- Agent nào đang suy nghĩ hoặc xử lý.
- Agent nào đã hoàn thành.
- Agent nào gặp lỗi.
- Agent nào đang chờ Agent khác.

### Conversation

Mỗi tin nhắn cần hiển thị:

- Tên Agent.
- Role.
- Model.
- Nội dung.
- Thời gian.
- Task liên quan.

### Task Progress

Hiển thị:

- Task.
- Agent phụ trách.
- Trạng thái.
- Kết quả.
- Tiến độ.

---

## 7. LƯU LỊCH SỬ VÀ KHÔI PHỤC

Mỗi Collaboration Session cần lưu:

- Team ID.
- Team Configuration Snapshot.
- Agent ID.
- Role.
- Provider.
- Model.
- Messages.
- Tasks.
- Execution History.
- Token Usage.
- Final Result.

Lưu ý: Nên lưu snapshot cấu hình tại thời điểm bắt đầu phiên để khi người dùng thay đổi Team, phiên cũ vẫn giữ được thông tin phân công ban đầu.

Cho phép mở lại lịch sử và xem chính xác Agent nào đã thực hiện nhiệm vụ nào.

---

## 8. TOKEN & COST TRACKING

Theo dõi mức sử dụng:

- Theo Provider.
- Theo Model.
- Theo Agent.
- Theo Role.
- Theo Task.
- Theo Session.

Không sử dụng số liệu giả.

Nếu Provider không cung cấp Usage thì ghi rõ chưa có dữ liệu.

---

## 9. TEST CASE BẮT BUỘC

### Test 1: Phân công vai trò

Tạo một Team có 4 Agent.

Gán:
- Model A = Leader.
- Model B = Developer.
- Model C = Reviewer.
- Model D = Tester.

Lưu Team.

Tải lại trang và kiểm tra cấu hình còn chính xác không.

### Test 2: Đồng bộ Collaboration

Mở `/collab`.

Chọn Team vừa tạo.

Kiểm tra đủ 4 Agent, đúng Model và đúng Role.

### Test 3: Thực thi thực tế

Giao một nhiệm vụ lập trình.

Kiểm tra:
- Leader có thực sự được gọi không?
- Developer có được gọi đúng Model không?
- Reviewer có được gọi đúng Model không?
- Tester có được gọi đúng Model không?

Kiểm tra lịch sử thực thi ở Backend, không chỉ dựa vào giao diện.

### Test 4: Thay đổi phân công

Quay lại `/agents/teams`.

Đổi Developer từ Model B sang Model E.

Lưu lại.

Tạo phiên Collaboration mới.

Kiểm tra Developer sử dụng Model E.

Phiên cũ vẫn giữ cấu hình snapshot ban đầu.

### Test 5: Xử lý lỗi

Kiểm tra:
- Model bị lỗi API.
- API Key hết quota.
- Agent bị vô hiệu hóa.
- Team không có Leader.
- Agent không có Model hợp lệ.
- Provider mất kết nối.

Hệ thống phải thông báo rõ ràng và không tự động gán sai Model.

---

## 10. YÊU CẦU TRIỂN KHAI

Trước khi code:

1. Kiểm tra frontend `/agents/teams`.
2. Kiểm tra frontend `/collab`.
3. Kiểm tra API `/api/v1/ai/agent-teams`.
4. Kiểm tra Backend Orchestrator.
5. Kiểm tra cấu trúc Provider và Model.
6. Kiểm tra Database.
7. Xác định những phần đã có và những phần còn thiếu.

Sau đó mới triển khai.

Không tạo lại chức năng đã tồn tại.

Không thay đổi API theo hướng phá vỡ dữ liệu cũ.

Không hardcode Model.

Không giả lập hoạt động của Agent.

Không chỉ hoàn thiện giao diện mà bỏ qua Backend.

## 11. KẾT QUẢ MONG MUỐN

Tôi muốn có một quy trình hoàn chỉnh:

`/agents/teams`
→ Chọn Provider và Model
→ Gán vai trò cho từng Model
→ Cấu hình nhiệm vụ
→ Lưu Team qua API
→ `/collab` đọc cấu hình Team
→ Orchestrator điều phối
→ Đúng Model thực hiện đúng nhiệm vụ
→ Theo dõi tiến độ
→ Tổng hợp kết quả.

**NGUYÊN TẮC CUỐI CÙNG:**

`/agents/teams` là nơi cấu hình và phân công.

`/api/v1/ai/agent-teams` là nơi lưu trữ và cung cấp cấu hình.

`/collab` là nơi sử dụng cấu hình để thực thi.

Backend Orchestrator là nơi đảm bảo từng Model thực hiện đúng vai trò.

Hãy triển khai đầy đủ luồng dữ liệu này, không chỉ kết nối giao diện giữa hai trang.