"""Keep tests offline: never touch the real Supabase project or the profiles folder.

Variables that already exist win over .env (python-dotenv does not override
them), so blanking them here stops app.main from connecting to Supabase.
"""

import os

for name in ("SUPABASE_URL", "SUPABASE_SERVICE_KEY", "SUPABASE_ANON_KEY"):
    os.environ[name] = ""
os.environ["AUTH_MODE"] = "off"
os.environ["VOLUNTEER_SESSION_SECRET"] = "test-only-volunteer-session-secret"


def volunteer_headers(email: str = "volunteer@utsavsync.test") -> dict:
    """A signed volunteer pass, as issued after redeeming an access code."""
    from app.auth import issue_volunteer_token
    token, _ = issue_volunteer_token("volunteer:" + email, email)
    return {"Authorization": "Bearer " + token}
