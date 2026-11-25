# MindFlow AI Collaboration Room --- Nâng cấp tương tác đa AI và xuất kết quả

> **Mục tiêu:** Nâng cấp tính năng **Phòng hợp tác** hiện có trong
> MindFlow để nhiều AI Agent thuộc các nhà cung cấp khác nhau có thể
> thực sự đọc, trao đổi, phản biện, chuyển giao nhiệm vụ và cùng hoàn
> thành công việc trong một phòng chat. Sau khi hoàn thành, hệ thống
> phải hiển thị kết quả rõ ràng và cho phép người dùng tải các file do
> Agent tạo ra.
>
> **Yêu cầu quan trọng:** Phải kiểm tra code
> hiện tại, , sau đó triển khai end-to-end.

------------------------------------------------------------------------

## 1. Bối cảnh hiện tại

Trang hiện tại: `/collab` --- **Phòng hợp tác**.

Giao diện hiện đã có: - Tạo phòng và đặt tên phòng. - Danh sách Agent có
thể chọn làm thành viên. - Hiển thị tên Agent, provider/model. - Khung
hội thoại chung. - Tin nhắn người dùng và tin nhắn Agent. - Khu vực nhắc
tới Agent bằng `@mention`. - Bộ đếm số tin nhắn và token. - Nút làm mới
và xóa phòng.

Các vấn đề nhìn thấy trong phiên bản hiện tại: 1. Có Agent trả về lỗi
`PROVIDER_REQUEST_REJECTED`. 2. Agent được gọi có lúc trả lời rằng nó
không nhìn thấy kết quả do Agent khác gửi vào phòng. 3. Chưa chứng minh
được luồng trao đổi Agent-to-Agent thực sự: Agent A gửi kết quả, Agent B
nhận được đúng nội dung đó trong context và phản hồi trực tiếp. 4. Chưa
có quy trình hoàn chỉnh để giao nhiệm vụ, theo dõi từng lượt xử lý, tổng
hợp kết quả và xuất file bàn giao. 5. Cần phân biệt lỗi provider, lỗi
cấu hình model/API key, lỗi timeout, lỗi giới hạn quota và lỗi
orchestration; không được biến mọi lỗi thành một câu trả lời chung
chung.

Hãy xác minh các vấn đề trên trong code và log thực tế. Không được mặc
định nguyên nhân nếu chưa kiểm tra.

------------------------------------------------------------------------

## 2. Kết quả sản phẩm cần đạt

Sau khi nâng cấp, người dùng có thể:

1.  Tạo một phòng hợp tác và chọn nhiều Agent.
2.  Kết nối Agent sử dụng các provider khác nhau:
    -   OpenAI
    -   Anthropic Claude
    -   Google Gemini
    -   DeepSeek
    -   Groq
    -   Custom API (ưu tiên hỗ trợ API tương thích OpenAI; nếu endpoint
        không tương thích thì cần adapter riêng).
3.  Gửi tin nhắn chung cho phòng.
4.  Gọi riêng Agent bằng `@mention`.
5.  Bật chế độ tự động để các Agent chủ động đọc, phản hồi và phản biện
    theo chính sách điều phối.
6.  Cho Agent trả lời trực tiếp tin nhắn của Agent khác, có liên kết tới
    tin nhắn được trả lời.
7.  Chuyển nhiệm vụ giữa các Agent và giữ nguyên context cần thiết.
8.  Có một Agent Moderator/Leader điều phối, yêu cầu phản biện và tổng
    hợp khi người dùng chọn chế độ này.
9.  Theo dõi trạng thái từng Agent: đang chờ, đang xử lý, đang dùng
    tool, hoàn thành, thất bại, bị hủy.
10. Hiển thị kết quả cuối cùng, các kết quả trung gian, nguồn tham chiếu
    và file đính kèm.
11. Tạo file thực tế (ví dụ: `.md`, `.txt`, `.json`, `.csv`, `.pdf`,
    `.docx`, `.xlsx`, `.zip` khi phù hợp với chức năng hiện có) và cho
    phép tải về.
12. Có lịch sử chạy, chi phí/token, thời gian xử lý và khả năng chạy lại
    tác vụ thất bại.

**Không chấp nhận:** Chỉ gọi lần lượt nhiều API rồi ghép các câu trả lời
độc lập vào giao diện. Các Agent phải thực sự được cấp nội dung phù hợp
từ cùng một cuộc hội thoại và có thể phản hồi dựa trên kết quả của Agent
trước.

------------------------------------------------------------------------

## 3. Chế độ hoạt động

Triển khai hai chế độ chính và một chế độ điều phối tùy chọn.

### 3.1. Directed Discussion --- Trao đổi theo chỉ định

-   Người dùng gửi tin nhắn bình thường: hiển thị trong phòng, không tự
    động gọi tất cả Agent.
-   Người dùng gọi `@Claude`, `@GPT`, `@Gemini`...: chỉ Agent được gọi
    nhận nhiệm vụ, trừ khi người dùng chọn nhiều Agent.
-   Agent được gọi phải nhận:
    -   System instruction riêng của Agent.
    -   Tin nhắn người dùng.
    -   Các tin nhắn liên quan trong phòng.
    -   Kết quả của Agent khác nếu có liên quan.
    -   File/context được người dùng đính kèm và Agent có quyền truy
        cập.
-   Agent phải có thể trả lời một tin nhắn cụ thể của Agent khác.
-   Nếu Agent được gọi cần ý kiến của Agent khác, nó có thể đề xuất
    chuyển giao; việc tự gọi Agent khác phải tuân theo giới hạn và quyền
    của phòng.

### 3.2. Free Discussion --- Tự động trao đổi có kiểm soát

-   Người dùng bật chế độ tự động khi tạo phòng hoặc trong cài đặt
    phòng.
-   Sau một tin nhắn mới, Orchestrator quyết định Agent nào cần tham gia
    dựa trên vai trò, nhiệm vụ, nội dung và trạng thái hiện tại.
-   Agent có thể đọc câu trả lời của Agent trước và tiếp tục thảo luận.
-   Không broadcast vô hạn cho tất cả Agent sau mỗi tin nhắn.
-   Cần có chính sách dừng rõ ràng:
    -   Đã đạt mục tiêu.
    -   Moderator kết luận.
    -   Đạt giới hạn lượt nói.
    -   Đạt giới hạn token/chi phí/thời gian.
    -   Người dùng bấm dừng.
-   Mặc định nên có giới hạn số vòng/lượt cho mỗi lần chạy; cho phép
    người dùng cấu hình trong giới hạn an toàn.
-   Phát hiện vòng lặp: hai Agent lặp lại nội dung, gọi nhau liên tục
    hoặc không tạo thêm thông tin mới.

### 3.3. Moderator Mode --- Điều phối và tổng hợp

-   Một Agent được chọn làm Moderator/Leader.
-   Moderator phân rã nhiệm vụ, chỉ định Agent theo vai trò, theo dõi
    kết quả và yêu cầu phản biện khi cần.
-   Moderator không được tự nhận kết quả của Agent khác nếu chưa có
    message/result tương ứng trong run.
-   Kết luận phải phân biệt:
    -   Điều đã được xác nhận.
    -   Đề xuất/ý kiến.
    -   Điểm còn bất đồng.
    -   Rủi ro và việc cần người dùng quyết định.
-   Người dùng có thể yêu cầu Moderator tổng hợp bất kỳ lúc nào.

------------------------------------------------------------------------

## 4. Luồng tương tác chuẩn

### 4.1. Ví dụ Directed Discussion

1.  Người dùng:
    `@Claude Thiết kế kiến trúc module quản lý nhân sự cho ERP React + NestJS + MongoDB.`
2.  Backend tạo một message và một Agent task/run cho Claude.
3.  Claude nhận lịch sử liên quan và trả lời.
4.  Kết quả Claude được lưu thành message trong cùng room.
5.  Người dùng:
    `@GPT Hãy review và phản biện đề xuất của Claude ở tin nhắn phía trên.`
6.  GPT phải được truyền nội dung đề xuất của Claude, không chỉ nhận câu
    hỏi trống.
7.  GPT trả lời và liên kết `replyToMessageId` tới message Claude.
8.  Người dùng:
    `@Gemini Đối chiếu hai phương án và chỉ ra phần chưa thống nhất.`
9.  Gemini nhận cả kết quả Claude và GPT, sau đó đưa ra đánh giá.
10. Người dùng yêu cầu Moderator tổng hợp. Hệ thống tạo kết luận và cho
    phép xuất file.

### 4.2. Ví dụ Free Discussion

1.  Người dùng gửi: "Phân tích codebase này và tìm nguyên nhân lỗi tạo
    đơn không trừ tồn kho".
2.  Orchestrator xác định đây là nhiệm vụ phân tích codebase.
3.  Planner/Architect phân rã công việc.
4.  Developer/Researcher Agent tìm luồng tạo đơn và cập nhật tồn kho.
5.  Reviewer Agent đọc bằng chứng và phản biện.
6.  Tester Agent đề xuất hoặc chạy kiểm thử nếu được cấp tool phù hợp.
7.  Moderator tổng hợp kết quả, trích file/đường dẫn/dòng code khi có dữ
    liệu thật.
8.  Nếu có đề xuất sửa code, chỉ thực hiện khi người dùng cho phép; sau
    đó chạy test/build trong sandbox.
9.  Tạo báo cáo và file bàn giao.

------------------------------------------------------------------------

## 5. Kiến trúc đề xuất

Trước khi code, hãy khảo sát kiến trúc hiện tại và tái sử dụng các
service/model có sẵn. Tên dưới đây là gợi ý theo trách nhiệm, không bắt
buộc tạo file trùng nếu codebase đã có thành phần tương đương.

``` text
MindFlow Frontend
  └── Collaboration Room UI
       ├── Room / Member Management
       ├── Message Timeline
       ├── @Mention / Reply
       ├── Run Controls
       ├── Agent Status
       └── Result & Artifact Panel
                 |
                 v
MindFlow Backend
  ├── Collaboration Room API
  ├── Message Service
  ├── Agent Orchestrator
  │    ├── Directed Dispatcher
  │    ├── Auto Discussion Manager
  │    ├── Moderator / Planner
  │    ├── Turn & Loop Guard
  │    └── Context Builder
  ├── Provider Gateway
  │    ├── OpenAI Adapter
  │    ├── Anthropic Adapter
  │    ├── Gemini Adapter
  │    ├── DeepSeek Adapter
  │    ├── Groq Adapter
  │    └── Custom API Adapter
  ├── Tool Execution / Sandbox (nếu được cấp quyền)
  ├── Artifact Service
  ├── Usage / Cost Tracking
  └── Realtime Event Publisher
                 |
          MongoDB + Redis (nếu cần)
                 |
          SSE / WebSocket
```

### 5.1. Provider Gateway

Tạo một lớp chuẩn hóa để Orchestrator không cần biết chi tiết từng nhà
cung cấp.

Giao diện logic tham khảo:

``` ts
interface AIProviderAdapter {
  validateConnection(config: ProviderConfig): Promise<ConnectionTestResult>;
  listModels?(config: ProviderConfig): Promise<ModelInfo[]>;
  generate(input: GenerateInput): Promise<GenerateResult>;
  stream?(input: GenerateInput): AsyncIterable<GenerateChunk>;
}
```

Chuẩn hóa dữ liệu: - `provider` - `model` - `messages` -
`systemInstruction` - `temperature` - `maxTokens` - `tools` (chỉ khi
model/provider hỗ trợ) - `timeoutMs` - `requestId` - `metadata`

Kết quả chuẩn hóa: - `content` - `finishReason` - `inputTokens` -
`outputTokens` - `totalTokens` - `providerRequestId` - `latencyMs` -
`usage` nếu provider trả về - `toolCalls` nếu có - `rawMetadata` đã lọc
dữ liệu nhạy cảm

Yêu cầu: - Không giả định mọi provider có cùng endpoint, định dạng
message, tool calling hoặc streaming. - OpenAI-compatible endpoint là
một chế độ của Custom API, không phải giả định cho mọi provider. - Không
hardcode API key trong frontend hoặc source code. - Không log API key,
Authorization header hoặc toàn bộ secret. - Kiểm tra timeout, retry có
backoff và giới hạn retry; không retry lỗi 4xx không thể khắc phục. -
Phân biệt lỗi authentication, model không tồn tại, quota/rate limit,
timeout, network, provider rejection và lỗi parse response. - Có
health/connection test cho từng cấu hình provider. - Không để một Agent
lỗi làm hỏng toàn bộ lượt chạy của các Agent khác nếu nhiệm vụ có thể
tiếp tục. - Không báo "Connected" chỉ dựa trên việc người dùng đã nhập
API key; phải có trạng thái kiểm tra kết nối.

### 5.2. Context Builder --- phần cần sửa trọng tâm

Đây là thành phần quan trọng nhất để khắc phục tình trạng Agent không
nhìn thấy câu trả lời của Agent khác.

Mỗi lần gọi Agent phải tạo context có cấu trúc: 1. System prompt của
Agent. 2. Vai trò và nhiệm vụ trong phòng. 3. Quy tắc phòng: chế độ,
giới hạn, quyền. 4. Mục tiêu hiện tại của run. 5. Tin nhắn người dùng
liên quan. 6. Các message trước trong phòng theo thứ tự thời gian. 7.
Kết quả Agent liên quan, gồm tên Agent, provider/model, thời gian và nội
dung. 8. Message đang được reply hoặc được mention. 9. File/artifact
liên quan dưới dạng metadata và nội dung trích xuất phù hợp. 10. Tool
results có nguồn gốc rõ ràng.

Quy tắc: - Message của Agent A phải được lưu thành message trước khi
Agent B được gọi đọc nó. - Khi gọi Agent B, truy vấn lại message từ
database theo `roomId`/`runId`/`sequence`, không chỉ dựa vào state tạm ở
frontend. - Không chỉ truyền nội dung câu hỏi mới mà bỏ mất lịch sử. -
Có thể dùng context window theo token; nếu lịch sử quá dài thì tóm tắt
các lượt cũ nhưng phải giữ nguyên kết luận, quyết định, bằng chứng, bất
đồng và artifact reference. - Không tự bịa nội dung message bị thiếu. -
Có thể giới hạn context theo `runId` để tránh lẫn các phiên thảo luận
không liên quan. - Lưu `contextMessageIds` hoặc context snapshot/version
để truy vết Agent đã nhận dữ liệu nào. - Tách system prompt khỏi nội
dung user/agent; coi nội dung message và file là dữ liệu không đáng tin
cậy, không cho phép chúng ghi đè system instruction.

### 5.3. Orchestrator

Orchestrator chịu trách nhiệm: - Nhận yêu cầu từ người dùng. - Xác định
mode: directed hoặc auto. - Xác định Agent đích qua mention hoặc
policy. - Tạo `run` và các `agentTask`. - Xếp lịch chạy tuần tự hoặc
song song khi phù hợp. - Chờ kết quả, lưu message, phát realtime
event. - Cập nhật context trước lượt tiếp theo. - Kiểm tra giới hạn
lượt, token, chi phí và thời gian. - Dừng, hủy, retry hoặc tiếp tục
run. - Tạo bản tổng hợp cuối cùng. - Ghi lại lý do chọn Agent và lý do
dừng.

Mặc định nên chạy tuần tự đối với các lượt cần đọc/phản biện kết quả
trước. Chỉ chạy song song khi các Agent làm các phần độc lập.

Không để nhiều Agent cùng sửa một file hoặc cùng thực hiện một hành động
ghi dữ liệu mà không có cơ chế khóa/kiểm soát.

------------------------------------------------------------------------

## 6. Database --- MongoDB

Khảo sát schema hiện tại trước khi tạo collection mới. Tái sử dụng
collection đang có nếu phù hợp và viết migration/backfill nếu cần. Các
collection đề xuất:

### 6.1. `collaboration_rooms`

``` ts
{
  _id: ObjectId,
  ownerId: ObjectId,
  workspaceId?: ObjectId,
  name: string,
  description?: string,
  mode: "directed" | "auto",
  moderatorAgentId?: ObjectId,
  settings: {
    maxTurnsPerRun: number,
    maxAgentsPerRun: number,
    maxTokensPerRun?: number,
    maxCostPerRun?: number,
    timeoutMs: number,
    allowAgentHandoff: boolean,
    requireApprovalForTools: boolean
  },
  status: "active" | "archived",
  createdAt: Date,
  updatedAt: Date
}
```

### 6.2. `collaboration_room_members`

``` ts
{
  _id: ObjectId,
  roomId: ObjectId,
  agentId: ObjectId,
  role: "member" | "moderator",
  enabled: boolean,
  speakingPolicy: "mention_only" | "auto_eligible" | "moderator_only",
  createdAt: Date
}
```

### 6.3. `collaboration_messages`

``` ts
{
  _id: ObjectId,
  roomId: ObjectId,
  runId?: ObjectId,
  sequence: number,
  senderType: "user" | "agent" | "system" | "tool",
  senderId?: ObjectId,
  senderName: string,
  provider?: string,
  model?: string,
  content: string,
  contentParts?: Array<{
    type: "text" | "file" | "artifact" | "tool_result",
    text?: string,
    artifactId?: ObjectId,
    metadata?: Record<string, unknown>
  }>,
  mentions?: ObjectId[],
  replyToMessageId?: ObjectId,
  status: "complete" | "streaming" | "failed" | "cancelled",
  error?: {
    code: string,
    message: string,
    retryable: boolean
  },
  usage?: {
    inputTokens?: number,
    outputTokens?: number,
    totalTokens?: number,
    estimatedCost?: number,
    currency?: string
  },
  contextMessageIds?: ObjectId[],
  createdAt: Date,
  updatedAt?: Date
}
```

### 6.4. `collaboration_runs`

``` ts
{
  _id: ObjectId,
  roomId: ObjectId,
  initiatedBy: ObjectId,
  triggerMessageId: ObjectId,
  mode: "directed" | "auto",
  objective: string,
  status: "queued" | "running" | "completed" | "failed" | "cancelled",
  turnCount: number,
  maxTurns: number,
  totalTokens: number,
  estimatedCost?: number,
  finalMessageId?: ObjectId,
  startedAt?: Date,
  completedAt?: Date,
  stopReason?: string,
  createdAt: Date
}
```

### 6.5. `collaboration_agent_tasks`

``` ts
{
  _id: ObjectId,
  runId: ObjectId,
  roomId: ObjectId,
  agentId: ObjectId,
  assignedBy: "user" | "orchestrator" | "agent",
  task: string,
  inputMessageIds: ObjectId[],
  dependsOnTaskIds?: ObjectId[],
  status: "queued" | "running" | "completed" | "failed" | "cancelled",
  outputMessageId?: ObjectId,
  error?: {
    code: string,
    message: string,
    retryable: boolean
  },
  attempt: number,
  startedAt?: Date,
  completedAt?: Date,
  usage?: Record<string, unknown>,
  createdAt: Date
}
```

### 6.6. `collaboration_artifacts`

``` ts
{
  _id: ObjectId,
  roomId: ObjectId,
  runId?: ObjectId,
  messageId?: ObjectId,
  createdByAgentId?: ObjectId,
  name: string,
  mimeType: string,
  extension: string,
  size: number,
  storageKey: string,
  checksum?: string,
  status: "ready" | "processing" | "failed" | "deleted",
  visibility: "room_members" | "owner_only",
  metadata?: Record<string, unknown>,
  createdAt: Date,
  expiresAt?: Date
}
```

### 6.7. `ai_provider_connections`

Nếu MindFlow đã có provider settings thì dùng lại, không tạo bản lưu
trùng.

``` ts
{
  _id: ObjectId,
  ownerId: ObjectId,
  workspaceId?: ObjectId,
  provider: "openai" | "anthropic" | "google" | "deepseek" | "groq" | "custom",
  displayName: string,
  baseUrl?: string,
  encryptedApiKey: string,
  defaultModel?: string,
  enabled: boolean,
  connectionStatus: "untested" | "connected" | "error",
  lastTestedAt?: Date,
  lastErrorCode?: string,
  createdAt: Date,
  updatedAt: Date
}
```

**Bảo mật:** mã hóa API key bằng cơ chế quản lý secret phía server;
không trả `encryptedApiKey` về client. Phân quyền theo
owner/workspace/tenant. Không để người dùng tham chiếu connection của
workspace khác.

### 6.8. Index cần xem xét

-   `collaboration_rooms`: `{ ownerId: 1, updatedAt: -1 }`
-   `collaboration_room_members`: `{ roomId: 1, agentId: 1 }` unique
-   `collaboration_messages`: `{ roomId: 1, sequence: 1 }` unique
-   `collaboration_messages`: `{ runId: 1, sequence: 1 }`
-   `collaboration_runs`: `{ roomId: 1, createdAt: -1 }`
-   `collaboration_agent_tasks`: `{ runId: 1, status: 1 }`
-   `collaboration_artifacts`: `{ roomId: 1, createdAt: -1 }`
-   Provider connection: index theo owner/workspace/provider.

Điều chỉnh index theo query thực tế và dữ liệu hiện có. Không tạo index
trùng lặp.

------------------------------------------------------------------------

## 7. Backend API đề xuất

Kiểm tra route convention hiện tại trước khi thêm API. Có thể triển khai
theo REST:

### Room

-   `GET /api/collab/rooms` --- danh sách phòng.
-   `POST /api/collab/rooms` --- tạo phòng.
-   `GET /api/collab/rooms/:roomId` --- chi tiết phòng.
-   `PATCH /api/collab/rooms/:roomId` --- cập nhật tên/cài đặt.
-   `DELETE /api/collab/rooms/:roomId` --- xóa hoặc archive theo
    convention hiện tại.
-   `PUT /api/collab/rooms/:roomId/members` --- cập nhật danh sách
    Agent.

### Message và run

-   `GET /api/collab/rooms/:roomId/messages?cursor=...` --- lấy lịch sử
    phân trang.
-   `POST /api/collab/rooms/:roomId/messages` --- gửi tin nhắn.
-   `POST /api/collab/rooms/:roomId/runs` --- bắt đầu một lượt thảo
    luận.
-   `GET /api/collab/runs/:runId` --- trạng thái và kết quả run.
-   `POST /api/collab/runs/:runId/cancel` --- dừng run.
-   `POST /api/collab/runs/:runId/retry` --- retry task/run được phép.
-   `POST /api/collab/runs/:runId/summarize` --- yêu cầu tổng hợp.
-   `GET /api/collab/runs/:runId/tasks` --- xem các Agent task.

### Provider

-   `GET /api/ai-providers` --- danh sách provider connection đã cấu
    hình, không trả secret.
-   `POST /api/ai-providers` --- thêm kết nối.
-   `PATCH /api/ai-providers/:id` --- sửa cấu hình.
-   `DELETE /api/ai-providers/:id` --- xóa kết nối.
-   `POST /api/ai-providers/:id/test` --- kiểm tra API
    key/endpoint/model.
-   `GET /api/ai-providers/:id/models` --- lấy model khả dụng nếu
    provider hỗ trợ.

### Artifact

-   `GET /api/collab/rooms/:roomId/artifacts` --- danh sách file.
-   `GET /api/collab/artifacts/:artifactId/download` --- tải file có
    kiểm tra quyền.
-   `DELETE /api/collab/artifacts/:artifactId` --- xóa file theo quyền.
-   `POST /api/collab/runs/:runId/export` --- tạo gói bàn giao.

Không nhất thiết tạo tất cả endpoint nếu codebase đã có API tương đương.
Giữ API nhất quán và validate input bằng schema validation đang dùng.

------------------------------------------------------------------------

## 8. Realtime và trạng thái Agent

Dùng SSE hoặc WebSocket tùy hạ tầng hiện tại. Không tạo hai cơ chế
realtime song song nếu một cơ chế đã đáp ứng.

Các event chuẩn hóa:

``` ts
type CollaborationEvent =
  | { type: "message.created"; roomId: string; message: MessageDTO }
  | { type: "message.delta"; roomId: string; messageId: string; delta: string }
  | { type: "agent.status"; roomId: string; runId: string; agentId: string; status: string }
  | { type: "task.created"; roomId: string; task: AgentTaskDTO }
  | { type: "task.updated"; roomId: string; task: AgentTaskDTO }
  | { type: "run.updated"; roomId: string; run: RunDTO }
  | { type: "artifact.created"; roomId: string; artifact: ArtifactDTO }
  | { type: "run.completed"; roomId: string; runId: string }
  | { type: "run.failed"; roomId: string; runId: string; error: ErrorDTO };
```

Yêu cầu: - Frontend cập nhật theo event, không cần reload thủ công. -
Khi mất kết nối, client reconnect và lấy message mới từ cursor/sequence
cuối. - Tránh hiển thị trùng message khi reconnect. - Message phải được
persist trước hoặc trong quy trình phát event để không mất kết quả. -
Streaming delta chỉ là nội dung tạm; khi hoàn tất phải cập nhật message
cuối cùng. - Có trạng thái rõ ràng cho từng Agent và từng task.

------------------------------------------------------------------------

## 9. Giao diện cần cập nhật trên trang `/collab`

Giữ lại bố cục hiện tại nếu phù hợp. Không phá vỡ sidebar, workspace
layout, màu sắc, typography và responsive design của MindFlow.

### 9.1. Khu vực tạo phòng/cài đặt phòng

Bổ sung: - Chế độ: `Trao đổi theo chỉ định` / `Tự động thảo luận`. -
Agent Moderator (không bắt buộc). - Giới hạn lượt nói tối đa. - Giới hạn
token/chi phí (nếu hệ thống có usage tracking). - Cho phép Agent chuyển
giao nhiệm vụ. - Yêu cầu phê duyệt trước khi chạy tool hoặc sửa file. -
Hiển thị provider/model và trạng thái kết nối của từng Agent.

### 9.2. Danh sách Agent thành viên

Mỗi Agent cần hiển thị: - Tên và avatar/icon. - Vai trò: Architect,
Developer, Reviewer, Tester, Researcher, Moderator... - Provider và
model. - Trạng thái kết nối. - Trạng thái trong run hiện tại. - Bật/tắt
tham gia phòng. - Chính sách tham gia: chỉ khi mention / được phép tự
tham gia.

Không hiển thị API key hoặc thông tin bí mật.

### 9.3. Message Timeline

Mỗi message cần thể hiện: - Avatar và tên người gửi. - Nhãn
provider/model (có thể thu gọn). - Nội dung Markdown/code block. - Thời
gian. - Reply/quote message. - Agent đang được mention. - Token/usage
nếu người dùng mở chi tiết. - Trạng thái lỗi và nút thử lại khi phù
hợp. - File/artifact đính kèm và nút tải về.

Thêm action: - Reply. - Copy. - Retry Agent. - Gọi Agent khác phản biện
nội dung này. - Tạo task từ message. - Export nội dung liên quan.

### 9.4. Composer

-   Ô nhập hỗ trợ `@mention` autocomplete.
-   Chọn một hoặc nhiều Agent.
-   Nút gửi tin nhắn.
-   Chọn Directed/Auto nếu quyền cho phép đổi theo từng lượt.
-   Đính kèm file theo cơ chế upload hiện tại.
-   Nút dừng run.
-   Hiển thị Agent nào sẽ nhận message trước khi gửi.
-   Không tự gọi Agent khi người dùng chỉ gõ tên nhưng chưa chọn mention
    hợp lệ.

### 9.5. Result & Artifact Panel

Khi run kết thúc, hiển thị: - Tóm tắt kết quả. - Kết luận cuối cùng của
Moderator (nếu có). - Các điểm đồng thuận/bất đồng. - Danh sách Agent đã
tham gia. - Trạng thái từng task. - Token, chi phí ước tính và thời gian
chạy. - File được tạo. - Nút tải từng file. - Nút tải toàn bộ gói ZIP. -
Nút chạy lại hoặc tiếp tục thảo luận.

------------------------------------------------------------------------

## 10. Tạo kết quả và file bàn giao

Đây là yêu cầu bắt buộc, không chỉ hiển thị câu trả lời dạng text.

### 10.1. Loại kết quả

Tùy nhiệm vụ, hệ thống hỗ trợ: - Báo cáo Markdown (`.md`). - Văn bản
(`.txt`). - JSON có cấu trúc (`.json`). - CSV (`.csv`). - PDF/DOCX/XLSX
nếu backend có thư viện phù hợp. - Source code/file do Agent tạo trong
sandbox. - ZIP chứa các file kết quả và báo cáo.

### 10.2. Quy trình tạo file

1.  Agent đề xuất file cần tạo hoặc người dùng yêu cầu xuất.
2.  Orchestrator tạo artifact task.
3.  Backend kiểm tra loại file, tên file, dung lượng và quyền.
4.  Nội dung được tạo bằng service phù hợp.
5.  Nếu cần tạo source code hoặc chạy build/test, thực hiện trong
    sandbox riêng biệt; không thực thi code AI tạo trực tiếp trên host
    production.
6.  Kiểm tra file tồn tại, dung lượng, MIME type và checksum.
7.  Lưu metadata vào `collaboration_artifacts`.
8.  Gắn artifact vào message/run.
9.  Phát event `artifact.created`.
10. Frontend hiển thị file và download link có kiểm tra quyền.
11. Có thể đóng gói ZIP gồm:
    -   `README.md` --- mô tả kết quả.
    -   `FINAL-REPORT.md` --- kết luận, phạm vi, giới hạn.
    -   `discussion-transcript.md` --- nội dung thảo luận đã chọn.
    -   `agent-results/` --- kết quả từng Agent.
    -   `files/` --- file được tạo.
    -   `test-results/` --- kết quả test nếu có.
    -   `manifest.json` --- danh sách file, kích thước, checksum và
        nguồn tạo.

Không đưa API key, `.env`, secret, token hoặc dữ liệu riêng tư vào ZIP.
Không tự đưa toàn bộ lịch sử phòng vào gói xuất nếu người dùng chưa
chọn.

### 10.3. Trải nghiệm tải file

-   Tải một file.
-   Tải toàn bộ ZIP.
-   Hiển thị tên file, loại file, kích thước và thời gian tạo.
-   Link download có xác thực/quyền truy cập; không dùng đường dẫn file
    local trực tiếp.
-   Nếu file tạo thất bại, hiển thị lỗi cụ thể và cho phép retry.
-   Nếu run chưa xong, thể hiện trạng thái đang tạo file.

------------------------------------------------------------------------

## 11. Xử lý lỗi --- đặc biệt `PROVIDER_REQUEST_REJECTED`

Phải truy vết toàn bộ luồng:

``` text
User message
  -> mention/mode parser
  -> room member validation
  -> provider connection lookup
  -> credential decryption
  -> provider adapter
  -> provider HTTP request
  -> response normalization
  -> message persistence
  -> context refresh
  -> next agent dispatch
  -> realtime event
  -> frontend render
```

Với lỗi `PROVIDER_REQUEST_REJECTED`: 1. Tìm nơi phát sinh mã lỗi này. 2.
Xác định lỗi gốc từ provider response (HTTP status, provider error code,
request ID nếu có). 3. Kiểm tra base URL, model ID, API key, headers,
body schema và endpoint. 4. Kiểm tra model có hỗ trợ endpoint/tính năng
đang gọi không. 5. Kiểm tra adapter có chuyển đổi message/tool/stream
đúng định dạng không. 6. Không hiển thị raw secret hoặc thông tin nhạy
cảm. 7. Lưu error code an toàn, thông báo dễ hiểu và hành động khắc
phục. 8. Có nút kiểm tra lại kết nối/provider.

Ví dụ thông báo: - `AUTHENTICATION_FAILED`: API key không hợp lệ hoặc đã
hết hiệu lực. - `MODEL_NOT_FOUND`: model không tồn tại hoặc không được
cấp quyền. - `RATE_LIMITED`: provider đang giới hạn request; hiển thị
thời gian retry nếu có. - `QUOTA_EXCEEDED`: tài khoản/provider hết quota
hoặc ngân sách. - `REQUEST_TIMEOUT`: provider phản hồi quá thời gian. -
`UNSUPPORTED_FEATURE`: model không hỗ trợ tính năng được yêu cầu. -
`PROVIDER_UNAVAILABLE`: provider tạm thời không khả dụng. -
`INVALID_PROVIDER_RESPONSE`: response không đúng định dạng mong đợi.

Không tự động đổi sang model khác nếu có thể làm thay đổi chất lượng/kết
quả mà người dùng không biết. Nếu fallback được bật, phải ghi rõ Agent
đã dùng model nào thực tế.

------------------------------------------------------------------------

## 12. Bảo mật và quyền riêng tư

-   API key chỉ được xử lý ở backend và mã hóa khi lưu.
-   Không gửi key xuống frontend, không ghi key vào log.
-   Kiểm tra quyền truy cập room, message, run và artifact ở mọi
    endpoint.
-   Tenant/workspace isolation nếu MindFlow có multi-tenant.
-   Chống prompt injection từ message, file và tool output.
-   Phân biệt instruction hệ thống với nội dung do user/Agent cung cấp.
-   Giới hạn file upload, MIME type, dung lượng và thời gian lưu.
-   Sandbox riêng cho code execution, build, test và zip.
-   Chỉ cấp tool đúng quyền cho Agent; mặc định read-only.
-   Các hành động ghi/sửa/xóa/deploy phải có approval nếu chưa được cấp
    quyền rõ ràng.
-   Có rate limit, concurrency limit và giới hạn ngân sách.
-   Có audit log cho provider connection, run, tool execution và
    artifact download.
-   Không gửi code/tài liệu nhạy cảm tới provider bên ngoài nếu
    workspace policy không cho phép.

------------------------------------------------------------------------

## 13. Kiểm thử bắt buộc

Tạo unit test, integration test và E2E test theo cấu trúc dự án hiện
tại.

### 13.1. Provider tests

-   Mỗi provider có adapter test riêng.
-   Test API key sai.
-   Test model sai.
-   Test rate limit/quota.
-   Test timeout/network.
-   Test response không hợp lệ.
-   Test streaming và non-streaming nếu hỗ trợ.
-   Test Custom API với endpoint tương thích OpenAI.
-   Test provider không hỗ trợ tool calling.

Có thể dùng mock provider để test CI; không yêu cầu API key thật trong
pipeline.

### 13.2. Collaboration tests

1.  Tạo room với hai Agent khác provider.
2.  User mention Agent A.
3.  Agent A trả lời và message được persist.
4.  Agent B được gọi ở lượt sau.
5.  Assert context gửi Agent B có nội dung Agent A.
6.  Assert Agent B reply đúng `replyToMessageId`.
7.  Kiểm tra Directed mode không tự gọi Agent không được mention.
8.  Kiểm tra Auto mode chỉ gọi Agent phù hợp.
9.  Kiểm tra Moderator tổng hợp đúng các kết quả đã lưu.
10. Kiểm tra giới hạn lượt và dừng run.
11. Kiểm tra Agent lỗi không làm mất kết quả của Agent khác.
12. Kiểm tra cancel/retry và reconnect realtime không tạo message trùng.

### 13.3. Artifact tests

-   Tạo file Markdown.
-   Tạo JSON hợp lệ.
-   Tạo ZIP có manifest.
-   Kiểm tra download quyền đúng/sai.
-   Kiểm tra checksum.
-   Kiểm tra không đưa secret vào ZIP.
-   Kiểm tra file lớn hoặc file lỗi.
-   Kiểm tra artifact hiển thị sau reconnect/reload.

### 13.4. E2E scenario quan trọng nhất

Dùng hai mock Agent khác provider: - Agent A trả lời chính xác một chuỗi
nhận diện, ví dụ `ARCH-RESULT-739`. - Agent B được yêu cầu nhắc lại và
phản biện chuỗi đó. - Test xác nhận request của Agent B thực sự chứa
chuỗi `ARCH-RESULT-739`. - Agent B trả lời dựa trên chuỗi đó. - Người
dùng yêu cầu xuất báo cáo. - Hệ thống tạo `.md` và `.zip`, tải xuống
thành công.

Đây là test chứng minh Agent-to-Agent context sharing thực sự hoạt động,
không phải chỉ render nhiều bubble chat.

------------------------------------------------------------------------

## 14. Kế hoạch triển khai theo giai đoạn

Không triển khai tất cả trong một lần nếu codebase lớn. Mỗi giai đoạn
phải build/test được.

### Phase 0 --- Audit code hiện tại

-   Đọc toàn bộ luồng `/collab`.
-   Tìm frontend page/components, API routes, controller/service,
    models, provider adapters, agent execution logic.
-   Tìm nơi tạo `PROVIDER_REQUEST_REJECTED`.
-   Tìm cách message được lưu và cách context được tạo.
-   Tìm cấu hình provider/model và cách lấy API key.
-   Viết báo cáo audit: thành phần đã có, thành phần lỗi, nguyên nhân có
    bằng chứng, file cần sửa.
-   Không sửa giao diện lớn ở phase này.

### Phase 1 --- Sửa provider integration

-   Chuẩn hóa Provider Gateway.
-   Sửa các adapter hiện có.
-   Bổ sung/hoàn thiện OpenAI, Claude, Gemini, DeepSeek, Groq, Custom
    API.
-   Thêm connection test.
-   Thêm error mapping.
-   Test từng provider bằng mock và test thật nếu có credentials trong
    môi trường dev.

### Phase 2 --- Sửa Agent-to-Agent context

-   Xây Context Builder.
-   Đảm bảo message được persist trước lượt kế tiếp.
-   Đảm bảo Agent B nhận được kết quả Agent A.
-   Hỗ trợ reply và @mention nhiều Agent.
-   Viết integration test `ARCH-RESULT-739`.

### Phase 3 --- Orchestration và hai chế độ

-   Directed Discussion.
-   Free Discussion có giới hạn.
-   Moderator/Leader.
-   Task handoff.
-   Turn limit, budget limit, timeout, cancel, retry, loop guard.

### Phase 4 --- Realtime UI

-   Trạng thái Agent/task/run.
-   Streaming nếu provider hỗ trợ.
-   Message reply, mention, lỗi, retry.
-   Reconnect và đồng bộ lịch sử.
-   Responsive, loading/empty/error states.

### Phase 5 --- Artifact và export

-   Artifact Service.
-   Tạo file Markdown/JSON.
-   Đóng gói ZIP.
-   Download có kiểm tra quyền.
-   Report và manifest.

### Phase 6 --- Hardening

-   Security review.
-   Permission/tenant tests.
-   Cost tracking.
-   Logging/observability.
-   E2E tests.
-   Build production và kiểm tra regression các tính năng cũ.

------------------------------------------------------------------------

## 15. Deliverables bắt buộc sau khi hoàn thành

Không chỉ trả lời "đã hoàn thành". Hãy cung cấp kết quả có thể kiểm
chứng.

### 15.1. Code

-   Toàn bộ code đã cập nhật trong đúng codebase.
-   Không tạo file demo thay cho tích hợp thật.
-   Không xóa tính năng hiện có nếu không có lý do và chưa được chấp
    thuận.
-   Không để TODO giả hoặc mock response trong luồng production.
-   Cập nhật migration/schema/config cần thiết.

### 15.2. Báo cáo

Tạo `AI-COLLABORATION-IMPLEMENTATION-REPORT.md`, gồm: 1. Tóm tắt thay
đổi. 2. Kiến trúc trước và sau. 3. Các file đã tạo/sửa/xóa. 4. Nguyên
nhân gốc của lỗi cũ và cách khắc phục. 5. Provider nào đã tích hợp và
trạng thái kiểm thử. 6. Luồng Agent-to-Agent đã xác minh ra sao. 7. Kết
quả unit/integration/E2E tests. 8. Build result. 9. Hạn chế còn lại. 10.
Cách cấu hình API key và chạy local/production. 11. Ảnh chụp giao diện
sau cập nhật nếu môi trường hỗ trợ.

### 15.3. File bàn giao

Tạo gói:

``` text
mindflow-ai-collaboration-update.zip
├── source-changes/              # chỉ gồm patch/code cần bàn giao nếu phù hợp
├── docs/
│   ├── AI-COLLABORATION-IMPLEMENTATION-REPORT.md
│   ├── AI-COLLABORATION-ARCHITECTURE.md
│   └── AI-COLLABORATION-API.md
├── test-results/
│   └── TEST-REPORT.md
└── manifest.json
```

Nếu làm trực tiếp trong Git repository, không nhất thiết copy toàn bộ
repository vào ZIP. Hãy cung cấp patch/diff hoặc danh sách file thay
đổi, đồng thời tạo ZIP bàn giao gọn. Không đưa `node_modules`, build
cache, `.git`, `.env`, credentials, private keys hoặc dữ liệu người dùng
vào ZIP.

Nếu môi trường thực thi không cho phép tạo file/ZIP, phải nêu rõ giới
hạn, cung cấp các file đã tạo được và không giả vờ rằng ZIP đã tồn tại.

------------------------------------------------------------------------

## 16. Tiêu chí nghiệm thu --- Definition of Done

Chỉ đánh dấu hoàn thành khi đáp ứng các tiêu chí sau:

-   [ ] Người dùng tạo được phòng với ít nhất hai Agent thuộc hai
    provider khác nhau.
-   [ ] User mention đúng Agent và Agent đó nhận đúng nhiệm vụ.
-   [ ] Agent A gửi message được lưu trong room.
-   [ ] Agent B nhận được nội dung Agent A trong context backend.
-   [ ] Agent B phản hồi có liên kết tới message Agent A.
-   [ ] Directed mode không tự gọi Agent ngoài chỉ định.
-   [ ] Auto mode tự chọn Agent có kiểm soát và dừng đúng điều kiện.
-   [ ] Moderator tổng hợp dựa trên dữ liệu thực tế của run.
-   [ ] Trạng thái Agent/task/run cập nhật realtime hoặc đồng bộ lại
    chính xác.
-   [ ] Lỗi provider hiển thị cụ thể, có thể chẩn đoán và retry phù hợp.
-   [ ] Token/chi phí được ghi nhận khi provider trả usage; nếu chỉ ước
    tính phải đánh dấu là ước tính.
-   [ ] Tạo được file `.md` và `.json`.
-   [ ] Tạo và tải được ZIP chứa báo cáo/kết quả.
-   [ ] Kiểm tra quyền truy cập artifact.
-   [ ] Không lộ API key/secret.
-   [ ] Build thành công.
-   [ ] Test quan trọng chạy thành công và có báo cáo.
-   [ ] Các tính năng phòng hợp tác hiện tại không bị regression.

------------------------------------------------------------------------

## 17. Hướng dẫn làm việc cho AI Developer

1.  Bắt đầu bằng việc đọc cấu trúc repository và tìm đúng implementation
    hiện tại của `/collab`.
2.  Không đoán tên file, framework, database hoặc API. Hãy xác minh từ
    code.
3.  Trước khi sửa, tạo audit report ngắn với file path và bằng chứng.
4.  Ưu tiên sửa lỗi Agent không nhận được message/context trước khi làm
    đẹp UI.
5.  Không thay toàn bộ hệ thống bằng một framework mới nếu có thể sửa
    kiến trúc hiện tại.
6.  Tận dụng model/provider/agent configuration đang có; tránh tạo hai
    nguồn dữ liệu cấu hình.
7.  Chia nhỏ công việc theo phase, sau mỗi phase chạy test/build liên
    quan.
8.  Nếu thiếu API key thật, dùng mock provider để kiểm chứng luồng
    orchestration; ghi rõ provider nào chưa thể test thật.
9.  Không tuyên bố provider đã tích hợp hoàn chỉnh nếu mới chỉ tạo
    adapter hoặc mock.
10. Không tự ý sửa production data, xóa collection hoặc chạy migration
    phá hủy.
11. Không commit secret hoặc file cấu hình chứa credentials.
12. Khi hoàn tất, xuất báo cáo và ZIP bàn giao theo mục 15.

**Ưu tiên số một:** chứng minh được Agent B thật sự nhận và hiểu nội
dung Agent A đã gửi. Sau đó mới mở rộng auto discussion, Moderator,
realtime polish và artifact export.

**Kết quả mong muốn cuối cùng:** `/collab` trở thành một phòng làm việc
đa AI thực sự trong MindFlow --- các Agent khác provider có thể trao đổi
qua lại dựa trên cùng context, được điều phối có kiểm soát, tạo ra kết
quả có thể kiểm chứng và bàn giao thành file tải xuống.
