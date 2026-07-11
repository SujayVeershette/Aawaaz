"""
Aawaaz Backend Server
Runs on http://localhost:8000
Frontend talks to this. This talks to Gemini API.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import os
import sys
import json
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agent.state import ConversationState
from agent.eligibility import (
    check_eligibility, get_next_question,
    load_schemes, get_missing_fields_for_eligible
)
from agent.gemma_agent import extract_profile_updates
from ocr.local_ocr import run_ocr, ocr_status
from form_filler.form_filler import fill_scheme_form, fill_scheme_form_sync, SCHEME_FORMS, PLAYWRIGHT_AVAILABLE

from google import genai

# ── Pydantic Request Models ──────────────────────────────────────
class ChatRequest(BaseModel):
    message: str = ""
    simulated_offline: bool = False

class ScanRequest(BaseModel):
    image: str = ""
    doc_type: str = "aadhar"

class FillFormRequest(BaseModel):
    scheme_id: str = "pm_kisan"
    headless: bool = False   # False = show browser window (better for demo!)

app = FastAPI(
    title="Aawaaz Backend API",
    description="Voice agent API for rural Indians to discover government schemes",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Global state (single user for hackathon demo) ──────────────
state = ConversationState()
schemes = load_schemes()

# ── Configure Gemini (google-genai SDK) ────────────────────────
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
if GEMINI_API_KEY:
    gemini_client = genai.Client(api_key=GEMINI_API_KEY)
    gemini_model = gemini_client  # Truthy alias for status checks
    print(f"[Server] Gemini configured ✓")
else:
    gemini_client = None
    gemini_model = None
    print(f"[Server] WARNING: No GEMINI_API_KEY found in .env")


SYSTEM_PROMPT = """You are Aawaaz (आवाज़), a warm and helpful voice agent for rural Indians who cannot read or write.
Your job: collect their profile through natural conversation and tell them which government schemes they qualify for.

RULES:
- Always respond in simple Hindi (mix of Devanagari and Hinglish is fine)
- Maximum 2-3 short sentences per response
- Be warm, patient, encouraging — like a trusted friend
- Ask only ONE question at a time
- Never use English jargon or technical terms
- If user says something unclear, gently ask again

CURRENT USER PROFILE: {profile}
ELIGIBLE SCHEMES SO FAR: {eligible}
NEXT FIELD NEEDED: {next_field}
NEXT QUESTION TO ASK: {next_question}
CONVERSATION HISTORY:
{history}

User just said: {user_input}

Respond naturally in Hindi. If next_field is not 'none', weave the next question naturally into your response."""


def build_gemini_prompt(user_input: str) -> str:
    profile = state.profile.to_dict()
    eligible = check_eligibility(state.profile, schemes)
    next_q = get_next_question(state.profile, schemes)

    return SYSTEM_PROMPT.format(
        profile=json.dumps(profile, ensure_ascii=False),
        eligible=json.dumps([s["name"] for s in eligible], ensure_ascii=False),
        next_field=next_q["field"] if next_q else "none — profile complete",
        next_question=next_q["question"] if next_q else "बताएं कि कौन सी योजनाएं मिलती हैं और apply करने को पूछें",
        history=state.get_history_text(last_n=6),
        user_input=user_input
    )


def get_rule_based_response(user_input: str = "") -> str:
    """Fallback when Gemini is unavailable."""
    lower_input = user_input.strip().lower()
    if lower_input in ["हेलो", "hello", "hi", "hey", "नमस्ते", "namaste", "namaskar", "start"] and not state.profile.name:
        return "नमस्ते! मैं आवाज़ हूँ। आपका पूरा नाम क्या है और आप क्या काम करते हैं?"

    next_q = get_next_question(state.profile, schemes)
    eligible = check_eligibility(state.profile, schemes)

    if next_q:
        q = next_q["question"]
        if next_q.get("can_scan"):
            q += " आप बोल सकते हैं या document camera के सामने रख सकते हैं।"
        return q
    elif eligible:
        names = "、".join([s["name"] for s in eligible[:3]])
        return f"बहुत अच्छा! आप {names} के लिए eligible हैं। क्या मैं आपका application तैयार करूं?"
    else:
        return "थोड़ी और जानकारी चाहिए। कृपया अपने बारे में बताते रहें।"


# ── ROUTES ────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {
        "status": "ok",
        "gemini": gemini_model is not None,
        "schemes_loaded": len(schemes),
        "ocr": ocr_status(),
        "form_filler": {
            "playwright": PLAYWRIGHT_AVAILABLE,
            "supported_schemes": list(SCHEME_FORMS.keys()),
        },
    }


@app.post("/chat")
def chat(payload: Optional[ChatRequest] = None):
    if payload is None:
        payload = ChatRequest()
    user_message = payload.message.strip()

    if not user_message:
        return {"response": "कृपया कुछ बोलें।", "mode": "gemini_live"}

    # Add to history
    state.add_turn("user", user_message)

    # Extract profile fields from speech BEFORE calling Gemini
    next_q = get_next_question(state.profile, schemes, skipped_fields=state.skipped_fields)
    if next_q:
        field_name = next_q["field"]
        updates = extract_profile_updates(user_message, field_name)
        if updates:
            state.profile.fill_from_dict(updates)
            state.field_ask_counts[field_name] = 0
            print(f"[Server] Extracted from speech: {updates}")
            try:
                from storage.local_db import save_profile
                save_profile(state.profile.to_dict())
            except Exception:
                pass
        else:
            state.field_ask_counts[field_name] = state.field_ask_counts.get(field_name, 0) + 1
            if state.field_ask_counts[field_name] >= 2:
                state.skipped_fields.add(field_name)
                print(f"[Server] Field '{field_name}' asked 2x without extraction — skipping (Gemma 4 local error recovery)")
                next_q = get_next_question(state.profile, schemes, skipped_fields=state.skipped_fields)

    # ── Privacy & PII Shield: Auto-route to local Gemma 4 for confidential fields ──
    is_confidential_turn = False
    if next_q and next_q["field"] in ("aadhar", "bank_account", "ifsc"):
        is_confidential_turn = True
        print(f"[Server] 🔒 Confidential PII field requested ('{next_q['field']}'). Auto-switching to Local Gemma 4 (gemma4:e2b) PII Shield!")
    elif any(char.isdigit() for char in user_message) and len([c for c in user_message if c.isdigit()]) >= 8:
        is_confidential_turn = True
        print("[Server] 🔒 Confidential spoken numbers (8+ digits) detected. Auto-switching to Local Gemma 4 PII Shield!")

    # Call Gemini ONLY if not simulated_offline AND not a confidential PII turn
    agent_response = None
    mode = "gemini_live"

    if not payload.simulated_offline and not is_confidential_turn and gemini_client:
        try:
            prompt = build_gemini_prompt(user_message)
            response = gemini_client.models.generate_content(
                model="gemini-flash-latest",
                contents=prompt,
            )
            agent_response = response.text.strip() if response.text else None
            if agent_response:
                print(f"[Server] Gemini response: {agent_response[:100]}...")
        except Exception as e:
            print(f"[Server] Gemini error: {e}")
            agent_response = None

    # Fallback / PII Shield routing to local Gemma 4 (gemma4:e2b) & rule-based engine
    if not agent_response or payload.simulated_offline or is_confidential_turn:
        mode = "gemma_local_pii_shield" if is_confidential_turn else "gemma_local"
        from agent.gemma_agent import query_gemma_ollama, build_prompt
        # Attempt local Gemma 4 (e2b) inference if Ollama is running locally
        try:
            gemma_prompt = build_prompt(state, user_message, schemes)
            gemma_resp = query_gemma_ollama(gemma_prompt, model="gemma4:e2b")
            if gemma_resp:
                agent_response = gemma_resp
                print("[Server] Gemma 4 (gemma4:e2b) local inference successful")
        except Exception as e:
            pass
        if not agent_response:
            agent_response = get_rule_based_response(user_message)
            if is_confidential_turn:
                print("[Server] 🔒 Local PII Shield -> Rule-based / Gemma 4 handled confidential turn cleanly")
            elif payload.simulated_offline:
                print("[Server] Simulated Offline -> Gemma Local (rule-based engine + Gemma 4 fall-through) triggered")

    state.add_turn("agent", agent_response)

    # Get updated eligibility
    eligible = check_eligibility(state.profile, schemes)

    return {
        "response": agent_response,
        "mode": mode,
        "eligible_schemes": [
            {"id": s["id"], "name": s["name"], "benefit": s["benefit"]}
            for s in eligible
        ],
        "profile_complete": len(state.profile.to_dict()),
        "next_field": next_q["field"] if next_q else None
    }


@app.post("/scan")
def scan(payload: Optional[ScanRequest] = None):
    """
    Handle document scan — LOCAL OCR only.
    Image data never leaves the device.
    Tesseract extracts fields; falls back to mock if not installed.
    """
    if payload is None:
        payload = ScanRequest()

    doc_type = payload.doc_type        # aadhar | ration | passbook
    image_b64 = payload.image          # base64-encoded photo from frontend camera

    print(f"[Server] /scan → doc_type={doc_type}, image={'yes' if image_b64 else 'no (mock)'}")

    # ── Run local OCR (Tesseract on-device) ──────────────────
    existing = state.profile.to_dict()
    extracted = run_ocr(image_b64, doc_type, existing_profile=existing)

    # ── Merge into profile ────────────────────────────────────
    state.profile.fill_from_dict(extracted)

    # ── Build confirmation message ────────────────────────────
    if not extracted:
        confirmation = "Document scan हुआ लेकिन कोई data नहीं मिला। दोबारा try करें।"
    elif doc_type == "aadhar":
        name = extracted.get("name", state.profile.name or "")
        uid  = extracted.get("aadhar", state.profile.aadhar or "")
        confirmation = (
            f"Aadhar scan हो गया! नाम: {name}"
            + (f", Aadhar: {uid}" if uid else "")
            + "। क्या यह सही है?"
        )
    elif doc_type == "ration":
        card_type = extracted.get("ration_card_type", "")
        fam_size  = extracted.get("family_size", "")
        confirmation = (
            f"Ration card scan हुआ: {card_type} card"
            + (f", {fam_size} सदस्य" if fam_size else "")
            + "। ठीक है?"
        )
    elif doc_type == "passbook":
        bank = extracted.get("bank_name", "")
        acc  = extracted.get("bank_account", "")
        masked = f"XXXX{acc[-4:]}" if acc and len(acc) >= 4 else acc
        confirmation = (
            f"Passbook scan: {bank + ' — ' if bank else ''}Account {masked}। Correct है?"
        )
    else:
        confirmation = "Document scan complete। Data save हो गया।"

    try:
        from storage.local_db import save_profile
        save_profile(state.profile.to_dict())
    except Exception:
        pass

    eligible = check_eligibility(state.profile, schemes)

    return {
        "response": confirmation,
        "extracted": extracted,
        "fields_count": len(extracted),
        "mode": "gemma_local",        # OCR always runs locally — offline safe
        "ocr_engine": ocr_status(),
        "eligible_schemes": [
            {"id": s["id"], "name": s["name"], "benefit": s["benefit"]}
            for s in eligible
        ],
    }


@app.post("/fill-form")
async def fill_form(payload: Optional[FillFormRequest] = None):
    """
    Open the real government scheme website and auto-fill the application
    form using data already collected in the user's profile.

    Returns:
      - List of fields filled and their values
      - Screenshot (base64 PNG) of the filled form
      - Hindi message for TTS playback
      - Paused at: OTP step (we always stop there)

    The browser window opens visibly (headless=False by default)
    so judges can watch the form being filled in real time.
    """
    if payload is None:
        payload = FillFormRequest()

    scheme_id = payload.scheme_id
    profile   = state.profile.to_dict()

    # ── Guard: need minimum profile data ──────────────────────
    if not profile:
        return {
            "success": False,
            "message": "पहले अपनी जानकारी दें — नाम, Aadhar, और bank details ज़रूरी हैं।",
        }


    # ── Check Playwright available ────────────────────────────
    if not PLAYWRIGHT_AVAILABLE:
        return {
            "success": False,
            "message": (
                "Form filler install नहीं है। "
                "Run: pip install playwright && playwright install chromium"
            ),
            "install_cmd": "pip install playwright && playwright install chromium",
        }

    # ── Run form filler (opens real browser directly in async event loop) ──────────────────
    print(f"[Server] /fill-form → scheme={scheme_id}, profile_fields={list(profile.keys())}")
    result = await fill_scheme_form(scheme_id, profile, headless=payload.headless)

    # ── Log what happened ─────────────────────────────────────
    if result.get("success"):
        n = len(result.get("fields_filled", []))
        print(f"[Server] Form fill complete: {n} fields filled for {scheme_id}")
    else:
        print(f"[Server] Form fill failed: {result.get('error', 'unknown')}")

    # ── Add profile summary to response ──────────────────────
    result["profile_used"] = {
        k: ("XXXX" + str(v)[-4:] if k in ("aadhar", "bank_account") else v)
        for k, v in profile.items()
    }

    return result


@app.get("/status")
def status():
    """Get current agent status — called after each turn."""
    eligible = check_eligibility(state.profile, schemes)
    next_q = get_next_question(state.profile, schemes)

    return {
        "eligible_schemes": [
            {"id": s["id"], "name": s["name"], "benefit": s["benefit"]}
            for s in eligible
        ],
        "mode": "gemini_live",
        "profile_fields": list(state.profile.to_dict().keys()),
        "turn_count": state.turn_count,
        "next_field": next_q["field"] if next_q else None,
        "next_question": next_q["question"] if next_q else None
    }


@app.post("/queue")
def queue_application():
    """Queue applications for submission."""
    eligible = check_eligibility(state.profile, schemes)
    profile = state.profile.to_dict()

    queued = []
    for scheme in eligible:
        from storage.local_db import queue_application as qa
        qa(scheme["id"], profile, scheme["name"])
        queued.append(scheme["name"])

    # Save profile
    from storage.local_db import save_profile
    save_profile(profile)

    return {
        "queued": queued,
        "message": f"{len(queued)} application{'s' if len(queued) > 1 else ''} queued successfully",
        "response": f"आपके {len(queued)} application{'s' if len(queued) > 1 else ''} save हो गए। Internet आने पर automatically submit हो जाएंगे।"
    }


@app.post("/reset")
def reset():
    """Reset conversation state — for new demo."""
    global state
    state = ConversationState()
    print("[Server] State reset")
    return {"status": "reset", "message": "नई शुरुआत हो गई।"}


# ── Serve Frontend Static Files (http://localhost:8000/index.html) ─────────
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

frontend_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend")
if os.path.exists(frontend_path):
    @app.get("/")
    @app.get("/index.html")
    def serve_index():
        return FileResponse(os.path.join(frontend_path, "index.html"))

    app.mount("/", StaticFiles(directory=frontend_path), name="frontend")


if __name__ == "__main__":
    import uvicorn
    print("\n" + "="*50)
    print("  AAWAAZ BACKEND SERVER (FastAPI)")
    print("  Running on http://localhost:8000")
    print("  API Docs available at http://localhost:8000/docs")
    print("  Gemini API:", "✓ Ready" if gemini_model else "✗ Missing API key")
    print("  Schemes loaded:", len(schemes))
    print("="*50 + "\n")
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
