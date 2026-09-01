"""Entry point for the AI deployment. See app_standard.py for why this exists."""

import os
import runpy

os.environ["ENGINE"] = "cloud"
os.environ["ALLOW_ENGINE_SWITCH"] = "false"

runpy.run_path("app.py", run_name="__main__")
