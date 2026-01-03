# process_agents/utils.py

import os

# ----------------------------- # LOAD INSTRUCTIONS FROM FILE # -----------------------------
def load_instruction(filename: str) -> str:
    instruction_dir = os.path.join(os.path.dirname(__file__), "..", "instructions")
    instruction_path = os.path.join(instruction_dir, filename)
    with open(instruction_path, "r", encoding="utf-8") as f:
        return f.read()
