"""Create one email-bound volunteer pass. Run from hackathon_backend/."""
from __future__ import annotations
import argparse
import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone
import httpx
from dotenv import load_dotenv

from app.storage import tls_verify

load_dotenv()
parser = argparse.ArgumentParser(description="Issue a one-time UtsavSync volunteer access code")
parser.add_argument("email", help="Volunteer email address")
parser.add_argument("--expires-hours", type=int, default=72)
args = parser.parse_args()
url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_SERVICE_KEY")
if not url or not key:
    raise SystemExit("Set SUPABASE_URL and SUPABASE_SERVICE_KEY in hackathon_backend/.env first")
if args.expires_hours < 1 or args.expires_hours > 8760:
    raise SystemExit("--expires-hours must be between 1 and 8760")
email = args.email.strip().lower()
if "@" not in email:
    raise SystemExit("Enter a valid volunteer email address")
code = secrets.token_urlsafe(24)
headers = {"apikey": key, "Content-Type": "application/json", "Prefer": "return=minimal"}
if not key.startswith("sb_"):
    headers["Authorization"] = "Bearer " + key
payload = {
    "email": email,
    "code_hash": hashlib.sha256(code.encode("utf-8")).hexdigest(),
    "expires_at": (datetime.now(timezone.utc) + timedelta(hours=args.expires_hours)).isoformat(),
}
response = httpx.post(url.rstrip("/") + "/rest/v1/volunteer_access_codes",
                      headers=headers, json=payload, timeout=10, verify=tls_verify())
if response.status_code >= 400:
    raise SystemExit("Could not issue code in Supabase: " + response.text)
print("Send this one-time code to " + email + ":")
print(code)
print("It expires in " + str(args.expires_hours) + " hours. The database stores only its hash.")
