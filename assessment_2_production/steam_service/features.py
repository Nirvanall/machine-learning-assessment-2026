"""Fixed row-wise features shared by exported training pipelines and serving.

Medians, scalers, vocabularies and TF-IDF belong to the fitted inner pipeline.
This transformer never learns from inference requests.
"""

import ast
import html
import re
import unicodedata
from datetime import date

import numpy as np
import pandas as pd

from steam_service.schemas import GameInput

BASE_NUMERIC = ["Price", "Required age", "Windows", "Mac", "Linux", "Achievements", "year"]
ENGINEERED = ["log_price", "log_achievements", "log_age", "platform_count",
              "is_free", "age_restricted", "release_month_sin", "release_month_cos",
              "genre_count", "category_count", "language_count", "description_length",
              "description_word_count", "price_missing", "age_missing",
              "achievements_missing", "platform_flags_missing"]


def normalize_labels(values):
    tokens = [" ".join(unicodedata.normalize("NFKC", value).split()).casefold() for value in values]
    return ",".join(dict.fromkeys(token for token in tokens if token))


def split_labels(value):
    """Importable tokenizer, with exactly the experiment notebook's semantics."""
    return [item.strip() for item in str(value).split(",")
            if item.strip() and item.strip().casefold() != "free to play"]


def clean_description(value):
    text = html.unescape(unicodedata.normalize("NFKC", value))
    return " ".join(re.sub(r"<[^>]+>", " ", text).split())


class GameFeatureTransformer:
    def fit(self, X, y=None):
        self.transform(X)
        return self

    def __sklearn_is_fitted__(self):
        return True  # stateless; fitted vocabulary/imputation lives in the inner pipeline

    def transform(self, X):
        records = X.to_dict(orient="records") if isinstance(X, pd.DataFrame) else X
        games = [game if isinstance(game, GameInput) else GameInput.model_validate(game) for game in records]
        if not games:
            raise ValueError("At least one game is required")
        out = pd.DataFrame({
            "Price": [g.price for g in games],
            "Required age": [g.required_age for g in games],
            "Windows": [g.windows for g in games],
            "Mac": [g.mac for g in games],
            "Linux": [g.linux for g in games],
            "Achievements": [g.achievements for g in games],
            "year": [(g.as_of_date - g.release_date).days / 365.0 for g in games],
            "Genres": [normalize_labels(g.genres) for g in games],
            "Tags": [normalize_labels(g.tags) for g in games],
            "About the game": [clean_description(g.description) for g in games],
        })
        for name in BASE_NUMERIC:
            out[name] = pd.to_numeric(out[name], errors="raise").astype(float)
        for source, target in [("Price", "log_price"), ("Achievements", "log_achievements"), ("year", "log_age")]:
            out[target] = np.log1p(out[source].clip(lower=0))
        out["platform_count"] = out[["Windows", "Mac", "Linux"]].sum(axis=1, min_count=3)
        out["is_free"] = out["Price"].eq(0).astype(float).where(out["Price"].notna())
        out["age_restricted"] = out["Required age"].gt(0).astype(float).where(out["Required age"].notna())
        months = np.asarray([g.release_date.month for g in games])
        out["release_month_sin"] = np.sin(2 * np.pi * months / 12)
        out["release_month_cos"] = np.cos(2 * np.pi * months / 12)
        out["genre_count"] = out["Genres"].map(lambda value: len(split_labels(value)))
        out["category_count"] = [len(g.categories) for g in games]
        out["language_count"] = [len(g.supported_languages) for g in games]
        out["description_length"] = out["About the game"].str.len()
        out["description_word_count"] = out["About the game"].str.split().str.len()
        for source, target in [("Price", "price_missing"), ("Required age", "age_missing"),
                               ("Achievements", "achievements_missing")]:
            out[target] = out[source].isna().astype(int)
        out["platform_flags_missing"] = out[["Windows", "Mac", "Linux"]].isna().sum(axis=1)
        return out.replace([np.inf, -np.inf], np.nan)


def _source_list(value):
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return []
    if isinstance(value, (list, tuple, np.ndarray)):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    if not text:
        return []
    try:
        parsed = ast.literal_eval(text)
        if isinstance(parsed, (list, tuple)):
            return [str(item).strip() for item in parsed if str(item).strip()]
    except (SyntaxError, ValueError):
        pass
    return [item.strip() for item in text.split(",") if item.strip()]


def training_frame_to_games(frame: pd.DataFrame, as_of_date: date) -> list[GameInput]:
    """Adapt CLEANED experiment rows for export checks; never silently repair new API inputs."""
    def number(value, integer=False):
        return None if pd.isna(value) else (int(value) if integer else float(value))

    def flag(value):
        return None if pd.isna(value) else bool(value)

    return [GameInput(
        release_date=row["release_date"].date(), as_of_date=as_of_date,
        price=number(row["Price"]), required_age=number(row["Required age"], True),
        achievements=number(row["Achievements"], True), windows=flag(row["Windows"]),
        mac=flag(row["Mac"]), linux=flag(row["Linux"]),
        genres=_source_list(row["Genres"]), tags=_source_list(row["Tags"]),
        categories=_source_list(row.get("Categories")),
        supported_languages=_source_list(row.get("Supported languages")),
        description="" if pd.isna(row["About the game"]) else str(row["About the game"]),
    ) for _, row in frame.iterrows()]
