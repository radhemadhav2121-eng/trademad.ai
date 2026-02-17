# TradeMad AI — Implementation Blueprint

This blueprint translates your requested features into a buildable system for a web app where users upload chart images and receive AI-driven analysis.

## 1) Core Features You Listed

1. File upload system for users to submit chart images.
2. AI model integration to process and analyze charts.
3. Backend processing to run a deep learning model.
4. Database to store submissions and analysis results.
5. User authentication/login to track user history.
6. API connections between the model service and website.

## 2) Suggested Architecture

```text
Frontend (Next.js/React)
  ├── Auth UI (sign up, login)
  ├── Upload UI (drag/drop image)
  ├── Results UI (analysis + history)
  └── Calls Backend API

Backend API (FastAPI/Node)
  ├── Auth endpoints (JWT/session)
  ├── Upload endpoints (presigned URL or multipart)
  ├── Submission endpoints
  ├── Result endpoints
  └── Queues jobs for inference

Worker / Model Service (Python)
  ├── Pulls pending jobs
  ├── Runs preprocessing
  ├── Runs deep learning inference
  ├── Optional post-processing (signals, confidence)
  └── Writes results back to DB

Storage + Data
  ├── Object storage (S3-compatible) for chart images
  ├── PostgreSQL for users/submissions/results
  └── Redis (optional) for queue/cache
```

## 3) Data Model (Minimal)

### `users`
- `id` (uuid, pk)
- `email` (unique)
- `password_hash`
- `created_at`

### `submissions`
- `id` (uuid, pk)
- `user_id` (fk -> users)
- `image_url`
- `status` (`pending|processing|completed|failed`)
- `created_at`

### `analysis_results`
- `id` (uuid, pk)
- `submission_id` (fk -> submissions)
- `model_version`
- `summary_text`
- `signals_json` (jsonb)
- `confidence_score` (float)
- `created_at`

## 4) API Contracts (MVP)

### Auth
- `POST /api/auth/register`
- `POST /api/auth/login`
- `POST /api/auth/logout`
- `GET /api/auth/me`

### Upload + Submission
- `POST /api/uploads/presign` → get upload URL
- `POST /api/submissions` → create submission record after upload
- `GET /api/submissions` → list current user submissions
- `GET /api/submissions/:id` → submission detail + result

### Internal / Worker
- `POST /internal/jobs/infer` (optional trigger endpoint)
- Queue-based processing strongly recommended over synchronous inference.

## 5) Processing Flow

1. User authenticates.
2. User uploads chart image to object storage.
3. Frontend calls `POST /api/submissions` with image reference.
4. Backend writes submission with `pending` status and enqueues job.
5. Worker picks job, runs model inference, stores output.
6. Backend updates submission status to `completed` or `failed`.
7. Frontend polls or receives websocket update to show result.

## 6) Security + Reliability Checklist

- Validate file type/size (PNG/JPG only, max size limit).
- Virus/malware scanning before model execution (if public uploads).
- Rate limits on upload and inference endpoints.
- Authz checks so users only access their own submissions.
- Store secrets in env/secret manager.
- Model versioning for reproducible outputs.
- Observability: request IDs, logs, inference timing, failure tracing.

## 7) Delivery Plan

### Phase 1 (MVP)
- User auth
- Image upload
- Async inference pipeline
- Basic analysis result rendering
- User history page

### Phase 2
- Better chart preprocessing
- Explainability overlays
- Retry/priority queues
- Admin dashboard for model health

### Phase 3
- Multi-model routing (different chart types)
- User feedback loop for model improvement
- Billing/usage metering

## 8) Recommended Stack

- **Frontend:** Next.js + TypeScript + Tailwind
- **Backend API:** FastAPI (Python) or NestJS (Node)
- **Model Worker:** Python + PyTorch/TensorFlow
- **Database:** PostgreSQL
- **Queue:** Redis + RQ/Celery (or BullMQ for Node)
- **Storage:** S3-compatible bucket
- **Auth:** JWT/session (or managed auth provider)

This gives a practical and scalable baseline for the exact capabilities you listed.
