# MindFlow AI – Multi-AI Chat UI Specification

> Tài liệu bổ sung cho roadmap hiện tại của MindFlow AI.
>
> Phạm vi chính: Hoàn thiện trải nghiệm giao diện Multi-AI Chat và cách người dùng tương tác với nhiều mô hình AI cùng lúc.
>
> Không xây dựng lại các module đã có và không thay đổi lộ trình 8 Phase hiện tại.

---

## 1. Mục tiêu

Phát triển giao diện Multi-AI Chat cho phép người dùng trò chuyện với nhiều mô hình AI trên cùng một màn hình.

Thay vì phải chuyển đổi qua lại giữa các chatbot, người dùng có thể nhập một câu hỏi duy nhất và nhận được nhiều câu trả lời từ các AI khác nhau.

Ví dụ:
- GPT
- Claude
- Gemini
- DeepSeek
- Qwen
- Các model khác được cấu hình trong hệ thống.

---

## 2. Giao diện Multi-AI Chat

### 2.1. Bố cục nhiều màn hình AI

Thiết kế giao diện theo dạng Dashboard với nhiều khung chat độc lập.

Mỗi khung đại diện cho một model AI.

Thông tin hiển thị trong từng khung:

- Tên Provider.
- Tên Model.
- Trạng thái hoạt động.
- Nội dung câu hỏi và câu trả lời.
- Trạng thái đang xử lý.
- Thời gian phản hồi.
- Token đầu vào và đầu ra nếu có.

### 2.2. Tùy chỉnh bố cục

Cho phép người dùng thay đổi cách hiển thị:

- 1 cột: Hiển thị một AI.
- 2 cột: Hiển thị hai AI song song.
- 3 cột: Hiển thị ba AI.
- 4 cột: Hiển thị bốn AI.
- Tự động điều chỉnh bố cục theo kích thước màn hình.

Cho phép:
- Thêm AI vào màn hình.
- Xóa AI khỏi màn hình.
- Thay đổi thứ tự các AI.
- Phóng to một khung chat.
- Thu nhỏ hoặc đóng khung chat.
- Chuyển đổi giữa các bố cục.

Không giới hạn giao diện chỉ ở bốn AI, nhưng cần có giới hạn số lượng model chạy đồng thời để kiểm soát chi phí và hiệu năng.

---

## 3. Thanh nhập liệu chung (Shared Input)

Đây là thành phần quan trọng nhất của tính năng.

Không sử dụng nhiều ô nhập liệu riêng biệt cho từng AI.

Thay vào đó, thiết kế một thanh nhập liệu chung ở cuối giao diện.

Chức năng:

- Nhập nội dung câu hỏi.
- Gửi câu hỏi đến tất cả AI đang được chọn.
- Hỗ trợ nhập nhiều dòng.
- Hỗ trợ Enter để gửi và Shift + Enter để xuống dòng.
- Hiển thị số lượng AI sẽ nhận câu hỏi.
- Cho phép bật/tắt AI trước khi gửi.
- Có nút dừng toàn bộ lượt phản hồi.

### Nguyên tắc hoạt động

Khi người dùng nhập:

"Hãy đề xuất cho tôi một ý tưởng kinh doanh ứng dụng AI."

Hệ thống gửi cùng một nội dung đến tất cả AI đang được chọn.

Ví dụ:

| Model | Nội dung gửi |
|---|---|
| GPT | Cùng một câu hỏi |
| Claude | Cùng một câu hỏi |
| Gemini | Cùng một câu hỏi |
| DeepSeek | Cùng một câu hỏi |

Mỗi AI xử lý độc lập và trả kết quả về khung chat tương ứng.

Không cần chờ một AI hoàn thành mới gửi yêu cầu đến AI tiếp theo.

---

## 4. Quản lý từng khung chat

Mỗi AI cần có các thao tác độc lập.

### 4.1. Thao tác câu trả lời

- Copy: Sao chép nội dung.
- Regenerate: Yêu cầu AI tạo lại câu trả lời.
- Stop: Dừng phản hồi của AI hiện tại.
- Expand: Phóng to khung chat.
- Collapse: Thu nhỏ khung chat.

### 4.2. Trạng thái phản hồi

Mỗi khung chat có trạng thái riêng:

- Idle: Chưa có yêu cầu.
- Loading: Đang xử lý.
- Streaming: Đang tạo câu trả lời.
- Completed: Hoàn thành.
- Error: Xảy ra lỗi.
- Cancelled: Đã dừng.

Nếu một AI gặp lỗi, những AI khác vẫn tiếp tục hoạt động bình thường.

### 4.3. Cuộn nội dung

- Mỗi khung chat có thanh cuộn riêng.
- Không ảnh hưởng đến vị trí cuộn của các AI khác.
- Có thể tự động cuộn xuống khi nhận câu trả lời mới.
- Cho phép tắt tự động cuộn khi người dùng đang đọc nội dung cũ.

---

## 5. Chế độ hiển thị và so sánh

Ngoài giao diện Multi Chat, bổ sung khả năng chuyển đổi cách xem kết quả.

### 5.1. Multi Chat Mode

Hiển thị nhiều AI trong các khung riêng biệt.

Phù hợp khi người dùng muốn theo dõi toàn bộ quá trình trò chuyện của nhiều model.

### 5.2. Compare Mode

Hiển thị câu trả lời theo dạng so sánh.

Các nội dung cần hỗ trợ:

- So sánh câu trả lời giữa các AI.
- Nhận biết điểm giống và khác nhau.
- Xem ưu điểm và hạn chế của từng câu trả lời.
- So sánh thời gian phản hồi.
- So sánh lượng token sử dụng.
- Đánh giá câu trả lời theo tiêu chí do người dùng lựa chọn.

Cho phép chuyển đổi qua lại giữa Multi Chat và Compare mà không mất dữ liệu hội thoại.

---

## 6. AI Synthesis – Tổng hợp câu trả lời

Tận dụng kết quả từ nhiều AI để tạo ra một câu trả lời tổng hợp.

Luồng hoạt động:

1. Người dùng gửi câu hỏi đến nhiều AI.
2. Các AI hoàn thành câu trả lời.
3. Người dùng nhấn nút "Tổng hợp câu trả lời".
4. Hệ thống gửi câu hỏi ban đầu và các kết quả đến một model được chọn.
5. Model tổng hợp phân tích và tạo câu trả lời cuối cùng.

Kết quả tổng hợp cần có:

- Những điểm thống nhất giữa các AI.
- Những điểm khác biệt.
- Những thông tin còn mâu thuẫn.
- Ưu điểm của từng phương án.
- Kết luận và đề xuất cuối cùng.

Cần phân biệt rõ câu trả lời gốc của từng AI và câu trả lời do AI tổng hợp tạo ra.

---

## 7. Responsive Design

### Desktop

- Ưu tiên hiển thị nhiều khung chat song song.
- Có thể thay đổi số cột.
- Thanh nhập liệu luôn dễ truy cập.
- Mỗi khung chat có thanh cuộn riêng.

### Tablet

- Tự động giảm số cột.
- Đảm bảo nội dung không bị tràn.
- Cho phép chuyển đổi bố cục.

### Mobile

Không nên cố hiển thị 3–4 AI cùng lúc trên màn hình nhỏ.

Đề xuất:
- Hiển thị từng AI dưới dạng Tab.
- Có thể vuốt ngang để chuyển đổi AI.
- Hiển thị số lượng AI đang tham gia.
- Có thể chuyển sang danh sách kết quả.
- Giữ thanh nhập liệu ở cuối màn hình.
- Có thể xem câu trả lời tổng hợp riêng.

---

## 8. Quy tắc tích hợp với hệ thống hiện tại

Đây là phần quan trọng để tránh ảnh hưởng đến kiến trúc MindFlow AI đang xây dựng.

- Tái sử dụng Provider Architecture hiện tại.
- Tái sử dụng Model Management.
- Tái sử dụng hệ thống cấu hình API Key.
- Tái sử dụng Conversation History.
- Không tạo thêm một hệ thống quản lý Provider riêng.
- Không tạo thêm cơ chế Authentication riêng.
- Không hardcode danh sách model vào giao diện.
- Danh sách model phải được lấy từ hệ thống đã cấu hình.
- Không làm ảnh hưởng đến AI Chat hiện tại.
- Đảm bảo tương thích với các provider và model có thể được bổ sung trong tương lai.

Nếu hệ thống đã có giao diện AI Chat đơn lẻ, hãy phát triển Multi-AI Chat thành một chế độ sử dụng mới thay vì thay thế hoặc phá bỏ chức năng cũ.

---

## 9. Yêu cầu về hiệu năng và trải nghiệm

- Các AI phải được xử lý độc lập.
- Không để một AI bị lỗi làm ảnh hưởng đến toàn bộ giao diện.
- Hạn chế render lại tất cả khung chat khi chỉ một AI cập nhật nội dung.
- Hỗ trợ streaming độc lập cho từng AI.
- Quản lý trạng thái loading riêng.
- Có cơ chế hủy request.
- Kiểm soát số lượng request đồng thời.
- Không tự động gửi lại request gây phát sinh chi phí ngoài ý muốn.
- Giữ nội dung hội thoại khi chuyển đổi bố cục.
- Đảm bảo giao diện hoạt động tốt khi có nhiều câu trả lời dài.

---

## 10. Tiêu chí hoàn thành

- Có thể chọn nhiều AI trên cùng một màn hình.
- Có thể gửi một câu hỏi chung đến tất cả AI đã chọn.
- Các AI phản hồi đồng thời.
- Mỗi AI hiển thị câu trả lời trong khung riêng.
- Có thể thao tác độc lập trên từng AI.
- Có thể thay đổi bố cục hiển thị.
- Có thể chuyển đổi Multi Chat và Compare.
- Có thể tổng hợp câu trả lời từ nhiều AI.
- Không mất dữ liệu khi thay đổi bố cục.
- Giao diện responsive trên Desktop, Tablet và Mobile.
- Tương thích với kiến trúc Provider và Model hiện tại.

---

## 11. Nguyên tắc triển khai

Đọc và phân tích source code hiện tại trước khi thực hiện.

Không tự ý xây dựng lại các module đã hoàn thành.

Không thay đổi roadmap 8 Phase hiện tại.

Tập trung triển khai các yêu cầu bổ sung của tài liệu này, tích hợp vào đúng Phase tương ứng:

- Phase 3: Hoàn thiện trải nghiệm Multi-Model Chat.
- Phase 4: Hoàn thiện Compare Mode và AI Synthesis.

Ưu tiên tái sử dụng component, API, service và cấu trúc dữ liệu hiện có.

Đảm bảo các tính năng mới hoạt động ổn định và không làm ảnh hưởng đến chức năng hiện tại của MindFlow AI.