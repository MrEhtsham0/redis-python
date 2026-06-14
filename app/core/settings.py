from pydantic_settings import BaseSettings
from pydantic import SecretStr,Field,ConfigDict
from functools import lru_cache


class Configurations(BaseSettings):
    redis_host: str = Field(..., validation_alias="REDIS_HOST")
    redis_port: int = Field(..., validation_alias="REDIS_PORT")
    redis_password: SecretStr = Field(..., validation_alias="REDIS_PASSWORD")
    redis_db: int = Field(0, validation_alias="REDIS_DB")
    worker_count: int = Field(3, validation_alias="WORKER_COUNT", ge=1)
    brpop_timeout: int = Field(0, validation_alias="BRPOP_TIMEOUT")
    openai_api_key:SecretStr=Field(..., validation_alias="OPENAI_API_KEY")
    tavily_api_key: SecretStr = Field(default="", validation_alias="TAVILY_API_KEY")
    tavily_max_results: int = Field(5)
    
    openai_model: str = Field("gpt-5-nano",validation_alias="OPENAI_MODEL")
    job_queue: str = Field("job_queue")
    job_processing_queue: str = Field("job_processing_queue")
    job_key_prefix: str = Field("job:")



    model_config = ConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="allow",
        case_sensitive=False,
    )
    @property
    def redis_password_str(self) -> str:
        return self.redis_password.get_secret_value()
    @property
    def openai_api_key_str(self) -> str:
        return self.openai_api_key.get_secret_value()

    @property
    def tavily_api_key_str(self) -> str:
        return self.tavily_api_key.get_secret_value()
        
@lru_cache(maxsize=1)
def get_config() -> Configurations:
    return Configurations()

config = get_config()