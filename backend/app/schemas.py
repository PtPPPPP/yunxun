from pydantic import BaseModel, Field


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=32)
    password: str = Field(..., min_length=4, max_length=64)
    display_name: str = Field(..., min_length=1, max_length=32)


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=32)
    password: str = Field(..., min_length=4, max_length=64)


class ProfileUpdateRequest(BaseModel):
    display_name: str = Field(..., min_length=1, max_length=32)


class DecisionRequest(BaseModel):
    crop: str = Field(..., min_length=1, max_length=20)
    stage: str = Field(..., min_length=1, max_length=20)
    rain_prob: int = Field(..., ge=0, le=100)
    soil_moisture: int = Field(42, ge=0, le=100)
    temperature: float = Field(24.5, ge=-20, le=55)
