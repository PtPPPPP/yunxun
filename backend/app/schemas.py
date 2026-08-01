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
    model_config_id: str | None = Field(None, max_length=64)


class ChatMessageRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=settings.max_message_length)
    model_name: str = Field("", max_length=64)
    model_config_id: str | None = Field(None, max_length=64)


class ModelConfigCreateRequest(BaseModel):
    provider: str = Field(..., min_length=1, max_length=32)
    display_name: str = Field(..., min_length=1, max_length=64)
    model: str = Field(..., min_length=1, max_length=128)
    base_url: str = Field("", max_length=512)
    api_key: str = Field(..., min_length=8, max_length=512)
    is_default: bool = False


class ModelConfigUpdateRequest(BaseModel):
    provider: str = Field(..., min_length=1, max_length=32)
    display_name: str = Field(..., min_length=1, max_length=64)
    model: str = Field(..., min_length=1, max_length=128)
    base_url: str = Field("", max_length=512)
    api_key: str | None = Field(None, min_length=8, max_length=512)
    replace_api_key: bool = False
    is_enabled: bool = True


class ModelConfigTestRequest(BaseModel):
    provider: str = Field(..., min_length=1, max_length=32)
    model: str = Field(..., min_length=1, max_length=128)
    base_url: str = Field("", max_length=512)
    api_key: str = Field(..., min_length=8, max_length=512)


class ChatSessionRenameRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=48)


class VisionRequest(BaseModel):
    image_base64: str = Field(..., min_length=32, max_length=settings.upload_max_base64_length)
    crop: str = Field("", max_length=32)
    symptom: str = Field("", max_length=300)


class DecisionRequest(BaseModel):
    crop: str = Field(..., min_length=1, max_length=20)
    stage: str = Field(..., min_length=1, max_length=20)
    rain_prob: int = Field(..., ge=0, le=100)
    soil_moisture: int = Field(42, ge=0, le=100)
    temperature: float = Field(24.5, ge=-20, le=55)
