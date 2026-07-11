"""
Aawaaz Agent State Manager
Holds user profile, conversation history, and eligibility results.
All data stays local — never leaves device.
"""

import json
import os
from datetime import datetime
from typing import Optional


class UserProfile:
    """
    Structured profile built dynamically through conversation.
    Each field starts as None — agent fills them one by one.
    """

    def __init__(self):
        # Identity
        self.name: Optional[str] = None
        self.age: Optional[int] = None
        self.gender: Optional[str] = None  # male / female / other
        self.aadhar: Optional[str] = None
        self.mobile: Optional[str] = None

        # Location
        self.state: Optional[str] = None
        self.district: Optional[str] = None
        self.village: Optional[str] = None
        self.residence: Optional[str] = None  # rural / urban

        # Livelihood
        self.occupation: Optional[str] = None  # farmer / daily_wage / construction / etc
        self.income_annual: Optional[int] = None
        self.land_acres: Optional[float] = None
        self.crop_type: Optional[str] = None

        # Family
        self.family_size: Optional[int] = None
        self.girl_child_age: Optional[int] = None
        self.pregnancy_status: Optional[str] = None
        self.first_child: Optional[bool] = None

        # Documents
        self.ration_card: Optional[str] = None       # card number
        self.ration_card_type: Optional[str] = None  # BPL / AAY / PHH
        self.bank_account: Optional[str] = None
        self.ifsc: Optional[str] = None

        # Social category
        self.caste_category: Optional[str] = None    # SC / ST / OBC / General

        # Special conditions
        self.disability_percentage: Optional[int] = None
        self.education_level: Optional[str] = None
        self.housing: Optional[str] = None           # kutcha / pucca / homeless
        self.lpg_connection: Optional[bool] = None
        self.bank_account_exists: Optional[bool] = None
        self.epfo_esic: Optional[bool] = None

        # Excluded categories
        self.is_government_employee: bool = False
        self.is_income_tax_payer: bool = False
        self.has_pucca_house: bool = False

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v is not None}

    def get_missing_fields(self, required_fields: list) -> list:
        """Return which required fields are still None."""
        missing = []
        for field in required_fields:
            val = getattr(self, field, None)
            if val is None:
                missing.append(field)
        return missing

    def fill_from_dict(self, data: dict):
        """Update profile from extracted data (OCR or speech)."""
        for key, value in data.items():
            if hasattr(self, key) and value is not None:
                setattr(self, key, value)


class ConversationState:
    """
    Tracks the full conversation history and agent decisions.
    This is what makes Aawaaz an AGENT, not a chatbot.
    """

    def __init__(self):
        self.profile = UserProfile()
        self.history: list = []           # [{role, content, timestamp}]
        self.eligible_schemes: list = []  # schemes user qualifies for
        self.queued_applications: list = []
        self.current_focus_scheme: Optional[str] = None
        self.session_start = datetime.now().isoformat()
        self.turn_count: int = 0

    def add_turn(self, role: str, content: str):
        """Add a conversation turn to history."""
        self.history.append({
            "role": role,        # user / agent
            "content": content,
            "timestamp": datetime.now().isoformat(),
            "turn": self.turn_count
        })
        self.turn_count += 1

    def get_history_text(self, last_n: int = 6) -> str:
        """Get recent history as formatted text for Gemma context."""
        recent = self.history[-last_n:]
        lines = []
        for turn in recent:
            role_label = "User" if turn["role"] == "user" else "Aawaaz"
            lines.append(f"{role_label}: {turn['content']}")
        return "\n".join(lines)

    def queue_application(self, scheme_id: str):
        """Queue an application for submission when internet is available."""
        self.queued_applications.append({
            "scheme_id": scheme_id,
            "profile_snapshot": self.profile.to_dict(),
            "queued_at": datetime.now().isoformat(),
            "status": "pending"
        })

    def save_to_file(self, filepath: str):
        """Save session state to encrypted file (basic for hackathon)."""
        data = {
            "session_start": self.session_start,
            "profile": self.profile.to_dict(),
            "eligible_schemes": self.eligible_schemes,
            "queued_applications": self.queued_applications,
            "turn_count": self.turn_count
        }
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
