from langchain_openai import ChatOpenAI

from app.core.settings import config

_llm: ChatOpenAI | None = None
_llm_model: str | None = None


def reset_llm() -> None:
    global _llm, _llm_model
    _llm = None
    _llm_model = None


def get_llm() -> ChatOpenAI:
    global _llm, _llm_model

    model = (config.openai_model or "").strip()
    if not model:
        raise RuntimeError("OPENAI_MODEL is not configured")

    if _llm is None or _llm_model != model:
        _llm = ChatOpenAI(
            model=model,
            api_key=config.openai_api_key_str,
            streaming=True,
        )
        _llm_model = model

    return _llm


def normalize_content(content: str | list) -> str:
    if not content:
        return ""
    if isinstance(content, list):
        return "".join(part.get("text", "") for part in content if isinstance(part, dict))
    return content
