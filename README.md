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
