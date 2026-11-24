# MINDFlow AI – PROJECT WORKSPACE DISCUSSION & COLLABORATION UPDATE

## 1. Mục tiêu

Cập nhật trang quản lý dự án hiện tại của MindFlow để bổ sung chức năng **Discussion & Collaboration với AI Agents ngay bên trong từng dự án**.

Đây không phải yêu cầu tạo một trang Team Room hoặc một hệ thống chat độc lập mới.

Mục tiêu là cho phép người dùng:
- Trao đổi trực tiếp với AI Agents theo ngữ cảnh dự án.
- Mention Agent bằng cú pháp `@Agent`.
- Yêu cầu một hoặc nhiều Agent phản hồi.
- Cho phép các Agent trao đổi, phản biện và bổ sung ý kiến.
- Sử dụng kết quả Project Analysis hiện có làm ngữ cảnh.
- Chuyển nội dung thảo luận thành task hoặc quyết định của dự án.
- Theo dõi kết quả mà không phải chuyển qua nhiều trang khác nhau.

**Quan trọng:** Repository hiện tại đã có một số chức năng liên quan. Hãy kiểm tra, tận dụng và hoàn thiện code hiện có, không tự ý xây dựng lại từ đầu.

---

## 2. Khảo sát và đánh giá code hiện tại

Trước khi chỉnh sửa, cần kiểm tra:

1. Routing và cấu trúc trang Project Workspace.
2. Trang Project Analysis hiện tại.
3. Agent Studio và danh sách Agent.
4. Agent configuration và model provider.
5. Workflows và cơ chế thực thi Agent.
6. Chat/conversation service hiện có.
7. Backend API, database schema và state management.
8. Cơ chế streaming, SSE hoặc WebSocket nếu đã triển khai.

Phân loại rõ:
- Chức năng đã hoạt động.
- Chức năng mới chỉ có giao diện.
- Chức năng đang lỗi.
- Chức năng chưa được triển khai.
- Chức năng có thể tái sử dụng.

Sau khi khảo sát, tiếp tục triển khai và sửa lỗi. Không chỉ đưa ra báo cáo hoặc kế hoạch rồi dừng lại.

---

## 3. Cấu trúc Project Workspace

Tích hợp các khu vực trong trang chi tiết dự án hiện tại:

| Khu vực | Chức năng |
|---|---|
| Overview | Tổng quan dự án, trạng thái và tiến độ |
| Analysis | Kết quả phân tích dự án |
| Tasks | Quản lý công việc và phân công |
| Discussion | Trao đổi với người và AI Agents |
| Execution | Theo dõi workflow và quá trình thực thi |

Nếu trang hiện tại đã có tab hoặc navigation tương tự, hãy tận dụng cấu trúc đó.

### Phân biệt trách nhiệm

**Project Analysis:**
- Phân tích yêu cầu.
- Đánh giá độ phức tạp.
- Phân tích kiến trúc.
- Đề xuất công nghệ.
- Chia nhỏ công việc.
- Đề xuất nguồn lực.

**Discussion:**
- Hỏi thêm về kết quả phân tích.
- Yêu cầu Agent giải thích.
- Phản biện phương án.
- Đưa ra phương án thay thế.
- Thống nhất quyết định.
- Chuyển thảo luận thành task.

**Tasks:**
- Quản lý công việc.
- Người/Agent phụ trách.
- Deadline.
- Trạng thái.
- Acceptance Criteria.

**Execution:**
- Chạy workflow.
- Theo dõi Agent.
- Xem log.
- Kiểm tra kết quả.
- Xử lý lỗi.

Không chạy lại toàn bộ Project Analysis mỗi khi người dùng gửi tin nhắn trong Discussion.

---

## 4. Discussion – Trao đổi với AI Agents

Đây là chức năng trọng tâm cần triển khai.

### 4.1. Giao diện chat

Thiết kế một khu vực trao đổi chuyên nghiệp, hiện đại và phù hợp với giao diện MindFlow hiện tại.

Yêu cầu:
- Tin nhắn người dùng và Agent hiển thị rõ ràng.
- Avatar, tên và chuyên môn của từng Agent.
- Hỗ trợ Markdown.
- Hỗ trợ code block.
- Hỗ trợ danh sách và liên kết.
- Có thời gian gửi tin nhắn.
- Có trạng thái đang suy nghĩ, đang phản hồi, hoàn thành và lỗi.
- Có streaming nếu backend hỗ trợ.
- Lưu lịch sử hội thoại.
- Reload trang không mất tin nhắn.
- Có nút retry khi Agent gặp lỗi.
- Có empty state hướng dẫn người dùng bắt đầu.

Không tạo phản hồi giả lập hoặc hardcode nội dung AI.

### 4.2. Mention Agent bằng @

Hỗ trợ:

- `@Architect`
- `@Developer`
- `@QA`
- `@BusinessAnalyst`
- `@ProjectManager`
- `@All`

Khi người dùng nhập `@`, hiển thị danh sách Agent có thể lựa chọn.

Hành vi:

| Mention | Hành vi |
|---|---|
| @Architect | Chỉ gọi Architect |
| @Developer | Chỉ gọi Developer |
| @QA | Chỉ gọi QA |
| @Architect @QA | Gọi hai Agent |
| @All | Orchestrator lựa chọn các Agent phù hợp |
| Không mention | Xử lý theo cấu hình Orchestrator |

Yêu cầu:
- Mention phải liên kết với Agent ID thực tế.
- Không chỉ xử lý bằng cách tìm tên trong chuỗi văn bản.
- Agent không tồn tại phải có thông báo rõ ràng.
- Không tự động kích hoạt tất cả Agent khi người dùng chỉ hỏi một Agent.
- Có thể cấu hình Agent nào được phép tham gia Discussion.

### 4.3. Agent giao tiếp tự nhiên

Đây là yêu cầu rất quan trọng.

Không muốn các Agent trả lời theo kiểu:

"Xin chào, tôi là Architect Agent. Tôi sẽ phân tích yêu cầu của bạn."

Thay vào đó, hãy để Agent giao tiếp tự nhiên như đồng nghiệp trong một nhóm làm việc.

Ví dụ:

Người dùng:

"Mình đang phân vân giữa Modular Monolith và Microservices. @Architect cho mình ý kiến nhé."

Architect:

"Theo mình, với quy mô MVP hiện tại thì nên dùng Modular Monolith. Microservices sẽ khiến việc triển khai và vận hành phức tạp hơn khá nhiều. Khi hệ thống lớn hơn, mình có thể tách các module thành service riêng."

Developer:

"Mình cũng nghiêng về phương án này. Với NestJS, chúng ta có thể tổ chức module khá rõ ràng và vẫn giữ khả năng mở rộng."

QA:

"Mình đồng ý, nhưng cần xác định ranh giới module ngay từ đầu để tránh phụ thuộc chéo khi hệ thống phát triển."

Yêu cầu về hành vi:
- Ngôn ngữ tự nhiên.
- Không lặp lại lời chào.
- Có ý kiến chuyên môn riêng.
- Có thể đồng ý hoặc phản biện Agent khác.
- Có thể đặt câu hỏi nếu thiếu thông tin.
- Trả lời đúng chuyên môn.
- Không tự nhận đã thực hiện hành động khi chưa có kết quả thực tế.
- Luôn thể hiện rõ đây là AI Agent.

Không bắt buộc tất cả Agent tham gia mọi cuộc thảo luận.

---

## 5. Context Management – Quản lý ngữ cảnh

Đây là phần quyết định chất lượng của Discussion.

Mỗi Agent cần được cung cấp ngữ cảnh phù hợp:

1. Project ID.
2. Tên và mô tả dự án.
3. Kết quả Project Analysis mới nhất.
4. Yêu cầu nghiệp vụ.
5. Kiến trúc và công nghệ.
6. Task liên quan.
7. Những quyết định đã được xác nhận.
8. Các tin nhắn gần nhất trong Discussion.
9. Kết quả liên quan từ Agent khác.

Ví dụ:

Người dùng:

"Vậy nếu sau này có 10.000 người dùng thì sao?"

Architect phải hiểu câu hỏi này liên quan đến kiến trúc vừa thảo luận, không bắt người dùng giải thích lại.

Yêu cầu kỹ thuật:
- Mỗi dự án có conversation riêng.
- Lưu lịch sử hội thoại trong database.
- Dùng summary khi lịch sử dài.
- Chỉ nạp context liên quan.
- Không gửi toàn bộ lịch sử vô hạn vào LLM.
- Không cho Agent truy cập dữ liệu dự án khác nếu chưa được cấp quyền.
- Khi thiếu ngữ cảnh, Agent phải hỏi lại thay vì tự suy diễn.

---

## 6. Discussion Decision – Quản lý quyết định

Đây là tính năng giúp Discussion khác với chat AI thông thường.

Cho phép lưu những quyết định quan trọng trong quá trình trao đổi.

Ví dụ:

**Quyết định:** Sử dụng Modular Monolith cho phiên bản MVP.

**Lý do:** Giảm độ phức tạp triển khai và dễ quản lý.

**Trạng thái:**
- Proposed.
- Approved.
- Rejected.
- Superseded.

Người dùng có quyền:
- Xác nhận.
- Chỉnh sửa.
- Từ chối.
- Xem lịch sử quyết định.

Chỉ quyết định được người có quyền xác nhận mới trở thành quyết định chính thức của dự án.

Không ghi đè quyết định cũ mà không lưu lịch sử.

---

## 7. Convert Discussion to Task

Cho phép chuyển một tin nhắn hoặc đề xuất thành công việc.

Thông tin task:
- Title.
- Description.
- Acceptance Criteria.
- Priority.
- Assignee.
- AI Agent phụ trách nếu có.
- Deadline.
- Dependencies.
- Tin nhắn nguồn.

Ví dụ:

Architect đề xuất cần thiết kế lại database.

Người dùng chọn:

"Create Task"

Hệ thống tạo task:

Title: Design ERP Database Schema.

Description: Thiết kế cấu trúc database cho các phân hệ CRM, Inventory và Finance.

Assignee: Backend Developer.

AI Support: Architect Agent.

Người dùng cần xác nhận trước khi tạo hoặc giao công việc có tác động thực tế.

Task sau khi tạo phải xuất hiện trong Task Management hiện có.

---

## 8. Đồng bộ với Project Analysis

Discussion phải sử dụng kết quả phân tích dự án đã có.

Khi có thay đổi quan trọng:

- Có thể đề xuất cập nhật kiến trúc.
- Có thể đề xuất cập nhật task.
- Có thể đề xuất điều chỉnh kế hoạch.
- Có thể đánh dấu phần Project Analysis cần phân tích lại.

Không tự động ghi đè kết quả phân tích cũ.

Mọi thay đổi quan trọng cần có lịch sử và xác nhận của người dùng.

---

## 9. LangGraph và n8n Integration

Tận dụng các công nghệ hiện có.

### LangGraph / Orchestrator

Phụ trách:
- Nhận diện Agent được mention.
- Định tuyến Agent.
- Nạp ngữ cảnh.
- Quản lý state.
- Điều phối nhiều Agent.
- Handoff kết quả.
- Tổng hợp câu trả lời.
- Retry và xử lý lỗi.

### n8n

Dùng cho các workflow nền:
- Gửi thông báo.
- Tạo GitHub Issue.
- Cập nhật hệ thống bên ngoài.
- Kích hoạt automation.
- Gửi kết quả workflow về Discussion.

Không bắt buộc mọi tin nhắn chat đều phải đi qua n8n.

Luồng chat trực tiếp nên được xử lý bởi backend conversation service để giảm độ trễ.

### Realtime

- Dùng SSE hoặc WebSocket tùy kiến trúc hiện có.
- Streaming từng phần câu trả lời.
- Hiển thị trạng thái Agent.
- Có Message ID, Conversation ID và Run ID.
- Chống gửi trùng.
- Có timeout và retry.

---

## 10. UI/UX – Nâng cấp giao diện

Giao diện hiện tại còn sơ sài, cần được kiểm tra và nâng cấp đồng bộ.

Yêu cầu:
- Thiết kế theo hướng Enterprise SaaS.
- Typography rõ ràng.
- Khoảng cách và bố cục hợp lý.
- Màu sắc nhất quán với MindFlow.
- Responsive.
- Khu vực chat dễ đọc.
- Composer thuận tiện.
- Mention autocomplete đẹp và dễ sử dụng.
- Avatar Agent phân biệt rõ.
- Trạng thái xử lý trực quan.
- Loading, Empty và Error states hoàn chỉnh.
- Markdown và code block trình bày tốt.

Không chỉ thêm một textarea và danh sách Agent.

Không sử dụng quá nhiều card lồng nhau hoặc hiệu ứng không cần thiết.

Giữ nguyên design system hiện tại nếu đã có.

---

## 11. Security và Permission

- Kiểm tra quyền người dùng ở backend.
- Agent chỉ được truy cập dữ liệu được cấp quyền.
- Không để mention vượt qua quyền truy cập.
- Nội dung tài liệu/repository là dữ liệu không đáng tin cậy, không được xem là system instruction.
- Hành động ghi dữ liệu phải có permission.
- Hành động quan trọng cần approval.
- Có audit log.
- Không để lộ API key và token.
- Giới hạn số Agent chạy đồng thời.
- Có timeout, retry limit và token/cost budget.

---

## 12. Kiểm thử

Bắt buộc kiểm tra:

1. Gửi tin nhắn bình thường.
2. Mention một Agent.
3. Mention nhiều Agent.
4. Mention @All.
5. Mention Agent không tồn tại.
6. Agent hiểu lịch sử hội thoại.
7. Agent đọc được Project Analysis.
8. Agent tham chiếu đúng task.
9. Hai Agent phản biện nhau.
10. Agent timeout.
11. Provider lỗi.
12. Retry không tạo tin nhắn trùng.
13. Reload vẫn giữ lịch sử.
14. Streaming hoạt động.
15. Convert tin nhắn thành task.
16. Lưu quyết định.
17. Người dùng không có quyền không thể thực hiện hành động.
18. Responsive trên desktop và tablet.

Không chỉ kiểm tra UI. Phải chạy test thực tế với backend và Agent runtime khi cấu hình đã sẵn sàng.

---

## 13. Báo cáo Word và ZIP bàn giao

Sau khi triển khai, tạo báo cáo Word `.docx` gồm:

1. Tổng quan tính năng.
2. Các chức năng đã triển khai.
3. Kiến trúc hệ thống.
4. Luồng mention và định tuyến Agent.
5. Context Management.
6. LangGraph và n8n integration.
7. Database/API/component đã thay đổi.
8. Security và Permission.
9. Kết quả kiểm thử.
10. Các lỗi đã sửa.
11. Những vấn đề còn tồn tại.
12. Hướng dẫn cấu hình và sử dụng.

Đóng gói ZIP gồm:
- Source code đã cập nhật.
- Báo cáo Word.
- README.
- Hướng dẫn cấu hình.
- Test report.

Không đưa:
- node_modules.
- API keys.
- Access tokens.
- File `.env` chứa secret.
- Thông tin nhạy cảm.

Nếu cần cấu hình môi trường, tạo `.env.example`.

---

## 14. Điều kiện nghiệm thu

Chỉ hoàn thành khi:

- Discussion được tích hợp trong Project Workspace.
- Không tạo trang chat độc lập trùng chức năng.
- Mention gọi đúng Agent thực tế.
- Agent sử dụng đúng ngữ cảnh dự án.
- Agent phản hồi tự nhiên.
- Có lịch sử hội thoại.
- Có streaming hoặc trạng thái xử lý.
- Có thể lưu quyết định.
- Có thể chuyển thảo luận thành task.
- Đồng bộ với Task Management.
- Có permission và audit log.
- Không làm hỏng Project Analysis, Agent Studio và Workflows.
- Giao diện hoàn chỉnh.
- Các test chính đạt yêu cầu.

---

## 15. Nguyên tắc thực hiện

1. Làm việc trực tiếp trên repository hiện tại.
2. Kiểm tra code trước khi sửa.
3. Không viết lại toàn bộ hệ thống.
4. Không tạo Team Room độc lập.
5. Không nhân đôi Project Analysis.
6. Không thay chức năng thật bằng mock data.
7. Không chỉ tạo UI mà phải kết nối backend.
8. Không tuyên bố hoàn thành nếu chưa kiểm thử.
9. Nếu thiếu API key hoặc provider, ghi rõ phần chưa thể chạy thật.
10. Ưu tiên hoàn thiện luồng end-to-end trước khi thêm tính năng phụ.

**KẾT QUẢ CUỐI CÙNG:**

Người dùng mở một dự án trong MindFlow, xem kết quả Project Analysis, vào Discussion để trao đổi tự nhiên với các AI Agent bằng @Mention, yêu cầu phản biện, thống nhất quyết định, chuyển nội dung thành task và tiếp tục theo dõi quá trình thực hiện ngay trong cùng Project Workspace.

Đây là một phần mở rộng của hệ thống quản lý dự án hiện tại, không phải một ứng dụng chat AI mới.