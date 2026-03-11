# Local RAG Chat

A fully local Retrieval-Augmented Generation application that allows users to upload documents and chat with them using a local language model.

This project was designed as a production-style AI application that runs entirely on local infrastructure, without relying on external cloud APIs. It combines document ingestion, semantic search, vector storage, and local LLM inference into a clean full-stack experience.

## Overview

Local RAG Chat enables users to:

- upload PDF, TXT, and Markdown documents
- automatically process and index those documents
- ask natural language questions about indexed content
- retrieve relevant document chunks through semantic search
- generate answers using a local LLM running with Ollama
- inspect source references used to produce each answer
- interact through a modern chat interface inspired by ChatGPT

The system is designed for privacy, local-first workflows, and portfolio-level presentation of a complete AI product.

## Key Features

### Local-first architecture

All major components run locally:

- local LLM via Ollama
- local embedding generation
- local vector database persistence with ChromaDB
- local backend with FastAPI
- local frontend with Next.js

No external AI APIs are required.

### End-to-end RAG pipeline

The application implements a complete Retrieval-Augmented Generation workflow:

1. document upload
2. text extraction
3. chunking
4. embeddings generation
5. vector storage
6. semantic retrieval
7. prompt construction
8. local LLM answer generation
9. answer rendering with sources

### Document support

Supported file types:

- PDF
- TXT
- Markdown

### Chat experience

The frontend includes:

- ChatGPT-style layout
- streaming assistant responses
- markdown rendering
- syntax highlighting for code blocks
- copy response action
- regenerate response action
- typing indicator
- source expansion panel
- multi-document selection

### Document management

Users can:

- upload files
- view indexed documents
- select one or more documents for retrieval scope
- delete indexed documents

## Tech Stack

### Frontend

- Next.js 14
- React
- TypeScript
- Tailwind CSS
- Zustand
- react-dropzone
- react-markdown
- react-syntax-highlighter
- Lucide React

### Backend

- Python
- FastAPI
- LangChain
- Ollama
- ChromaDB
- PyPDF

### Infrastructure

- Docker
- Docker Compose
- local environment configuration with `.env`

## Architecture

### High-level flow

```text
Document Upload
↓
Text Extraction
↓
Chunking
↓
Embedding Generation
↓
Vector Storage (ChromaDB)
↓
User Question
↓
Query Embedding
↓
Similarity Search
↓
Top-K Retrieval
↓
Prompt Construction
↓
Local LLM Generation (Ollama)
↓
Answer + Sources
```

### Project structure

```text
ragChat/
├── backend/
│   ├── api/
│   ├── core/
│   ├── embeddings/
│   ├── ingestion/
│   ├── prompts/
│   ├── retrieval/
│   ├── services/
│   ├── storage/
│   ├── .env
│   ├── main.py
│   └── requirements.txt
├── frontend/
│   ├── app/
│   ├── components/
│   ├── hooks/
│   ├── services/
│   ├── styles/
│   ├── types/
│   ├── .env
│   ├── package.json
│   └── tailwind.config.ts
├── docker/
│   ├── backend.Dockerfile
│   ├── frontend.Dockerfile
│   └── docker-compose.yml
├── tests/
├── vector_db/
└── README.md
```

## How It Works

### Document ingestion

When a document is uploaded, the backend:

- saves the file locally
- extracts raw text
- splits content into chunks
- enriches metadata
- generates embeddings
- stores chunks in ChromaDB

Current chunking settings:

- `chunk_size = 800`
- `chunk_overlap = 200`

### Retrieval

When a user sends a question, the backend:

- embeds the question
- performs semantic similarity search in ChromaDB
- retrieves the top relevant chunks
- formats the retrieved context
- builds the final prompt
- sends the prompt to the local LLM
- returns the generated answer with source references

### Prompting

The application uses a constrained RAG prompt so the model answers only from the indexed context.

Example behavior:

- if the answer exists in the document set, the assistant answers based on those sources
- if the answer is not present, the assistant should respond that it could not find the answer in the provided documents

## API Endpoints

### Document endpoints

#### `POST /documents/upload`

Uploads and indexes a document.

#### `GET /documents`

Lists indexed documents.

#### `DELETE /documents/{id}`

Removes a document and its indexed vectors.

### Chat endpoints

#### `POST /chat`

Returns a full answer after retrieval and generation.

#### `POST /chat/stream`

Streams answer tokens progressively using SSE-style events.

### Health endpoint

#### `GET /health`

Basic backend health check.

## Local Development Requirements

Before running the project, make sure the following tools are installed.

### Required software

#### Backend

- Python 3.11 or newer
- pip
- virtual environment support

#### Frontend

- Node.js 18 or newer
- npm

#### Local AI runtime

- Ollama installed and available in your system path

#### Optional

- Docker
- Docker Compose

## Required Ollama Models

This project expects two local models:

- a chat model
- an embedding model

Recommended examples:

- chat model: `llama3.1`
- embedding model: `mxbai-embed-large`

Install them with:

```bash
ollama pull llama3.1
ollama pull mxbai-embed-large
```

Start Ollama:

```bash
ollama serve
```

## Running the Project Locally

### 1. Clone the repository

```bash
git clone https://github.com/imsupeer/ragChat.git
cd ragChat
```

### 2. Configure the backend

Go to the backend folder:

```bash
cd backend
```

Setup the environment file:

```env
APP_NAME=Local RAG Chat
APP_ENV=development
API_HOST=0.0.0.0
API_PORT=8000
CORS_ORIGINS=http://localhost:3000

OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_CHAT_MODEL=llama3.1
OLLAMA_EMBED_MODEL=mxbai-embed-large

CHROMA_PERSIST_DIRECTORY=./vector_db
DOCUMENTS_DIRECTORY=./storage/docs
REGISTRY_PATH=./storage/registry.json

CHUNK_SIZE=800
CHUNK_OVERLAP=200
TOP_K=5
MAX_CONTEXT_CHUNKS=5
```

Create and activate a virtual environment.

On Linux/macOS:

```bash
python -m venv venv
source venv/bin/activate
```

On Windows PowerShell:

```powershell
python -m venv venv
venv\Scripts\Activate.ps1
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Run the backend:

```bash
uvicorn main:app --reload
```

The backend will be available at:

```text
http://localhost:8000
```

Swagger documentation:

```text
http://localhost:8000/docs
```

### 3. Configure the frontend

Open a new terminal and go to the frontend folder:

```bash
cd frontend
```

Setup the frontend environment file:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_MODEL_STATUS=Ollama running
```

Install dependencies:

```bash
npm install
```

Start the frontend:

```bash
npm run dev
```

The frontend will be available at:

```text
http://localhost:3000
```

## Running with Docker

If you prefer containerized execution, use the Docker setup included in the project.

From the `docker/` directory:

```bash
cd docker
docker compose up --build
```

This will start:

- the frontend container
- the backend container

Note that Ollama must still be available and reachable from the backend container, depending on your host configuration.

## Recommended Startup Order

For the smoothest local setup, use this order:

1. start Ollama
2. make sure the required models are installed
3. start the backend and frontend using docker
4. upload a document
5. begin chatting

## Example Usage

### Upload a document

Use the sidebar to upload a file such as:

- `mobydick.txt`
- `notes.md`
- `paper.pdf`

### Ask questions

Examples:

- `Who is Captain Ahab?`
- `Summarize the main idea of this document.`
- `What does the document say about system architecture?`
- `List the most important technical decisions mentioned.`
- `Which section discusses deployment?`

### Review source references

Each assistant message can display its sources in a collapsible references panel, allowing users to inspect which parts of the indexed documents were used.

## Development Notes

### Chroma metadata

Metadata stored with each chunk must use primitive values only. Avoid `None`, nested objects, or unsupported types when writing metadata into ChromaDB.

### Multilingual behavior

If documents are in English, questions asked in English may produce more accurate retrieval results than questions in Portuguese, depending on the embedding model and local LLM used.

### Persistence

The project stores:

- uploaded files in `backend/storage/docs/`
- registry data in `backend/storage/registry.json`
- vector database files in `vector_db/`

## Testing

Run tests from the project root:

```bash
pytest
```

## Portfolio Value

This project demonstrates practical experience in:

- full-stack AI product development
- Retrieval-Augmented Generation architecture
- local LLM integration
- vector search systems
- LangChain orchestration
- document ingestion pipelines
- modern React and Next.js frontend engineering
- streaming UX patterns
- production-style code organization
- Docker-based local infrastructure
