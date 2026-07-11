"""
Aawaaz Eligibility Engine
Pure Python, zero dependencies.
Runs entirely offline — no API calls.
Checks user profile against each scheme's eligibility rules.
"""

import json
import os
from typing import Optional
from agent.state import UserProfile


def load_schemes(schemes_path: str = None) -> list:
    """Load scheme database from local JSON file."""
    if schemes_path is None:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        schemes_path = os.path.join(base, "schemes", "schemes.json")
    with open(schemes_path, "r", encoding="utf-8") as f:
        return json.load(f)


def check_eligibility(profile: UserProfile, schemes: list) -> list:
    """
    Check which schemes the user is eligible for.
    Returns list of eligible scheme dicts with reason.
    """
    if not profile.state and not profile.occupation and not profile.name:
        return []

    eligible = []

    for scheme in schemes:
        rules = scheme.get("eligibility", {})
        result = _evaluate_scheme(profile, rules, scheme)
        if result["eligible"]:
            eligible.append({
                "id": scheme["id"],
                "name": scheme["name"],
                "full_name": scheme["full_name"],
                "benefit": scheme["benefit"],
                "required_fields": scheme["required_fields"],
                "apply_url": scheme.get("apply_url", ""),
                "reason": result["reason"]
            })

    return eligible


def _evaluate_scheme(profile: UserProfile, rules: dict, scheme: dict) -> dict:
    """Evaluate one scheme against profile. Returns {eligible, reason}."""

    # Check excluded categories first
    if "excluded_categories" in rules:
        if "government_employee" in rules["excluded_categories"] and profile.is_government_employee:
            return {"eligible": False, "reason": "Government employee excluded"}
        if "income_tax_payer" in rules["excluded_categories"] and profile.is_income_tax_payer:
            return {"eligible": False, "reason": "Income tax payer excluded"}
        if "pucca_house_owner" in rules["excluded_categories"] and profile.has_pucca_house:
            return {"eligible": False, "reason": "Pucca house owner excluded"}

    # Occupation check
    if "occupation" in rules:
        if profile.occupation is None:
            return {"eligible": False, "reason": "Occupation not provided"}
        if profile.occupation not in rules["occupation"]:
            return {"eligible": False, "reason": f"Occupation must be one of {rules['occupation']}"}

    # Land checks
    if "land_acres_max" in rules:
        if profile.land_acres is None:
            return {"eligible": False, "reason": "Land size not provided"}
        if profile.land_acres > rules["land_acres_max"]:
            return {"eligible": False, "reason": f"Land exceeds {rules['land_acres_max']} acres limit"}

    if "land_acres_min" in rules:
        if profile.land_acres is None:
            return {"eligible": False, "reason": "Land size not provided"}
        if profile.land_acres < rules["land_acres_min"]:
            return {"eligible": False, "reason": f"Minimum land {rules['land_acres_min']} acres required"}

    # Income check
    if "income_annual_max" in rules:
        if profile.income_annual is None:
            return {"eligible": False, "reason": "Annual income not provided"}
        if profile.income_annual > rules["income_annual_max"]:
            return {"eligible": False, "reason": f"Income exceeds ₹{rules['income_annual_max']:,} limit"}

    # Gender check
    if "gender" in rules:
        if profile.gender is None:
            return {"eligible": False, "reason": "Gender not provided"}
        if profile.gender not in rules["gender"]:
            return {"eligible": False, "reason": f"Scheme is for {rules['gender']} only"}

    # Age checks
    if "age_min" in rules:
        if profile.age is None:
            return {"eligible": False, "reason": "Age not provided"}
        if profile.age < rules["age_min"]:
            return {"eligible": False, "reason": f"Minimum age is {rules['age_min']}"}

    if "age_max" in rules:
        if profile.age is None:
            return {"eligible": False, "reason": "Age not provided"}
        if profile.age > rules["age_max"]:
            return {"eligible": False, "reason": f"Maximum age is {rules['age_max']}"}

    # Ration card type
    if "ration_card_type" in rules:
        if profile.ration_card_type is None:
            return {"eligible": False, "reason": "Ration card type not provided"}
        if profile.ration_card_type not in rules["ration_card_type"]:
            return {"eligible": False, "reason": f"Ration card must be {rules['ration_card_type']}"}

    # Residence
    if "residence" in rules:
        if profile.residence is None:
            return {"eligible": False, "reason": "Residence (rural/urban) not provided"}
        if profile.residence not in rules["residence"]:
            return {"eligible": False, "reason": f"Must reside in {rules['residence']}"}

    # Caste category
    if "caste_category" in rules:
        if profile.caste_category is None:
            return {"eligible": False, "reason": "Caste category not provided"}
        if profile.caste_category not in rules["caste_category"]:
            return {"eligible": False, "reason": f"Must be {rules['caste_category']}"}

    # Disability
    if "disability_percentage_min" in rules:
        if profile.disability_percentage is None:
            return {"eligible": False, "reason": "Disability percentage not provided"}
        if profile.disability_percentage < rules["disability_percentage_min"]:
            return {"eligible": False, "reason": f"Minimum {rules['disability_percentage_min']}% disability required"}

    # Education level
    if "education_level" in rules:
        if profile.education_level is None:
            return {"eligible": False, "reason": "Education level not provided"}
        if profile.education_level not in rules["education_level"]:
            return {"eligible": False, "reason": f"Must be studying at {rules['education_level']}"}

    # No bank account (Jan Dhan)
    if "bank_account" in rules and rules["bank_account"] is False:
        if profile.bank_account_exists is None:
            return {"eligible": False, "reason": "Bank account status unknown"}
        if profile.bank_account_exists is True:
            return {"eligible": False, "reason": "Already has bank account"}

    # No LPG connection
    if "lpg_connection" in rules and rules["lpg_connection"] is False:
        if profile.lpg_connection is None:
            return {"eligible": False, "reason": "LPG connection status unknown"}
        if profile.lpg_connection is True:
            return {"eligible": False, "reason": "Already has LPG connection"}

    # Girl child age
    if "girl_child_age_max" in rules:
        if profile.girl_child_age is None:
            return {"eligible": False, "reason": "Girl child age not provided"}
        if profile.girl_child_age > rules["girl_child_age_max"]:
            return {"eligible": False, "reason": f"Girl child must be under {rules['girl_child_age_max']} years"}

    # EPFO/ESIC
    if "epfo_esic" in rules and rules["epfo_esic"] is False:
        if profile.epfo_esic is None:
            return {"eligible": False, "reason": "EPFO/ESIC status unknown"}
        if profile.epfo_esic is True:
            return {"eligible": False, "reason": "Already covered under EPFO/ESIC"}

    # Pregnancy
    if "pregnancy_status" in rules:
        if profile.pregnancy_status is None:
            return {"eligible": False, "reason": "Pregnancy status not provided"}

    # Passed all checks
    return {"eligible": True, "reason": "Meets all eligibility criteria"}


def get_missing_fields_for_eligible(profile: UserProfile, schemes: list) -> dict:
    """
    For schemes the user MIGHT qualify for (if more info given),
    return what fields are still needed.
    Used by agent to decide what to ask next.
    """
    missing_map = {}
    for scheme in schemes:
        missing = profile.get_missing_fields(scheme["required_fields"])
        if missing:
            missing_map[scheme["id"]] = {
                "scheme_name": scheme["name"],
                "missing": missing
            }
    return missing_map


def get_next_question(profile: UserProfile, schemes: list, language: str = "hi") -> Optional[dict]:
    """
    THE CORE AGENT DECISION.
    Looks at all schemes, finds the most blocking missing field,
    and returns the question to ask next.
    This is what makes Aawaaz adaptive — nothing is hardcoded.
    """
    # Count how many schemes each field is blocking
    field_block_count = {}
    field_questions = {}

    for scheme in schemes:
        missing = profile.get_missing_fields(scheme["required_fields"])
        questions = scheme.get(f"questions_{language}", {})

        for field in missing:
            field_block_count[field] = field_block_count.get(field, 0) + 1
            if field not in field_questions and field in questions:
                field_questions[field] = questions[field]

    if not field_block_count:
        return None  # All fields collected

    # Conversational field weights: ask natural identity & background questions before asking for documents like Aadhar / Bank account upfront.
    field_priority_weight = {
        "name": 100,
        "occupation": 95,
        "state": 90,
        "residence": 85,
        "age": 80,
        "gender": 75,
        "income_annual": 70,
        "housing": 65,
        "land_acres": 60,
        "family_size": 55,
        "ration_card": 50,
        "ration_card_type": 45,
        "caste_category": 40,
        "disability_percentage": 35,
        "education_level": 30,
        "crop_type": 25,
        "girl_child_age": 20,
        "pregnancy_status": 15,
        "lpg_connection": 10,
        "bank_account_exists": 5,
        "aadhar": -50,       # Asked later or filled via document scan
        "bank_account": -60, # Asked later when applying
        "ifsc": -70,
        "address": -80,
    }

    # Pick the field with highest combined score so basic conversation happens first
    most_blocking = max(field_block_count, key=lambda f: field_block_count[f] * 10 + field_priority_weight.get(f, 0))

    # Default questions for fields without scheme-specific ones
    default_questions_hi = {
        "name": "Aapka poora naam kya hai?",
        "aadhar": "Aapka Aadhar number batayein, ya card camera ke saamne rakhein.",
        "age": "Aapki umar kitni hai?",
        "gender": "Aap purush hain ya mahila?",
        "state": "Aap kaunse rajya mein rehte hain?",
        "mobile": "Aapka mobile number kya hai?",
        "bank_account": "Aapka bank account number kya hai?",
        "ifsc": "Aapki bank ki IFSC code kya hai? Passbook pe likhi hoti hai.",
        "ration_card": "Kya aapke paas ration card hai?",
        "ration_card_type": "Aapka ration card kaun sa hai — BPL, AAY, ya PHH?",
        "income_annual": "Aapke parivar ki ek saal mein total kamai kitni hai?",
        "land_acres": "Aapke paas kitni zameen hai? Acres mein batayein.",
        "occupation": "Aap kya kaam karte hain? Kisan, mazdoor, ya kuch aur?",
        "family_size": "Aapke ghar mein kitne log hain?",
        "caste_category": "Aapki jaati SC, ST, OBC, ya General hai?",
        "residence": "Aap gaon mein rehte hain ya sheher mein?",
        "housing": "Aapka ghar pakka hai ya kachcha?",
        "disability_percentage": "Disability certificate mein kitna percentage likha hai?",
        "education_level": "Aap abhi kaunsi class mein padh rahe hain?",
        "crop_type": "Aap kaunsi fasal ugaate hain?",
        "girl_child_age": "Aapki beti ki umar kitni hai?",
        "pregnancy_status": "Kya aap abhi pregnant hain?",
        "lpg_connection": "Kya ghar mein pehle se gas cylinder connection hai?",
        "bank_account_exists": "Kya aapka kisi bhi bank mein account hai?",
        "address": "Aapka poora pata kya hai — gaon, tehsil, jila?",
    }

    question_text = field_questions.get(
        most_blocking,
        default_questions_hi.get(most_blocking, f"Kripya {most_blocking} ke baare mein batayein.")
    )

    return {
        "field": most_blocking,
        "question": question_text,
        "blocking_count": field_block_count[most_blocking],
        "can_scan": most_blocking in ["aadhar", "ration_card", "bank_account", "ifsc"]
    }
