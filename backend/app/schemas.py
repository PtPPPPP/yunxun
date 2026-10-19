from datetime import date
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, UUID4, field_validator


def validate_iso_date(value: str) -> str:
    date.fromisoformat(value)
    return value


# 保持 Python 层与接口层都是 ISO 字符串，同时校验真实日历日期。
IsoDate = Annotated[str, Field(pattern=r"^\d{4}-\d{2}-\d{2}$"), AfterValidator(validate_iso_date)]


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=32)
    password: str = Field(..., min_length=4, max_length=64)
    display_name: str = Field(..., min_length=1, max_length=32)


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=32)
    password: str = Field(..., min_length=4, max_length=64)


class LogoutRequest(BaseModel):
    session_id: str = Field(..., pattern=r"^[a-f0-9]{64}$")


class GuestUpgradeRequest(RegisterRequest):
    model_config = ConfigDict(extra="forbid")

    @field_validator("username", "display_name", mode="before")
    @classmethod
    def strip_names(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("password")
    @classmethod
    def reject_blank_password(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("密码不能全为空格。")
        return value


class ProfileUpdateRequest(BaseModel):
    display_name: str = Field(..., min_length=1, max_length=32)


def reject_blank_secret(value: str) -> str:
    if not value.strip():
        raise ValueError("密码不能全为空格。")
    return value


NewPassword = Annotated[str, Field(min_length=8, max_length=64), AfterValidator(reject_blank_secret)]


class PasswordProofRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    current_password: str = Field(..., min_length=1, max_length=64)


class PasswordChangeRequest(PasswordProofRequest):
    new_password: NewPassword


class PasswordRecoveryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(..., min_length=1, max_length=32)
    recovery_code: str = Field(..., min_length=1, max_length=128)
    new_password: NewPassword


class PlotBaseRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=32)
    area_mu: float = Field(..., gt=0, le=100_000)
    soil_type: str = Field(..., min_length=1, max_length=16)
    irrigation: str = Field(..., min_length=1, max_length=16)
    notes: str = Field("", max_length=300)


class PlotCreateRequest(PlotBaseRequest):
    """创建地块时顺带填第一茬的作物与定植日期，后端一并建出这条茬次。"""

    crop: str = Field(..., min_length=1, max_length=20)
    planted_on: IsoDate | None = None


class PlotUpdateRequest(PlotBaseRequest):
    """地块整体替换。作物与日期属于茬次，改茬走 /api/seasons。

    仍然接受这两个可选字段以兼容旧界面：给了就改当前茬次。
    """

    crop: str | None = Field(None, min_length=1, max_length=20)
    planted_on: IsoDate | None = None


class SeasonCreateRequest(BaseModel):
    plot_id: str = Field(..., min_length=1, max_length=64)
    crop: str = Field(..., min_length=1, max_length=20)
    started_on: IsoDate | None = None
    notes: str = Field("", max_length=300)


class SeasonUpdateRequest(BaseModel):
    crop: str = Field(..., min_length=1, max_length=20)
    started_on: IsoDate | None = None
    ended_on: IsoDate | None = None
    notes: str = Field("", max_length=300)


class FarmRecordCreateRequest(BaseModel):
    plot_id: str = Field(..., min_length=1, max_length=64)
    # 省略则按日期唯一匹配，显式 null 则保留未归茬。
    season_id: str | None = Field(None, min_length=1, max_length=64)
    kind: str = Field(..., min_length=1, max_length=16)
    happened_on: IsoDate
    crop: str = Field("", max_length=20)
    material: str = Field("", max_length=40)
    detail: str = Field("", max_length=300)
    quantity: str = Field("", max_length=40)
    cost: float | None = Field(None, ge=0, le=1_000_000)
    safe_days: int | None = Field(None, ge=0, le=365)
    yield_kg: float | None = Field(None, ge=0, le=10_000_000)
    unit_price: float | None = Field(None, ge=0, le=1_000_000)


class FarmRecordSubmissionRequest(FarmRecordCreateRequest):
    # 一次确认保存使用同一 UUID，断线重试复用已有记录主键，无需新建幂等表。
    submission_id: UUID4 | None = None


class FarmTaskCreateRequest(BaseModel):
    plot_id: str | None = Field(None, max_length=64)
    title: str = Field(..., min_length=1, max_length=60)
    due_on: IsoDate
    # 待办备注要能装下整段今日农活建议，所以比台账的说明字段宽松。
    notes: str = Field("", max_length=1000)


class FarmTaskUpdateRequest(FarmTaskCreateRequest):
    done: bool = False


class DecisionRequest(BaseModel):
    crop: str = Field(..., min_length=1, max_length=20)
    stage: str = Field(..., min_length=1, max_length=20)
    rain_prob: int = Field(..., ge=0, le=100)
    soil_moisture: int = Field(42, ge=0, le=100)
    temperature: float = Field(24.5, ge=-20, le=55)


class OnboardingUpdateRequest(BaseModel):
    skipped: bool
