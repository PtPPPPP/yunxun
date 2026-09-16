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


class PlotBaseRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=32)
    area_mu: float = Field(..., gt=0, le=100_000)
    soil_type: str = Field(..., min_length=1, max_length=16)
    irrigation: str = Field(..., min_length=1, max_length=16)
    notes: str = Field("", max_length=300)


class PlotCreateRequest(PlotBaseRequest):
    """创建地块时顺带填第一茬的作物与定植日期，后端一并建出这条茬次。"""

    crop: str = Field(..., min_length=1, max_length=20)
    planted_on: str | None = Field(None, pattern=r"^\d{4}-\d{2}-\d{2}$")


class PlotUpdateRequest(PlotBaseRequest):
    """地块整体替换。作物与日期属于茬次，改茬走 /api/seasons。

    仍然接受这两个可选字段以兼容旧界面：给了就改当前茬次。
    """

    crop: str | None = Field(None, min_length=1, max_length=20)
    planted_on: str | None = Field(None, pattern=r"^\d{4}-\d{2}-\d{2}$")


class SeasonCreateRequest(BaseModel):
    plot_id: str = Field(..., min_length=1, max_length=64)
    crop: str = Field(..., min_length=1, max_length=20)
    started_on: str | None = Field(None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    notes: str = Field("", max_length=300)


class SeasonUpdateRequest(BaseModel):
    crop: str = Field(..., min_length=1, max_length=20)
    started_on: str | None = Field(None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    ended_on: str | None = Field(None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    notes: str = Field("", max_length=300)


class FarmRecordCreateRequest(BaseModel):
    plot_id: str = Field(..., min_length=1, max_length=64)
    kind: str = Field(..., min_length=1, max_length=16)
    happened_on: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    crop: str = Field("", max_length=20)
    material: str = Field("", max_length=40)
    detail: str = Field("", max_length=300)
    quantity: str = Field("", max_length=40)
    cost: float | None = Field(None, ge=0, le=1_000_000)
    safe_days: int | None = Field(None, ge=0, le=365)
    yield_kg: float | None = Field(None, ge=0, le=10_000_000)
    unit_price: float | None = Field(None, ge=0, le=1_000_000)


class FarmTaskCreateRequest(BaseModel):
    plot_id: str | None = Field(None, max_length=64)
    title: str = Field(..., min_length=1, max_length=60)
    due_on: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
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
