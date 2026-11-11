"""Validate the notebook's Parquet contract without requiring the real CSV or training models."""

import ast
import hashlib
import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from steam_data import OWNER_COLUMNS, OWNER_LB, OWNER_UB, OWNER_MID, add_estimated_owner_columns, ownership_target
from steam_service.features import BASE_NUMERIC, ENGINEERED, GameFeatureTransformer
from steam_service.schemas import GameInput


@pytest.fixture
def dataset_contract():
    notebook = json.loads(Path("assessment_1_modeling/notebooks/steam_model_experiments.ipynb").read_text())
    source = next("".join(cell["source"]) for cell in notebook["cells"]
                  if "def validate_engineered_dataset" in "".join(cell["source"]))
    functions = [node for node in ast.parse(source).body if isinstance(node, ast.FunctionDef)]
    raw_columns = ["Genres", "Tags", "About the game"]
    model_columns = BASE_NUMERIC + ENGINEERED + raw_columns
    scope = dict(Path=Path, hashlib=hashlib, json=json, np=np, pd=pd,
        OWNER_COLUMNS=OWNER_COLUMNS, OWNER_LB=OWNER_LB, OWNER_UB=OWNER_UB, OWNER_MID=OWNER_MID, ownership_target=ownership_target,
        EXPECTED_DATASET_VERSION="steam-games-extra-v1", OBSERVATION_DATE=pd.Timestamp("2023-07-05"),
        CLASSES=[0, 1, 2], CLASS_NAMES=["0–<20k owners", "20k–<100k owners", "100k–200m owners"],
        BASE_NUMERIC=BASE_NUMERIC, ENGINEERED=ENGINEERED, RAW_MODEL_COLUMNS=raw_columns,
        MODEL_COLUMNS=model_columns)
    exec(compile(ast.Module(body=functions, type_ignores=[]), "<dataset validation>", "exec"), scope)
    games = [GameInput(release_date=date(2020, 1, 1), as_of_date=date(2023, 7, 5)) for _ in range(3)]
    frame = GameFeatureTransformer().transform(games)
    frame["steam_appid"] = frame["AppID"] = [1, 2, 3]
    frame["release_date"] = pd.Timestamp("2020-01-01")
    frame["Estimated owners"] = ["0 - 20000", "20000 - 50000", "100000 - 200000"]
    frame = add_estimated_owner_columns(frame)
    frame["target"] = ownership_target(frame)
    metadata = dict(dataset_version="steam-games-extra-v1", observation_date="2023-07-05",
        class_mapping=dict(zip(["0", "1", "2"], scope["CLASS_NAMES"])),
        existing_experiment_features=model_columns.copy(), retained_rows=len(frame), column_count=len(frame.columns))
    return scope, frame, metadata


def test_validation_preserves_precomputed_values_and_missingness(dataset_contract):
    scope, frame, metadata = dataset_contract
    original = frame.copy(deep=True)
    scope["validate_engineered_dataset"](frame, metadata)
    pd.testing.assert_frame_equal(frame, original)
    assert frame["Price"].isna().all()


@pytest.mark.parametrize("case", ["midpoint", "target", "duplicate_id", "missing_feature", "version",
                                  "observation_date", "infinite", "text_null", "recent_release", "feature_leak",
                                  "negative_lower_bound", "reversed_bounds", "crossing_bounds"])
def test_reject_invalid_engineered_datasets(dataset_contract, case):
    scope, frame, metadata = dataset_contract
    if case == "midpoint":
        frame.loc[0, OWNER_MID] += 1
    elif case == "target":
        frame.loc[0, "target"] = 2
    elif case == "duplicate_id":
        frame.loc[1, "steam_appid"] = 1
    elif case == "missing_feature":
        frame = frame.drop(columns="log_price")
    elif case in ["version", "observation_date"]:
        metadata["dataset_version" if case == "version" else case] = "invalid"
    elif case == "infinite":
        frame.loc[0, "Price"] = np.inf
    elif case == "text_null":
        frame.loc[0, "Tags"] = None
    elif case == "recent_release":
        frame.loc[0, "release_date"] = pd.Timestamp("2023-01-01")
    elif case in ["negative_lower_bound", "reversed_bounds", "crossing_bounds"]:
        lower, upper = {"negative_lower_bound": (-1, 20_000),
                        "reversed_bounds": (30_000, 20_000),
                        "crossing_bounds": (10_000, 50_000)}[case]
        frame.loc[0, [OWNER_LB, OWNER_UB, OWNER_MID]] = [lower, upper, (lower + upper) / 2]
    else:
        metadata["existing_experiment_features"].append("target")
    with pytest.raises(ValueError):
        scope["validate_engineered_dataset"](frame, metadata)


def test_parquet_loading_without_csv_and_checksum_verification(dataset_contract, tmp_path):
    scope, frame, metadata = dataset_contract
    path = tmp_path / "games-extra.parquet"
    manifest = path.with_suffix(".manifest.json")
    frame.to_parquet(path, index=False)
    metadata.update(output_file=path.name, output_sha256=scope["file_sha256"](path))
    manifest.write_text(json.dumps(metadata))
    loaded, actual_metadata, checksum = scope["load_engineered_dataset"](path, manifest)
    pd.testing.assert_frame_equal(loaded, frame)
    assert actual_metadata["dataset_version"] == metadata["dataset_version"]
    assert checksum == metadata["output_sha256"]
    with path.open("ab") as stream:
        stream.write(b"changed")
    with pytest.raises(ValueError, match="checksum"):
        scope["load_engineered_dataset"](path, manifest)
    with pytest.raises(FileNotFoundError):
        scope["load_engineered_dataset"](path, tmp_path / "missing.json")
