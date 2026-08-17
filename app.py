"""Hugging Face Spaces entrypoint.

Loads the Gradio demo from securing_ai_agents_with_information_flow_control/app.py
by file path so this module name (`app`) does not collide with that file.

Do not pip-install the PyPI package named `spaces` — Hugging Face already
provides it. That other package has no GPU decorator and crashes the Space.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import spaces  # noqa: F401  (ZeroGPU runtime)

APP_DIR = Path(__file__).resolve().parent / "securing_ai_agents_with_information_flow_control"
APP_FILE = APP_DIR / "app.py"

if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

_spec = importlib.util.spec_from_file_location("llm_fw_gradio", APP_FILE)
if _spec is None or _spec.loader is None:
    raise ImportError(f"Cannot load demo from {APP_FILE}")
_mod = importlib.util.module_from_spec(_spec)
sys.modules["llm_fw_gradio"] = _mod
_spec.loader.exec_module(_mod)

demo = _mod.demo
launch_demo = _mod.launch_demo

if __name__ == "__main__":
    launch_demo()
