"""Health response schema."""

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Shape of the /health JSON body."""

    status: str = Field(..., examples=["ok"])
    app: str = Field(..., examples=["ReckonFlow"])
    version: str = Field(..., examples=["0.1.0"])
