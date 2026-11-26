# REBUILD WORKFLOWS PAGE – MINDFLOW AI

## 1. Mục tiêu

Tiến hành thay đổi toàn bộ trang `/agents/workflows`.

Hiện tại website đang có giao diện tự xây dựng Workflow Builder gồm Node Catalog, Canvas, Node Editor, Sticky Note Editor và chức năng chỉnh sửa JSON.

**Yêu cầu: XÓA phần Workflow Builder tự xây dựng hiện tại và thay thế bằng giao diện quản lý n8n Workflow chuyên nghiệp.**

Định hướng kiến trúc:

- MindFlow AI: Control Center – quản lý, cấu hình, giám sát và điều phối workflow.
- n8n: Workflow Engine – thiết kế node, kết nối, xử lý logic và thực thi workflow.
- Backend: Trung gian giao tiếp giữa MindFlow AI và n8n thông qua REST API.

Không xây dựng lại các tính năng mà n8n đã hỗ trợ.

---

## 2. Xóa các thành phần hiện tại

Kiểm tra code của trang `/agents/workflows` và loại bỏ các thành phần thuộc Workflow Builder cũ:

- Node Catalog.
- AI Agent Node tự xây dựng.
- Set / Edit Fields Node.
- Code (JavaScript) Node.
- IF / ELSE Node.
- Merge Node.
- Gmail / Telegram Node tự xây dựng.
- Canvas kéo thả node.
- Node Connection Editor.
- Node Parameter Editor.
- Sticky Note Editor.
- Chỉnh sửa thuộc tính node trực tiếp trên website.
- Chức năng tạo và kết nối node thủ công.
- Các thành phần UI chỉ phục vụ cho trình dựng workflow riêng.

Đặc biệt:
- Xóa các component, state, hook và logic không còn sử dụng sau khi thay đổi.
- Không chỉ ẩn giao diện bằng CSS.
- Không để lại các component cũ gây xung đột hoặc khó bảo trì.
- Không xóa các chức năng dùng chung với những trang khác.
- Không làm ảnh hưởng đến Agent Studio, Agent Teams, AI Chat và các module hiện có.

Có thể giữ lại logic Import JSON, Export JSON và Validate JSON nếu có thể tái sử dụng.

---

## 3. Giao diện Workflows mới

Thiết kế lại trang `/agents/workflows` thành một trang quản lý workflow.

### 3.1. Header

Hiển thị:

- Tiêu đề: Workflow Management.
- Mô tả: Quản lý, đồng bộ và giám sát các quy trình tự động hóa thông qua n8n.
- Trạng thái kết nối n8n:
  - Connected.
  - Disconnected.
  - Connection Error.
- Nút Refresh Connection.
- Nút Import Workflow.
- Nút Create Workflow.

### 3.2. Dashboard Statistics

Hiển thị các thẻ thống kê:

| Chỉ số | Mô tả |
|---|---|
| Total Workflows | Tổng số workflow được quản lý |
| Active Workflows | Số workflow đang kích hoạt |
| Inactive Workflows | Số workflow chưa kích hoạt |
| Executions Today | Tổng số lần thực thi hôm nay |
| Failed Executions | Số lần thực thi thất bại |

Dữ liệu phải lấy từ backend/n8n khi đã kết nối.

Không tự tạo số liệu giả để hiển thị như dữ liệu thực tế.

### 3.3. Workflow Management

Xây dựng khu vực quản lý workflow dạng danh sách hoặc card.

Mỗi workflow cần hiển thị:

- Tên workflow.
- Mô tả.
- Workflow ID trên n8n.
- Trạng thái Active/Inactive.
- Thời điểm cập nhật gần nhất.
- Lần thực thi gần nhất.
- Kết quả thực thi gần nhất nếu có.

Các thao tác:

1. View Details.
2. Open in n8n.
3. Import / Update JSON.
4. Export JSON.
5. Activate / Deactivate.
6. View Executions.
7. Delete Workflow.

Yêu cầu:
- Có tìm kiếm theo tên workflow.
- Có lọc theo trạng thái.
- Có phân trang nếu danh sách lớn.
- Có xác nhận trước khi xóa hoặc thực hiện thao tác quan trọng.

---

## 4. Chức năng Import JSON Workflow

Đây là chức năng quan trọng nhất cần giữ lại từ giao diện cũ.

Cho phép người dùng nhập workflow JSON được export từ n8n.

Giao diện gồm:

- Khu vực upload file `.json`.
- Textarea để dán JSON trực tiếp.
- Nút Validate JSON.
- Nút Import Workflow.
- Nút Cancel.

### Quy trình:

1. Người dùng upload hoặc dán JSON.
2. Frontend gửi dữ liệu đến backend để kiểm tra.
3. Backend kiểm tra JSON có hợp lệ hay không.
4. Kiểm tra các trường cấu trúc workflow cần thiết như `name`, `nodes`, `connections`.
5. Kiểm tra dữ liệu node và connections.
6. Hiển thị thông tin workflow trước khi import.
7. Người dùng xác nhận import.
8. Backend sử dụng n8n REST API để tạo workflow trên n8n.
9. Nhận workflow ID từ n8n.
10. Lưu thông tin liên kết workflow vào database của MindFlow AI.

Nếu JSON không hợp lệ:
- Hiển thị lỗi cụ thể.
- Không thực hiện import.
- Không làm mất nội dung JSON người dùng đã nhập.

Không tự ý sửa cấu trúc workflow JSON nếu chưa có sự xác nhận.

---

## 5. Chức năng Update JSON Workflow

Cho phép cập nhật workflow đã tồn tại.

Quy trình:

1. Người dùng chọn workflow.
2. Chọn Update JSON.
3. Upload hoặc dán JSON mới.
4. Validate JSON.
5. Hiển thị thông tin thay đổi.
6. Xác nhận cập nhật.
7. Backend sử dụng n8n REST API cập nhật đúng workflow tương ứng.
8. Đồng bộ thông tin mới về MindFlow AI.

Yêu cầu quan trọng:

- Phải lưu `n8n_workflow_id` để nhận diện workflow.
- Không tạo workflow mới khi người dùng đang cập nhật workflow cũ.
- Phân biệt rõ Create và Update.
- Không ghi đè nhầm workflow.
- Có cơ chế xử lý lỗi khi cập nhật thất bại.
- Không tự động xóa workflow đang tồn tại nếu quá trình cập nhật lỗi.

---

## 6. Chức năng Export JSON

Cho phép người dùng:

- Export JSON từ workflow đã lưu.
- Tải file JSON về máy.
- Sao lưu workflow.
- Kiểm tra JSON trước khi export.

Ưu tiên lấy dữ liệu workflow mới nhất từ n8n thay vì chỉ lấy bản JSON cũ được lưu trong database.

---

## 7. Chức năng Open in n8n

Mỗi workflow cần có nút:

**Open in n8n**

Khi nhấn:
- Mở giao diện n8n Editor.
- Điều hướng trực tiếp đến workflow tương ứng.
- Sử dụng URL n8n được cấu hình trong hệ thống.
- Không hardcode URL ở nhiều component.

Ví dụ cấu hình:

`N8N_BASE_URL`

Đường dẫn đến workflow phải được xây dựng theo cấu hình thực tế của phiên bản n8n đang sử dụng.

Việc chỉnh sửa node, kết nối node, prompt kỹ thuật và credentials sẽ thực hiện trực tiếp trên n8n.

---

## 8. Workflow Execution History

Bổ sung khu vực theo dõi lịch sử chạy workflow.

Hiển thị:

| Thông tin | Mô tả |
|---|---|
| Execution ID | ID lần chạy |
| Workflow | Tên workflow |
| Status | Success / Error / Running / Waiting |
| Started At | Thời gian bắt đầu |
| Finished At | Thời gian kết thúc |
| Duration | Thời gian thực thi |

Cho phép:

- Xem chi tiết execution.
- Xem lỗi nếu thất bại.
- Lọc theo workflow.
- Lọc theo trạng thái.
- Lọc theo thời gian.

Dữ liệu phải đồng bộ từ n8n.

Không giả lập kết quả execution khi chưa kết nối được n8n.

---

## 9. Kiến trúc Backend và n8n

Không gọi n8n REST API trực tiếp từ frontend.

Luồng xử lý:

`Frontend → MindFlow Backend → n8n REST API`

Backend chịu trách nhiệm:

- Quản lý n8n API Key.
- Gọi n8n REST API.
- Import workflow.
- Update workflow.
- Export workflow.
- Activate / Deactivate workflow.
- Lấy danh sách workflow.
- Lấy execution history.
- Kiểm tra trạng thái kết nối.
- Đồng bộ dữ liệu với database.

### Bảo mật

- Không lưu n8n API Key trong localStorage.
- Không gửi n8n API Key xuống frontend.
- Không hardcode API Key trong source code.
- Sử dụng Environment Variables hoặc cơ chế quản lý secrets an toàn.
- Không đưa credentials bí mật vào JSON trả về frontend.
- Kiểm tra quyền người dùng trước các thao tác quản trị workflow.
- Không để người dùng workspace này truy cập workflow của workspace khác.

### Lưu ý API

Trước khi triển khai:
- Kiểm tra phiên bản n8n đang sử dụng.
- Đọc tài liệu REST API tương ứng.
- Kiểm tra các endpoint thực tế hỗ trợ Create, Update, Activate, Deactivate, Delete, Executions.
- Không tự suy đoán endpoint hoặc request body.
- Xử lý đúng response và lỗi từ n8n.

---

## 10. Database

Kiểm tra database hiện tại trước khi thiết kế thêm bảng.

Nếu chưa có cấu trúc phù hợp, xây dựng bảng quản lý liên kết workflow với các trường tham khảo:

| Field | Ý nghĩa |
|---|---|
| id | ID nội bộ |
| workspace_id | Workspace sở hữu |
| n8n_workflow_id | ID workflow trên n8n |
| name | Tên workflow |
| description | Mô tả |
| active | Trạng thái |
| tags | Nhóm workflow |
| last_synced_at | Thời điểm đồng bộ |
| created_at | Thời điểm tạo |
| updated_at | Thời điểm cập nhật |

Đảm bảo một workflow không bị tạo trùng ngoài ý muốn.

Không lưu credentials bí mật trong bảng workflow.

---

## 11. Thiết kế UI/UX

Giữ nguyên Design System hiện tại của MindFlow AI:

- Sidebar hiện tại.
- Header hiện tại.
- Màu sắc và typography hiện tại.
- Border radius.
- Card style.
- Button style.
- Responsive layout.

Giao diện mới cần:
- Chuyên nghiệp theo phong cách SaaS.
- Dễ sử dụng.
- Không quá nhiều thông tin trên một màn hình.
- Có trạng thái Loading.
- Có Empty State.
- Có Error State.
- Có Success Notification.
- Có xác nhận cho các thao tác quan trọng.
- Responsive trên desktop, tablet và mobile.

Không cần tạo Canvas hoặc mô phỏng giao diện n8n.

---

## 12. Những điều KHÔNG ĐƯỢC LÀM

1. Không xây dựng lại n8n bên trong MindFlow AI.
2. Không tự phát triển hệ thống kéo thả node.
3. Không tạo một hệ thống kết nối node riêng.
4. Không chỉnh sửa node parameters trực tiếp trên MindFlow AI.
5. Không tạo hệ thống Credentials riêng để lưu API Key của n8n.
6. Không hardcode dữ liệu workflow giả.
7. Không phá vỡ các module hiện có.
8. Không thay đổi cấu trúc routing không liên quan.
9. Không xóa các API hoặc component đang được sử dụng ở module khác.
10. Không chỉ làm UI mà bỏ qua tích hợp backend.

---

## 13. Thứ tự triển khai

### Phase 1 – Cleanup
- Kiểm tra toàn bộ source code trang Workflows.
- Xóa Workflow Builder cũ.
- Xóa các component và logic không còn cần thiết.
- Giữ lại các chức năng có thể tái sử dụng.

### Phase 2 – New UI
- Xây dựng Workflow Management.
- Xây dựng Dashboard Statistics.
- Xây dựng Workflow List.
- Xây dựng Import/Export JSON.
- Xây dựng Workflow Details.

### Phase 3 – n8n Integration
- Kết nối backend với n8n.
- Implement Create / Update.
- Implement Activate / Deactivate.
- Implement Export.
- Implement Open in n8n.
- Implement Connection Status.

### Phase 4 – Monitoring
- Execution History.
- Execution Details.
- Error Monitoring.
- Workflow Status Synchronization.

### Phase 5 – Testing
- Kiểm tra Import JSON hợp lệ.
- Kiểm tra Import JSON không hợp lệ.
- Kiểm tra tạo workflow mới.
- Kiểm tra cập nhật workflow cũ.
- Kiểm tra không tạo trùng workflow.
- Kiểm tra Activate / Deactivate.
- Kiểm tra Export JSON.
- Kiểm tra n8n mất kết nối.
- Kiểm tra phân quyền workspace.
- Kiểm tra responsive.
- Kiểm tra không ảnh hưởng các module khác.

---

## 14. Kết quả mong muốn

Sau khi hoàn thành:

**MindFlow AI**
- Là trung tâm quản lý workflow.
- Quản lý nhiều workflow.
- Quản lý các workflow phục vụ AI Agents.
- Import / Export JSON.
- Theo dõi lịch sử chạy.
- Theo dõi trạng thái.
- Quản lý workspace và phân quyền.

**n8n**
- Là nơi thiết kế workflow.
- Là nơi thêm/xóa/chỉnh sửa node.
- Là nơi cấu hình kết nối và logic.
- Là nơi quản lý credentials.
- Là nơi thực thi automation.

**YÊU CẦU CUỐI CÙNG:**

Hãy đọc và phân tích source code hiện tại trước khi chỉnh sửa. Ưu tiên tái sử dụng API, service, database và component đang có nếu phù hợp.

Thực hiện trực tiếp trên project hiện tại, không tạo project mới, không chỉ viết giao diện demo.

Không tự ý thay đổi các module ngoài phạm vi.

Sau khi hoàn thành, báo cáo:
1. Những component cũ đã xóa.
2. Những component mới đã tạo.
3. API backend đã triển khai.
4. Các endpoint n8n đã tích hợp.
5. Database đã thay đổi.
6. Các chức năng đã kiểm thử.
7. Những phần còn cần cấu hình hoặc chưa thể kết nối thực tế.