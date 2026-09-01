"""Entry point for the NO-AI deployment.

Streamlit Community Cloud identifies an app by repo + branch + main file, so
deploying the same repo twice needs two entry files. That is the only reason
this exists — it sets configuration and hands off to the shared UI, so there
is one copy of the application code, not two that quietly diverge.

Environment must be set BEFORE config is imported, since config reads it at
import time.
"""

import os
import runpy

os.environ["ENGINE"] = "offline"
os.environ["ALLOW_ENGINE_SWITCH"] = "false"

# Belt and braces. Even if a key is present in this deployment's secrets by
# mistake, this app cannot reach it — so "the free one can never spend money"
# is enforced here, not left to whoever configures the dashboard.
os.environ.pop("ANTHROPIC_API_KEY", None)

runpy.run_path("app.py", run_name="__main__")
