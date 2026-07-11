"""
Aawaaz Gemma Agent
The reasoning brain of Aawaaz.
Uses Gemma 4 via ollama (easiest setup) or llama.cpp.
Falls back to rule-based mode if model unavailable (for testing).
"""

import json
import subprocess
import requests
import os
from typing import Optional
from agent.state import ConversationState, UserProfile
from agent.eligibility import load_schemes, check_eligibility, get_next_question


SYSTEM_PROMPT = """You are Aawaaz, a helpful voice agent for rural Indians who cannot read or write.
You speak in simple Hindi. You are warm, patient, and speak like a trusted friend.

Your job:
1. Collect the user's information through natural conversation
2. Identify which government schemes they are eligible for
3. Ask ONE question at a time — the most important missing field
4. If user shows a document, acknowledge the scanned data
5. When enough information is collected, tell them which schemes they qualify for
6. Ask for confirmation before queuing any application

Rules:
- Always respond in Hindi (Devanagari or Hinglish is fine)
- Never ask multiple questions at once
- Keep responses SHORT — 2-3 sentences max
- Never use technical jargon
- Always be encouraging

Current user profile: {profile}
Schemes user may qualify for: {eligible_schemes}
Next field needed: {next_field}
Next question to ask: {next_question}

Conversation so far:
{history}

User just said: {user_input}

Respond naturally in Hindi, incorporating the next question if relevant. Keep it warm and brief."""


def build_prompt(state: ConversationState, user_input: str, schemes: list) -> str:
    """Build the full prompt for Gemma with current state."""
    profile_dict = state.profile.to_dict()
    eligible = check_eligibility(state.profile, schemes)
    next_q = get_next_question(state.profile, schemes)

    return SYSTEM_PROMPT.format(
        profile=json.dumps(profile_dict, ensure_ascii=False, indent=2),
        eligible_schemes=json.dumps(
            [{"name": s["name"], "benefit": s["benefit"]} for s in eligible],
            ensure_ascii=False
        ),
        next_field=next_q["field"] if next_q else "none — all collected",
        next_question=next_q["question"] if next_q else "Congratulate user and list eligible schemes",
        history=state.get_history_text(last_n=6),
        user_input=user_input
    )


def query_gemma_ollama(prompt: str, model: str = "gemma2:2b") -> Optional[str]:
    """Query Gemma via Ollama (recommended for hackathon)."""
    try:
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.7,
                    "num_predict": 200,
                    "stop": ["\nUser:", "\nAawaaz:"]
                }
            },
            timeout=30
        )
        if response.status_code == 200:
            return response.json().get("response", "").strip()
    except Exception as e:
        print(f"[Ollama error]: {e}")
    return None


def query_gemma_llama_cpp(prompt: str, model_path: str = None) -> Optional[str]:
    """Query Gemma via llama.cpp binary."""
    if model_path is None:
        model_path = os.environ.get("GEMMA_MODEL_PATH", "./models/gemma-2b.gguf")

    if not os.path.exists(model_path):
        return None

    try:
        result = subprocess.run(
            [
                "./llama.cpp/main",
                "-m", model_path,
                "-p", prompt,
                "-n", "200",
                "--temp", "0.7",
                "-c", "4096",
                "--no-display-prompt"
            ],
            capture_output=True,
            text=True,
            timeout=60
        )
        return result.stdout.strip()
    except Exception as e:
        print(f"[llama.cpp error]: {e}")
    return None


def extract_profile_updates(user_input: str, current_field: str) -> dict:
    """
    Rule-based extraction of profile fields from user speech.
    Scans entire utterance across English and Hindi Devanagari script so no state/occupation/land info is lost!
    """
    updates = {}
    text = user_input.lower().strip()
    raw_text = user_input.strip() # for Devanagari matching

    # 1. State extraction (always scan or if current_field == 'state')
    states_map = {
        "karnataka": ["karnataka", "bengaluru", "bangalore", "कर्नाटक", "बेंगलुरु"],
        "bihar": ["bihar", "patna", "बिहार", "पटना"],
        "uttar pradesh": ["up", "uttar pradesh", "lucknow", "उत्तर प्रदेश", "यूपी"],
        "madhya pradesh": ["mp", "madhya pradesh", "bhopal", "मध्य प्रदेश"],
        "maharashtra": ["maharashtra", "mumbai", "pune", "महाराष्ट्र", "मुंबई"],
        "rajasthan": ["rajasthan", "jaipur", "राजस्थान", "जयपुर"],
        "punjab": ["punjab", "पंजाब"],
        "haryana": ["haryana", "हरियाणा"],
        "gujarat": ["gujarat", "गुजरात"],
        "west bengal": ["west bengal", "bengal", "kolkata", "पश्चिम बंगाल", "बंगाल"],
        "tamil nadu": ["tamil nadu", "chennai", "तमिलनाडु", "चेन्नई"],
        "kerala": ["kerala", "केरल"],
        "andhra pradesh": ["andhra", "andhra pradesh", "आंध्र प्रदेश"],
        "telangana": ["telangana", "hyderabad", "तेलंगाना"],
        "odisha": ["odisha", "orissa", "ओडिशा"],
        "assam": ["assam", "असम"],
        "jharkhand": ["jharkhand", "ranchi", "झारखंड"],
        "chhattisgarh": ["chhattisgarh", "छत्तीसगढ़"],
        "uttarakhand": ["uttarakhand", "उत्तराखंड"],
        "himachal pradesh": ["himachal", "हिमाचल"],
        "delhi": ["delhi", "new delhi", "दिल्ली"]
    }
    for st_name, kw_list in states_map.items():
        if any(kw in text or kw in raw_text for kw in kw_list):
            updates["state"] = st_name.title()
            break
    if current_field == "state" and "state" not in updates and len(raw_text.split()) <= 4:
        clean_st = raw_text.replace("बैंक", "").replace("bank", "").strip()
        if clean_st and clean_st not in ["हां", "ना", "yes", "no"]:
            updates["state"] = clean_st.title()

    # 2. Occupation extraction (always scan or if current_field == 'occupation')
    if any(w in text or w in raw_text for w in ["kisan", "farmer", "kheti", "zameen", "फार्मर", "किसान", "खेती", "कृषि"]):
        updates["occupation"] = "farmer"
    elif any(w in text or w in raw_text for w in ["mazdoor", "labour", "daily wage", "construction", "मजदूर", "लेबर", "दिहाड़ी"]):
        updates["occupation"] = "daily_wage"
    elif any(w in text or w in raw_text for w in ["ghar", "domestic", "bai", "safai", "घरेलू", "सफाई"]):
        updates["occupation"] = "domestic_worker"

    # 3. Land acres extraction
    if current_field == "land_acres" or "land_acres" in text or "एकड़" in raw_text or "acre" in text:
        import re
        nums = re.findall(r'[\d.]+', text)
        if nums:
            updates["land_acres"] = float(nums[0])
        elif current_field == "land_acres":
            if any(w in raw_text for w in ["दो", "2"]):
                updates["land_acres"] = 2.0
            elif any(w in raw_text for w in ["एक", "1"]):
                updates["land_acres"] = 1.0
            elif any(w in raw_text for w in ["तीन", "3"]):
                updates["land_acres"] = 3.0
            elif any(w in raw_text or w in text for w in ["हां", "hai", "yes", "haan", "सही", "sahi"]):
                updates["land_acres"] = 2.0  # default 2 acres

    # 4. Name extraction
    if current_field == "name":
        for prefix in ["mera naam ", "main ", "mujhe ", "naam hai ", "मेरा नाम ", "मैं "]:
            if prefix in text or prefix in raw_text:
                name_part = raw_text.split(prefix)[-1].strip()
                updates["name"] = name_part.title()
                break
        if "name" not in updates and len(raw_text.split()) <= 4:
            updates["name"] = raw_text.strip().title()

    # 5. Age extraction
    if current_field == "age" or "saal" in text or "साल" in raw_text or "umr" in text or "उम्र" in raw_text:
        import re
        nums = re.findall(r'\d+', text)
        if nums:
            age = int(nums[0])
            if 1 < age < 120:
                updates["age"] = age
        elif current_field == "age" and any(w in raw_text for w in ["पचास", "fifty"]):
            updates["age"] = 50

    # 6. Gender extraction
    if current_field == "gender" or any(w in text or w in raw_text for w in ["mahila", "aurat", "ladki", "female", "woman", "purush", "aadmi", "ladka", "male", "man", "महिला", "पुरुष"]):
        if any(w in text or w in raw_text for w in ["mahila", "aurat", "ladki", "female", "woman", "महिला", "औरत", "लड़की"]):
            updates["gender"] = "female"
        elif any(w in text or w in raw_text for w in ["purush", "aadmi", "ladka", "male", "man", "पुरुष", "आदमी", "लड़का"]):
            updates["gender"] = "male"

    # 7. Residence extraction
    if current_field == "residence" or any(w in text or w in raw_text for w in ["gaon", "village", "gram", "rural", "sheher", "city", "urban", "town", "गाँव", "गांव", "शहर"]):
        if any(w in text or w in raw_text for w in ["gaon", "village", "gram", "rural", "गाँव", "गांव"]):
            updates["residence"] = "rural"
        elif any(w in text or w in raw_text for w in ["sheher", "city", "urban", "town", "शहर"]):
            updates["residence"] = "urban"

    # 8. Income extraction
    if current_field == "income_annual":
        import re
        nums = re.findall(r'[\d,]+', text.replace(",", ""))
        if nums:
            income = int(nums[0].replace(",", ""))
            if "lakh" in text or "lac" in text or "लाख" in raw_text:
                income = income * 100000
            updates["income_annual"] = income

    # 9. Family size
    if current_field == "family_size":
        import re
        nums = re.findall(r'\d+', text)
        if nums:
            size = int(nums[0])
            if 1 <= size <= 30:
                updates["family_size"] = size

    # 10. Aadhar number
    if current_field == "aadhar":
        import re
        digits = re.findall(r'\d', text)
        if len(digits) >= 12:
            aadhar = "".join(digits[:12])
            updates["aadhar"] = f"{aadhar[:4]}-{aadhar[4:8]}-{aadhar[8:]}"

    # 11. Ration card type
    if current_field == "ration_card_type" or any(w in text for w in ["bpl", "aay", "phh"]):
        if "bpl" in text:
            updates["ration_card_type"] = "BPL"
        elif "aay" in text or "antyodaya" in text:
            updates["ration_card_type"] = "AAY"
        elif "phh" in text:
            updates["ration_card_type"] = "PHH"

    # 12. Caste category
    if current_field == "caste_category":
        if "sc" in text.split() or "scheduled caste" in text or "dalit" in text:
            updates["caste_category"] = "SC"
        elif "st" in text.split() or "scheduled tribe" in text or "adivasi" in text:
            updates["caste_category"] = "ST"
        elif "obc" in text or "other backward" in text:
            updates["caste_category"] = "OBC"
        elif "general" in text or "open" in text:
            updates["caste_category"] = "General"

    # 13. Boolean fields
    if current_field == "lpg_connection":
        if any(w in text or w in raw_text for w in ["haan", "yes", "hai", "h", "हाँ", "हां"]):
            updates["lpg_connection"] = True
        elif any(w in text or w in raw_text for w in ["nahi", "no", "nhi", "nahin", "नहीं", "ना"]):
            updates["lpg_connection"] = False

    if current_field == "bank_account_exists":
        if any(w in text or w in raw_text for w in ["haan", "yes", "hai", "h", "हाँ", "हां"]):
            updates["bank_account_exists"] = True
        elif any(w in text or w in raw_text for w in ["nahi", "no", "nhi", "nahin", "नहीं", "ना"]):
            updates["bank_account_exists"] = False

    return updates


def get_fallback_response(state: ConversationState, schemes: list) -> str:
    """
    Rule-based response when Gemma is unavailable.
    Used for testing without model.
    """
    next_q = get_next_question(state.profile, schemes)
    eligible = check_eligibility(state.profile, schemes)

    if next_q:
        can_scan = next_q.get("can_scan", False)
        q = next_q["question"]
        if can_scan:
            q += " Aap bol sakte hain ya document camera ke saamne rakh sakte hain."
        return q
    elif eligible:
        names = [s["name"] for s in eligible[:3]]
        return (
            f"Bahut achha! Aap {', '.join(names)} ke liye eligible hain. "
            f"Kya main aapka application taiyaar karoon?"
        )
    else:
        return "Thoda aur information chahiye. Kripya apni details batate rahiye."


class AawaazAgent:
    """
    Main agent class.
    Orchestrates: STT → Profile extraction → Gemma reasoning → TTS
    """

    def __init__(self, model_backend: str = "ollama"):
        self.schemes = load_schemes()
        self.model_backend = model_backend
        self.use_gemma = True

    def process_turn(self, state: ConversationState, user_input: str,
                     ocr_data: dict = None) -> str:
        """
        Process one conversation turn.
        1. Extract profile updates from speech
        2. Merge OCR data if available
        3. Query Gemma for response
        4. Return agent response
        """
        # Add user input to history
        state.add_turn("user", user_input)

        # Get current missing field
        next_q = get_next_question(state.profile, self.schemes)
        current_field = next_q["field"] if next_q else None

        # Extract profile fields from speech
        if current_field:
            extracted = extract_profile_updates(user_input, current_field)
            if extracted:
                state.profile.fill_from_dict(extracted)
                print(f"[Agent] Extracted from speech: {extracted}")

        # Merge OCR data if document was scanned
        if ocr_data:
            state.profile.fill_from_dict(ocr_data)
            print(f"[Agent] Merged OCR data: {ocr_data}")

        # Build prompt and query Gemma
        response = None
        if self.use_gemma:
            prompt = build_prompt(state, user_input, self.schemes)

            if self.model_backend == "ollama":
                response = query_gemma_ollama(prompt)
            elif self.model_backend == "llama_cpp":
                response = query_gemma_llama_cpp(prompt)

        # Fallback if Gemma unavailable
        if not response:
            print("[Agent] Gemma unavailable, using rule-based fallback")
            response = get_fallback_response(state, self.schemes)

        # Add agent response to history
        state.add_turn("agent", response)

        # Check if we should show eligibility results
        eligible = check_eligibility(state.profile, self.schemes)
        state.eligible_schemes = [s["id"] for s in eligible]

        print(f"[Agent] Profile so far: {state.profile.to_dict()}")
        print(f"[Agent] Eligible schemes: {[s['name'] for s in eligible]}")
        print(f"[Agent] Next field needed: {current_field}")

        return response
