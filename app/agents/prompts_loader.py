from pathlib import Path

PROMPTS_DIR = Path(__file__).parent / "prompts"


def load_prompt(filename: str) -> str:
    return (PROMPTS_DIR / filename).read_text(encoding="utf-8")


def load_prompt_with_thinking(filename: str) -> str:
    return f"{load_prompt(filename)}\n\n{load_prompt('thinking_format.md')}"
