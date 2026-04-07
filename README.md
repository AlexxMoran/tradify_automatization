# Tradify Automatization

Backend service for invoice enrichment and PDF post-processing.

The project processes commercial invoice PDFs, extracts line items, generates customs-friendly goods descriptions, and returns a merged PDF document.

## Stack

- Python 3.13
- FastAPI
- Uvicorn
- Pydantic / pydantic-settings
- httpx
- pdfplumber
- PyMuPDF (`fitz`)
- pypdf
- OpenAI Python SDK
- uv

## Local Run

Install dependencies with `uv`, then start the API:

```bash
uv sync
uv run uvicorn main:app --host 0.0.0.0 --port 8080
```

Health check:

```bash
curl http://localhost:8080/health
```

## Required Environment Variables

Application settings are loaded from environment variables or a local `.env` file.

Required in production:

- `API_KEY`
- `BASELINKER_API_TOKEN`
- `DESCRIPTION_GENERATION_MODE`
- `OPENAI_API_KEY`

Optional:

- `OPENAI_MODEL`
- `BASELINKER_API_URL`
- `BASELINKER_TIMEOUT_SECONDS`

Notes:

- Use `DESCRIPTION_GENERATION_MODE=hybrid`.
- `OPENAI_API_KEY` is required because goods description generation is AI-only.

## Docker

Build locally:

```bash
docker build -t invoice-builder .
```

Run locally:

```bash
docker run --rm -p 8080:8080 --env-file .env invoice-builder
```

## Deploy To Google Cloud Run

This repository includes a `Dockerfile`, so Cloud Run can build and run the service as a container.

### 1. Enable GCP services

Enable these APIs in your Google Cloud project:

- Cloud Run
- Cloud Build
- Artifact Registry
- Secret Manager

### 2. Create secrets

Create these secrets in Secret Manager:

- `invoice-builder-api-key`
- `invoice-builder-baselinker-token`
- `invoice-builder-openai-api-key`

The OpenAI secret is required because `DESCRIPTION_GENERATION_MODE=hybrid` is the supported mode.

### 3. Deploy

Replace the placeholder values before running:

```bash
gcloud run deploy invoice-builder \
  --source . \
  --region europe-central2 \
  --allow-unauthenticated \
  --memory 2Gi \
  --cpu 1 \
  --concurrency 1 \
  --timeout 300 \
  --set-env-vars DESCRIPTION_GENERATION_MODE=hybrid,OPENAI_MODEL=gpt-5-mini \
  --update-secrets API_KEY=invoice-builder-api-key:latest,BASELINKER_API_TOKEN=invoice-builder-baselinker-token:latest,OPENAI_API_KEY=invoice-builder-openai-api-key:latest
```

Why these defaults:

- `--allow-unauthenticated` keeps Apps Script integration simple.
- Access is still protected by the application-level `X-API-Key` header.
- `--concurrency 1` is safer for PDF-heavy and memory-heavy requests.
- `--memory 2Gi` gives headroom for PDF parsing and merging.

### 4. Verify the deployment

Open the service URL and check:

```bash
curl https://YOUR_CLOUD_RUN_URL/health
```

Generate a PDF:

```bash
curl -X POST https://YOUR_CLOUD_RUN_URL/generate \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_API_KEY" \
  -d '{"order_id":"12345"}' \
  --output invoice_12345.pdf
```

## Google Apps Script Example

Store these values in `Script Properties`:

- `INVOICE_API_URL`
- `INVOICE_API_KEY`

Example Apps Script:

```javascript
function generateInvoice(orderId) {
  const props = PropertiesService.getScriptProperties();
  const baseUrl = props.getProperty('INVOICE_API_URL');
  const apiKey = props.getProperty('INVOICE_API_KEY');

  const response = UrlFetchApp.fetch(baseUrl + '/generate', {
    method: 'post',
    contentType: 'application/json',
    headers: {
      'X-API-Key': apiKey,
    },
    payload: JSON.stringify({
      order_id: String(orderId),
    }),
    muteHttpExceptions: true,
  });

  if (response.getResponseCode() !== 200) {
    throw new Error(response.getContentText());
  }

  const blob = response.getBlob().setName('invoice_' + orderId + '.pdf');
  return DriveApp.createFile(blob);
}
```

## API Overview

### `GET /health`

Returns a simple service status payload.

### `POST /generate`

Protected by `X-API-Key`.

Request body:

```json
{
  "order_id": "12345"
}
```

Response:

- `200 OK`
- `application/pdf`

### `POST /generate-test`

Protected by `X-API-Key`.

Accepts a PDF upload and returns the merged test PDF.
