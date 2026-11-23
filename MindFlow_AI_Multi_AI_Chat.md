# MindFlow AI – Multi-AI Chat UI Specification

> Tài liệu bổ sung cho roadmap hiện tại của MindFlow AI.
>
> Phạm vi chính: Hoàn thiện trải nghiệm giao diện Multi-AI Chat và cách người dùng tương tác với nhiều mô hình AI cùng lúc.
>
> Không xây dựng lại các module đã có và không thay đổi lộ trình 8 Phase hiện tại.

---

## 1. Mục tiêu

Phát triển giao diện Multi-AI Chat cho phép người dùng trò chuyện với nhiều mô hình AI trên cùng một màn hình.

Thay vì phải chuyển đổi qua lại giữa các chatbot, người dùng có thể lựa chọn nhiều AI, phân chia nhiệm vụ và nhận kết quả từ các mô hình khác nhau trong cùng một giao diện.

Hệ thống hỗ trợ hai phương thức tương tác:

- **Same Question:** Gửi cùng một câu hỏi đến nhiều AI để so sánh câu trả lời.
- **Different Questions:** Giao các câu hỏi hoặc nhiệm vụ khác nhau cho từng AI, sau đó tổng hợp kết quả thành một câu trả lời hoàn chỉnh.

Ví dụ các model:

- GPT
- Claude
- Gemini
- DeepSeek
- Qwen
- Các model khác được cấu hình trong hệ thống.

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

Thiết kế một khu vực nhập liệu chung ở cuối giao diện. Khu vực này thay đổi theo chế độ hoạt động mà người dùng lựa chọn.

### 3.1. Hai chế độ hoạt động

Bổ sung bộ chuyển đổi giữa hai chế độ:

**Mode 1 – Same Question**

Cho phép gửi cùng một câu hỏi đến tất cả AI đang được chọn.

Ví dụ:

Người dùng nhập:

"Hãy đề xuất cho tôi một ý tưởng kinh doanh ứng dụng AI."

Hệ thống gửi cùng nội dung đến tất cả AI.

| Model | Nội dung gửi |
|---|---|
| GPT | Cùng một câu hỏi |
| Claude | Cùng một câu hỏi |
| Gemini | Cùng một câu hỏi |
| DeepSeek | Cùng một câu hỏi |

Mỗi AI xử lý độc lập và trả kết quả về khung chat tương ứng.

Phù hợp khi người dùng muốn:

- So sánh câu trả lời giữa nhiều model.
- Tìm kiếm nhiều góc nhìn khác nhau.
- Đánh giá độ chính xác của thông tin.
- Lựa chọn câu trả lời tốt nhất.

**Mode 2 – Different Questions**

Cho phép người dùng giao các câu hỏi hoặc nhiệm vụ khác nhau cho từng AI.

Mỗi AI có một ô nhập liệu riêng để người dùng xác định nhiệm vụ cần thực hiện.

Ví dụ:

| Model | Nhiệm vụ |
|---|---|
| GPT | Phân tích ưu điểm và nhược điểm của ý tưởng kinh doanh |
| Claude | Phân tích thị trường và đối thủ cạnh tranh |
| Gemini | Đề xuất chiến lược marketing |
| DeepSeek | Phân tích chi phí và khả năng triển khai |

Các AI nhận nhiệm vụ riêng biệt và xử lý đồng thời.

Sau khi hoàn thành, người dùng có thể tổng hợp kết quả từ tất cả AI thành một nội dung thống nhất.

Phù hợp khi người dùng muốn:

- Chia nhỏ một vấn đề lớn thành nhiều nhiệm vụ.
- Tận dụng thế mạnh của từng model.
- Nghiên cứu một chủ đề từ nhiều khía cạnh.
- Xây dựng một quy trình làm việc có nhiều AI phối hợp.

### 3.2. Giao diện nhập liệu theo chế độ

**Same Question:**

- Một ô nhập liệu chung.
- Hiển thị danh sách AI đang được chọn.
- Hiển thị số lượng AI sẽ nhận câu hỏi.
- Cho phép bật/tắt AI trước khi gửi.
- Hỗ trợ nhập nhiều dòng.
- Hỗ trợ Enter để gửi và Shift + Enter để xuống dòng.
- Có nút dừng toàn bộ lượt phản hồi.

**Different Questions:**

- Mỗi AI có một ô nhập liệu riêng.
- Hiển thị tên Provider và Model tương ứng.
- Cho phép thêm hoặc xóa AI.
- Cho phép thay đổi model cho từng nhiệm vụ.
- Có thể nhập câu hỏi khác nhau cho từng AI.
- Hiển thị rõ nhiệm vụ được giao cho từng model.
- Có nút gửi tất cả nhiệm vụ để các AI xử lý đồng thời.
- Cho phép gửi lại từng nhiệm vụ riêng biệt.

Không bắt buộc phải sử dụng đủ ba hoặc bốn AI. Người dùng có thể chọn hai AI hoặc số lượng AI khác theo giới hạn hệ thống.

### 3.3. Nguyên tắc hoạt động

- Các AI xử lý độc lập.
- Không cần chờ một AI hoàn thành mới gửi yêu cầu đến AI tiếp theo.
- Mỗi AI có trạng thái và kết quả riêng.
- Nếu một AI gặp lỗi, các AI khác vẫn tiếp tục hoạt động bình thường.
- Không tự động gửi lại request gây phát sinh chi phí ngoài ý muốn.

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

### 4.4. Quản lý câu hỏi và nhiệm vụ

Đối với Same Question:

- Hiển thị câu hỏi chung trong từng khung chat.
- Đảm bảo người dùng nhận biết các AI đang trả lời cùng một câu hỏi.

Đối với Different Questions:

- Hiển thị câu hỏi riêng của từng AI.
- Phân biệt rõ nhiệm vụ của từng model.
- Cho phép chỉnh sửa và gửi lại nhiệm vụ.
- Không làm mất kết quả của các AI khác khi một nhiệm vụ được gửi lại.

---

## 5. Chế độ hiển thị và so sánh

Ngoài giao diện Multi Chat, bổ sung khả năng chuyển đổi cách xem kết quả.

### 5.1. Multi Chat Mode

Hiển thị nhiều AI trong các khung riêng biệt.

Phù hợp khi người dùng muốn theo dõi toàn bộ quá trình trò chuyện của nhiều model.

Hỗ trợ cả Same Question và Different Questions.

### 5.2. Compare Mode

Hiển thị câu trả lời theo dạng so sánh.

Các nội dung cần hỗ trợ:

- So sánh câu trả lời giữa các AI.
- Nhận biết điểm giống và khác nhau.
- Xem ưu điểm và hạn chế của từng câu trả lời.
- So sánh thời gian phản hồi.
- So sánh lượng token sử dụng.
- Đánh giá câu trả lời theo tiêu chí do người dùng lựa chọn.

Đối với Different Questions, Compare Mode cần thể hiện rõ nhiệm vụ ban đầu của từng AI để tránh so sánh các câu trả lời không cùng ngữ cảnh.

Cho phép chuyển đổi qua lại giữa Multi Chat và Compare mà không mất dữ liệu hội thoại.

---

## 6. AI Synthesis – Tổng hợp câu trả lời

Tận dụng kết quả từ nhiều AI để tạo ra một câu trả lời tổng hợp.

AI Synthesis phải hỗ trợ cả Same Question và Different Questions.

### 6.1. Tổng hợp trong Same Question Mode

Luồng hoạt động:

1. Người dùng gửi một câu hỏi đến nhiều AI.
2. Các AI hoàn thành câu trả lời.
3. Người dùng nhấn nút "Tổng hợp câu trả lời".
4. Hệ thống gửi câu hỏi ban đầu và các kết quả đến một model được chọn.
5. Model tổng hợp phân tích, đối chiếu và tạo câu trả lời cuối cùng.

Kết quả tổng hợp cần có:

- Những điểm thống nhất giữa các AI.
- Những điểm khác biệt.
- Những thông tin còn mâu thuẫn.
- Ưu điểm và hạn chế của từng câu trả lời.
- Kết luận và đề xuất cuối cùng.

### 6.2. Tổng hợp trong Different Questions Mode

Đây là chức năng quan trọng giúp nhiều AI phối hợp giải quyết một vấn đề lớn.

Luồng hoạt động:

1. Người dùng phân chia các nhiệm vụ khác nhau cho từng AI.
2. Các AI xử lý nhiệm vụ độc lập.
3. Sau khi có kết quả, người dùng nhấn nút "Tổng hợp câu trả lời".
4. Hệ thống gửi toàn bộ câu hỏi và câu trả lời tương ứng của từng AI đến model tổng hợp.
5. Model tổng hợp phân tích, liên kết thông tin và tạo thành một câu trả lời hoàn chỉnh.

Ví dụ:

- GPT phân tích ý tưởng kinh doanh.
- Claude phân tích thị trường và đối thủ cạnh tranh.
- Gemini đề xuất chiến lược marketing.
- DeepSeek phân tích chi phí triển khai.

AI Synthesis sẽ kết hợp toàn bộ kết quả thành một bản phân tích kinh doanh hoàn chỉnh.

Không chỉ ghép nối nguyên văn các câu trả lời mà phải phân tích mối liên hệ giữa các nhiệm vụ, phát hiện thông tin bổ trợ và đưa ra kết luận có tính thống nhất.

Kết quả tổng hợp cần có:

1. Tổng quan vấn đề và các nhiệm vụ đã thực hiện.
2. Tóm tắt kết quả từ từng AI.
3. Những thông tin có liên quan và bổ trợ lẫn nhau.
4. Những điểm khác biệt hoặc mâu thuẫn.
5. Phân tích và đánh giá tổng hợp.
6. Kết luận và đề xuất cuối cùng.

### 6.3. Lựa chọn model AI tổng hợp

Cho phép người dùng chủ động lựa chọn model AI thực hiện việc tổng hợp.

Yêu cầu:

- Hiển thị danh sách các model AI hiện có trong hệ thống.
- Có thể chọn GPT, Claude, Gemini, DeepSeek, Qwen hoặc các model khác đã được cấu hình.
- Cho phép sử dụng một model đang hoạt động trong hệ thống để tổng hợp.
- Không hardcode danh sách model.
- Tận dụng Provider Architecture và Model Management hiện tại.
- Cho phép thay đổi model tổng hợp trước khi thực hiện.
- Hiển thị trạng thái xử lý và kết quả tổng hợp riêng biệt.

Model tổng hợp không bắt buộc phải là một trong những model đã tham gia trả lời ban đầu. Người dùng có thể lựa chọn một model khác nếu model đó đã được cấu hình và có thể sử dụng.

### 6.4. Quyền kiểm soát của người dùng

- Cho phép chọn những câu trả lời được đưa vào tổng hợp.
- Cho phép bỏ qua kết quả của một AI.
- Cho phép thay đổi model tổng hợp.
- Cho phép thực hiện tổng hợp lại bằng model khác.
- Không tự động tổng hợp khi chưa có sự đồng ý của người dùng.
- Không làm mất câu hỏi và câu trả lời ban đầu sau khi tổng hợp.
- Cho phép xem lại kết quả gốc của từng AI.

### 6.5. Phân biệt kết quả gốc và kết quả tổng hợp

Giao diện cần phân biệt rõ:

- Original Responses: Câu trả lời gốc từ từng AI.
- Synthesized Response: Câu trả lời do model tổng hợp tạo ra.

Kết quả tổng hợp cần có thông tin về model đã thực hiện tổng hợp.

Cho phép người dùng chuyển đổi giữa việc xem kết quả tổng hợp và các câu trả lời gốc.

---

## 7. Responsive Design

### Desktop

- Ưu tiên hiển thị nhiều khung chat song song.
- Có thể thay đổi số cột.
- Thanh nhập liệu luôn dễ truy cập.
- Mỗi khung chat có thanh cuộn riêng.
- Hỗ trợ giao diện nhập nhiệm vụ riêng cho từng AI.
- Có không gian riêng để hiển thị kết quả tổng hợp.

### Tablet

- Tự động giảm số cột.
- Đảm bảo nội dung không bị tràn.
- Cho phép chuyển đổi bố cục.
- Có thể sử dụng danh sách AI để chuyển đổi giữa các khung chat.

### Mobile

Không nên cố hiển thị 3–4 AI cùng lúc trên màn hình nhỏ.

Đề xuất:

- Hiển thị từng AI dưới dạng Tab.
- Có thể vuốt ngang để chuyển đổi AI.
- Hiển thị số lượng AI đang tham gia.
- Có thể chuyển sang danh sách kết quả.
- Giữ thanh nhập liệu ở cuối màn hình.
- Đối với Different Questions, hiển thị từng nhiệm vụ theo dạng danh sách hoặc từng thẻ riêng.
- Có thể xem câu trả lời tổng hợp riêng.

Đảm bảo thao tác chuyển đổi giữa các model không làm mất dữ liệu.

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
- Tái sử dụng API và service hiện có nếu phù hợp.
- Quản lý riêng câu hỏi, nhiệm vụ và kết quả tương ứng của từng AI.
- Đảm bảo dữ liệu của Same Question và Different Questions được lưu trữ đúng ngữ cảnh.

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
- Quản lý trạng thái riêng cho từng nhiệm vụ trong Different Questions.
- Không yêu cầu tất cả AI phải hoàn thành mới có thể xem các kết quả đã hoàn thành.
- Có thể theo dõi tiến trình hoàn thành của toàn bộ nhiệm vụ.

---

## 10. Tiêu chí hoàn thành

### 10.1. Multi-AI Chat

- Có thể chọn nhiều AI trên cùng một màn hình.
- Có thể gửi một câu hỏi chung đến tất cả AI đã chọn.
- Các AI phản hồi đồng thời.
- Mỗi AI hiển thị câu trả lời trong khung riêng.
- Có thể thao tác độc lập trên từng AI.
- Có thể thay đổi bố cục hiển thị.
- Có thể chuyển đổi Multi Chat và Compare.
- Không mất dữ liệu khi thay đổi bố cục.

### 10.2. Different Questions Mode

- Có hai chế độ Same Question và Different Questions.
- Có thể giao nhiệm vụ khác nhau cho từng AI.
- Có thể chọn tối thiểu 2–3 AI để phối hợp.
- Mỗi AI có ô nhập nhiệm vụ riêng.
- Có thể thay đổi model cho từng nhiệm vụ.
- Các AI xử lý nhiệm vụ đồng thời.
- Có thể gửi lại từng nhiệm vụ độc lập.
- Có thể theo dõi trạng thái từng nhiệm vụ.

### 10.3. AI Synthesis

- Có thể tổng hợp nhiều câu trả lời từ Same Question Mode.
- Có thể tổng hợp nhiều kết quả từ Different Questions Mode.
- Có thể lựa chọn model AI thực hiện tổng hợp.
- Có thể lựa chọn những kết quả muốn đưa vào tổng hợp.
- Kết quả tổng hợp có tính liên kết, không chỉ ghép nội dung.
- Có thể nhận diện điểm thống nhất và mâu thuẫn.
- Giữ nguyên lịch sử câu hỏi và câu trả lời gốc.
- Phân biệt rõ câu trả lời gốc và kết quả tổng hợp.

### 10.4. Responsive và tương thích

- Giao diện responsive trên Desktop, Tablet và Mobile.
- Tương thích với Provider Architecture và Model Management hiện tại.
- Không ảnh hưởng đến AI Chat hiện tại.
- Không phát sinh hệ thống quản lý Provider trùng lặp.

---

## 11. Nguyên tắc triển khai

Đọc và phân tích source code hiện tại trước khi thực hiện.

Không tự ý xây dựng lại các module đã hoàn thành.

Không thay đổi roadmap 8 Phase hiện tại.

Tập trung triển khai các yêu cầu bổ sung của tài liệu này, tích hợp vào đúng Phase tương ứng:

- **Phase 3:** Hoàn thiện trải nghiệm Multi-Model Chat, Shared Input, Same Question và Different Questions.
- **Phase 4:** Hoàn thiện Compare Mode và AI Synthesis, bao gồm khả năng tổng hợp kết quả từ nhiều nhiệm vụ khác nhau.

Ưu tiên tái sử dụng component, API, service và cấu trúc dữ liệu hiện có.

Trước khi triển khai:

1. Phân tích kiến trúc frontend và backend hiện tại.
2. Kiểm tra Provider Architecture và Model Management.
3. Kiểm tra Conversation History và cơ chế lưu trữ hội thoại.
4. Xác định các component có thể tái sử dụng.
5. Đề xuất cách tích hợp tính năng mới vào hệ thống hiện tại.
6. Xác định các API cần bổ sung hoặc điều chỉnh nếu thực sự cần thiết.

Trong quá trình triển khai:

- Không hardcode model hoặc provider.
- Không tạo dữ liệu giả để thay thế API thực tế.
- Không phá vỡ các chức năng hiện tại.
- Không tự ý thay đổi các module ngoài phạm vi.
- Đảm bảo xử lý lỗi độc lập cho từng AI.
- Đảm bảo kiểm soát request và chi phí API.

Sau khi triển khai:

- Kiểm tra Same Question Mode.
- Kiểm tra Different Questions Mode.
- Kiểm tra Compare Mode.
- Kiểm tra AI Synthesis với cả hai chế độ.
- Kiểm tra khả năng lựa chọn model tổng hợp.
- Kiểm tra responsive.
- Kiểm tra việc lưu và khôi phục lịch sử hội thoại.
- Kiểm tra khả năng hoạt động khi một hoặc nhiều AI gặp lỗi.

Đảm bảo các tính năng mới hoạt động ổn định và không làm ảnh hưởng đến chức năng hiện tại của MindFlow AI.