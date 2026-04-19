# Tradify Automatization

Backend service for automated invoice PDF processing. The application fetches
an invoice, extracts line items, generates customs-friendly goods descriptions,
and returns a final PDF where the original document is merged with an enriched
goods description table.

## What The Application Does

The service covers one main workflow: turn a BaseLinker order or manually
uploaded invoice PDF into a document ready for customs or operational use.

High-level steps:

1. The API receives an `order_id` or a PDF file for manual test processing.
2. For an `order_id`, the service fetches the external invoice PDF from BaseLinker.
3. The PDF is parsed: the app detects the invoice table, line items, HS codes,
   quantities, prices, currency, weights, and document metadata.
4. For each line item, the app builds context from the source item name, HS code,
   origin, local brand/category rules, and normalized hints.
5. OpenAI generates customs-friendly EN/PL goods descriptions and missing fields:
   material, made in, country of origin, melt and pour, and manufacturer data.
6. Local validation and the review phase check the result, apply strict rules,
   and use fallbacks when AI output is not reliable enough.
7. The service renders an additional PDF page with the enriched table.
8. The original invoice PDF and the new page are merged into one PDF.

The API returns `application/pdf`: the original invoice plus an added page with
enriched goods descriptions.

## Inputs And Outputs

### Input

- `POST /generate` receives JSON with an `order_id`.
- `POST /generate-test` receives a PDF upload and optional `order_id`.

### Output

- HTTP `200 OK`.
- Content-Type: `application/pdf`.
- Response body: merged PDF document.

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
- Docker
- Google Cloud Run

## Architecture

The main pipeline is assembled in `main.py` and implemented in
`domains/invoice_enrichment/application/invoice_processing_pipeline.py`.

Key parts:

- `clients/baselinker.py` - BaseLinker integration and invoice PDF fetching.
- `invoice_pdf_parser/` - invoice table and line item extraction from PDF files.
- `goods_description/` - rules, normalization, OpenAI generation/review,
  validation, and fallback handling.
- `pdf_document/` - additional PDF page rendering and merge with the original.
- `domains/invoice_enrichment/api.py` - FastAPI endpoints.

Simplified flow:

```text
order_id / uploaded PDF
        |
        v
InvoiceSource
        |
        v
Parser -> ParsedDocument + line items
        |
        v
Goods Description Generator
  - local rules
  - normalization
  - OpenAI generation
  - OpenAI review
  - validation/fallback
        |
        v
PDF Builder -> description PDF
        |
        v
MergeService -> original PDF + description PDF
        |
        v
application/pdf response
```

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

Generate from BaseLinker order:

```bash
curl -X POST http://localhost:8080/generate \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_API_KEY" \
  -d '{"order_id":"12345"}' \
  --output invoice_12345.pdf
```

Run a manual PDF test:

```bash
curl -X POST http://localhost:8080/generate-test \
  -H "X-API-Key: YOUR_API_KEY" \
  -F "order_id=manual-test" \
  -F "pdf=@invoice.pdf;type=application/pdf" \
  --output invoice_manual_test_mutated.pdf
```

## Required Environment Variables

Application settings are loaded from environment variables or a local `.env` file.

Required in production:

- `API_KEY`
- `BASELINKER_API_TOKEN`
- `DESCRIPTION_GENERATION_MODE`
- `OPENAI_API_KEY`

Optional:

- `HOST`
- `PORT`
- `OPENAI_MODEL`
- `OPENAI_REASONING_EFFORT`
- `BASELINKER_API_URL`
- `BASELINKER_TIMEOUT_SECONDS`

Recommended defaults:

```env
DESCRIPTION_GENERATION_MODE=hybrid
OPENAI_MODEL=gpt-5.2
OPENAI_REASONING_EFFORT=medium
```

## API Overview

### `GET /`

Returns a simple service message.

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

Form fields:

- `pdf` - uploaded invoice PDF.
- `order_id` - optional test order id, defaults to `manual-test`.

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

This repository includes a `Dockerfile`, so Cloud Run can build and run the
service as a container.

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

The OpenAI secret is required because `DESCRIPTION_GENERATION_MODE=hybrid` is
the supported mode.

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
  --set-env-vars DESCRIPTION_GENERATION_MODE=hybrid,OPENAI_MODEL=gpt-5.2,OPENAI_REASONING_EFFORT=medium \
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
