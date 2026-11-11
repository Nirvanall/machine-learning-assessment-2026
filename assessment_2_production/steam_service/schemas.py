"""Internal canonical game fields and the compact public prediction response."""

import calendar
import re
from datetime import date
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StringConstraints, field_validator, model_validator

Label = Annotated[str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=200)]
NonnegativeFloat = Annotated[float, Field(strict=True, ge=0, le=1_000_000_000, allow_inf_nan=False)]
NonnegativeInt = Annotated[StrictInt, Field(ge=0, le=2_147_483_647)]


class GameInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    release_date: date
    as_of_date: date
    price: NonnegativeFloat | None = None
    required_age: NonnegativeInt | None = Field(default=None, le=120)
    achievements: NonnegativeInt | None = None
    windows: StrictBool | None = None
    mac: StrictBool | None = None
    linux: StrictBool | None = None
    genres: list[Label] = Field(default_factory=list, max_length=100)
    tags: list[Label] = Field(default_factory=list, max_length=500)
    categories: list[Label] = Field(default_factory=list, max_length=100)
    supported_languages: list[Label] = Field(default_factory=list, max_length=200)
    description: str = Field(default="", strict=True, max_length=100_000)

    @field_validator("release_date", "as_of_date", mode="before")
    @classmethod
    def iso_date_only(cls, value):
        if type(value) is date:
            return value
        if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            raise ValueError("Use an ISO calendar date: YYYY-MM-DD")
        return value

    @field_validator("genres", "tags")
    @classmethod
    def separate_labels(cls, values):
        if any("," in value for value in values):
            raise ValueError("Supply each label as a separate list item, without commas")
        return values

    @model_validator(mode="after")
    def supported_game_age(self):
        if self.as_of_date.year <= 1:
            raise ValueError("as_of_date must support at least one year of game history")
        year = self.as_of_date.year - 1
        cutoff = date(year, self.as_of_date.month,
                      min(self.as_of_date.day, calendar.monthrange(year, self.as_of_date.month)[1]))
        if self.release_date > cutoff:
            raise ValueError("The model supports games released at least one year before as_of_date")
        return self


class OwnerRange(BaseModel):
    label: str
    lower_bound: int
    upper_bound: int
    upper_bound_inclusive: bool


OWNER_RANGES = {
    0: OwnerRange(label="0–<20k owners", lower_bound=0, upper_bound=20_000, upper_bound_inclusive=False),
    1: OwnerRange(label="20k–<100k owners", lower_bound=20_000, upper_bound=100_000, upper_bound_inclusive=False),
    2: OwnerRange(label="100k–200m owners", lower_bound=100_000, upper_bound=200_000_000, upper_bound_inclusive=True),
}


PREDICTED_OWNER_RANGES = {
    0: "0 - 20000",
    1: "20000 - 100000",
    2: "100000 - 200000000",
}


class PredictionResponse(BaseModel):
    is_success: bool = True
    predicted_owner_range: str
    probability: Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]
    model_version: str
