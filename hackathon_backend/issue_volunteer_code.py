"""Create a UtsavSync volunteer access code. Run from hackathon_backend/.

    .venv\\Scripts\\python issue_volunteer_code.py volunteer@example.org        # only that email, 1 use
    .venv\\Scripts\\python issue_volunteer_code.py --any-email --uses 5          # any email, 5 uses in total
"""
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
parser = argparse.ArgumentParser(description="Issue a UtsavSync volunteer access code")
parser.add_argument("email", nargs="?", help="Volunteer email address (omit with --any-email)")
parser.add_argument("--any-email", action="store_true", help="Let any signed-in email redeem the code")
parser.add_argument("--uses", type=int, default=1, help="How many times the code can be redeemed in total (default 1)")
parser.add_argument("--expires-hours", type=int, default=72)
args = parser.parse_args()
url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_SERVICE_KEY")
if not url or not key:
    raise SystemExit("Set SUPABASE_URL and SUPABASE_SERVICE_KEY in hackathon_backend/.env first")
if args.expires_hours < 1 or args.expires_hours > 8760:
    raise SystemExit("--expires-hours must be between 1 and 8760")
if args.uses < 1 or args.uses > 1000:
    raise SystemExit("--uses must be between 1 and 1000")
if args.any_email == bool(args.email):
    raise SystemExit("Give either a volunteer email address or --any-email (not both)")
email = None
if args.email:
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
    "max_uses": args.uses,
}
response = httpx.post(url.rstrip("/") + "/rest/v1/volunteer_access_codes",
                      headers=headers, json=payload, timeout=10, verify=tls_verify())
if response.status_code >= 400:
    hint = " (re-run supabase_schema.sql in Supabase first)" if "max_uses" in response.text or "null" in response.text else ""
    raise SystemExit("Could not issue code in Supabase: " + response.text + hint)
who = email or "any signed-in email"
times = "once" if args.uses == 1 else f"up to {args.uses} times"
print(f"Volunteer code for {who}, usable {times}:")
print(code)
print(f"It expires in {args.expires_hours} hours. Share it privately; the database stores only its hash.")
