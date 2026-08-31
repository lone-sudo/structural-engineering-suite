"""Generate a license record for the development/local license store.

Never commit the generated licenses.json file. For production, use a database
or managed secret store.
"""
from __future__ import annotations

import json
import os
import secrets
import string
from pathlib import Path

LICENSES_FILE = Path(os.getenv("RCC_LICENSES_FILE", "licenses.json"))


def create_new_license(client_name: str, prefix: str = "RCC") -> str:
    rand_num = "".join(secrets.choice(string.digits) for _ in range(4))
    rand_chars = "".join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8))
    license_key = f"{prefix}-{rand_num}-{rand_chars}"

    licenses = json.loads(LICENSES_FILE.read_text()) if LICENSES_FILE.exists() else {}
    licenses[license_key] = {"user": client_name, "activated": False}
    LICENSES_FILE.write_text(json.dumps(licenses, indent=2))

    print(f"Generated license key: {license_key}")
    print(f"Assigned to: {client_name}")
    return license_key


if __name__ == "__main__":
    name = input("Enter Client / Engineer / Company Name: ").strip()
    if name:
        create_new_license(name)
