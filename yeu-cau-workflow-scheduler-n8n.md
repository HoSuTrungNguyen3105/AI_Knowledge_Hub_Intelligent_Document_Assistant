# Đặc tả chức năng: Workflow Scheduler -- Cấu hình lịch chạy tự động bằng n8n

**Vị trí:** Module riêng trong Automation Center, tích hợp với hệ thống
`/agents/workflows/...`.

**Mục tiêu:** Cho phép người dùng cấu hình thời gian và điều kiện kích
hoạt workflow. Đến thời điểm đã đặt, n8n tự động thực thi workflow mà
không cần người dùng mở website.

## 1. Mục tiêu và phạm vi

Xây dựng trang Workflow Scheduler để người dùng: - Chọn workflow đã tồn
tại. - Cấu hình lịch chạy một lần hoặc lặp lại. - Chọn múi giờ. - Bật,
tạm dừng, chỉnh sửa hoặc xóa lịch. - Chạy workflow ngay lập tức (Run
Now). - Theo dõi lần chạy tiếp theo và lịch sử thực thi. - Nhận thông
báo khi workflow thành công hoặc thất bại.

Đây là trang quản lý lịch chạy cho workflow hiện có, không phải trang
tạo workflow n8n từ đầu. Không tạo workflow hoặc Agent trùng lặp nếu hệ
thống đã có thành phần tương đương.

## 2. Các loại lịch cần hỗ trợ

  Loại lịch               Mô tả                                     Ví dụ
  ----------------------- ----------------------------------------- -----------------------
  Một lần                 Chạy tại ngày và giờ cụ thể               14:00 ngày 28/11/2026
  Hằng ngày               Chạy mỗi ngày vào giờ đặt trước           08:00 mỗi ngày
  Hằng tuần               Chạy vào một hoặc nhiều ngày trong tuần   09:00 thứ Hai
  Hằng tháng              Chạy vào ngày cụ thể trong tháng          Ngày 1 lúc 08:00
  Theo khoảng thời gian   Chạy lặp lại theo số phút/giờ             Mỗi 30 phút
  Cron tùy chỉnh          Người dùng nhập biểu thức Cron            `0 8 * * 1-5`

Yêu cầu: - Hỗ trợ timezone, mặc định `Asia/Ho_Chi_Minh`. - Hiển thị rõ
giờ địa phương. - Kiểm tra dữ liệu lịch trước khi lưu. - Xác định hành
vi cho ngày 29, 30, 31 khi tháng không có ngày tương ứng. - Lịch một lần
không được chọn thời điểm đã qua. - Không tự ý thay đổi timezone khi
chỉnh sửa lịch.

## 3. Giao diện trang Scheduler

Giữ nguyên layout, màu sắc, component và quy ước routing hiện tại.

### 3.1. Dashboard tổng quan

Hiển thị: - Tổng số lịch. - Số lịch đang hoạt động. - Số lịch tạm
dừng. - Số lần thực thi thành công. - Số lần thực thi thất bại. - Các
lần chạy sắp tới.

### 3.2. Danh sách lịch

Mỗi lịch hiển thị: - Tên lịch và mô tả. - Workflow được liên kết. - Tần
suất, thời gian và timezone. - Trạng thái: Active, Paused, Completed,
Error. - Lần chạy gần nhất và lần chạy tiếp theo. - Kết quả thực thi gần
nhất.

Thao tác: - Tạo lịch mới, xem chi tiết, chỉnh sửa. - Bật/tắt lịch. -
Chạy ngay (Run Now). - Xem lịch sử thực thi. - Xóa lịch (có xác nhận).

Có bộ lọc theo trạng thái, workflow, tần suất và tìm kiếm theo tên.

## 4. Form tạo và chỉnh sửa lịch

### 4.1. Thông tin cơ bản

-   Tên lịch, mô tả.
-   Chọn workflow đã tồn tại.
-   Trạng thái ban đầu Active hoặc Paused.
-   Chỉ hiển thị workflow người dùng có quyền truy cập và đủ điều kiện
    kích hoạt.

### 4.2. Cấu hình thời gian

-   Một lần: ngày và giờ.
-   Hằng ngày: giờ và phút.
-   Hằng tuần: một hoặc nhiều ngày trong tuần, giờ và phút.
-   Hằng tháng: ngày trong tháng, giờ và phút.
-   Khoảng thời gian: số phút hoặc giờ giữa hai lần.
-   Cron: biểu thức Cron và giải thích lịch chạy.

### 4.3. Tùy chọn bổ sung

-   Múi giờ.
-   Thời điểm bắt đầu và kết thúc hiệu lực.
-   Thông báo khi thành công/thất bại.
-   Giới hạn số lần chạy nếu cần.
-   Chính sách khi lần chạy trước chưa hoàn thành.

### 4.4. Xem trước lịch

Trước khi lưu, hiển thị: - Tóm tắt cấu hình. - 5--10 thời điểm chạy tiếp
theo. - Timezone áp dụng. - Cảnh báo nếu Cron không hợp lệ hoặc lịch
không khả thi.

Không chỉ hiển thị Cron; cần giải thích bằng ngôn ngữ dễ hiểu.

## 5. Cơ chế thực thi với n8n

### 5.1. Luồng tổng thể

1.  Người dùng tạo hoặc chỉnh sửa lịch trên frontend.
2.  Frontend gửi cấu hình đến NestJS Backend.
3.  Backend xác thực người dùng, workflow và dữ liệu lịch.
4.  Backend lưu cấu hình vào database.
5.  Backend đồng bộ lịch với cơ chế kích hoạt n8n đã chọn.
6.  Đến thời điểm cần chạy, scheduler kích hoạt workflow tương ứng trong
    n8n.
7.  n8n thực thi các node, Agent và tích hợp dịch vụ.
8.  n8n gửi kết quả thực thi về backend.
9.  Backend cập nhật lịch sử và trạng thái.
10. Frontend nhận cập nhật qua realtime hiện có hoặc polling.

Không yêu cầu người dùng mở website để lịch được kích hoạt.

### 5.2. Trách nhiệm thành phần

  -----------------------------------------------------------------------
  Thành phần                          Trách nhiệm
  ----------------------------------- -----------------------------------
  Frontend                            Cấu hình lịch, hiển thị trạng thái
                                      và lịch sử

  NestJS Backend                      Authentication, phân quyền, lưu cấu
                                      hình, quản lý trạng thái

  Scheduler                           Tính toán thời điểm đến hạn và kích
                                      hoạt đúng lịch

  n8n                                 Thực thi workflow, tích hợp dịch
                                      vụ, xử lý tự động

  AI Agents                           Phân tích và xử lý nhiệm vụ

  Database                            Lưu lịch, execution, trạng thái và
                                      lịch sử
  -----------------------------------------------------------------------

Không để frontend tự kích hoạt lịch bằng timer trình duyệt. Không phụ
thuộc frontend đang mở.

### 5.3. Chọn một phương án tích hợp

**Phương án A -- n8n Schedule Trigger** - Cấu hình Schedule Trigger cho
workflow. - Đồng bộ biểu thức lịch và timezone. - Publish workflow để
lịch có hiệu lực. - Backend cập nhật khi người dùng sửa hoặc tạm dừng
lịch.

**Phương án B -- Backend Central Scheduler + n8n Webhook** - Backend lưu
lịch trong database. - Scheduler phía server kiểm tra lịch đến hạn. -
Đến giờ, backend gọi webhook của workflow n8n. - n8n thực thi và
callback kết quả về backend.

Phương án B phù hợp khi cần quản lý nhiều lịch tập trung, nhưng phải có
scheduler bền vững, khóa chống chạy trùng và phục hồi sau restart.

Không kích hoạt đồng thời cả hai phương án cho cùng một lịch.

## 6. Trạng thái và lịch sử thực thi

### 6.1. Trạng thái lịch

  Trạng thái    Ý nghĩa
  ------------- ---------------------------
  `active`      Lịch đang hoạt động
  `paused`      Lịch tạm dừng
  `completed`   Lịch một lần đã chạy xong
  `error`       Lỗi cấu hình hoặc đồng bộ

### 6.2. Trạng thái execution

  Trạng thái    Ý nghĩa
  ------------- ------------------------
  `pending`     Đang chờ
  `running`     Đang chạy
  `success`     Hoàn thành
  `failed`      Thất bại
  `cancelled`   Đã hủy
  `skipped`     Bỏ qua theo chính sách

### 6.3. Execution History

Ghi nhận: - Schedule ID, Workflow ID, n8n Execution ID. - Thời điểm dự
kiến, bắt đầu và kết thúc. - Trạng thái và thời gian thực thi. - Lý do
thất bại, log phù hợp. - Số lần retry. - Kết quả hoặc liên kết tới kết
quả.

Cho phép xem chi tiết từng execution.

## 7. Quản lý lịch

### Pause / Resume

-   Pause ngừng các lần chạy trong tương lai, không xóa cấu hình.
-   Resume tiếp tục theo lịch đã lưu.
-   Không tự chạy bù các lần bị bỏ lỡ, trừ khi có chính sách chạy bù
    được chọn.

### Run Now

-   Kích hoạt workflow ngay.
-   Không làm thay đổi lịch định kỳ.
-   Ghi nhận là `manual` execution.
-   Áp dụng kiểm tra quyền và chống chạy trùng.

### Retry

-   Cho phép thử lại execution thất bại nếu workflow hỗ trợ.
-   Giới hạn số lần retry và khoảng chờ.
-   Không retry vô hạn.
-   Không lặp lại hành động có nguy cơ tạo giao dịch hoặc gửi thông báo
    trùng nếu chưa có idempotency.

### Delete

-   Có xác nhận.
-   Dừng cơ chế kích hoạt tương ứng.
-   Giữ lịch sử execution theo chính sách lưu trữ.
-   Không xóa workflow gốc.

## 8. Chống chạy trùng và xử lý sự cố

Hỗ trợ chính sách khi lần trước chưa hoàn thành: - `skip`: bỏ qua lần
mới. - `queue`: xếp lần mới vào hàng đợi. - `allow_parallel`: cho phép
chạy song song nếu workflow hỗ trợ.

Yêu cầu: - Mỗi execution có ID duy nhất. - Dùng idempotency key cho từng
lịch và thời điểm dự kiến. - Có khóa hoặc transaction tránh hai
scheduler kích hoạt cùng một lần. - Phục hồi lịch sau khi backend
restart. - Có chính sách xử lý lịch bị lỡ khi server ngừng hoạt động. -
Theo dõi lỗi đồng bộ backend/n8n. - Không đánh dấu thành công khi chưa
có xác nhận phù hợp.

## 9. Thông báo

Hỗ trợ các kênh hệ thống đã tích hợp: thông báo website, Email, Zalo OA,
Telegram hoặc Slack.

Các sự kiện: - Workflow bắt đầu. - Hoàn thành hoặc thất bại. - Bị bỏ
qua. - Cần người dùng phê duyệt. - Lịch không thể đồng bộ với n8n.

Không hardcode credential trong frontend.

## 10. API tham khảo

Điều chỉnh theo quy ước API hiện tại. Không tạo endpoint trùng chức
năng.

  Method     Endpoint tham khảo                                 Chức năng
  ---------- -------------------------------------------------- --------------------
  `GET`      `/api/workflow-schedules`                          Danh sách lịch
  `POST`     `/api/workflow-schedules`                          Tạo lịch
  `GET`      `/api/workflow-schedules/:id`                      Chi tiết
  `PATCH`    `/api/workflow-schedules/:id`                      Chỉnh sửa
  `POST`     `/api/workflow-schedules/:id/pause`                Tạm dừng
  `POST`     `/api/workflow-schedules/:id/resume`               Kích hoạt lại
  `POST`     `/api/workflow-schedules/:id/run-now`              Chạy ngay
  `DELETE`   `/api/workflow-schedules/:id`                      Xóa
  `GET`      `/api/workflow-schedules/:id/executions`           Lịch sử
  `GET`      `/api/workflow-schedules/:id/next-runs`            Lần chạy tiếp theo
  `POST`     `/api/workflow-schedules/:id/retry/:executionId`   Thử lại

Các API cần authentication, authorization, validation và kiểm tra quyền
truy cập workflow.

## 11. Dữ liệu lưu trữ tham khảo

### WorkflowSchedule

-   `id`
-   `name`
-   `description`
-   `workflow_id`
-   `schedule_type`
-   `cron_expression` (nullable)
-   `schedule_config`
-   `timezone`
-   `start_at`, `end_at` (nullable)
-   `status`
-   `concurrency_policy`
-   `notify_on_success`
-   `notify_on_failure`
-   `next_run_at`, `last_run_at`
-   `created_by`
-   `created_at`, `updated_at`

### WorkflowScheduleExecution

-   `id`
-   `schedule_id`
-   `workflow_id`
-   `n8n_execution_id` (nullable)
-   `idempotency_key`
-   `trigger_type` (`scheduled` hoặc `manual`)
-   `scheduled_for`
-   `started_at`, `finished_at`
-   `status`
-   `duration_ms`
-   `retry_count`
-   `error_message`
-   `result_summary`

Kiểu dữ liệu cuối cùng phải tuân theo convention database hiện tại.

## 12. Bảo mật và vận hành

-   Không đưa n8n API key, webhook secret hoặc credential ra frontend.
-   Backend giữ thông tin xác thực và gọi n8n.
-   Phân quyền theo workflow và schedule.
-   Xác thực webhook callback từ n8n.
-   Giới hạn tần suất tạo lịch và số execution.
-   Ghi audit log cho thao tác tạo, sửa, pause, resume, run now và xóa.
-   Không cho người dùng nhập URL tùy ý để backend gọi nếu chưa có kiểm
    soát SSRF.
-   Không để lịch lỗi tạo vòng lặp kích hoạt vô hạn.
-   Scheduler phải chạy trên server luôn hoạt động, không phụ thuộc máy
    người dùng.

## 13. Tiêu chí nghiệm thu

-   [ ] Có trang Workflow Scheduler tích hợp vào hệ thống.
-   [ ] Có dashboard thống kê và danh sách lịch.
-   [ ] Có bộ lọc và tìm kiếm.
-   [ ] Tạo được lịch một lần, ngày, tuần và tháng.
-   [ ] Hỗ trợ khoảng thời gian và Cron tùy chỉnh.
-   [ ] Hỗ trợ timezone, mặc định múi giờ Việt Nam.
-   [ ] Hiển thị các lần chạy tiếp theo.
-   [ ] Lịch kích hoạt khi website đóng.
-   [ ] Pause/Resume không mất cấu hình.
-   [ ] Có Run Now.
-   [ ] Có execution history và log lỗi.
-   [ ] Có chính sách skip/queue/parallel.
-   [ ] Có chống chạy trùng và retry có giới hạn.
-   [ ] Có thông báo theo cấu hình.
-   [ ] Có phân quyền và bảo vệ credential.
-   [ ] Phục hồi lịch đúng sau khi backend restart.
-   [ ] Không tạo hai cơ chế trigger cho cùng một lịch.

## 14. Thứ tự triển khai

### Giai đoạn 1 -- Schedule Configuration

-   Trang danh sách lịch.
-   Form tạo/chỉnh sửa.
-   Lịch một lần, ngày, tuần, tháng.
-   Timezone.
-   Lưu database.

### Giai đoạn 2 -- n8n Integration

-   Chọn một cơ chế kích hoạt thống nhất.
-   Đồng bộ lịch và trạng thái.
-   Kích hoạt đúng thời điểm.
-   Callback kết quả về backend.

### Giai đoạn 3 -- Execution Management

-   Lịch sử thực thi.
-   Run Now, Pause/Resume.
-   Retry.
-   Chống chạy trùng và xử lý lịch bị lỡ.

### Giai đoạn 4 -- Advanced Automation

-   Cron tùy chỉnh và khoảng thời gian.
-   Notification.
-   Human Approval.
-   Thống kê hiệu suất và chi phí.

## 15. Yêu cầu trước khi code

Trước khi triển khai, kiểm tra: 1. Cấu trúc frontend và route hiện tại.
2. Các workflow đã có. 3. Cách NestJS đang giao tiếp với n8n. 4. Mapping
workflow ID trong hệ thống và n8n. 5. Database schema và authentication.
6. Cách nhận execution status và callback. 7. Cơ chế deploy n8n hiện
tại.

Không tự ý tạo scheduler thứ hai nếu đã có cơ chế tương đương. Chọn một
kiến trúc thực thi duy nhất, tích hợp backend hiện tại, giữ nguyên chức
năng đang hoạt động và triển khai theo từng giai đoạn.

**Kết quả mong muốn:** Người dùng cấu hình lịch một lần trên website; hệ
thống tự động kích hoạt workflow bằng n8n đúng thời điểm, lưu lịch sử và
cho phép quản lý toàn bộ quá trình ngay trên website.
