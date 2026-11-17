
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class MachineInput(BaseModel):

    model_config = ConfigDict(extra="forbid")

    # Original six machine variables

    Type: Literal["L", "M", "H"]

    Air_temperature_K: float = Field(
        gt=0,
        allow_inf_nan=False
    )

    Process_temperature_K: float = Field(
        gt=0,
        allow_inf_nan=False
    )

    Rotational_speed_rpm: int = Field(
        gt=0,
        strict=True
    )

    Torque_Nm: float = Field(
        ge=0,
        allow_inf_nan=False
    )

    Tool_wear_min: int = Field(
        ge=0,
        strict=True
    )