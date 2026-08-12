"""Health probe response"""

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = Field(examples=["ok", "degraded", "unavailable"])
    app: str
    version: str
    database: bool | None = Field(
        default=None, description="True when SELECT 1 against the DB succeeds"
    )
    redis: bool | None = Field(
        default=None, description="True when Redis PING succeeds"
    )
