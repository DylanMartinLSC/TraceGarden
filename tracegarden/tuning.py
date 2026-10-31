"""Private, context-local experiment controls. Never accepted by the app API."""

from contextlib import contextmanager
from contextvars import ContextVar

from pydantic import BaseModel, ConfigDict, Field


class Tuning(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
    length_threshold: float = Field(4.0, ge=1, le=12)
    max_iterations: int = Field(10, ge=1, le=30)
    splice_threshold: int = Field(45, ge=0, le=180)
    simplify: float = Field(1.0, ge=0, le=4)
    path_precision: int = Field(3, ge=1, le=6)
    palette_distance: float = Field(12, ge=4, le=24)
    bilateral_sigma: float = Field(10, ge=0, le=30)
    alpha_width: float = Field(2.2, ge=1, le=4)
    shared_tolerance_scale: float = Field(1, ge=0.25, le=2)
    primitive_tolerance_scale: float = Field(1, ge=0.25, le=2)
    gradient_mse_limit: float = Field(12, ge=2, le=30)


_DEFAULT = Tuning()
_current = ContextVar("tracegarden_experiment_tuning", default=None)


def current():
    return _current.get() or _DEFAULT


@contextmanager
def experimental_tuning(values):
    token = _current.set(Tuning.model_validate(values))
    try:
        yield
    finally:
        _current.reset(token)
