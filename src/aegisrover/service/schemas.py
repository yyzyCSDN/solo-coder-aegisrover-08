from pydantic import BaseModel, Field

class PlanRequest(BaseModel):
    start: tuple[int, int]
    goal: tuple[int, int]
    width: int = Field(gt=0, le=500)
    height: int = Field(gt=0, le=500)
    blocked: list[tuple[int, int]] = Field(default_factory=list)

class PIDRequest(BaseModel):
    errors: list[float]
    dt: float = Field(gt=0)
    kp: float = 1
    ki: float = 0
    kd: float = 0
    minimum: float = -1
    maximum: float = 1

class EncodeRequest(BaseModel):
    kind: int = Field(ge=0, le=255)
    payload: str

class SimRequest(BaseModel):
    linear: float
    angular: float
    dt: float = Field(gt=0)
    steps: int = Field(gt=0, le=10000)
