from pydantic import BaseModel, Field, ValidationError

from app.agents.schemas.parse import parse_llm_json


class SearchPlan(BaseModel):
    search_query: str = Field(description="Optimized web search query")


def parse_search_plan(text: str, fallback_query: str) -> SearchPlan:
    try:
        return parse_llm_json(text, SearchPlan)
    except ValidationError:
        return SearchPlan(search_query=fallback_query)
