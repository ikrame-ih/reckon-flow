"""I define the health response schema"""

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """I describe the shape of the /health JSON body"""

    status: str = Field(..., examples=["ok"])
    app: str = Field(..., examples=["ReckonFlow"])
    version: str = Field(..., examples=["0.1.0"])
