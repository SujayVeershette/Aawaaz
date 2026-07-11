# 🏛️ आवाज़ — AAWAAZ
### **Enterprise Edge-to-Cloud Voice & Form Automation Infrastructure for India's Digital Public Infrastructure (`DPI`)**
*Built for the Google DeepMind Bengaluru Hackathon · Powered by Gemini 2.0 Flash, Local Gemma 4 Engine, and Intelligent Live DOM Automation*

---

## 🌟 Executive Summary & Architecture Vision
In India, over **800 million rural citizens** are eligible for life-changing central and state welfare schemes (`PM-KISAN, PM Fasal Bima Yojana, e-Shram, MGNREGA, Ayushman Bharat`). Yet, **less than 15%** successfully enroll due to three structural barriers:
1. **Linguistic & Digital Literacy Walls**: Official portals (`pmkisan.gov.in`, `pmfby.gov.in`) are complex English web applications requiring multi-step ASP.NET form navigation.
2. **Connectivity Deserts**: Rural habitations frequently suffer from 2G drops, packet loss, or total air-gapped internet disconnection.
3. **Privacy & Data Sovereignty Risks (`DPDP Act 2023`)**: Citizens fear sharing sensitive PII (`Aadhaar 12-digit UID, Bank Account numbers, IFSC codes`) with cloud chatbots that could log, cache, or leak confidential identity vectors.

**Aawaaz (`आवाज़`)** solves this through a **Zero-Trust Hybrid Edge-to-Cloud AI Architecture** that combines real-time multi-modal voice processing with strict **On-Device PII Shielding** and **Intelligent Live DOM Autonomous Form Filling**.

---

## 🏛️ Senior Architect System Design & Core Innovations

```mermaid
graph TD
    User["🎙️ Rural Citizen (Voice / Document OCR)"] -->|Audio / Text / Image| EdgeRouter["⚡ Aawaaz Hybrid Edge Router"]
    
    subgraph PrivacyShield [🔒 PII Confidentiality Shield (DPDP Act 2023 Compliant)]
        EdgeRouter -->|Tier 1 / Tier 2 PII Detected<br>Aadhaar, Bank, IFSC, Ration, 8+ Digits| LocalEngine["🛡️ On-Device Local Engine<br>Gemma 4 Autonomous / Fernet AES-256"]
        LocalEngine -->|Encrypted Local Store| LocalVault[("🔒 Local SQLite & Encrypted Vault<br>~/.aawaaz/data")]
    end
    
    subgraph CloudCluster [⚡ Cloud Edge Connected (Non-PII Intent & Reasoning)]
        EdgeRouter -->|Tier 3 Demographic Metadata<br>Age, Occupation, Land, State| CloudGemini["☁️ Google Gemini 2.0 Flash<br>High-Throughput Multi-Modal Inference"]
    end
    
    subgraph FormEngine [🤖 Autonomous Live DOM Form Automation]
        LocalVault -->|Decrypted Profile Snapshot| Playwright["⚡ Playwright Proactor Engine"]
        CloudGemini -->|Eligibility Rule Match (26 Schemes)| Playwright
        Playwright -->|Intelligent Live DOM Discovery| GovtPortals["🌐 Official Government Portals<br>PM-KISAN / PM Fasal Bima / e-Shram"]
        GovtPortals -->|Visual Green Highlight & Pause at OTP| DemoUI["🖥️ Real-Time Demo Dashboard / Mobile UI"]
    end
```

---

### 1. 🔒 Three-Tier PII Confidentiality Shield (`DPDP Act 2023 & UIDAI Sec 29 Compliant`)
To comply with India’s strict data sovereignty laws (`Digital Personal Data Protection Act 2023` and `Aadhaar Act Section 29`), Aawaaz enforces a rigorous three-tier security taxonomy:
- **Tier 1: Strictly Confidential PII & Financial Data (`Zero-Cloud Cutoff Mandatory`)**:
  - `aadhar` (`12-Digit UID`), `bank_account` (`Account Number`), `ifsc` (`Branch Routing Code`), `ration_card`, `mobile`.
  - **Enforcement**: The instant any of these fields are requested or spoken (`including any spoken numerical sequence ≥8 digits`), Aawaaz **severs cloud transmission immediately**. Inference transitions 100% locally to our **On-Device Edge Engine (`Gemma 4 Autonomous`)** and local encrypted store (`Fernet AES-256`).
- **Tier 2: Highly Sensitive Health & Social Classification (`Shield Triggered`)**:
  - `disability_percentage`, `pregnancy_status`, `caste_category` (`SC/ST/OBC/General`).
  - **Enforcement**: Processed via local rule isolation to prevent external profiling.
- **Tier 3: General Demographic Metadata (`Cloud Edge Safe`)**:
  - `age`, `gender`, `occupation`, `income_annual`, `land_acres`, `crop_type`, `state`, `district`, `village`.
  - **Enforcement**: Safely routed to **Google Gemini 2.0 Flash** for rapid intent reasoning and multi-scheme eligibility cross-referencing.

---

### 2. 🤖 Intelligent Live DOM Autonomous Form Filler (`The Holy Grail of Automation`)
Unlike rigid RPA scripts that break when government ASP.NET portal IDs or layout structures change, Aawaaz introduces the **Intelligent Live DOM Auto-Filler (`_fill_live_dom_fields`)**:
- **Dynamic Live Page Discovery**: Upon navigating to any official portal (`e.g. pmkisan.gov.in/RegistrationFormNew.aspx` or `pmfby.gov.in`), Aawaaz inspects all visible interactive DOM elements (`<input>`, `<select>`, `<textarea>`).
- **Semantic Contextual Matching**: The engine extracts element attributes (`id`, `name`, `placeholder`, `aria-label`) and traverses the DOM hierarchy to read associated `<label>` text and preceding table cell headers.
- **Auto-Typing & Visual Verification (`Hackathon Demo Mode`)**: Aawaaz matches DOM labels with decrypted citizen profile fields, auto-types values, triggers native input/change events, and **flashes each filled field in bright emerald green (`slow_mo=600ms`)** so judges can watch every field populate in real time!
- **Safety Lock at OTP Trigger**: The automation intentionally draws a **glowing, pulsing red target border around the 'Get OTP / Submit' button and HALTS completely without clicking**, guaranteeing 100% visual proof with zero database pollution on live government portals.

---

### 3. 🛡️ Self-Healing Windows Proactor Subprocess Fallback
On Windows, async web frameworks (`FastAPI/Uvicorn running in --reload or multi-worker mode`) often spawn subthreads utilizing `SelectorEventLoop`, which throws `NotImplementedError` when launching Chromium child processes via `asyncio.create_subprocess_exec`.
- **Aawaaz Self-Healing Architecture**: If `server.py` detects an `NotImplementedError` during form automation, it intercepts the exception and self-heals by spawning a clean, dedicated Python worker process initialized with a strict `asyncio.WindowsProactorEventLoopPolicy()`. Chromium launches reliably every single time across all OS environments.

---

## 📂 Repository & Module Structure
```
aawaaz-final/
├── backend/
│   ├── server.py              ← FastAPI Orchestrator (PII Shield, Event Loop Self-Healing)
│   ├── requirements.txt       ← Enterprise Dependency Stack
│   ├── .env                   ← API Keys & Environment Configuration
│   ├── agent/
│   │   ├── state.py           ← UserProfile (Tier 1/2/3 Security Classification)
│   │   ├── eligibility.py     ← 26 Central & State Scheme Rules Engine
│   │   └── gemma_agent.py     ← Local Gemma 4 Autonomous & Gemini Hybrid Router
│   ├── form_filler/
│   │   └── form_filler.py     ← Intelligent Live DOM Discovery & Playwright Engine
│   ├── schemes/
│   │   └── schemes.json       ← Comprehensive JSON Registry of 26 Schemes
│   ├── storage/               ← Local Fernet AES-256 Encrypted Vault
│   └── ocr/                   ← Local Vision / Document OCR Scanner
├── frontend/
│   └── index.html             ← Dynamic 3D Waveform Orb Dashboard & Edge Status UI
└── DEMO_RECORDING_SCRIPT.md   ← Official 3-Minute Hackathon Video Pitch Storyboard
```

---

## 🚀 Quickstart Guide (Running Locally & On Mobile)

### Step 1: Environment Setup
```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
```

### Step 2: Start the Aawaaz Backend Server
```powershell
uvicorn server:app --host 0.0.0.0 --port 8000 --reload
```
> **API Documentation**: Interactive OpenAPI Swagger docs are instantly available at `http://localhost:8000/docs`.

### Step 3: Launch the Dashboard (`Desktop & Mobile`)
- **On Laptop**: Open `http://localhost:8000/index.html` in Google Chrome or Microsoft Edge.
- **On Mobile Phone (`Local Wi-Fi Network Demo`)**: Connect your phone and laptop to the same Wi-Fi router or mobile hotspot. Open your laptop's local IPv4 address on your phone's browser (`e.g., http://192.168.124.206:8000/index.html`).

---

## 🏆 The 3-Minute Hackathon Demo Script (`Winning Flow`)

1. **Voice-First Empathy**: Click **🎙️ बात करें (Speak)** and speak in fluent Hindi:  
   `"नमस्ते! मेरा नाम रामू है, मैं बिहार के एक छोटे गाँव का किसान हूँ।"`  
   *Notice the 3D Waveform Orb pulse gracefully as Aawaaz responds aloud in clear Hindi voice.*
2. **The PII Confidentiality Shield (`The DPDP Act Moment`)**: Speak your confidential details:  
   `"मेरी उम्र 45 साल है, और मेरा आधार नंबर 8943 2109 5678 है।"`  
   *Point to the top right status badge as it **instantly flips to orange**: **`🔒 Local PII Shield (Gemma 4)`**. Explain how cloud transmission severed instantly upon detecting 12-digit Aadhaar PII.*
3. **Air-Gapped Edge Mode (`Zero Connectivity`)**: Click the top left network toggle: **`⚡ Cloud Edge Connected`** → **`🛡️ Air-Gapped Edge Mode`**. Show how local offline reasoning immediately discovers eligibility for **PM-KISAN (`₹6,000/year`)** and **PM Fasal Bima Yojana**.
4. **The Money Shot (`Autonomous Live DOM Form Automation`)**: Click **`⚡ Auto-Fill Form`** on **PM Fasal Bima** (`or PM-KISAN`).  
   *Watch Chromium pop open on screen navigating directly to the official government portal. Watch fields populate automatically and flash emerald green, before halting safely at the **Get OTP button** surrounded by a pulsing red target border!*

---

## ⚖️ License & Compliance
- Built with ❤️ for the **Google DeepMind Bengaluru Hackathon**.
- Fully compliant with **India Digital Personal Data Protection (`DPDP`) Act 2023** and **Aadhaar Act Section 29**.
