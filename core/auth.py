from __future__ import annotations

import hashlib
import hmac
import json
import os
from pathlib import Path

import streamlit as st

LICENSES_FILE = Path(os.getenv("RCC_LICENSES_FILE", "licenses.json"))


def _admin_key() -> str | None:
    try:
        value = st.secrets.get("RCC_ADMIN_KEY")
    except Exception:
        value = None
    return value or os.getenv("RCC_ADMIN_KEY")


def _load_licenses() -> dict:
    if not LICENSES_FILE.exists():
        return {}
    try:
        return json.loads(LICENSES_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _save_licenses(licenses: dict) -> None:
    LICENSES_FILE.write_text(json.dumps(licenses, indent=2), encoding="utf-8")


def _hash_pin(pin: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", pin.encode(), salt.encode(), 200_000
    ).hex()


def _truthy_env(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


def _dev_mode_enabled() -> bool:
    """Return True only when explicit local-development bypass is enabled."""
    return _truthy_env("RCC_DEV_MODE")


def _license_required() -> bool:
    """Licensing is opt-in.

    The public repository previously locked the whole application behind a
    PIN/license screen on first run, which stopped any engineer from simply
    cloning and running it and provided no real protection (the key
    generator and license store ship in the same repository). Enforcement is
    now opt-in via RCC_REQUIRE_LICENSE=true for deployments that actually
    need it.
    """
    return _truthy_env("RCC_REQUIRE_LICENSE")


def require_access_key() -> None:
    """Optional PIN-backed access without hard-coded credentials.

    By default the application is open. Set RCC_REQUIRE_LICENSE=true (and a
    real RCC_ADMIN_KEY / licence store) only if you are deploying a managed
    commercial instance. The local JSON fallback is for development only.
    """
    if not _license_required():
        st.session_state.authenticated = True
        st.session_state.license_user = "Open Source Mode"
        return

    # Explicit local-development bypass. Keep this OFF in production.
    if _dev_mode_enabled():
        st.session_state.authenticated = True
        st.session_state.license_user = "Local Development Mode"
        return

    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
        st.session_state.license_user = None

    if st.session_state.authenticated:
        return

    st.sidebar.markdown("### 🔒 Engineering License Login")
    entered_key = st.sidebar.text_input("Activation Key", type="password").strip().upper()
    pin = st.sidebar.text_input("4-Digit Security PIN", type="password", max_chars=4).strip()

    if st.sidebar.button("Sign In / Activate"):
        admin = _admin_key()
        if admin and hmac.compare_digest(entered_key, admin.upper()):
            st.session_state.authenticated = True
            st.session_state.license_user = "Administrator"
            st.rerun()

        licenses = _load_licenses()
        rec = licenses.get(entered_key)
        if rec is None:
            st.sidebar.error("Invalid license key.")
        elif not rec.get("activated", False):
            if not (len(pin) == 4 and pin.isdigit()):
                st.sidebar.warning("Choose a 4-digit PIN for first activation.")
            else:
                salt = os.urandom(16).hex()
                rec["activated"] = True
                rec["pin_salt"] = salt
                rec["pin_hash"] = _hash_pin(pin, salt)
                rec.pop("pin", None)
                _save_licenses(licenses)
                st.session_state.authenticated = True
                st.session_state.license_user = f"{rec.get('user', 'Engineer')} (Activated)"
                st.rerun()
        else:
            salt, expected = rec.get("pin_salt"), rec.get("pin_hash")
            if salt and expected and hmac.compare_digest(_hash_pin(pin, salt), expected):
                st.session_state.authenticated = True
                st.session_state.license_user = f"{rec.get('user', 'Engineer')} (Verified)"
                st.rerun()
            else:
                st.sidebar.error("Incorrect PIN.")

    st.warning(
        "⚠️ Access locked. Configure RCC_ADMIN_KEY in Streamlit Secrets/environment "
        "or use a provisioned license."
    )
    st.stop()
