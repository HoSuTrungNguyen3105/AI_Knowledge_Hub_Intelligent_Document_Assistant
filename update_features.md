# YÊU CẦU: NÂNG CẤP VÀ TÍCH HỢP CÁC TÍNH NĂNG AI VÀO HỆ THỐNG HIỆN TẠI

## 1. Mục tiêu

Tôi muốn phát triển hệ thống hiện tại thành một nền tảng AI cá nhân có tên tạm thời là **MindFlow AI**.

Đây là một AI Workspace cho phép người dùng kết nối và sử dụng nhiều AI Provider, tạo AI Assistant riêng, so sánh kết quả từ nhiều mô hình AI, phân tích tài liệu và tự động hóa các tác vụ.

**Lưu ý quan trọng:**
- Không tạo project mới.
- Không xóa hoặc viết lại toàn bộ hệ thống hiện tại.
- Không tự ý thay đổi công nghệ đang sử dụng.
- Không làm hỏng các chức năng đã hoàn thiện.
- Phải kiểm tra toàn bộ source code trước khi đưa ra phương án tích hợp.
- Tái sử dụng component, API, database và logic hiện có nếu phù hợp.
- Chỉ thay đổi những phần thực sự cần thiết.

## 2. Giai đoạn đầu: Phân tích hệ thống

Trước khi lập trình, hãy kiểm tra:

1. Cấu trúc thư mục frontend và backend.
2. Framework, thư viện và phiên bản đang sử dụng.
3. Cách tổ chức component và routing.
4. Cơ chế authentication và authorization.
5. Database, ORM và cấu trúc bảng hiện tại.
6. Cách frontend gọi API.
7. Các service, middleware và những chức năng đã có.
8. Những phần có thể tái sử dụng để tích hợp AI.

Sau khi kiểm tra, hãy lập bảng:

| Hạng mục | Hiện trạng | Phương án |
|---|---|---|
| Frontend | Đang sử dụng gì | Giữ nguyên hoặc nâng cấp |
| Backend | Đang sử dụng gì | Giữ nguyên hoặc mở rộng |
| Database | Đang sử dụng gì | Bổ sung bảng nếu cần |
| Authentication | Đang hoạt động thế nào | Tái sử dụng |
| AI Integration | Đã có hay chưa | Xây dựng hoặc mở rộng |
| API | Cấu trúc hiện tại | Bổ sung endpoint |

Không được bắt đầu viết code lớn khi chưa hiểu kiến trúc hiện tại.

## 3. Các tính năng cần tích hợp

### MODULE 1: AI PROVIDER MANAGEMENT

Cho phép người dùng kết nối nhiều nhà cung cấp AI.

Các provider dự kiến:
- OpenAI
- Google Gemini
- Anthropic Claude
- DeepSeek
- Ollama (Local AI)

Chức năng:
- Danh sách AI Provider.
- Thêm API Key.
- Kiểm tra kết nối.
- Lựa chọn model mặc định.
- Bật/tắt từng provider.
- Hiển thị trạng thái kết nối.
- Quản lý model được hỗ trợ.
- Quản lý API Key an toàn.

Yêu cầu:
- API Key chỉ được xử lý ở backend.
- Không lưu API Key dạng plaintext.
- Mã hóa API Key khi lưu database.
- Không trả API Key về frontend.
- Không hardcode API Key trong source code.

### MODULE 2: MULTI-MODEL AI CHAT

Xây dựng giao diện trò chuyện với nhiều mô hình AI.

Chức năng:
- Tạo cuộc trò chuyện mới.
- Chọn AI Provider.
- Chọn AI Model.
- Gửi và nhận tin nhắn.
- Streaming câu trả lời.
- Lưu lịch sử trò chuyện.
- Xem lại cuộc trò chuyện.
- Xóa và đổi tên cuộc trò chuyện.
- Regenerate câu trả lời.
- Copy nội dung.
- Hiển thị Markdown và code block.
- Upload file để AI phân tích.
- Cấu hình System Prompt.
- Cấu hình Temperature và giới hạn token.

### MODULE 3: MULTI-AI COMPARISON

Đây là một trong những tính năng quan trọng nhất của hệ thống.

Cho phép người dùng gửi cùng một câu hỏi đến nhiều AI Model cùng lúc.

Ví dụ:

Người dùng nhập:
"Giải thích kiến trúc Microservices và đưa ra ví dụ thực tế."

Hệ thống gửi câu hỏi đến:
- GPT
- Gemini
- Claude
- DeepSeek

Hiển thị kết quả dưới dạng nhiều cột hoặc các tab riêng biệt.

Thông tin cần hiển thị:
- Tên AI Provider.
- Model đang sử dụng.
- Nội dung trả lời.
- Thời gian phản hồi.
- Token usage nếu provider hỗ trợ.
- Chi phí ước tính nếu có dữ liệu giá.
- Trạng thái thành công/thất bại.

Có thêm chức năng:

**AI Synthesis:**
Cho phép chọn chức năng tổng hợp câu trả lời từ nhiều AI thành một câu trả lời cuối cùng.

Không để một provider lỗi làm toàn bộ quá trình so sánh thất bại.

### MODULE 4: AI AGENT STUDIO

Cho phép người dùng tự tạo AI Assistant của riêng mình.

Thông tin Agent:
- Name.
- Description.
- Avatar.
- System Prompt.
- Provider.
- Model.
- Temperature.
- Knowledge Base.
- Tools.
- Memory.

Ví dụ Agent:

1. Coding Assistant:
   Hỗ trợ lập trình, phân tích code và tìm lỗi.

2. Research Assistant:
   Hỗ trợ nghiên cứu và tổng hợp thông tin.

3. Business Assistant:
   Phân tích ý tưởng kinh doanh và lập kế hoạch.

4. Document Assistant:
   Đọc và phân tích tài liệu.

5. Personal Assistant:
   Hỗ trợ quản lý công việc và thông tin cá nhân.

Người dùng có thể tạo, chỉnh sửa, nhân bản và xóa Agent.

### MODULE 5: AI AGENT EXECUTION

Agent không chỉ trả lời câu hỏi mà phải có khả năng sử dụng công cụ.

Xây dựng cơ chế Function Calling / Tool Calling.

Các tool ban đầu:

- Calculator: Tính toán.
- DateTime: Xử lý ngày giờ.
- Document Search: Tìm kiếm tài liệu.
- Knowledge Search: Tìm kiếm dữ liệu trong Knowledge Base.
- Web Search: Tìm kiếm thông tin trên Internet thông qua dịch vụ tìm kiếm được cấu hình.
- Text Summarizer: Tóm tắt nội dung.
- Data Analyzer: Phân tích dữ liệu được cung cấp.

Luồng hoạt động:

1. Người dùng gửi yêu cầu.
2. AI phân tích yêu cầu.
3. AI xác định có cần sử dụng tool không.
4. Backend kiểm tra quyền và tham số.
5. Backend thực thi tool.
6. Kết quả được trả về AI.
7. AI tiếp tục xử lý.
8. Trả kết quả cuối cùng cho người dùng.

Phải có:
- Giới hạn số bước thực thi.
- Timeout.
- Token budget.
- Kiểm tra quyền sử dụng tool.
- Ghi lại lịch sử thực thi.
- Không cho phép thực thi code hoặc lệnh hệ thống tùy ý.

### MODULE 6: AI FILE INTELLIGENCE

Cho phép người dùng upload và phân tích tài liệu.

Hỗ trợ:
- PDF.
- DOCX.
- TXT.
- CSV.
- XLSX.

Chức năng:
- Tóm tắt tài liệu.
- Hỏi đáp dựa trên tài liệu.
- Trích xuất thông tin.
- So sánh nhiều tài liệu.
- Tạo báo cáo.
- Tìm kiếm nội dung.

### MODULE 7: RAG KNOWLEDGE BASE

Xây dựng hệ thống Knowledge Base cho từng người dùng.

Quy trình:

1. Upload tài liệu.
2. Trích xuất nội dung.
3. Làm sạch dữ liệu.
4. Chia nội dung thành các chunks.
5. Tạo embeddings.
6. Lưu vector vào PostgreSQL + pgvector.
7. Khi người dùng hỏi, thực hiện similarity search.
8. Lấy những đoạn liên quan.
9. Đưa context vào AI Model.
10. Trả lời kèm nguồn trích dẫn.

Mỗi người dùng phải có dữ liệu riêng biệt.

### MODULE 8: AI MEMORY

Xây dựng bộ nhớ cho AI.

Phân loại:
- User Preferences.
- Project Context.
- Important Facts.
- Conversation Summaries.
- Long-term Memory.

AI có thể sử dụng thông tin phù hợp từ các cuộc trò chuyện trước để trả lời tốt hơn.

Người dùng có thể:
- Xem Memory.
- Chỉnh sửa Memory.
- Xóa Memory.
- Tắt Memory.

Không tự động lưu thông tin nhạy cảm nếu chưa có cơ chế đồng ý phù hợp.

### MODULE 9: AI RESEARCH ASSISTANT

Cho phép người dùng nhập một chủ đề và yêu cầu AI nghiên cứu.

Quy trình:
1. Phân tích chủ đề.
2. Chia thành các câu hỏi nhỏ.
3. Tìm kiếm thông tin.
4. Thu thập nguồn.
5. Đối chiếu thông tin.
6. Tổng hợp kết quả.
7. Tạo báo cáo.

Báo cáo cần có:
- Overview.
- Key Findings.
- Detailed Analysis.
- Advantages / Disadvantages.
- Conclusion.
- References.

Không được tự tạo nguồn hoặc bịa citation.

### MODULE 10: USAGE & COST MANAGEMENT

Theo dõi hoạt động sử dụng AI.

Hiển thị:
- Tổng số request.
- Token input.
- Token output.
- Provider.
- Model.
- Thời gian phản hồi.
- Chi phí ước tính.
- Lịch sử sử dụng.
- Lỗi API.

Phải phân biệt chi phí ước tính với chi phí thực tế được provider xác nhận.

## 4. Kiến trúc AI Provider

Không viết logic gọi từng AI trực tiếp trong các API endpoint.

Hãy xây dựng Provider Adapter Architecture.

Ví dụ:

AI Provider Interface
    |
    |-- OpenAI Adapter
    |-- Gemini Adapter
    |-- Claude Adapter
    |-- DeepSeek Adapter
    |-- Ollama Adapter

Các provider cần có interface thống nhất cho những chức năng được hỗ trợ:

- Chat.
- Streaming.
- Model Information.
- Token Usage.
- Function Calling.
- Error Handling.

Không giả định mọi provider hỗ trợ đầy đủ các tính năng giống nhau. Phải kiểm tra capabilities của từng model.

## 5. Yêu cầu về giao diện

Thiết kế theo phong cách AI SaaS hiện đại.

Các khu vực chính:

### Sidebar
- Dashboard.
- AI Chat.
- Compare AI.
- AI Agents.
- AI Research.
- Knowledge Base.
- Files.
- Workflows.
- Usage & Costs.
- Settings.

### Dashboard
Hiển thị:
- Tổng số cuộc trò chuyện.
- Số AI Agent.
- Số tài liệu.
- Tổng token usage.
- Chi phí ước tính.
- Các hoạt động gần đây.
- AI Model được sử dụng nhiều nhất.

### AI Chat
Giao diện tương tự các nền tảng AI Chat hiện đại.

### Compare AI
Giao diện so sánh nhiều AI Model trực quan, dễ theo dõi.

### AI Agents
Quản lý và tạo các AI Assistant.

### Settings
Quản lý tài khoản, API Key, Provider, Model và Memory.

Yêu cầu UI:
- Responsive Desktop, Tablet, Mobile.
- Loading State.
- Empty State.
- Error State.
- Skeleton Loading.
- Toast Notification.
- Modal xác nhận khi xóa.
- Không sử dụng dữ liệu giả khi đã kết nối API thật.

## 6. Database

Kiểm tra database hiện tại trước khi thay đổi.

Nếu cần, bổ sung các bảng tương ứng:

- ai_providers
- user_provider_credentials
- ai_models
- conversations
- messages
- agents
- agent_tools
- agent_executions
- tool_executions
- knowledge_bases
- documents
- document_chunks
- memories
- workflows
- workflow_nodes
- workflow_executions
- usage_logs

Không tạo bảng trùng với những bảng hiện có.

Sử dụng migration để quản lý thay đổi database.

## 7. Quy tắc lập trình

- Giữ nguyên công nghệ hiện tại nếu không có lý do thực sự cần thay đổi.
- Frontend sử dụng JavaScript/JSX nếu dự án đang dùng JavaScript.
- Nếu backend hiện tại đã có framework phù hợp, ưu tiên mở rộng thay vì chuyển đổi.
- Nếu chưa có backend Python và không có ràng buộc hiện tại, có thể sử dụng FastAPI.
- Không đặt business logic trực tiếp trong React component.
- Tách service, repository, controller/API và provider adapter.
- Không hardcode API Key.
- Không tạo dữ liệu giả để thay thế API thật.
- Không viết một file chứa quá nhiều logic.
- Xử lý đầy đủ loading, error và empty state.
- Có validation ở frontend và backend.
- Bảo vệ dữ liệu giữa các user.
- Không làm ảnh hưởng các tính năng đang hoạt động.
- Có test cho các chức năng quan trọng.

## 8. Lộ trình triển khai

Không triển khai tất cả cùng một lúc.

### Phase 1: Foundation
- Phân tích hệ thống.
- Authentication.
- Dashboard.
- Database.
- AI Provider Architecture.

### Phase 2: Multi-AI Integration
- Kết nối Gemini.
- Kết nối OpenAI.
- Provider Management.
- Model Management.
- Test Connection.

### Phase 3: AI Chat
- Multi-Model Chat.
- Streaming.
- Conversation History.
- Model Selection.

### Phase 4: Multi-AI Comparison
- Gửi request song song.
- Hiển thị nhiều kết quả.
- AI Synthesis.
- Token và cost tracking.

### Phase 5: AI Agent
- Agent Studio.
- Function Calling.
- Tool Management.
- Agent Execution History.

### Phase 6: RAG & Memory
- File Upload.
- Knowledge Base.
- Embeddings.
- Vector Search.
- AI Memory.

### Phase 7: Research & Workflow
- Research Assistant.
- Web Search.
- Workflow Automation.

### Phase 8: Production
- Testing.
- Security.
- Performance.
- Logging.
- Deployment.

## 9. Cách làm việc bắt buộc

Hãy thực hiện theo quy trình:

**Bước 1:** Phân tích source code hiện tại.

**Bước 2:** Báo cáo kiến trúc hiện tại và các phần cần thay đổi.

**Bước 3:** Đề xuất cấu trúc tích hợp phù hợp với project.

**Bước 4:** Liệt kê những file cần tạo, sửa và giữ nguyên.

**Bước 5:** Chia công việc thành từng Phase và Task nhỏ.

**Bước 6:** Triển khai từng Phase, không triển khai ồ ạt.

**Bước 7:** Sau mỗi Phase:
- Kiểm tra lỗi.
- Chạy test.
- Kiểm tra API.
- Kiểm tra giao diện.
- Đảm bảo tính năng cũ vẫn hoạt động.
- Báo cáo những gì đã hoàn thành và những gì còn thiếu.

**Bước 8:** Chỉ chuyển sang Phase tiếp theo khi Phase hiện tại đã hoạt động ổn định.

## 10. Kết quả mong muốn

Tôi muốn biến hệ thống hiện tại thành một nền tảng AI cá nhân có khả năng:

1. Kết nối nhiều AI Provider.
2. Chat với nhiều AI Model.
3. So sánh câu trả lời từ nhiều AI.
4. Tạo AI Assistant riêng.
5. Cho AI sử dụng Tools thông qua Function Calling.
6. Phân tích và tìm kiếm tài liệu.
7. Xây dựng Knowledge Base bằng RAG.
8. Lưu Memory.
9. Nghiên cứu và tổng hợp thông tin.
10. Tự động hóa các tác vụ.

Đây phải là một sản phẩm có chức năng thực tế, có thể sử dụng được, có kiến trúc mở rộng và có thể phát triển thành sản phẩm thương mại trong tương lai.

**Ưu tiên cao nhất:** Tích hợp thành công Multi-AI Chat, Multi-AI Comparison và AI Agent trước. Những module còn lại triển khai sau.