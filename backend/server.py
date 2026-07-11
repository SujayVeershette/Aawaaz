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

from google import genai

# ── Pydantic Request Models ──────────────────────────────────────
class ChatRequest(BaseModel):
    message: str = ""
    simulated_offline: bool = False

class ScanRequest(BaseModel):
    image: str = ""
    doc_type: str = "aadhar"

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
        "schemes_loaded": len(schemes)
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
    next_q = get_next_question(state.profile, schemes)
    if next_q:
        updates = extract_profile_updates(user_message, next_q["field"])
        if updates:
            state.profile.fill_from_dict(updates)
            print(f"[Server] Extracted from speech: {updates}")

    # Call Gemini ONLY if not simulated_offline
    agent_response = None
    mode = "gemini_live"

    if not payload.simulated_offline and gemini_client:
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

    # Fallback to rule-based (Gemma Local)
    if not agent_response or payload.simulated_offline:
        agent_response = get_rule_based_response(user_message)
        mode = "gemma_local"
        if payload.simulated_offline:
            print("[Server] Simulated Offline -> Gemma Local rule-based triggered")

    state.add_turn("agent", agent_response)

    # Get updated eligibility
    eligible = check_eligibility(state.profile, schemes)

    return {
        "response": agent_response,
        "mode": mode,
        "eligible_schemes": [
            {"name": s["name"], "benefit": s["benefit"]}
            for s in eligible
        ],
        "profile_complete": len(state.profile.to_dict()),
        "next_field": next_q["field"] if next_q else None
    }


@app.post("/scan")
def scan(payload: Optional[ScanRequest] = None):
    """Handle document scan - OCR extraction."""
    if payload is None:
        payload = ScanRequest()
    image_data = payload.image
    doc_type = payload.doc_type

    print(f"[Server] Document scan requested: {doc_type}")

    # For hackathon demo: use mock OCR
    # In production: send to on-device ML Kit
    # For hackathon demo: smart mock OCR that respects what user already spoke
    # In production: send image_data to on-device ML Kit / Gemini Vision
    mock_data = {
        "aadhar": {
            "aadhar": "8943-2109-5678",
            "name": state.profile.name or "राजू कुमार",
            "age": state.profile.age or 42,
            "gender": state.profile.gender or "male",
            "state": state.profile.state or "कर्नाटक"
        },
        "ration_card": {
            "ration_card": "RC-KT-2023-4521",
            "ration_card_type": state.profile.ration_card_type or "BPL",
            "family_size": state.profile.family_size or 4
        },
        "bank_passbook": {
            "bank_account": "3456789012",
            "ifsc": "SBIN0012345"
        }
    }

    extracted = mock_data.get(doc_type, mock_data["aadhar"])

    # Merge into profile (sensitive data — stays local)
    state.profile.fill_from_dict(extracted)
    print(f"[Server] OCR extracted: {extracted}")

    # Build confirmation message
    if doc_type == "aadhar":
        confirmation = f"मैंने scan किया: नाम {extracted.get('name', '')}, Aadhar {extracted.get('aadhar', '')}। क्या यह सही है?"
    elif doc_type == "ration_card":
        confirmation = f"Ration card scan हुआ: {extracted.get('ration_card_type', '')} card, {extracted.get('family_size', '')} सदस्य। सही है?"
    else:
        confirmation = f"Document scan हो गया। जानकारी save हो गई।"

    eligible = check_eligibility(state.profile, schemes)

    return {
        "response": confirmation,
        "extracted": extracted,
        "mode": "gemma_local",  # OCR always runs locally
        "eligible_schemes": [
            {"name": s["name"], "benefit": s["benefit"]}
            for s in eligible
        ]
    }


@app.get("/status")
def status():
    """Get current agent status — called after each turn."""
    eligible = check_eligibility(state.profile, schemes)
    next_q = get_next_question(state.profile, schemes)

    return {
        "eligible_schemes": [
            {"name": s["name"], "benefit": s["benefit"]}
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
