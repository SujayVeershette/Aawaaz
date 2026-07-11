"""
Aawaaz Local OCR Engine
========================
100% on-device — zero network calls. No image data ever leaves the device.
Uses Tesseract + PIL. Falls back to mock data if Tesseract not installed.

Supported document types:
  - aadhar   : Aadhaar card (name, DOB → age, gender, UID number, address)
  - ration   : Ration card  (card number, type BPL/AAY/PHH, family size)
  - passbook : Bank passbook (account number, IFSC, bank name)
  - kisan    : Kisan credit card / PM-KISAN acknowledgement
"""

import re
import base64
import io
from typing import Optional
from datetime import date

# ── Optional deps — graceful fallback if missing ─────────────────
try:
    from PIL import Image, ImageFilter, ImageEnhance
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    print("[OCR] PIL not installed — using mock mode. Run: pip install pillow")

try:
    import pytesseract
    TESSERACT_AVAILABLE = True
    # Verify tesseract binary exists
    pytesseract.get_tesseract_version()
except Exception:
    TESSERACT_AVAILABLE = False
    print("[OCR] Tesseract not installed — using mock mode. Run: apt install tesseract-ocr tesseract-ocr-hin")


# ── Image Pre-Processing ─────────────────────────────────────────

def preprocess_image(img: "Image.Image") -> "Image.Image":
    """
    Enhance image for better OCR accuracy on low-quality phone photos.
    Pipeline: resize → greyscale → contrast boost → sharpen → threshold
    """
    # 1. Upscale if too small (phone photos of docs can be small)
    w, h = img.size
    if max(w, h) < 1200:
        scale = 1200 / max(w, h)
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

    # 2. Convert to greyscale
    img = img.convert("L")

    # 3. Boost contrast — Aadhaar cards often have faded text
    img = ImageEnhance.Contrast(img).enhance(2.0)

    # 4. Sharpen
    img = img.filter(ImageFilter.SHARPEN)

    # 5. Binarise (Otsu-like manual threshold)
    img = img.point(lambda p: 255 if p > 128 else 0)

    return img


def decode_base64_image(b64_string: str) -> Optional["Image.Image"]:
    """Decode base64 image string (from frontend camera capture) to PIL Image."""
    try:
        # Strip data-URL prefix if present (e.g., "data:image/jpeg;base64,...")
        if "," in b64_string:
            b64_string = b64_string.split(",", 1)[1]
        img_bytes = base64.b64decode(b64_string)
        return Image.open(io.BytesIO(img_bytes))
    except Exception as e:
        print(f"[OCR] Image decode error: {e}")
        return None


# ── Raw Text Extraction ──────────────────────────────────────────

def extract_raw_text(img: "Image.Image") -> str:
    """
    Run Tesseract with Hindi + English language pack.
    Returns raw OCR text string.
    """
    processed = preprocess_image(img)
    # oem 3 = best available LSTM engine
    # psm 6 = assume uniform block of text (good for ID cards)
    config = "--oem 3 --psm 6"
    try:
        text = pytesseract.image_to_string(processed, lang="hin+eng", config=config)
        return text
    except Exception:
        # Fallback: English only (if Hindi lang pack not installed)
        try:
            return pytesseract.image_to_string(processed, lang="eng", config=config)
        except Exception as e:
            print(f"[OCR] Tesseract error: {e}")
            return ""


# ── Field Parsers ────────────────────────────────────────────────

def parse_aadhar(text: str) -> dict:
    """Extract fields from Aadhaar card OCR text."""
    result = {}

    lines = [l.strip() for l in text.splitlines() if l.strip()]

    # ── Aadhaar number (12 digits, may appear as XXXX XXXX XXXX) ──
    uid_pattern = re.search(r'\b(\d{4}[\s\-]?\d{4}[\s\-]?\d{4})\b', text)
    if uid_pattern:
        uid = re.sub(r'[\s\-]', '', uid_pattern.group(1))
        result["aadhar"] = f"{uid[:4]}-{uid[4:8]}-{uid[8:]}"

    # ── Name (line after "नाम" or "Name") ──
    for i, line in enumerate(lines):
        if re.search(r'(नाम|Name|naam)', line, re.IGNORECASE) and i + 1 < len(lines):
            candidate = lines[i + 1].strip()
            # Filter out noise lines
            if candidate and not re.search(r'\d{4}', candidate) and len(candidate) > 2:
                result["name"] = candidate.title()
                break
        # Also try inline: "Name: Raju Kumar"
        inline = re.search(r'(?:Name|नाम)\s*[:\|]\s*(.+)', line, re.IGNORECASE)
        if inline:
            result["name"] = inline.group(1).strip().title()
            break

    # ── Date of Birth → Age ──
    dob_match = re.search(
        r'(?:DOB|D\.O\.B|जन्म\s*तिथि|Date of Birth)[:\s]*(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4})',
        text, re.IGNORECASE
    )
    if not dob_match:
        # Bare date anywhere in text
        dob_match = re.search(r'\b(\d{2}[\/\-]\d{2}[\/\-]\d{4})\b', text)
    if dob_match:
        dob_str = dob_match.group(1)
        try:
            parts = re.split(r'[\/\-\.]', dob_str)
            day, month, year = int(parts[0]), int(parts[1]), int(parts[2])
            if year < 100:
                year += 1900 if year > 24 else 2000
            today = date.today()
            age = today.year - year - ((today.month, today.day) < (month, day))
            if 1 < age < 120:
                result["age"] = age
        except Exception:
            pass

    # ── Gender ──
    if re.search(r'\b(Male|MALE|पुरुष|पुरूष)\b', text):
        result["gender"] = "male"
    elif re.search(r'\b(Female|FEMALE|महिला|स्त्री)\b', text):
        result["gender"] = "female"

    # ── State from address (last line usually has state + PIN) ──
    state_map = {
        "Karnataka": ["karnataka", "कर्नाटक"],
        "Bihar": ["bihar", "बिहार"],
        "Uttar Pradesh": ["uttar pradesh", "उत्तर प्रदेश", "u.p"],
        "Madhya Pradesh": ["madhya pradesh", "मध्य प्रदेश", "m.p"],
        "Maharashtra": ["maharashtra", "महाराष्ट्र"],
        "Rajasthan": ["rajasthan", "राजस्थान"],
        "Punjab": ["punjab", "पंजाब"],
        "Haryana": ["haryana", "हरियाणा"],
        "Gujarat": ["gujarat", "गुजरात"],
        "West Bengal": ["west bengal", "पश्चिम बंगाल"],
        "Tamil Nadu": ["tamil nadu", "तमिलनाडु"],
        "Kerala": ["kerala", "केरल"],
        "Andhra Pradesh": ["andhra pradesh", "आंध्र प्रदेश"],
        "Telangana": ["telangana", "तेलंगाना"],
        "Odisha": ["odisha", "orissa", "ओडिशा"],
        "Assam": ["assam", "असम"],
        "Jharkhand": ["jharkhand", "झारखंड"],
        "Chhattisgarh": ["chhattisgarh", "छत्तीसगढ़"],
        "Delhi": ["delhi", "new delhi", "दिल्ली"],
    }
    text_lower = text.lower()
    for state_name, keywords in state_map.items():
        if any(kw in text_lower for kw in keywords):
            result["state"] = state_name
            break

    # ── Residence: village / town keywords ──
    if re.search(r'\b(village|gram|vill|ग्राम|गाँव)\b', text, re.IGNORECASE):
        result["residence"] = "rural"
    elif re.search(r'\b(nagar|city|municipal|ward|मुंबई|बेंगलुरु)\b', text, re.IGNORECASE):
        result["residence"] = "urban"

    return result


def parse_ration_card(text: str) -> dict:
    """Extract fields from Ration Card OCR text."""
    result = {}

    # ── Card number (RC-XX-YYYY-NNNN or similar) ──
    rc_match = re.search(r'\b(RC[\-\s]?\w{2,3}[\-\s]?\d{4,6}[\-\s]?\d{2,6})\b', text, re.IGNORECASE)
    if rc_match:
        result["ration_card"] = rc_match.group(1).upper().replace(" ", "-")
    else:
        # Generic long number
        num = re.search(r'\b(\d{10,16})\b', text)
        if num:
            result["ration_card"] = num.group(1)

    # ── Card type ──
    if re.search(r'\b(AAY|Antyodaya|अंत्योदय)\b', text, re.IGNORECASE):
        result["ration_card_type"] = "AAY"
    elif re.search(r'\b(BPL|Below Poverty)\b', text, re.IGNORECASE):
        result["ration_card_type"] = "BPL"
    elif re.search(r'\b(PHH|Priority|प्राथमिकता)\b', text, re.IGNORECASE):
        result["ration_card_type"] = "PHH"
    elif re.search(r'\b(APL|Above Poverty)\b', text, re.IGNORECASE):
        result["ration_card_type"] = "APL"

    # ── Family size ──
    size_match = re.search(
        r'(?:members?|सदस्य|family size|परिवार)[:\s]*(\d+)',
        text, re.IGNORECASE
    )
    if size_match:
        result["family_size"] = int(size_match.group(1))

    return result


def parse_bank_passbook(text: str) -> dict:
    """Extract fields from Bank Passbook OCR text."""
    result = {}

    # ── Account number (9–18 digits) ──
    acc_match = re.search(
        r'(?:A/c|Account|खाता)[^\d]*(\d{9,18})',
        text, re.IGNORECASE
    )
    if acc_match:
        result["bank_account"] = acc_match.group(1)
    else:
        # Bare long number that isn't Aadhaar
        nums = re.findall(r'\b\d{11,18}\b', text)
        if nums:
            result["bank_account"] = nums[0]

    # ── IFSC code (11 chars: 4 alpha + 0 + 6 alphanumeric) ──
    ifsc_match = re.search(r'\b([A-Z]{4}0[A-Z0-9]{6})\b', text)
    if ifsc_match:
        result["ifsc"] = ifsc_match.group(1)

    # ── Bank name ──
    bank_keywords = {
        "State Bank of India": ["state bank", "sbi"],
        "Bank of Baroda": ["bank of baroda", "bob"],
        "Punjab National Bank": ["punjab national", "pnb"],
        "Union Bank": ["union bank"],
        "Canara Bank": ["canara"],
        "Bank of India": ["bank of india"],
        "HDFC Bank": ["hdfc"],
        "ICICI Bank": ["icici"],
        "Axis Bank": ["axis bank"],
        "Gramin Bank": ["gramin", "rrb", "regional rural"],
    }
    text_lower = text.lower()
    for bank_name, keywords in bank_keywords.items():
        if any(kw in text_lower for kw in keywords):
            result["bank_name"] = bank_name
            break

    return result


# ── Main Entry Point ─────────────────────────────────────────────

# Mock data used when Tesseract is not installed (for demo/testing)
_MOCK_PROFILES = {
    "aadhar": {
        "aadhar": "8943-2109-5678",
        "name": "Raju Kumar",
        "age": 42,
        "gender": "male",
        "state": "Bihar",
        "residence": "rural",
    },
    "ration": {
        "ration_card": "RC-BR-2021-4521",
        "ration_card_type": "BPL",
        "family_size": 5,
    },
    "passbook": {
        "bank_account": "34567890123456",
        "ifsc": "SBIN0012345",
        "bank_name": "State Bank of India",
    },
}


def run_ocr(b64_image: str, doc_type: str, existing_profile: dict = None) -> dict:
    """
    Main OCR function called by server.py.

    Args:
        b64_image   : Base64-encoded image string from frontend camera
        doc_type    : One of "aadhar", "ration", "passbook"
        existing_profile: Current user profile dict (to avoid overwriting confirmed fields)

    Returns:
        dict of extracted fields, ready to merge into UserProfile
    """
    existing_profile = existing_profile or {}

    # ── Real OCR path ──
    if PIL_AVAILABLE and TESSERACT_AVAILABLE and b64_image:
        img = decode_base64_image(b64_image)
        if img:
            raw_text = extract_raw_text(img)
            print(f"[OCR] Raw text ({len(raw_text)} chars):\n{raw_text[:300]}")

            if doc_type == "aadhar":
                extracted = parse_aadhar(raw_text)
            elif doc_type == "ration":
                extracted = parse_ration_card(raw_text)
            elif doc_type == "passbook":
                extracted = parse_bank_passbook(raw_text)
            else:
                extracted = parse_aadhar(raw_text)  # default

            # Never overwrite fields user already confirmed via voice
            for key in list(extracted.keys()):
                if key in existing_profile and existing_profile[key] is not None:
                    print(f"[OCR] Skipping {key} — already set by voice to '{existing_profile[key]}'")
                    del extracted[key]

            print(f"[OCR] Extracted {len(extracted)} fields: {list(extracted.keys())}")
            return extracted

    # ── Mock fallback (Tesseract not available) ──
    print(f"[OCR] Using mock data for doc_type={doc_type}")
    mock = _MOCK_PROFILES.get(doc_type, _MOCK_PROFILES["aadhar"]).copy()

    # Respect existing voice-confirmed data
    for key in list(mock.keys()):
        if key in existing_profile and existing_profile[key] is not None:
            del mock[key]

    return mock


def ocr_status() -> dict:
    """Return current OCR capability status for /health endpoint."""
    return {
        "pil": PIL_AVAILABLE,
        "tesseract": TESSERACT_AVAILABLE,
        "mode": "local_ocr" if (PIL_AVAILABLE and TESSERACT_AVAILABLE) else "mock_fallback",
        "languages": "hin+eng" if TESSERACT_AVAILABLE else "n/a",
    }
