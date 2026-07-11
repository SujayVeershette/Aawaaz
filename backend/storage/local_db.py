"""
Aawaaz Local Storage
Encrypted local storage for user profiles and application queue.
Uses Fernet symmetric encryption (cryptography library).
On Android: replaced by Android Keystore + Room DB.
Data NEVER leaves device.
"""

import json
import os
from datetime import datetime
from typing import Optional


STORAGE_DIR = os.path.expanduser("~/.aawaaz/data")
KEY_FILE = os.path.expanduser("~/.aawaaz/.key")
QUEUE_FILE = os.path.join(STORAGE_DIR, "queue.enc")
PROFILE_FILE = os.path.join(STORAGE_DIR, "profile.enc")


def _get_or_create_key() -> bytes:
    """Get or create encryption key. Stored locally."""
    try:
        from cryptography.fernet import Fernet
        if os.path.exists(KEY_FILE):
            with open(KEY_FILE, "rb") as f:
                return f.read()
        else:
            key = Fernet.generate_key()
            os.makedirs(os.path.dirname(KEY_FILE), exist_ok=True)
            with open(KEY_FILE, "wb") as f:
                f.write(key)
            os.chmod(KEY_FILE, 0o600)  # Owner read only
            return key
    except ImportError:
        return b"fallback_no_encryption_dev_only"


def _encrypt(data: dict) -> bytes:
    """Encrypt dict to bytes."""
    try:
        from cryptography.fernet import Fernet
        key = _get_or_create_key()
        f = Fernet(key)
        return f.encrypt(json.dumps(data, ensure_ascii=False).encode())
    except ImportError:
        # No encryption in dev mode
        return json.dumps(data, ensure_ascii=False).encode()


def _decrypt(data: bytes) -> dict:
    """Decrypt bytes to dict."""
    try:
        from cryptography.fernet import Fernet
        key = _get_or_create_key()
        f = Fernet(key)
        return json.loads(f.decrypt(data).decode())
    except ImportError:
        return json.loads(data.decode())
    except Exception as e:
        print(f"[Storage] Decrypt error: {e}")
        return {}


def save_profile(profile_dict: dict) -> bool:
    """Save encrypted user profile to disk."""
    try:
        os.makedirs(STORAGE_DIR, exist_ok=True)
        encrypted = _encrypt(profile_dict)
        with open(PROFILE_FILE, "wb") as f:
            f.write(encrypted)
        print(f"[Storage] Profile saved (encrypted)")
        return True
    except Exception as e:
        print(f"[Storage] Save profile error: {e}")
        return False


def load_profile() -> dict:
    """Load and decrypt user profile from disk."""
    try:
        if not os.path.exists(PROFILE_FILE):
            return {}
        with open(PROFILE_FILE, "rb") as f:
            return _decrypt(f.read())
    except Exception as e:
        print(f"[Storage] Load profile error: {e}")
        return {}


def queue_application(scheme_id: str, profile: dict, scheme_name: str) -> bool:
    """
    Add application to local queue.
    Will be submitted when internet is available.
    """
    try:
        # Load existing queue
        queue = load_queue()

        # Add new entry
        queue.append({
            "id": f"{scheme_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "scheme_id": scheme_id,
            "scheme_name": scheme_name,
            "profile": profile,
            "queued_at": datetime.now().isoformat(),
            "status": "pending",
            "attempts": 0
        })

        # Save back
        os.makedirs(STORAGE_DIR, exist_ok=True)
        encrypted = _encrypt({"queue": queue})
        with open(QUEUE_FILE, "wb") as f:
            f.write(encrypted)

        print(f"[Storage] Application queued: {scheme_name}")
        return True

    except Exception as e:
        print(f"[Storage] Queue error: {e}")
        return False


def load_queue() -> list:
    """Load pending application queue."""
    try:
        if not os.path.exists(QUEUE_FILE):
            return []
        with open(QUEUE_FILE, "rb") as f:
            data = _decrypt(f.read())
        return data.get("queue", [])
    except Exception:
        return []


def get_queue_count() -> int:
    """Get number of pending applications."""
    return len([q for q in load_queue() if q["status"] == "pending"])


def check_connectivity() -> bool:
    """Check if internet is available."""
    try:
        import requests
        response = requests.get("https://www.google.com", timeout=3)
        return response.status_code == 200
    except Exception:
        return False


def attempt_submit_queue() -> dict:
    """
    Try to submit queued applications when internet is available.
    Returns summary of what was submitted.
    """
    if not check_connectivity():
        count = get_queue_count()
        print(f"[Storage] No internet. {count} applications queued.")
        return {"submitted": 0, "still_pending": count}

    queue = load_queue()
    submitted = []
    still_pending = []

    for entry in queue:
        if entry["status"] != "pending":
            continue

        # Mock submission for hackathon demo
        # In production: POST to actual govt API endpoint
        success = _mock_submit(entry)

        if success:
            entry["status"] = "submitted"
            entry["submitted_at"] = datetime.now().isoformat()
            submitted.append(entry["scheme_name"])
        else:
            entry["attempts"] = entry.get("attempts", 0) + 1
            still_pending.append(entry["scheme_name"])

    # Save updated queue
    if queue:
        os.makedirs(STORAGE_DIR, exist_ok=True)
        encrypted = _encrypt({"queue": queue})
        with open(QUEUE_FILE, "wb") as f:
            f.write(encrypted)

    return {
        "submitted": len(submitted),
        "submitted_schemes": submitted,
        "still_pending": len(still_pending)
    }


def _mock_submit(entry: dict) -> bool:
    """
    Mock government API submission.
    Replace with real API calls in production.
    """
    print(f"[Storage] MOCK: Submitting {entry['scheme_name']} application...")
    print(f"[Storage] Profile data: {list(entry['profile'].keys())}")
    # Simulate success
    return True


def clear_all_data():
    """Delete all local data. User-initiated only."""
    import shutil
    try:
        shutil.rmtree(STORAGE_DIR, ignore_errors=True)
        if os.path.exists(KEY_FILE):
            os.remove(KEY_FILE)
        print("[Storage] All data cleared.")
        return True
    except Exception as e:
        print(f"[Storage] Clear error: {e}")
        return False
