# FEATURE SPECIFICATION: CODEBASE ARCHITECTURE ANALYZER (MINDFLOW AI MODULE)

## 1. Bối cảnh & Định hướng tích hợp
- **Mục tiêu:** Tích hợp trực tiếp tính năng **Codebase Architecture & Dependency Analyzer** thành một trang/module mới bên trong hệ thống **MINDFlow AI** hiện tại (tuyệt đối không khởi tạo repository hay project mới).
- **Tận dụng hạ tầng sẵn có của MINDFlow AI:**
  - Tái sử dụng hệ thống Authentication, Layout chung (Sidebar/Header), UI Components, cấu hình kết nối **MongoDB** (Mongoose), cấu hình LLM và **n8n Webhook** hiện đang chạy trong dự án.
  - Khai thác dữ liệu/ngữ cảnh sẵn có trên MINDFlow AI (ví dụ: user hiện tại, workspace, API keys, lịch sử phân tích hoặc các node/workflow liên quan) để đồng bộ trải nghiệm người dùng.

---

## 2. Yêu cầu kỹ thuật & Quy tắc phát triển cho AI Coding
Trước khi viết code, AI cần quét cấu trúc thư mục hiện tại của **MINDFlow AI** để tuân thủ 100% quy ước đặt tên, kiến trúc thư mục, state management và styling của dự án gốc:
1. **Không cài đặt dư thừa:** Kiểm tra `package.json` hiện tại trước. Tận dụng các thư viện UI, icon, HTTP client, và thư viện vẽ sơ đồ (nếu MINDFlow AI đã dùng React Flow hoặc Mermaid thì tái sử dụng ngay).
2. **Tuân thủ Routing & Layout hiện tại:** Thêm route mới (ví dụ: `/code-analyzer` hoặc `/architecture`) vào cấu hình router/menu điều hướng sẵn có của MINDFlow AI.
3. **Đồng bộ Database (MongoDB):** Tạo thêm các Mongoose Model mới trong thư mục models hiện tại của backend, liên kết trực tiếp với `userId` (và `workspaceId` nếu có) từ hệ thống Auth của MINDFlow AI.

---

## 3. Kiến trúc Module & Luồng dữ liệu

### Luồng xử lý tích hợp (End-to-End Flow)
1. **Trang chủ Module (`/code-analyzer`):**
   - Khi người dùng truy cập, gọi API lấy danh sách các dự án đã phân tích của user hiện tại kèm các **Dự án mẫu mặc định (`isPublicDemo: true`)** để người mới vào có thể bấm xem sơ đồ và dữ liệu file ngay lập tức.
2. **Upload & Phân tích Codebase:**
   - Người dùng upload file `.zip` mã nguồn (hoặc chọn lại dự án đã lưu).
   - **Backend (MINDFlow API):**
     - Giải nén trong bộ nhớ/thư mục tạm, áp dụng bộ lọc thông minh để loại bỏ thư mục rác (`node_modules`, `.git`, `dist`, `build`, `.next`, `venv`, file ảnh/lock/test).
     - Dùng Static Code Parser (AST/Regex) trích xuất chính xác danh sách `import/export` và liên kết giữa các file (xử lý được repo 1.000+ file mà không tốn token).
     - Lưu metadata dự án vào MongoDB với trạng thái `PROCESSING`, sau đó đẩy danh sách file theo từng batch (10–15 file/lô) sang **n8n Webhook** hiện tại.
3. **Xử lý AI trên n8n:**
   - n8n nhận dữ liệu batch, gọi LLM phân tích vai trò từng file và ý nghĩa luồng dữ liệu giữa các file kết nối.
   - Trả kết quả JSON chuẩn về callback endpoint của MINDFlow AI để cập nhật MongoDB và chuyển trạng thái sang `COMPLETED`.
4. **Hiển thị tương tác (3-Pane Workspace):**
   - **Cột trái (File Explorer):** Cây thư mục dự án, thanh tìm kiếm nhanh file.
   - **Cột giữa (Architecture Graph):** Sơ đồ trực quan hiển thị kết nối giữa các module/file (gom nhóm theo thư mục nếu > 50 file, cho phép click mở rộng từng cụm).
   - **Cột phải (AI Code Insight):** Khi click vào một node (file) hoặc edge (đường nối), hiển thị tóm tắt chức năng, luồng dữ liệu truyền tải và danh sách các file phụ thuộc lấy từ API.

---

## 4. Thiết kế MongoDB Schema (Mở rộng trên DB MINDFlow AI)

Tạo 2 collection mới trong database MongoDB hiện tại, tham chiếu đến `User` hiện có của hệ thống:

### 4.1. Collection: `code_projects`
```javascript
const CodeProjectSchema = new mongoose.Schema({
  userId: { type: mongoose.Schema.Types.ObjectId, ref: 'User', index: true }, // Liên kết user hiện tại của MINDFlow AI
  name: { type: String, required: true },
  description: { type: String, default: '' },
  isPublicDemo: { type: Boolean, default: false, index: true }, // Hiển thị sẵn cho người mới vào xem
  status: { 
    type: String, 
    enum: ['PROCESSING', 'COMPLETED', 'FAILED'], 
    default: 'PROCESSING' 
  },
  stats: {
    totalRawFiles: Number,
    analyzedFiles: Number,
    primaryLanguage: String
  },
  // Lưu cấu trúc đồ thị (nodes, edges, clusters) để render tức thì từ API
  diagramData: {
    nodes: { type: Array, default: [] },
    edges: { type: Array, default: [] }
  }
}, { timestamps: true });
```

### 4.2. Collection: `code_project_files`
```javascript
const CodeProjectFileSchema = new mongoose.Schema({
  projectId: { type: mongoose.Schema.Types.ObjectId, ref: 'CodeProject', required: true, index: true },
  filePath: { type: String, required: true },
  fileName: { type: String, required: true },
  moduleGroup: { type: String, index: true }, // Tên thư mục/module để gom nhóm khi repo lớn
  language: { type: String },
  aiSummary: { type: String, default: '' },
  roleTag: { type: String, default: '' }, // VD: Controller, Service, Model, Util
  imports: [{
    targetFile: String,
    relationLabel: String // VD: "Gọi hàm xác thực JWT"
  }],
  importedBy: [{ type: String }] // Phục vụ Impact Analysis (file nào đang gọi file này)
}, { timestamps: true });
```

---

## 5. Danh sách API Endpoints cần bổ sung vào Backend MINDFlow AI
Tất cả endpoint sử dụng chung middleware xác thực (`authMiddleware`) và chuẩn response format hiện tại của MINDFlow AI:

- `GET /api/code-analyzer/projects`: Lấy danh sách dự án của user hiện tại + các dự án mẫu (`isPublicDemo: true`).
- `GET /api/code-analyzer/projects/:id`: Lấy thông tin tổng quan, `diagramData` và cây thư mục của một dự án (tải tức thì từ MongoDB).
- `GET /api/code-analyzer/projects/:id/files/:fileId`: Lấy chi tiết phân tích AI, `imports` và `importedBy` của một file cụ thể khi user click trên sơ đồ.
- `POST /api/code-analyzer/upload`: Nhận file `.zip`, lọc file rác, tách AST/Regex imports, lưu bản ghi `PROCESSING` vào MongoDB và kích hoạt n8n Webhook.
- `POST /api/code-analyzer/webhook/callback`: Endpoint nội bộ nhận kết quả JSON từ n8n sau khi LLM xử lý xong, cập nhật `CodeProject` và `CodeProjectFile`.

---

## 6. Prompt lệnh trực tiếp cho AI Coding (Copy & Paste vào Cursor / Windsurf)

> **Hướng dẫn thực thi cho AI:**
> "Hãy đọc kỹ file đặc tả này và quét toàn bộ cấu trúc thư mục hiện tại của dự án **MINDFlow AI** (bao gồm `package.json`, cấu trúc thư mục frontend/backend, cách kết nối MongoDB, middleware Auth, và layout/router hiện tại).
> 
> Nhiệm vụ của bạn là xây dựng tính năng **Codebase Architecture Analyzer** như một **trang/module mới bên trong MINDFlow AI**, tuyệt đối không tạo project mới và phải tái sử dụng tối đa UI components, cấu hình MongoDB và luồng gọi n8n sẵn có.
> 
> Hãy thực hiện tuần tự theo 3 bước sau và xác nhận với tôi sau mỗi bước:
> 1. **Bước 1 (Khảo sát & Thiết kế Schema):** Liệt kê các file/thư viện sẵn có trong MINDFlow AI sẽ được tái sử dụng. Tạo 2 Mongoose model `CodeProject` và `CodeProjectFile` cùng các API routes trong backend hiện tại. Tạo thêm 1 seed script nhỏ để sinh sẵn 1 dự án mẫu (`isPublicDemo: true`) vào MongoDB.
> 2. **Bước 2 (Bộ lọc & Phân tích tĩnh + Kết nối n8n):** Viết service giải nén file `.zip`, lọc bỏ thư mục rác (`node_modules`, `.git`, `dist`...), trích xuất danh sách `import/export` bằng Regex/AST, lưu vào MongoDB và bắn payload sang n8n Webhook.
> 3. **Bước 3 (Giao diện trang `/code-analyzer`):** Thêm menu vào Sidebar hiện tại của MINDFlow AI. Xây dựng trang giao diện 3 cột (Cây thư mục - Sơ đồ kết nối các file - Khung AI Insight bên phải) sử dụng chung theme/style của MINDFlow AI, tự động load dự án mẫu từ API khi người mới truy cập."