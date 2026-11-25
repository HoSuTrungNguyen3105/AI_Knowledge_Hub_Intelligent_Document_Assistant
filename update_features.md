# UPGRADE AI MODEL & AGENT EVALUATION CENTER – MINDFLOW

## 1. Mục tiêu

Hãy kiểm tra và nâng cấp toàn diện tính năng và có tên là **AI Model & Agent Evaluation Center** ( hiện đang là trang /compare ) hiện đang tồn tại trong website MindFlow.

Hiện tại tính năng đã có nhưng còn sơ sài, chưa đủ chiều sâu để trở thành một hệ thống đánh giá, kiểm thử và giám sát chất lượng AI Model và AI Agent chuyên nghiệp.

Mục tiêu là biến nó thành một nền tảng Evaluation & Observability thực sự, có thể sử dụng để đánh giá các mô hình LLM, so sánh nhiều Model, kiểm tra Agent, theo dõi hiệu suất và phát hiện vấn đề trong quá trình vận hành.

**Yêu cầu quan trọng:**
- Không tạo thêm một trang Evaluation Center mới nếu trang hiện tại đã tồn tại.
- Không xóa bỏ hoặc phá vỡ các tính năng đang hoạt động.
- Không chỉ làm đẹp giao diện. Phải kiểm tra và hoàn thiện cả logic, dữ liệu, API, backend và cơ chế đánh giá.
- Tái sử dụng kiến trúc, component, design system và các module hiện có.
- Không tạo dữ liệu giả để hiển thị thành kết quả đánh giá thật.
- Nếu chưa có API hoặc provider thật, phải thể hiện rõ trạng thái chưa cấu hình.

## 2. Khảo sát hiện trạng trước khi code

Trước tiên hãy đọc source code và xác định:

1. Trang AI Model & Agent Evaluation Center đang nằm ở đâu.
2. Các component, API, service, database và state management liên quan.
3. Những chức năng đã có và những chức năng đang thiếu.
4. Model provider nào đang được tích hợp.
5. Agent nào có thể được đánh giá.
6. Cơ chế lưu lịch sử đánh giá hiện tại.
7. Các vấn đề về UI/UX, hiệu suất, bảo mật và xử lý lỗi.

Sau khi khảo sát, lập danh sách:
- Existing features.
- Missing features.
- Broken features.
- Technical debt.
- Implementation plan.

Sau đó tiến hành nâng cấp trực tiếp.

## 3. Các module cần hoàn thiện

### A. Evaluation Dashboard

Xây dựng dashboard tổng quan với các chỉ số:

- Total Evaluations.
- Total Models Tested.
- Total Agents Evaluated.
- Average Accuracy.
- Average Latency.
- Average Token Usage.
- Average Cost per Evaluation.
- Pass Rate.
- Failure Rate.
- Regression Rate.

Biểu đồ:
- Chất lượng Model theo thời gian.
- So sánh hiệu suất giữa các Model.
- Chi phí sử dụng Model.
- Latency và token usage.
- Tỷ lệ thành công của Agent.
- Chất lượng đánh giá theo từng bộ Dataset.

Cho phép lọc theo thời gian, Model, Agent, Project và Evaluation Run.

Các số liệu phải lấy từ dữ liệu thực tế. Không tự tạo KPI giả.

### B. LLM Model Evaluation

Cho phép đánh giá và so sánh các Model như:

- OpenAI GPT.
- Anthropic Claude.
- Google Gemini.
- Các Model tương thích OpenAI API.
- Local Model nếu hệ thống hỗ trợ.

Các tiêu chí đánh giá:

**Quality**
- Answer Correctness.
- Relevance.
- Faithfulness.
- Context Precision.
- Context Recall.
- Hallucination Rate.
- Instruction Following.

**Performance**
- Time to First Token.
- Total Latency.
- Tokens per Second.
- Input Tokens.
- Output Tokens.

**Cost**
- Input Cost.
- Output Cost.
- Total Cost.
- Cost per Successful Task.

**Reliability**
- Success Rate.
- Timeout Rate.
- Error Rate.
- Retry Rate.

Cho phép chạy cùng một Dataset trên nhiều Model để so sánh kết quả trong cùng điều kiện.

Lưu ý: Các tiêu chí cần có cách đo phù hợp. Không được coi kết quả LLM-as-a-Judge là ground truth. Cần hỗ trợ dữ liệu đáp án chuẩn, assertion hoặc đánh giá của con người khi phù hợp.

### C. Agent Evaluation

Đây là phần quan trọng nhất.

Cho phép kiểm tra Agent không chỉ dựa trên câu trả lời cuối cùng mà còn dựa trên toàn bộ quá trình thực hiện nhiệm vụ.

Các tiêu chí:

- Task Completion Rate.
- Goal Achievement.
- Tool Calling Accuracy.
- Tool Selection Accuracy.
- Planning Quality.
- Reasoning Process Quality.
- Context Retention.
- Memory Retrieval Accuracy.
- Workflow Execution Success.
- Error Recovery.
- Agent Handoff Accuracy.
- Human Intervention Rate.

Mỗi Evaluation Run cần hiển thị:

- Input Task.
- Expected Outcome.
- Actual Output.
- Agent được sử dụng.
- Model được sử dụng.
- Các Tool đã gọi.
- Thời gian thực hiện từng bước.
- Token Usage.
- Chi phí.
- Lỗi phát sinh.
- Kết quả đánh giá.
- Evidence và lý do chấm điểm.

Không được đánh giá Agent chỉ bằng cách kiểm tra câu trả lời cuối cùng.

### D. Dataset Management

Xây dựng khu vực quản lý bộ dữ liệu kiểm thử.

Chức năng:

- Tạo Dataset.
- Chỉnh sửa Dataset.
- Xóa Dataset.
- Import JSON/CSV.
- Export Dataset.
- Quản lý phiên bản Dataset.
- Gắn tag theo lĩnh vực.
- Phân loại theo loại nhiệm vụ.

Ví dụ Dataset:

1. General Question Answering.
2. Coding Tasks.
3. RAG Evaluation.
4. Tool Calling.
5. Multi-Agent Collaboration.
6. Workflow Execution.
7. Customer Support.
8. Structured Output.
9. Vietnamese Language Evaluation.

Mỗi test case cần có:
- Input.
- Expected Output hoặc Expected Behavior.
- Evaluation Criteria.
- Ground Truth nếu có.
- Metadata.
- Tags.

Hỗ trợ chạy thử một test case hoặc toàn bộ Dataset.

### E. Model Comparison Lab

Xây dựng giao diện so sánh Model trực quan.

Cho phép:
- Chọn từ 2 đến 5 Model.
- Chọn Dataset.
- Chọn Evaluation Metrics.
- Chạy cùng một bài kiểm thử trên nhiều Model.
- Xem kết quả song song.

Kết quả hiển thị:

| Metric | Model A | Model B | Model C |
|---|---|---|---|
| Accuracy | Actual | Actual | Actual |
| Latency | Actual | Actual | Actual |
| Cost | Actual | Actual | Actual |
| Hallucination | Actual | Actual | Actual |
| Pass Rate | Actual | Actual | Actual |

Có biểu đồ và phân tích ưu nhược điểm.

Cho phép xác định Model phù hợp nhất theo từng mục tiêu:
- Best Quality.
- Lowest Cost.
- Fastest Response.
- Best Reliability.
- Best Overall Trade-off.

Không mặc định Model đắt nhất là tốt nhất.

### F. Evaluation History & Regression Testing

Lưu toàn bộ lịch sử Evaluation Run.

Cho phép:
- Xem lại từng lần chạy.
- So sánh hai lần đánh giá.
- Phát hiện chất lượng giảm sau khi thay đổi Model.
- Phát hiện regression khi thay đổi Prompt.
- Phát hiện regression khi thay đổi Agent hoặc Tool.
- Theo dõi lịch sử phiên bản.

Ví dụ:

Model GPT sau khi cập nhật Prompt:
- Accuracy giảm 8%.
- Latency tăng 15%.
- Cost tăng 12%.

Hệ thống phải cảnh báo và chỉ rõ các test case bị ảnh hưởng.

Hỗ trợ thiết lập Baseline để làm mốc so sánh.

### G. Prompt Evaluation

Xây dựng chức năng kiểm tra chất lượng Prompt.

- Lưu nhiều phiên bản Prompt.
- Chạy cùng một Dataset trên nhiều Prompt.
- So sánh đầu ra.
- Đánh giá độ chính xác.
- Phát hiện Prompt Regression.
- So sánh chi phí và latency.
- Cho phép chọn phiên bản tốt hơn.

Không tự động thay Prompt production khi chưa có sự phê duyệt.

### H. AI Evaluation Report

Tạo báo cáo sau mỗi Evaluation Run.

Báo cáo cần có:

1. Executive Summary.
2. Evaluation Configuration.
3. Model / Agent Information.
4. Dataset Information.
5. Evaluation Metrics.
6. Performance Analysis.
7. Cost Analysis.
8. Failed Test Cases.
9. Error Analysis.
10. Recommendations.

Cho phép:
- Xuất PDF.
- Xuất Excel/CSV.
- Xuất JSON.
- Chia sẻ báo cáo nếu hệ thống có chức năng phân quyền phù hợp.

## 4. Evaluation Engine và kiến trúc xử lý

Thiết kế Evaluation Engine có khả năng mở rộng.

Quy trình:

1. Người dùng chọn Model hoặc Agent.
2. Chọn Dataset.
3. Chọn Metrics.
4. Tạo Evaluation Run.
5. Engine thực thi test case.
6. Thu thập kết quả và telemetry.
7. Chấm điểm.
8. Lưu kết quả.
9. Tổng hợp báo cáo.
10. So sánh với Baseline.

Yêu cầu kỹ thuật:

- Tách Evaluation Engine khỏi UI.
- Hỗ trợ chạy bất đồng bộ cho các bộ test lớn.
- Có trạng thái Pending, Running, Completed, Failed, Cancelled.
- Có Progress Tracking.
- Có Retry hợp lý.
- Có Timeout.
- Có kiểm soát concurrency.
- Có giới hạn token và chi phí.
- Có khả năng dừng Evaluation Run.
- Không chạy trùng lặp khi người dùng gửi request nhiều lần.
- Lưu đầy đủ execution trace.
- Phân biệt lỗi từ Provider, Model, Agent, Tool và Evaluation Engine.

Có thể sử dụng LangGraph cho các luồng Agent Evaluation phức tạp nếu kiến trúc hiện tại phù hợp. Không bắt buộc sử dụng LangGraph cho mọi bài kiểm thử.

## 5. Observability

Bổ sung khả năng quan sát hoạt động của Model và Agent:

- Trace ID.
- Run ID.
- Model ID.
- Agent ID.
- Prompt Version.
- Tool Calls.
- Latency.
- Token Usage.
- Cost.
- Error Details.
- Retry History.

Cho phép xem chi tiết một Trace theo dạng timeline.

Phải bảo vệ dữ liệu nhạy cảm, API Key và nội dung riêng tư của khách hàng. Không ghi log bí mật hoặc dữ liệu nhạy cảm không cần thiết.

## 6. UI/UX Requirements

Thiết kế lại giao diện theo phong cách Enterprise SaaS hiện đại.

Yêu cầu:
- Chuyên nghiệp, rõ ràng, trực quan.
- Không nhồi nhét quá nhiều thông tin.
- Có hệ thống Tabs hoặc Sidebar hợp lý.
- Có bộ lọc và tìm kiếm.
- Có bảng dữ liệu chuyên nghiệp.
- Có biểu đồ dễ đọc.
- Có Detail View cho từng Evaluation Run.
- Có Loading, Empty, Error và Success States.
- Responsive Desktop, Tablet và Mobile.
- Tái sử dụng design system hiện tại của MindFlow.

Đề xuất cấu trúc:

1. Overview.
2. Model Evaluation.
3. Agent Evaluation.
4. Comparison Lab.
5. Datasets.
6. Prompt Evaluation.
7. History & Regression.
8. Traces & Observability.
9. Reports.
10. Settings.

Không nhất thiết tạo tất cả thành các trang độc lập. Có thể tổ chức dưới dạng tab hoặc sub-navigation nếu phù hợp với kiến trúc hiện tại.

## 7. Testing và Acceptance Criteria

Phải kiểm thử thực tế:

- Đánh giá một Model.
- So sánh nhiều Model.
- Đánh giá một Agent.
- Kiểm thử Tool Calling.
- Kiểm thử RAG.
- Kiểm thử Structured Output.
- Import Dataset.
- Export Dataset.
- Lưu Evaluation History.
- Phát hiện Regression.
- So sánh Prompt.
- Xử lý Provider Timeout.
- Xử lý API Error.
- Retry và Cancel Run.
- Giới hạn chi phí.
- Kiểm tra quyền truy cập dữ liệu.
- Kiểm tra giao diện Responsive.

Không được đánh dấu chức năng Completed nếu chỉ có giao diện mà chưa có logic thực thi.

## 8. Báo cáo và bàn giao

Sau khi hoàn thành:

1. Chạy build và kiểm tra lỗi.
2. Chạy các test liên quan.
3. Kiểm tra lại các chức năng cũ.
4. Ghi lại những chức năng đã hoàn thành.
5. Ghi lại chức năng chưa thể hoàn thiện do thiếu API, provider hoặc cấu hình.
6. Xuất báo cáo Word (.docx) chuyên nghiệp, có:
   - Tổng quan hệ thống.
   - Các chức năng đã nâng cấp.
   - Kiến trúc kỹ thuật.
   - Database/API thay đổi.
   - Hướng dẫn sử dụng.
   - Kết quả kiểm thử.
   - Hạn chế còn tồn tại.
   - Hướng phát triển tiếp theo.
7. Đóng gói source code và báo cáo Word thành file ZIP.

ZIP cần chứa source code cần thiết, tài liệu, báo cáo và file cấu hình mẫu `.env.example`.

Không đưa `node_modules`, API Key, mật khẩu, token hoặc thông tin bí mật vào ZIP.

## 9. Nguyên tắc thực hiện

Đây là nhiệm vụ nâng cấp một sản phẩm đang tồn tại, không phải tạo một prototype mới.

Ưu tiên:
- Tính chính xác.
- Khả năng kiểm chứng.
- Khả năng mở rộng.
- Hiệu quả thực tế.
- Bảo mật.
- Trải nghiệm người dùng.

Hãy bắt đầu bằng việc khảo sát source code, lập kế hoạch nâng cấp, sau đó triển khai trực tiếp trên hệ thống hiện tại.

**Kết quả cuối cùng phải là một AI Model & Agent Evaluation Center có thể thực sự chạy kiểm thử, đo lường, so sánh, phát hiện lỗi và đánh giá chất lượng AI — không chỉ là một dashboard đẹp với các con số minh họa.**