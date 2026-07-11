"""
Aawaaz Form Filler
==================
Uses Playwright (async) to open real government scheme websites
and auto-fill form fields from the user's collected profile.

Strategy:
  1. Open the real portal URL in a visible browser (so judges can see it)
  2. Navigate to the registration/application form
  3. Auto-fill every field we have data for
  4. STOP before OTP / CAPTCHA — print clear message and highlight unfilled fields
  5. Return a status dict for the server to relay to the frontend

Why stop before OTP:
  - Government sites require Aadhaar OTP to the user's registered mobile
  - This is intentional — the agent can't and shouldn't bypass it
  - The demo shows: "Agent fills everything, user only needs to enter OTP"
  - That IS the value proposition — illiterate user only does the one thing they can (receive OTP)

Usage (from server.py):
    from form_filler.form_filler import fill_scheme_form
    result = await fill_scheme_form("pm_kisan", profile_dict)

Requires:
    pip install playwright
    playwright install chromium
"""

import asyncio
import json
from typing import Optional

try:
    from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    print("[FormFiller] Playwright not installed. Run: pip install playwright && playwright install chromium")


# ── Scheme Form Configs ──────────────────────────────────────────
# Each entry defines:
#   url        : Direct URL to the form page (not homepage)
#   fields     : List of {selector, profile_key, label} to fill
#   otp_trigger: CSS selector that triggers OTP (we stop just before this)
#   pause_msg  : Message shown to user when we pause

SCHEME_FORMS = {
    "pm_kisan": {
        "name": "PM-KISAN",
        "url": "https://pmkisan.gov.in/RegistrationForm.aspx",
        "fields": [
            # The actual PM-KISAN form uses Aadhaar for lookup first
            # After lookup, these fields appear:
            {"selector": "#ContentPlaceHolder1_txtfarmername, input[placeholder*='Name'], input[id*='farmer'], input[id*='name']",  "profile_key": "name",         "label": "Farmer Name"},
            {"selector": "#ContentPlaceHolder1_ddlfarmercategory, select[id*='category'], select[id*='caste']", "profile_key": "caste_category", "label": "Category", "type": "select"},
            {"selector": "#ContentPlaceHolder1_txtmobileno, input[placeholder*='Mobile'], input[id*='mobile']",    "profile_key": "mobile",       "label": "Mobile Number"},
            {"selector": "#ContentPlaceHolder1_txtaccno, input[placeholder*='Account'], input[id*='accno'], input[id*='account']",       "profile_key": "bank_account", "label": "Account Number"},
            {"selector": "#ContentPlaceHolder1_ddlbankname, select[id*='bank']",    "profile_key": "bank_name",    "label": "Bank Name", "type": "select"},
            {"selector": "#ContentPlaceHolder1_txtifsccode, input[placeholder*='IFSC'], input[id*='ifsc']",    "profile_key": "ifsc",         "label": "IFSC Code"},
            {"selector": "#ContentPlaceHolder1_txtaddress1, input[placeholder*='Address'], input[id*='address'], input[id*='village']",    "profile_key": "village",      "label": "Village / Address"},
            {"selector": "#ContentPlaceHolder1_txtdistrict, input[placeholder*='District'], input[id*='district']",    "profile_key": "district",     "label": "District"},
        ],
        "aadhar_field": "#ContentPlaceHolder1_txtadharno, input[placeholder*='Aadhaar'], input[id*='adhar'], input[id*='aadhar']",
        "aadhar_submit": "#ContentPlaceHolder1_btnsubmit, button:has-text('Submit'), input[type='submit']",
        "otp_trigger": "#ContentPlaceHolder1_btnsendotp, button:has-text('Get OTP'), button:has-text('Send OTP'), input[value*='OTP']",
        "pause_msg": "PM-KISAN form filled! Click 'Get OTP' — you will receive an OTP on your registered mobile number.",
        "highlight_color": "#4ade80",  # green
    },

    "pmay_g": {
        "name": "PMAY-G (Gramin)",
        "url": "https://pmayg.nic.in/netiay/home.aspx",
        "fields": [
            {"selector": "input[name*='name'], input[id*='name']",      "profile_key": "name",         "label": "Applicant Name"},
            {"selector": "input[name*='father'], input[id*='father']",   "profile_key": "guardian_name","label": "Father/Husband Name"},
            {"selector": "input[name*='mobile'], input[id*='mobile']",   "profile_key": "mobile",       "label": "Mobile"},
            {"selector": "input[name*='aadhar'], input[id*='aadhar']",   "profile_key": "aadhar",       "label": "Aadhaar"},
        ],
        "otp_trigger": "input[type='submit'][value*='OTP'], button:has-text('OTP')",
        "pause_msg": "PMAY-G form filled! OTP required — check your Aadhaar-linked mobile.",
        "highlight_color": "#60a5fa",  # blue
    },

    "ayushman_bharat": {
        "name": "Ayushman Bharat (PMJAY)",
        "url": "https://beneficiary.nha.gov.in/",
        "fields": [
            {"selector": "input[placeholder*='Mobile'], input[id*='mobile']", "profile_key": "mobile", "label": "Mobile Number"},
        ],
        "otp_trigger": "button:has-text('Get OTP'), input[value*='OTP']",
        "pause_msg": "Ayushman Bharat portal opened. Enter your mobile number and click 'Get OTP' to check eligibility.",
        "highlight_color": "#f97316",  # orange
    },

    "pm_ujjwala": {
        "name": "PM Ujjwala Yojana",
        "url": "https://www.pmuy.gov.in/ujjwala2.html",
        "fields": [
            {"selector": "input[name*='name'], input[id*='name']",        "profile_key": "name",    "label": "Name"},
            {"selector": "input[name*='mobile'], input[id*='mobile']",    "profile_key": "mobile",  "label": "Mobile"},
            {"selector": "input[name*='aadhar'], input[id*='aadhar']",    "profile_key": "aadhar",  "label": "Aadhaar"},
            {"selector": "input[name*='address'], input[id*='address']",  "profile_key": "village", "label": "Address"},
        ],
        "otp_trigger": "button:has-text('Submit'), input[type='submit']",
        "pause_msg": "Ujjwala form filled! Review the details and submit — you may need Aadhaar OTP.",
        "highlight_color": "#a78bfa",  # purple
    },

    "jan_dhan": {
        "name": "Jan Dhan Yojana",
        "url": "https://pmjdy.gov.in/scheme",
        "fields": [],  # PMJDY requires visiting a bank branch; portal is informational
        "otp_trigger": None,
        "pause_msg": "PM Jan Dhan Yojana: Visit your nearest bank branch with Aadhaar to open a zero-balance account. I've pre-filled your details below.",
        "highlight_color": "#34d399",
    },

    "pm_fasal_bima": {
        "name": "PM Fasal Bima Yojana (PMFBY)",
        "url": "https://pmfby.gov.in/farmerRegistrationForm",
        "fields": [
            {"selector": "input[placeholder*='Name'], input[id*='name'], input[name*='name']", "profile_key": "name", "label": "Farmer Name"},
            {"selector": "input[placeholder*='Mobile'], input[id*='mobile'], input[name*='mobile']", "profile_key": "mobile", "label": "Mobile Number"},
            {"selector": "input[placeholder*='Aadhaar'], input[id*='aadhar'], input[name*='aadhar']", "profile_key": "aadhar", "label": "Aadhaar Number"},
            {"selector": "input[placeholder*='Address'], input[id*='address'], input[name*='address']", "profile_key": "village", "label": "Village/Address"},
            {"selector": "input[placeholder*='Account'], input[id*='account'], input[name*='account']", "profile_key": "bank_account", "label": "Account Number"},
            {"selector": "input[placeholder*='IFSC'], input[id*='ifsc'], input[name*='ifsc']", "profile_key": "ifsc", "label": "IFSC Code"},
        ],
        "aadhar_field": "input[placeholder*='Aadhaar'], input[id*='aadhar']",
        "otp_trigger": "button:has-text('Submit'), button:has-text('Get OTP'), button:has-text('Verify')",
        "pause_msg": "PM Fasal Bima form filled! Click 'Get OTP' / 'Submit' to complete verification.",
        "highlight_color": "#10b981",
    },

    "e_shram": {
        "name": "e-Shram Portal",
        "url": "https://register.eshram.gov.in/#/user/self",
        "fields": [
            {"selector": "input[placeholder*='Aadhaar'], input[id*='aadhar']", "profile_key": "aadhar", "label": "Aadhaar Number"},
            {"selector": "input[placeholder*='Mobile'], input[id*='mobile']", "profile_key": "mobile", "label": "Aadhaar Linked Mobile"},
        ],
        "aadhar_field": "input[placeholder*='Aadhaar'], input[id*='aadhar']",
        "otp_trigger": "button:has-text('Send OTP'), button:has-text('Submit'), input[value*='OTP']",
        "pause_msg": "e-Shram portal ready! Click 'Send OTP' to verify your Aadhaar linked mobile number.",
        "highlight_color": "#3b82f6",
    },

    "sukanya_samridhi": {
        "name": "Sukanya Samriddhi Yojana",
        "url": "https://www.nsiindia.gov.in/InternalPage.aspx?Id_Pk=89",
        "fields": [
            {"selector": "input[name*='name']", "profile_key": "name", "label": "Applicant Name"},
            {"selector": "input[name*='mobile']", "profile_key": "mobile", "label": "Mobile"},
        ],
        "otp_trigger": None,
        "pause_msg": "Sukanya Samriddhi Yojana: Portal opened and details prepared. Visit your nearest post office or bank branch to deposit initial form.",
        "highlight_color": "#ec4899",
    },

    "viklang_pension": {
        "name": "Indira Gandhi National Disability Pension",
        "url": "https://nsap.nic.in/",
        "fields": [
            {"selector": "input[name*='name'], input[id*='name']", "profile_key": "name", "label": "Applicant Name"},
            {"selector": "input[name*='mobile'], input[id*='mobile']", "profile_key": "mobile", "label": "Mobile Number"},
            {"selector": "input[name*='aadhar'], input[id*='aadhar']", "profile_key": "aadhar", "label": "Aadhaar"},
        ],
        "otp_trigger": "button:has-text('Submit'), button:has-text('Apply'), input[type='submit']",
        "pause_msg": "Disability Pension portal ready! Review your details and proceed for verification.",
        "highlight_color": "#8b5cf6",
    },

    "old_age_pension": {
        "name": "Indira Gandhi National Old Age Pension",
        "url": "https://nsap.nic.in/",
        "fields": [
            {"selector": "input[name*='name'], input[id*='name']", "profile_key": "name", "label": "Applicant Name"},
            {"selector": "input[name*='mobile'], input[id*='mobile']", "profile_key": "mobile", "label": "Mobile Number"},
            {"selector": "input[name*='aadhar'], input[id*='aadhar']", "profile_key": "aadhar", "label": "Aadhaar"},
        ],
        "otp_trigger": "button:has-text('Submit'), button:has-text('Apply'), input[type='submit']",
        "pause_msg": "Old Age Pension portal ready! Review your details and proceed for verification.",
        "highlight_color": "#f59e0b",
    },

    "kisan_credit_card": {
        "name": "Kisan Credit Card (KCC)",
        "url": "https://www.myscheme.gov.in/schemes/kcc",
        "fields": [
            {"selector": "input[name*='name'], input[id*='name']", "profile_key": "name", "label": "Farmer Name"},
            {"selector": "input[name*='mobile'], input[id*='mobile']", "profile_key": "mobile", "label": "Mobile Number"},
            {"selector": "input[name*='aadhar'], input[id*='aadhar']", "profile_key": "aadhar", "label": "Aadhaar"},
        ],
        "otp_trigger": "button:has-text('Apply'), button:has-text('Check Eligibility')",
        "pause_msg": "Kisan Credit Card portal opened! Details loaded for verification.",
        "highlight_color": "#14b8a6",
    },

    "matru_vandana": {
        "name": "Pradhan Mantri Matru Vandana Yojana (PMMVY)",
        "url": "https://pmmvy.wcd.gov.in/",
        "fields": [
            {"selector": "input[name*='name'], input[id*='name']", "profile_key": "name", "label": "Beneficiary Name"},
            {"selector": "input[name*='mobile'], input[id*='mobile']", "profile_key": "mobile", "label": "Mobile Number"},
            {"selector": "input[name*='aadhar'], input[id*='aadhar']", "profile_key": "aadhar", "label": "Aadhaar Number"},
        ],
        "otp_trigger": "button:has-text('Login'), button:has-text('Send OTP'), button:has-text('Verify')",
        "pause_msg": "PMMVY portal opened! Verify your mobile number via OTP to submit application.",
        "highlight_color": "#f43f5e",
    },

    "sc_scholarship": {
        "name": "Post-Matric Scholarship for SC Students",
        "url": "https://scholarships.gov.in/",
        "fields": [
            {"selector": "input[name*='name'], input[id*='name']", "profile_key": "name", "label": "Student Name"},
            {"selector": "input[name*='mobile'], input[id*='mobile']", "profile_key": "mobile", "label": "Mobile Number"},
            {"selector": "input[name*='aadhar'], input[id*='aadhar']", "profile_key": "aadhar", "label": "Aadhaar Number"},
        ],
        "otp_trigger": "button:has-text('Submit'), button:has-text('Send OTP')",
        "pause_msg": "National Scholarship Portal opened! Verify via OTP to continue registration.",
        "highlight_color": "#6366f1",
    },

    "obc_scholarship": {
        "name": "Post-Matric Scholarship for OBC Students",
        "url": "https://scholarships.gov.in/",
        "fields": [
            {"selector": "input[name*='name'], input[id*='name']", "profile_key": "name", "label": "Student Name"},
            {"selector": "input[name*='mobile'], input[id*='mobile']", "profile_key": "mobile", "label": "Mobile Number"},
            {"selector": "input[name*='aadhar'], input[id*='aadhar']", "profile_key": "aadhar", "label": "Aadhaar Number"},
        ],
        "otp_trigger": "button:has-text('Submit'), button:has-text('Send OTP')",
        "pause_msg": "National Scholarship Portal opened! Verify via OTP to continue registration.",
        "highlight_color": "#06b6d4",
    },

    "mnrega": {
        "name": "Mahatma Gandhi NREGA Job Card",
        "url": "https://nrega.nic.in/",
        "fields": [
            {"selector": "input[name*='name'], input[id*='name']", "profile_key": "name", "label": "Applicant Name"},
            {"selector": "input[name*='mobile'], input[id*='mobile']", "profile_key": "mobile", "label": "Mobile Number"},
        ],
        "otp_trigger": "button:has-text('Submit'), button:has-text('Search'), button:has-text('Register')",
        "pause_msg": "MGNREGA portal opened! Review details to register for job card.",
        "highlight_color": "#84cc16",
    },
}


# ── Core Filler ──────────────────────────────────────────────────

async def fill_scheme_form(
    scheme_id: str,
    profile: dict,
    headless: bool = False,   # False = show browser to judges!
    slow_mo: int = 600,       # ms between actions — makes it visible
) -> dict:
    """
    Open scheme portal and auto-fill form with profile data.

    Returns:
        {
          "success": bool,
          "scheme": str,
          "fields_filled": [{"label": str, "value": str}],
          "fields_skipped": [str],   # profile fields we didn't have
          "paused_at": str,          # what stopped us (OTP/CAPTCHA)
          "message": str,            # Hindi message for user
          "screenshot_b64": str,     # base64 PNG of final state
        }
    """
    if not PLAYWRIGHT_AVAILABLE:
        return {
            "success": False,
            "error": "Playwright not installed",
            "message": "Form filler not available. Install playwright first.",
        }

    config = SCHEME_FORMS.get(scheme_id)
    if not config:
        config = {
            "name": scheme_id.replace("_", " ").title(),
            "url": "https://www.myscheme.gov.in/search",
            "fields": [
                {"selector": "input[placeholder*='Search'], input[type='text']", "profile_key": "name", "label": "Applicant Info"},
            ],
            "otp_trigger": "button:has-text('Apply'), button:has-text('Submit')",
            "pause_msg": f"{scheme_id.replace('_', ' ').title()} portal ready! Pre-filling user profile details.",
            "highlight_color": "#38bdf8",
        }

    fields_filled = []
    fields_skipped = []
    screenshot_b64 = None

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=headless,
            slow_mo=slow_mo,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",  # avoid bot detection
            ]
        )
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            locale="hi-IN",   # Indian locale for form defaults
        )
        page = await context.new_page()

        try:
            # ── 1. Navigate to form ──
            print(f"[FormFiller] Opening {config['url']}")
            try:
                await page.goto(config["url"], wait_until="domcontentloaded", timeout=30000)
            except Exception as e:
                print(f"[FormFiller] goto warning/timeout ({e}), continuing with partial DOM...")
            await page.wait_for_timeout(2000)  # let JS render

            # ── 2. Fill Aadhaar field first (many portals start with Aadhaar lookup) ──
            aadhar_sel = config.get("aadhar_field")
            if aadhar_sel and profile.get("aadhar"):
                try:
                    await page.wait_for_selector(aadhar_sel, timeout=5000)
                    await page.fill(aadhar_sel, profile["aadhar"].replace("-", ""))
                    await _highlight_field(page, aadhar_sel, "#facc15")  # yellow
                    fields_filled.append({"label": "Aadhaar Number", "value": profile["aadhar"]})
                    print(f"[FormFiller] Filled Aadhaar: {profile['aadhar']}")
                    await page.wait_for_timeout(800)
                except PlaywrightTimeout:
                    print(f"[FormFiller] Aadhaar field not found: {aadhar_sel}")

            # ── 3. Fill all configured fields ──
            for field_config in config.get("fields", []):
                selector = field_config["selector"]
                profile_key = field_config["profile_key"]
                label = field_config["label"]
                field_type = field_config.get("type", "input")

                value = profile.get(profile_key)
                if not value:
                    fields_skipped.append(f"{label} (no data)")
                    continue

                try:
                    element = await page.wait_for_selector(selector, timeout=3000)
                    if not element:
                        fields_skipped.append(f"{label} (selector not found)")
                        continue

                    if field_type == "select":
                        await _fill_select(page, selector, str(value))
                    else:
                        await page.fill(selector, str(value))

                    await _highlight_field(page, selector, config["highlight_color"])
                    fields_filled.append({"label": label, "value": str(value)})
                    print(f"[FormFiller] ✓ Filled '{label}' = '{value}'")
                    await page.wait_for_timeout(400)

                except PlaywrightTimeout:
                    fields_skipped.append(f"{label} (field not visible)")
                    print(f"[FormFiller] ✗ Field not found: {label} ({selector})")
                except Exception as e:
                    fields_skipped.append(f"{label} (error: {str(e)[:40]})")
                    print(f"[FormFiller] ✗ Error filling '{label}': {e}")

            # ── 4. Highlight the OTP button and PAUSE ──
            otp_sel = config.get("otp_trigger")
            if otp_sel:
                try:
                    otp_btn = await page.wait_for_selector(otp_sel, timeout=5000)
                    if otp_btn:
                        # Pulse-highlight the OTP button in red to draw attention
                        await page.evaluate(f"""
                            const btn = document.querySelector('{otp_sel.replace("'", "\\'")}');
                            if (btn) {{
                                btn.style.border = '3px solid #ef4444';
                                btn.style.boxShadow = '0 0 15px #ef4444';
                                btn.style.animation = 'pulse 1s infinite';
                                btn.scrollIntoView({{behavior: 'smooth', block: 'center'}});
                            }}
                        """)
                        print(f"[FormFiller] ⏸ Paused at OTP trigger: {otp_sel}")
                except PlaywrightTimeout:
                    print("[FormFiller] OTP button not visible yet (may appear after Aadhaar lookup)")

            # ── 5. Take screenshot of filled state ──
            await page.wait_for_timeout(1000)
            screenshot_bytes = await page.screenshot(full_page=False)
            import base64
            screenshot_b64 = base64.b64encode(screenshot_bytes).decode("utf-8")

            # ── 6. Build result ──
            pause_msg = config.get("pause_msg", "Form filled! OTP required to proceed.")

            # Hindi message for TTS
            n_filled = len(fields_filled)
            hindi_message = (
                f"मैंने {config['name']} का form भर दिया है। "
                f"{n_filled} field{'s' if n_filled != 1 else ''} automatically fill हो गए। "
                f"अब OTP enter करें जो आपके mobile पर आएगा।"
            )

            return {
                "success": True,
                "scheme": config["name"],
                "fields_filled": fields_filled,
                "fields_skipped": fields_skipped,
                "paused_at": "otp_required",
                "pause_message": pause_msg,
                "message": hindi_message,
                "screenshot_b64": screenshot_b64,
            }

        except Exception as e:
            print(f"[FormFiller] Error: {e}")
            # Still try screenshot
            try:
                screenshot_bytes = await page.screenshot()
                import base64
                screenshot_b64 = base64.b64encode(screenshot_bytes).decode("utf-8")
            except Exception:
                pass

            return {
                "success": False,
                "scheme": config.get("name", scheme_id),
                "error": str(e),
                "fields_filled": fields_filled,
                "fields_skipped": fields_skipped,
                "message": f"Form खुला लेकिन कुछ error आई। Details check करें।",
                "screenshot_b64": screenshot_b64,
            }

        finally:
            # Keep browser open for 30s so judges can see filled form
            if not headless:
                print("[FormFiller] Browser will close in 30 seconds...")
                await page.wait_for_timeout(30000)
            await browser.close()


# ── Helpers ──────────────────────────────────────────────────────

async def _highlight_field(page, selector: str, color: str = "#4ade80"):
    """Flash-highlight a filled field so judges can see it being populated."""
    safe_selector = selector.replace("'", "\\'").replace('"', '\\"')
    try:
        await page.evaluate(f"""
            (() => {{
                const el = document.querySelector('{safe_selector}');
                if (!el) return;
                const orig = el.style.background;
                el.style.background = '{color}';
                el.style.transition = 'background 0.3s';
                setTimeout(() => {{
                    el.style.background = '{color}44';  // fade to light tint
                }}, 800);
            }})();
        """)
    except Exception:
        pass  # Non-critical


async def _fill_select(page, selector: str, value: str):
    """
    Fill a <select> dropdown — tries value match, then text match.
    Government form selects often have inconsistent values.
    """
    value_lower = value.lower()
    options = await page.evaluate(f"""
        (() => {{
            const sel = document.querySelector('{selector}');
            if (!sel) return [];
            return Array.from(sel.options).map(o => ({{value: o.value, text: o.text}}));
        }})();
    """)

    for opt in options:
        if (opt["value"].lower() == value_lower or
                value_lower in opt["text"].lower() or
                opt["text"].lower() in value_lower):
            await page.select_option(selector, value=opt["value"])
            return

    # Fallback: just try direct select
    try:
        await page.select_option(selector, label=value)
    except Exception:
        await page.select_option(selector, value=value)


# ── Sync Wrapper (for FastAPI which uses asyncio internally) ──────

def fill_scheme_form_sync(scheme_id: str, profile: dict, headless: bool = False) -> dict:
    """Sync wrapper — use this from non-async server code."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # FastAPI context — schedule as coroutine
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, fill_scheme_form(scheme_id, profile, headless))
                return future.result(timeout=60)
        else:
            return loop.run_until_complete(fill_scheme_form(scheme_id, profile, headless))
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "message": "Form filler error — check logs.",
        }


# ── CLI Test ─────────────────────────────────────────────────────

if __name__ == "__main__":
    # Quick test with mock profile
    mock_profile = {
        "name": "Raju Kumar",
        "aadhar": "894321095678",
        "mobile": "9876543210",
        "bank_account": "34567890123456",
        "ifsc": "SBIN0012345",
        "village": "Rampur",
        "district": "Patna",
        "state": "Bihar",
        "land_acres": 2.0,
        "caste_category": "OBC",
        "occupation": "farmer",
    }

    print("Testing PM-KISAN form filler...")
    result = asyncio.run(fill_scheme_form("pm_kisan", mock_profile, headless=False))
    print(json.dumps({k: v for k, v in result.items() if k != "screenshot_b64"}, indent=2))
