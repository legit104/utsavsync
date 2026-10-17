"""Keep tests offline: never touch the real Supabase project or the profiles folder.

Variables that already exist win over .env (python-dotenv does not override
them), so blanking them here stops app.main from connecting to Supabase.
"""

import os

for name in ("SUPABASE_URL", "SUPABASE_SERVICE_KEY", "SUPABASE_ANON_KEY"):
    os.environ[name] = ""
os.environ["AUTH_MODE"] = "off"
