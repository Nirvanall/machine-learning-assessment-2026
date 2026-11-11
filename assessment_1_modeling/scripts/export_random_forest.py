"""Reproduce the fixed forest on recorded NON-TEST rows and export a versioned ONNX bundle.

No tuning or test evaluation occurs. Prefer direct notebook export if its fitted forest is available.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "assessment_2_production"))

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from steam_data import ownership_target
from steam_service.artifacts import sha256
from steam_service.export import export_model
from steam_service.features import BASE_NUMERIC, split_labels, training_frame_to_games


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, default=ROOT / "artifacts/steam_experiments/quick")
    parser.add_argument("--model-version", required=True)
    parser.add_argument("--output-root", type=Path, default=ROOT / "models")
    args = parser.parse_args()
    manifest_file = args.run_dir / "run_manifest.json"
    run = json.loads(manifest_file.read_text())
    if run["run_mode"] == "smoke" or run["final_model"] != "Random forest":
        raise ValueError("This recipe reproduces the recorded fixed Random forest selection only")
    source = ROOT / "data" / run["dataset_file"]
    metadata_file = source.with_suffix(".manifest.json")
    if sha256(source) != run["dataset_sha256"] or sha256(metadata_file) != run["dataset_manifest_sha256"]:
        raise ValueError("Dataset or manifest changed since the experiment")
    frame = pd.read_parquet(source).sort_values("AppID").reset_index(drop=True)
    assert frame.AppID.is_unique and np.array_equal(frame.target, ownership_target(frame))
    splits_file = args.run_dir / "split_manifest.csv"
    splits = pd.read_csv(splits_file)
    assert splits.AppID.is_unique and set(splits.AppID) == set(frame.AppID)
    assert set(splits.split) <= {"train", "validation", "test", "development_refit_only"}
    test_ids = set(splits.loc[splits.split.eq("test"), "AppID"])
    assert len(test_ids) == run["test_rows"]
    training = frame.loc[~frame.AppID.isin(test_ids)].copy()
    assert len(training) == run["final_refit_rows"]
    model_features = BASE_NUMERIC + ["Genres", "Tags", "About the game"]
    inputs = training[model_features]
    preprocessor = ColumnTransformer([
        ("numeric", Pipeline([("imputer", SimpleImputer(strategy="median", keep_empty_features=True))]), BASE_NUMERIC),
        ("genres", CountVectorizer(tokenizer=split_labels, token_pattern=None, lowercase=False,
                                    binary=True, dtype=np.float32), "Genres"),
        ("tags", CountVectorizer(tokenizer=split_labels, token_pattern=None, lowercase=False,
                                  binary=True, min_df=2, max_features=500, dtype=np.float32), "Tags"),
    ], remainder="drop", sparse_threshold=1.0)
    trees = 200 if run["run_mode"] == "quick" else 500
    estimator = Pipeline([("features", preprocessor), ("model", RandomForestClassifier(
        n_estimators=trees, max_features="sqrt", min_samples_leaf=2,
        class_weight="balanced_subsample", random_state=run["seed"], n_jobs=4))])
    print(f"Refitting fixed Random Forest ({trees} trees) on {len(training):,} non-test games", flush=True)
    estimator.fit(inputs, training.target)
    examples = pd.concat([part.sample(min(500, len(part)), random_state=42)
                          for _, part in training.groupby("target")])
    observation_date = pd.Timestamp(run["observation_date"]).date()
    path = export_model(estimator, model_version=args.model_version,
        training_observation_date=observation_date,
        validation_games=training_frame_to_games(examples, observation_date),
        reference_features=examples[model_features], output_root=args.output_root,
        provenance={"recipe": "fixed-random-forest-v1", "experiment_mode": run["run_mode"],
                    "experiment_manifest_sha256": sha256(manifest_file), "split_manifest_sha256": sha256(splits_file),
                    "dataset_sha256": sha256(source), "refit_rows": len(training),
                    "test_rows_used_for_training": 0, "trees": trees, "seed": run["seed"]})
    print("Exported:", path)

if __name__ == "__main__":
    main()
