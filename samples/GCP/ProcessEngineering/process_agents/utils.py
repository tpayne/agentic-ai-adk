# process_agents/utils.py
import os
import logging

logger = logging.getLogger("ProcessArchitect.Utils")

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# Load instruction from a file in the instructions directory
def load_instruction(filename: str) -> str:
    logger.info(f"Loading instruction from {filename}")
    try:
        instruction_path = os.path.join(PROJECT_ROOT, "instructions", filename)
        with open(instruction_path, "r", encoding="utf-8") as f:
            instruction = f.read()
            logger.debug(f"Instruction content: {instruction[:100]}...")  # Log first 100 chars
            return instruction
    except FileNotFoundError:
        logger.error(f"Instruction file {filename} not found.")
        raise
    except Exception as e:
        logger.error(f"Error loading instruction file {filename}: {e}")
        raise
