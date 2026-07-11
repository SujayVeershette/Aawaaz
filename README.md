# आवाज़ — AAWAAZ
**Local-First Voice Agent · Google DeepMind Bengaluru Hackathon**

---

## Why Aawaaz + FastAPI?
- **FastAPI Core**: Async-first backend with automatic Pydantic request validation and high-speed JSON serialization.
- **Interactive API Explorer**: Auto-generated live documentation at `http://localhost:8000/docs` to demonstrate live scheme discovery to judges.
- **Modern Google GenAI SDK**: Powered by `google-genai` (`gemini-2.0-flash`) with robust local-first OCR (`Gemma` fallback).

---

## Folder Structure
```
aawaaz-final/
├── frontend/
│   └── index.html         ← Open directly in Chrome
└── backend/
    ├── server.py          ← FastAPI Server (Uvicorn)
    ├── requirements.txt   ← Python Dependencies
    ├── .env.example       ← Copy to .env and add your API key
    ├── agent/             ← Conversation state & Eligibility rules
    ├── schemes/           ← Rural scheme JSON definitions
    ├── storage/           ← Encrypted local profile storage
    └── ocr/               ← Document scanner & OCR pipeline
```

---

## Run In 3 Steps (Using `uv`)

### Step 1 — Add your API key
```bash
cd backend
cp .env.example .env
# Open .env and paste your Gemini API key:
# GEMINI_API_KEY=your_api_key_here
```

### Step 2 — Create Virtual Environment & Start Backend (`uv`)
```bash
cd backend

# Create virtual environment with uv
uv venv

# Activate virtual environment
# On Windows (PowerShell):
.\.venv\Scripts\activate
# On Linux / macOS:
source .venv/bin/activate

# Install dependencies using uv fast pip
uv pip install -r requirements.txt

# Start FastAPI server
python server.py
# OR run with uvicorn directly:
# uvicorn server:app --host 0.0.0.0 --port 8000 --reload
```
> **API Docs Ready**: Once running, open [http://localhost:8000/docs](http://localhost:8000/docs) to test endpoints live!

### Step 3 — Open Frontend
```bash
# Just double-click frontend/index.html to open in Chrome!
# Or from terminal:
start ../frontend/index.html   # Windows
open ../frontend/index.html    # macOS / Linux
```

---

## Demo Flow for Judges (The 2-Minute Winning Pitch)
1. **Interactive Greeting & Waveform Orb**: Page loads → The **Audio Waveform Orb** breathes gently in the center while Hindi greeting plays naturally.
2. **Handsfree Voice Interaction**: Click 🎤 mic once → speak in Hindi (`"नमस्ते, मेरा नाम राजू है और मैं बिहार से हूँ"`). The Orb turns **Green/Emerald** and pulses with concentric soundwave ripples!
3. **Smart Orb States**: When AI processes your query, the Orb turns **Purple** (`Thinking...`). When AI speaks back, the Orb turns **Orange** and pulses to the speech rhythm!
4. **Offline Resilience Story (Highest Impact Moment)**: Click the header button `[ 📶 4G Online ]` to flip it to **`[ 📴 Offline (2G/No Net) ]`**. The status pill instantly switches from `Gemini Live` to **`🔒 Gemma Local`**. Speak again and show judges how Aawaaz continues working offline via local rules & encrypted queue without dropping a beat!
5. **Real-Time Extraction & Schemes**: Scheme badges automatically slide in (`Pradhan Mantri Awas Yojana`, etc.) based on extracted profile data.
6. **Document OCR**: Click 📷 camera → hold up an Aadhar card or Ration card → mock OCR extracts profile details cleanly.
7. **Live API Explorer**: Open `http://localhost:8000/docs` to show the judges clean Pydantic schemas (`ChatRequest` with `simulated_offline`, `ScanRequest`).

---

## API Key & Security
- Get your free API key: [Google AI Studio](https://aistudio.google.com/api-keys)
- **Zero Cloud PII**: Profile data and scanned documents are encrypted via `Fernet` and stay 100% local (`~/.aawaaz/data`).
- Never commit `.env` to GitHub (ignored via `.gitignore`).

