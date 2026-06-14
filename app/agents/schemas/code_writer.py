from pydantic import BaseModel, Field, ValidationError

from app.agents.schemas.parse import parse_llm_json


class CodeWriterOutput(BaseModel):
    user_query: str = Field(
        description="Clear, well-phrased restatement of what the user asked for"
    )
    description: str = Field(
        description="Brief explanation of the approach and how the code works"
    )
    code: str = Field(description="Complete runnable code without markdown fences")
    language: str = Field(default="python", description="Programming language of the code")


def format_code_writer_output(output: CodeWriterOutput) -> str:
    return (
        f"## Task\n{output.user_query}\n\n"
        f"## Description\n{output.description}\n\n"
        f"## Code\n```{output.language}\n{output.code}\n```"
    )


def parse_code_writer_response(text: str) -> CodeWriterOutput:
    try:
        return parse_llm_json(text, CodeWriterOutput)
    except ValidationError as error:
        raise RuntimeError("Code writer returned invalid structured output") from error
