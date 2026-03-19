
# Bank Statement Extractor

A minimal working prototype that accepts uploaded bank statements (PDF, JPG, PNG), sends them to the **GLM-OCR** HuggingFace Space for document understanding, and returns structured transaction JSON.

---

## Architecture

```
project-root/
│
├── backend/
│   ├── main.py               # FastAPI app factory + CORS + router wiring
│   ├── requirements.txt      # Python dependencies
│   ├── routers/
│   │   └── statement.py      # POST /upload-statement, GET /transactions, GET /health
│   ├── services/
│   │   └── ocr_service.py    # GLM-OCR HuggingFace Space integration
│   ├── models/
│   │   └── transaction.py    # Pydantic schemas (Transaction, StatementData, …)
│   └── utils/
│       └── file_handler.py   # Temp file save / cleanup / PDF→images
│
└── frontend/                 # Stitch MCP generated UI
```

---

## Prerequisites

| Requirement | Notes |
|-------------|-------|
| Python 3.11+ | |
| poppler | Required by `pdf2image` for PDF conversion |

### Install poppler

```bash
# Ubuntu / Debian
sudo apt-get install -y poppler-utils

# macOS
brew install poppler

# Windows — download from https://github.com/oschwartz10612/poppler-windows/releases
```

---

## Setup & Run

```bash
# 1. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 2. Install Python dependencies
pip install -r backend/requirements.txt

# 3. Start the API server (from project root)
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

The API will be available at `http://localhost:8000`.

Interactive docs: `http://localhost:8000/docs`

---

## API Reference

### `POST /api/upload-statement`

Upload a bank statement file and receive structured transaction data.

**Request** — `multipart/form-data`

| Field | Type | Description |
|-------|------|-------------|
| `file` | file | PDF, JPG, or PNG bank statement |

**Response** — `200 OK`

```json
{
  "status": "success",
  "message": "Extracted 12 transaction(s) from statement.pdf.",
  "filename": "statement.pdf",
  "statement": {
    "account_holder": "John Doe",
    "bank_name": "HDFC Bank",
    "account_number": "XXXX1234",
    "transactions": [
      {
        "date": "2024-01-15",
        "description": "UPI SWIGGY PAYMENT",
        "debit": 350.0,
        "credit": null,
        "balance": 10500.0
      }
    ]
  },
  "raw_ocr_text": "..."
}
```

---

### `GET /api/transactions`

Returns the structured data from the most recent upload.

**Response** — `200 OK` (same `StatementData` shape as above) or `404` if nothing has been uploaded yet.

---

### `GET /api/health`

```json
{ "status": "ok", "timestamp": "2024-01-15T10:30:00Z", "service": "bank-statement-extractor" }
```

---

## OCR Model

The system uses the **GLM-OCR** model hosted at:
`https://huggingface.co/spaces/prithivMLmods/GLM-OCR-Demo`

The Gradio Space API (`/process_image`) is called with `task="Table"` which is optimised for extracting structured tabular data from bank statements.

Cold-start latency on the first request is expected (Zero GPU Space). Subsequent requests are faster.

---

## Example curl

```bash
curl -X POST http://localhost:8000/api/upload-statement \
  -F "file=@/path/to/statement.pdf"
```
