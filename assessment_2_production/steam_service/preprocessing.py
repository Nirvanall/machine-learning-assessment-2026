"""CSV-shaped raw JSON -> validated Python game features -> ONNX input matrix.

Only declared predictors are forwarded; identities, outcome columns and media URLs
are accepted as record metadata but never used for classification or fetched.
"""
import ast
from datetime import date, datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StringConstraints, field_validator

from steam_service.schemas import GameInput, Label, NonnegativeFloat, NonnegativeInt


def source_list(value):
    if value is None or value == "":
        return []
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        if text.startswith(("[", "(")):
            try:
                parsed = ast.literal_eval(text)
            except (ValueError, SyntaxError, RecursionError):
                raise ValueError("Invalid list representation") from None
            if not isinstance(parsed, (list, tuple)):
                raise ValueError("Expected a list")
            return list(parsed)
        return [token.strip() for token in text.split(",") if token.strip()]
    return value


def source_date(value):
    if type(value) is date:
        return value
    if not isinstance(value, str):
        raise ValueError("Expected a release date string")
    text = value.strip()
    for fmt in ["%Y-%m-%d", "%b %d, %Y", "%b %Y"]:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    raise ValueError("Use YYYY-MM-DD, Mon DD, YYYY or Mon YYYY")


class RawGameRecord(BaseModel):
    # Full games.csv records contain many non-predictor fields. Discard them here.
    model_config = ConfigDict(extra="ignore")

    appid: Annotated[StrictInt, Field(gt=0)] = Field(alias="AppID")
    name: Annotated[str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=1000)] = Field(alias="Name")
    release_date: date = Field(alias="Release date")
    as_of_date: date | None = Field(default=None, alias="As of date")
    price: NonnegativeFloat | None = Field(default=None, alias="Price")
    required_age: NonnegativeInt | None = Field(default=None, alias="Required age", le=120)
    achievements: NonnegativeInt | None = Field(default=None, alias="Achievements")
    windows: bool | None = Field(default=None, alias="Windows", strict=True)
    mac: bool | None = Field(default=None, alias="Mac", strict=True)
    linux: bool | None = Field(default=None, alias="Linux", strict=True)
    genres: list[Label] = Field(default_factory=list, alias="Genres", max_length=100)
    tags: list[Label] = Field(default_factory=list, alias="Tags", max_length=500)
    categories: list[Label] = Field(default_factory=list, alias="Categories", max_length=100)
    supported_languages: list[Label] = Field(default_factory=list, alias="Supported languages", max_length=200)
    description: str = Field(default="", alias="About the game", strict=True, max_length=100_000)

    @field_validator("appid", "required_age", "achievements", mode="before")
    @classmethod
    def csv_integers(cls, value):
        if isinstance(value, str):
            if not value.strip():
                return None
            try:
                number = float(value)
                if number.is_integer():
                    return int(number)
            except (ValueError, OverflowError):
                pass
        return value

    @field_validator("price", mode="before")
    @classmethod
    def csv_price(cls, value):
        if isinstance(value, str):
            if not value.strip():
                return None
            try:
                return float(value)
            except ValueError:
                pass
        return value

    @field_validator("windows", "mac", "linux", mode="before")
    @classmethod
    def csv_boolean(cls, value):
        if isinstance(value, str):
            text = value.strip().casefold()
            if not text:
                return None
            if text in {"true", "1", "1.0", "yes"}:
                return True
            if text in {"false", "0", "0.0", "no"}:
                return False
        if type(value) in (int, float) and value in (0, 1):
            return bool(value)
        return value

    @field_validator("genres", "tags", "categories", "supported_languages", mode="before")
    @classmethod
    def csv_lists(cls, value):
        return source_list(value)

    @field_validator("genres", "tags")
    @classmethod
    def individual_labels(cls, value):
        return GameInput.separate_labels(value)

    @field_validator("description", mode="before")
    @classmethod
    def missing_description(cls, value):
        return "" if value is None else value

    @field_validator("release_date", mode="before")
    @classmethod
    def csv_release_date(cls, value):
        return source_date(value)

    @field_validator("as_of_date", mode="before")
    @classmethod
    def reference_date(cls, value):
        return None if value is None else GameInput.iso_date_only(value)

    def to_game(self, default_as_of_date):
        # An explicit predictor allowlist prevents identities/outcomes from leaking in.
        fields = {name: getattr(self, name) for name in GameInput.model_fields
                  if name != "as_of_date"}
        return GameInput(**fields, as_of_date=self.as_of_date or default_as_of_date)
