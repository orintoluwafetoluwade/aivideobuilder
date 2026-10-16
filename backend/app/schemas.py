from pydantic import BaseModel, Field
from typing import Literal

class ProjectCreate(BaseModel):
    topic: str = Field(min_length=3, max_length=500)
    style: str = Field(default="Cinematic documentary", max_length=100)
    format: Literal["YouTube landscape", "YouTube Shorts"] = "YouTube landscape"
    duration_minutes: int = Field(default=3, ge=1, le=15)
