from pydantic import BaseModel, Field

from backend.app.core.config import get_settings


settings = get_settings()


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=32)
    password: str = Field(..., min_length=4, max_length=64)
    display_name: str = Field(..., min_length=1, max_length=32)


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=32)
    password: str = Field(..., min_length=4, max_length=64)


class ProfileUpdateRequest(BaseModel):
    display_name: str = Field(..., min_length=1, max_length=32)
    preferred_model: str = Field("", max_length=64)


class ChatSessionCreateRequest(BaseModel):
    title: str = Field("新会话", min_length=1, max_length=48)
    feature: str = Field("chat", min_length=1, max_length=20)
    model_name: str = Field("", max_length=64)


class ChatMessageRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=settings.max_message_length)
    model_name: str = Field("", max_length=64)


class ChatSessionRenameRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=48)


class VisionRequest(BaseModel):
    image_base64: str = Field(..., min_length=32, max_length=12_000_000)
    crop: str = Field("", max_length=32)
    symptom: str = Field("", max_length=300)


class DecisionRequest(BaseModel):
    crop: str = Field(..., min_length=1, max_length=20)
    stage: str = Field(..., min_length=1, max_length=20)
    rain_prob: int = Field(..., ge=0, le=100)
    soil_moisture: int = Field(42, ge=0, le=100)
    temperature: float = Field(24.5, ge=-20, le=55)
