# MindFlow AI -- Multi-AI Chat

## 1. Mục tiêu

Phát triển tính năng **Multi-AI Chat** cho MindFlow AI, cho phép người
dùng gửi một câu hỏi đến nhiều mô hình AI cùng lúc và xem các câu trả
lời song song trên cùng một màn hình.

Mục tiêu không chỉ là tập hợp nhiều chatbot, mà còn giúp người dùng **so
sánh, đánh giá và tổng hợp** câu trả lời từ nhiều mô hình AI.

## 2. Giao diện Multi-AI Chat

### 2.1. Bố cục màn hình

-   Hiển thị nhiều khung chat trên cùng một trang.
-   Mỗi khung đại diện cho một model AI riêng.
-   Mỗi khung hiển thị:
    -   Tên nhà cung cấp và tên model.
    -   Trạng thái hoạt động.
    -   Nội dung hội thoại.
    -   Trạng thái đang trả lời, hoàn thành hoặc lỗi.
    -   Thời gian phản hồi và thông tin token nếu provider có trả về.
-   Hỗ trợ bố cục 1, 2 hoặc nhiều cột tùy số lượng AI được chọn.
-   Cho phép thêm, xóa và thay đổi model trong danh sách đang so sánh.
-   Có thể phóng to một khung chat để đọc nội dung chi tiết.

### 2.2. Thanh nhập liệu dùng chung

-   Chỉ sử dụng **một ô nhập liệu chung** cho toàn bộ các AI đang được
    chọn.
-   Khi người dùng gửi câu hỏi, hệ thống gửi cùng nội dung đến tất cả
    model đã chọn.
-   Mỗi AI xử lý độc lập và hiển thị câu trả lời trong khung riêng.
-   Không cần chờ model này hoàn thành mới gửi yêu cầu đến model tiếp
    theo.
-   Có thể gửi câu hỏi tiếp theo khi lượt trả lời trước đã hoàn tất hoặc
    theo cơ chế xử lý lượt hội thoại mà hệ thống hỗ trợ.

### 2.3. Thao tác trên từng câu trả lời

-   Sao chép nội dung.
-   Tạo lại câu trả lời (Regenerate).
-   Dừng phản hồi của model đó.
-   Hiển thị thời gian phản hồi.
-   Hiển thị token đầu vào/đầu ra khi có dữ liệu.
-   Báo lỗi riêng cho từng model; lỗi của một model không làm mất kết
    quả từ các model còn lại.

## 3. Quản lý hội thoại

-   Tạo hội thoại mới.
-   Đổi tên và xóa hội thoại.
-   Lưu lịch sử tin nhắn và các model tham gia.
-   Mở lại và tiếp tục hội thoại cũ.
-   Cho phép thêm hoặc bỏ model khỏi hội thoại.
-   Lưu riêng trạng thái và nội dung phản hồi của từng model trong mỗi
    lượt gửi.
-   Khi thêm model mới giữa hội thoại, cần xác định rõ lịch sử nào sẽ
    được gửi cho model đó để bảo đảm ngữ cảnh nhất quán.

## 4. Các chế độ sử dụng

### 4.1. Multi Chat

Hiển thị các AI trong những khung chat riêng biệt. Người dùng gửi một
câu hỏi chung và theo dõi phản hồi đồng thời.

### 4.2. Compare AI

Hiển thị câu trả lời theo dạng so sánh để người dùng dễ đánh giá:

-   Điểm giống nhau.
-   Điểm khác nhau.
-   Ưu điểm và hạn chế của từng câu trả lời.
-   Model nào phù hợp hơn với mục đích đang thực hiện.

Việc đánh giá nên dựa trên nội dung thực tế và tiêu chí do người dùng
chọn, không mặc định model nào luôn tốt nhất.

### 4.3. AI Synthesis

Sau khi các model hoàn thành, người dùng có thể chọn **Tổng hợp câu trả
lời**.

-   Gửi câu hỏi ban đầu và các câu trả lời đã nhận đến một model được
    chọn làm model tổng hợp.
-   Yêu cầu model tổng hợp chỉ ra điểm thống nhất, điểm mâu thuẫn và
    thông tin cần kiểm chứng.
-   Đưa ra kết luận hoặc phương án đề xuất.
-   Hiển thị rõ đây là nội dung tổng hợp, không phải câu trả lời trực
    tiếp của các model nguồn.

## 5. Kiến trúc xử lý đề xuất

``` text
                         USER
                           |
                           v
                    SHARED INPUT
                           |
                           v
                    MULTI-AI MANAGER
                           |
             +-------------+-------------+
             |             |             |
             v             v             v
          Provider A   Provider B   Provider C
             |             |             |
             v             v             v
          Model A       Model B       Model C
             |             |             |
             v             v             v
          Response      Response      Response
             |             |             |
             +-------------+-------------+
                           |
                           v
                    MULTI-AI UI
                           |
                 +---------+---------+
                 |                   |
                 v                   v
             Compare AI          AI Synthesis
```

### 5.1. Backend

-   Tái sử dụng hệ thống provider/model và cấu hình API key hiện có.
-   Tạo lớp điều phối Multi-AI Manager để nhận một câu hỏi và phân phối
    đến các model được chọn.
-   Gọi các model song song, không xử lý tuần tự.
-   Có thể dùng `Promise.allSettled()` nếu backend sử dụng
    JavaScript/Node.js để nhận kết quả thành công và lỗi độc lập từ từng
    model.
-   Chuẩn hóa kết quả trả về theo một cấu trúc thống nhất, bất kể
    provider nào.
-   Quản lý timeout, retry có giới hạn, hủy yêu cầu và giới hạn số model
    chạy đồng thời.
-   Không để lộ API key ở frontend.

### 5.2. Streaming

Ưu tiên hỗ trợ streaming để từng khung chat hiển thị nội dung ngay khi
model tạo ra câu trả lời.

Có thể sử dụng SSE hoặc cơ chế streaming phù hợp với kiến trúc backend
hiện tại. Mỗi luồng cần gắn với đúng hội thoại, lượt gửi và model để
tránh hiển thị nhầm nội dung giữa các khung.

### 5.3. Dữ liệu hội thoại

Mỗi lượt gửi nên lưu được:

-   Hội thoại.
-   Nội dung câu hỏi chung.
-   Danh sách model được yêu cầu.
-   Trạng thái riêng của từng model.
-   Nội dung phản hồi của từng model.
-   Thời điểm bắt đầu và kết thúc.
-   Token và thời gian xử lý nếu provider cung cấp.
-   Thông tin lỗi nếu yêu cầu thất bại.

## 6. Trải nghiệm người dùng và responsive

-   Desktop: ưu tiên bố cục nhiều cột, có thể cuộn độc lập trong từng
    khung chat.
-   Màn hình nhỏ: chuyển sang dạng tab, carousel hoặc từng khung xếp
    dọc; tránh ép quá nhiều cột khiến nội dung khó đọc.
-   Có chế độ toàn màn hình cho một model.
-   Có trạng thái loading riêng cho từng AI.
-   Có thể dừng riêng từng model hoặc dừng toàn bộ lượt gửi.
-   Giữ thanh nhập liệu dễ truy cập khi cuộn nội dung.
-   Đồng bộ nội dung câu hỏi giữa các khung nhưng giữ phản hồi độc lập.

## 7. Lưu ý về chi phí và giới hạn

Vì một câu hỏi được gửi đến nhiều model nên chi phí API và lượng token
có thể tăng theo số model được chọn.

Cần triển khai:

-   Hiển thị số model sẽ nhận câu hỏi trước khi gửi.
-   Thiết lập giới hạn số model chạy đồng thời.
-   Theo dõi token và chi phí ước tính nếu provider cung cấp dữ liệu.
-   Xử lý rate limit và quota riêng của từng provider.
-   Cho phép người dùng chọn model trước mỗi lượt gửi.
-   Tránh tự động gửi lại nhiều lần khi gặp lỗi để không phát sinh chi
    phí ngoài ý muốn.

## 8. Lộ trình triển khai

### Giai đoạn 1 -- Multi-AI Chat cơ bản

-   Chọn nhiều model từ provider đã cấu hình.
-   Hiển thị các khung chat song song.
-   Một ô nhập liệu chung.
-   Gửi câu hỏi đồng thời đến các model.
-   Hiển thị phản hồi và trạng thái riêng từng model.
-   Xử lý lỗi độc lập.

### Giai đoạn 2 -- Hoàn thiện trải nghiệm

-   Streaming độc lập cho từng khung.
-   Sao chép, tạo lại và dừng phản hồi.
-   Lưu và tiếp tục lịch sử hội thoại.
-   Tùy chỉnh bố cục và phóng to khung chat.
-   Responsive cho mobile.

### Giai đoạn 3 -- Tính năng khác biệt

-   Compare AI: so sánh các câu trả lời.
-   AI Synthesis: tổng hợp câu trả lời từ nhiều model.
-   Thống kê tốc độ, token và chi phí.
-   Đánh giá câu trả lời theo tiêu chí do người dùng chọn.

## 9. Tiêu chí nghiệm thu

-   Một lần gửi tạo yêu cầu đến tất cả model đang được chọn.
-   Các model được gọi song song, không phải lần lượt.
-   Mỗi model hiển thị phản hồi trong đúng khung của nó.
-   Một model lỗi không ảnh hưởng đến các model còn lại.
-   Streaming không trộn nội dung giữa các model.
-   Người dùng có thể dừng hoặc tạo lại phản hồi riêng lẻ.
-   Hội thoại được lưu và có thể mở lại.
-   Chi phí, token và trạng thái lỗi được hiển thị khi có dữ liệu.
-   Giao diện sử dụng được trên desktop và mobile.

## 10. Định hướng sản phẩm

MindFlow AI nên phát triển Multi-AI Chat thành một không gian làm việc
với nhiều mô hình AI, tập trung vào ba giá trị:

1.  **Hỏi một lần -- nhận nhiều góc nhìn:** nhiều model cùng xử lý một
    câu hỏi.
2.  **So sánh có cơ sở:** người dùng nhận biết điểm mạnh, điểm yếu và sự
    khác biệt giữa các câu trả lời.
3.  **Tổng hợp thành kết quả:** kết hợp các góc nhìn thành một câu trả
    lời có cấu trúc.

Đây là định hướng giúp MindFlow AI tạo giá trị khác biệt thay vì chỉ là
giao diện tập hợp nhiều chatbot.
