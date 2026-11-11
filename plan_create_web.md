# AI KNOWLEDGE HUB – PROJECT SPECIFICATION

## 1. Project Overview

Build a full-stack AI-powered knowledge management platform named **AI Knowledge Hub**.

The platform allows users to upload documents, organize their knowledge base, chat with AI using their own documents, and execute intelligent tasks through AI Agents.

The main purpose is to demonstrate practical AI Application Development skills, including:

- Python.
- FastAPI.
- OpenAI API.
- Gemini API.
- Retrieval-Augmented Generation (RAG).
- Vector Database.
- AI Agents.
- Function Calling.

This must be a functional application, not just a UI prototype.

## 2. Technology Stack

### Frontend
- Next.js with App Router.
- JavaScript (JSX), do not use TypeScript.
- Tailwind CSS.
- React Hooks.
- Axios.
- Zustand for global state management.
- React Markdown for rendering AI responses.
- Lucide React for icons.

### Backend
- Python 3.12+.
- FastAPI.
- Pydantic.
- SQLAlchemy.
- Alembic.
- JWT Authentication.
- Async API endpoints where appropriate.

### AI Integration
- OpenAI API.
- Google Gemini API.
- Provider abstraction to switch between OpenAI and Gemini.
- Structured Outputs.
- Streaming Responses.
- Function Calling / Tool Calling.

### Database
- PostgreSQL.
- pgvector extension.
- Vector embeddings storage.
- SQLAlchemy ORM.

### Infrastructure
- Docker.
- Docker Compose.
- Environment variables.
- Separate frontend and backend services.

## 3. Project Architecture

Use a modular architecture:

ai-knowledge-hub/
│
├── frontend/
│   ├── app/
│   │   ├── (auth)/
│   │   ├── dashboard/
│   │   ├── knowledge/
│   │   ├── chat/
│   │   ├── agents/
│   │   ├── settings/
│   │   └── layout.js
│   ├── components/
│   ├── hooks/
│   ├── services/
│   ├── stores/
│   ├── utils/
│   └── package.json
│
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   └── v1/
│   │   ├── core/
│   │   ├── models/
│   │   ├── schemas/
│   │   ├── services/
│   │   │   ├── ai/
│   │   │   ├── rag/
│   │   │   ├── embeddings/
│   │   │   └── agents/
│   │   ├── tools/
│   │   ├── repositories/
│   │   └── main.py
│   ├── alembic/
│   ├── requirements.txt
│   └── Dockerfile
│
├── docker-compose.yml
├── .env.example
└── README.md

Keep frontend and backend completely separated.

## 4. Main Features

### 4.1 Authentication

Implement:
- Register.
- Login.
- Logout.
- JWT access token.
- Refresh token.
- Current user profile.
- Password hashing.
- Protected routes.

Every user's documents, conversations, and knowledge bases must be isolated.

### 4.2 Dashboard

Create an overview dashboard showing:
- Total uploaded documents.
- Total knowledge bases.
- Total conversations.
- AI requests usage.
- Recent activity.
- Quick actions.

### 4.3 Knowledge Base Management

Users can:
- Create knowledge bases.
- Edit knowledge bases.
- Delete knowledge bases.
- View document lists.
- Upload PDF, DOCX, TXT, and Markdown files.
- Delete uploaded documents.
- View document processing status.

Each document should have:
- Original filename.
- File size.
- Upload date.
- Processing status.
- Number of chunks.
- Associated knowledge base.

### 4.4 RAG Pipeline

Implement a complete RAG pipeline:

1. User uploads a document.
2. Backend extracts text.
3. Clean and normalize the extracted text.
4. Split text into chunks.
5. Generate embeddings.
6. Store embeddings in PostgreSQL using pgvector.
7. User asks a question.
8. Convert the question into an embedding.
9. Retrieve relevant document chunks using vector similarity.
10. Send the retrieved context to the selected LLM.
11. Generate an answer based on retrieved context.
12. Return the answer with source citations.

Requirements:
- Configurable chunk size and overlap.
- Metadata for every chunk.
- Similarity search.
- Top-K retrieval.
- Optional metadata filtering.
- Source filename and page number where available.
- Similarity score.
- Prevent answers from pretending to know information not found in the documents.

The AI must clearly indicate when the knowledge base does not contain enough information.

### 4.5 AI Chat

Create a ChatGPT-style interface.

Features:
- Create conversations.
- Rename conversations.
- Delete conversations.
- Conversation history.
- Markdown responses.
- Code syntax highlighting.
- Streaming responses.
- Stop generation.
- Regenerate responses.
- Copy responses.
- Display referenced documents.
- Select a knowledge base.
- Switch between OpenAI and Gemini.

Allow users to choose:
- AI provider.
- Model.
- Temperature.
- Knowledge base.
- RAG enabled/disabled.

Never expose API keys to the frontend.

### 4.6 OpenAI and Gemini Integration

Create a provider abstraction.

Example structure:

services/ai/
├── base_provider.py
├── openai_provider.py
├── gemini_provider.py
└── ai_factory.py

Requirements:
- Unified interface.
- Switch providers without changing business logic.
- Support text generation.
- Support streaming.
- Support embeddings through compatible embedding providers.
- Support structured outputs.
- Support function calling.

Do not assume OpenAI and Gemini have identical APIs. Implement provider-specific adapters.

Use environment variables for API configuration.

### 4.7 AI Agent

Implement an AI Agent that can understand user requests and select appropriate tools.

Create an agent orchestration service.

The agent should support:

- User input analysis.
- Tool selection.
- Tool execution.
- Result observation.
- Final response generation.
- Tool execution history.
- Error handling.
- Maximum execution steps.

Implement at least these tools:

**Tool 1: Search Knowledge Base**
- Search relevant document chunks.
- Return document references.
- Return relevant content.

**Tool 2: Summarize Document**
- Summarize an uploaded document.
- Support short and detailed summaries.

**Tool 3: Calculator**
- Perform mathematical calculations.
- Validate inputs.
- Never use unrestricted Python eval.

**Tool 4: Create Note**
- Create a note from the user's request.
- Store it in the database.

**Tool 5: Search Conversation History**
- Search previous conversations belonging to the current user.

The agent must use Function Calling / Tool Calling rather than simply pretending to execute tools.

Security:
- Only execute predefined tools.
- Validate every tool argument.
- Check user ownership before accessing data.
- Never execute arbitrary shell commands.
- Never execute arbitrary code generated by an LLM.
- Require user confirmation for sensitive or destructive actions.

### 4.8 Function Calling

Implement function calling for both supported AI providers where possible.

Example:

User:
"Find the document discussing FastAPI and summarize it."

Expected workflow:
1. AI identifies the required operation.
2. AI calls search_knowledge_base.
3. Backend executes the tool.
4. Results are returned to the AI.
5. AI calls summarize_document if needed.
6. AI generates the final response.

Store tool execution logs for debugging.

### 4.9 Settings

Implement:
- AI provider selection.
- Model selection.
- API key configuration.
- Default temperature.
- Default embedding model.
- RAG configuration.
- Chunk size.
- Chunk overlap.
- Top-K retrieval.

API keys must be stored securely on the backend, never returned in API responses.

## 5. Database Design

Create appropriate SQLAlchemy models:

- User
- RefreshToken
- KnowledgeBase
- Document
- DocumentChunk
- Conversation
- Message
- Note
- AgentExecution
- ToolExecution

Use PostgreSQL with pgvector for embeddings.

Include:
- Relationships.
- Foreign keys.
- Indexes.
- Timestamps.
- User ownership.
- Database migrations using Alembic.

## 6. API Design

Use REST API with prefix:

/api/v1

Suggested endpoints:

Authentication:
- POST /auth/register
- POST /auth/login
- POST /auth/refresh
- POST /auth/logout
- GET /auth/me

Knowledge Bases:
- GET /knowledge-bases
- POST /knowledge-bases
- GET /knowledge-bases/{id}
- PATCH /knowledge-bases/{id}
- DELETE /knowledge-bases/{id}

Documents:
- POST /documents/upload
- GET /documents
- GET /documents/{id}
- DELETE /documents/{id}
- GET /documents/{id}/status

Chat:
- POST /chat/conversations
- GET /chat/conversations
- GET /chat/conversations/{id}
- DELETE /chat/conversations/{id}
- POST /chat/conversations/{id}/messages
- POST /chat/conversations/{id}/messages/stream

AI:
- POST /ai/generate
- POST /ai/embeddings
- POST /ai/agent/run
- GET /ai/providers

Notes:
- GET /notes
- POST /notes
- PATCH /notes/{id}
- DELETE /notes/{id}

Settings:
- GET /settings
- PATCH /settings

Use Pydantic schemas for request validation and response serialization.

## 7. UI/UX Requirements

Create a modern SaaS dashboard.

Design direction:
- Clean and minimal.
- Professional AI SaaS appearance.
- Responsive desktop and mobile layouts.
- Consistent spacing.
- Clear typography.
- Subtle borders and shadows.
- Loading skeletons.
- Empty states.
- Error states.
- Toast notifications.
- Confirmation dialogs.

Main layout:
- Sidebar navigation.
- Top navigation.
- Main content area.

Sidebar:
- Dashboard.
- Knowledge Bases.
- AI Chat.
- AI Agents.
- Notes.
- Settings.

Chat interface:
- Conversation sidebar.
- Main chat area.
- Message input.
- File/source references.
- AI provider selector.
- Streaming response indicator.

Do not create a static mockup. Connect every implemented feature to real backend APIs.

## 8. Security and Reliability

Implement:
- Password hashing.
- JWT validation.
- User-level data isolation.
- File upload validation.
- File size limits.
- MIME type validation.
- API rate limiting.
- CORS configuration.
- Input validation.
- SQL injection prevention through ORM.
- Safe error handling.
- API key protection.
- Tool execution restrictions.

Never commit API keys or secrets to Git.

## 9. Development Phases

Build the project in phases.

### Phase 1: Foundation
- Initialize Next.js.
- Initialize FastAPI.
- Configure PostgreSQL.
- Configure Docker Compose.
- Implement authentication.
- Create dashboard layout.

### Phase 2: Knowledge Management
- Create knowledge bases.
- Upload documents.
- Extract document content.
- Process document chunks.
- Store documents and metadata.

### Phase 3: RAG
- Implement embeddings.
- Integrate pgvector.
- Implement similarity search.
- Implement RAG question answering.
- Return source citations.

### Phase 4: LLM Providers
- Integrate OpenAI.
- Integrate Gemini.
- Implement provider abstraction.
- Implement streaming responses.
- Implement structured outputs.

### Phase 5: AI Agent
- Implement agent orchestration.
- Implement Function Calling.
- Build predefined tools.
- Add tool execution logs.
- Implement security restrictions.

### Phase 6: Finalization
- Connect all frontend features.
- Add error handling.
- Add loading states.
- Test all APIs.
- Add Docker configuration.
- Write README.
- Prepare deployment instructions.

## 10. Development Rules

IMPORTANT:

1. Build a real working application, not a demo with fake data.
2. Use JavaScript and JSX for Next.js. Do not use TypeScript.
3. Use Python for the AI backend.
4. Keep frontend and backend separated.
5. Use clean architecture and reusable components.
6. Do not put business logic directly inside React components.
7. Do not expose AI API keys to the browser.
8. Do not hardcode API keys.
9. Do not create unnecessary abstractions.
10. Handle errors properly.
11. Use environment variables.
12. Write clear documentation.
13. Implement features incrementally.
14. Do not skip database migrations.
15. Do not claim a feature is complete until it has been tested.

## 11. Expected Deliverables

Provide:

- Complete Next.js frontend.
- Complete FastAPI backend.
- PostgreSQL database schema.
- Alembic migrations.
- RAG implementation.
- OpenAI integration.
- Gemini integration.
- AI Agent implementation.
- Function Calling implementation.
- Docker Compose.
- .env.example.
- README.md.
- API documentation.
- Local development instructions.
- Deployment instructions.

## 12. First Task

Before writing code:

1. Analyze the complete requirements.
2. Propose the architecture.
3. Define the database schema.
4. Define API contracts.
5. Explain the RAG pipeline.
6. Explain the AI Agent execution flow.
7. Create a phased implementation plan.

Then start implementing Phase 1.

After completing each phase:
- Run the application.
- Test the implemented features.
- Fix errors.
- Summarize completed work.
- List remaining tasks.

Do not attempt to generate the entire project in one response. Work incrementally and maintain a working application throughout development.