"""Training-side ONNX exporter. sklearn/skl2onnx are never imported by the API."""
import importlib.metadata
import os
import re
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import onnx
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.utils.validation import check_is_fitted
from skl2onnx import convert_sklearn
from skl2onnx.common.data_types import FloatTensorType

from steam_service.artifacts import (ArtifactError, Manifest, OnnxPredictor, PreprocessingSpec,
    checked_probabilities, load_model, runtime_versions, sha256, transform_features)
from steam_service.features import GameFeatureTransformer
from steam_service.schemas import GameInput


def preprocessing_spec(preprocessor):
    if not isinstance(preprocessor, ColumnTransformer) or preprocessor.remainder != "drop" or preprocessor.transformer_weights:
        raise ArtifactError("Expected the declared ColumnTransformer without remainder/weights")
    transforms = [(name, transformer, columns) for name, transformer, columns in preprocessor.transformers_
                  if name != "remainder"]
    if [name for name, _, _ in transforms] != ["numeric", "genres", "tags"]:
        raise ArtifactError("ONNX forest export supports numeric, genres and tags only; no text/scaling")
    _, numeric, columns = transforms[0]
    if isinstance(numeric, Pipeline):
        if [name for name, _ in numeric.steps] != ["imputer"]:
            raise ArtifactError("Unsupported numeric pipeline")
        numeric = numeric.steps[0][1]
    if (not isinstance(numeric, SimpleImputer) or numeric.strategy != "median"
            or not numeric.keep_empty_features or numeric.add_indicator
            or not np.isnan(numeric.missing_values)):
        raise ArtifactError("Expected a fitted median imputer retaining empty columns")
    vocabularies = []
    for expected, (_, vectorizer, source) in zip(["Genres", "Tags"], transforms[1:], strict=True):
        if (source != expected or type(vectorizer) is not CountVectorizer or not vectorizer.binary
                or vectorizer.lowercase or vectorizer.analyzer != "word"
                or vectorizer.preprocessor is not None or vectorizer.stop_words is not None
                or vectorizer.strip_accents is not None or vectorizer.ngram_range != (1, 1)
                or getattr(vectorizer.tokenizer, "__name__", None) != "split_labels"):
            raise ArtifactError("Unsupported label encoding; align the feature contract")
        vocabulary = vectorizer.vocabulary_
        if sorted(vocabulary.values()) != list(range(len(vocabulary))):
            raise ArtifactError("Vocabulary indices are not contiguous")
        vocabularies.append(sorted(vocabulary, key=vocabulary.get))
    return PreprocessingSpec(numeric_columns=list(columns), medians=numeric.statistics_.tolist(),
                             genre_vocabulary=vocabularies[0], tag_vocabulary=vocabularies[1])


def export_model(trained_pipeline, *, model_version, training_observation_date,
                 validation_games, reference_features, output_root="models", provenance=None):
    """Export a fitted forest, never fit. Reject unsupported preprocessing and parity failures."""
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", model_version):
        raise ArtifactError("Invalid model version")
    destination = Path(output_root) / model_version
    if destination.exists():
        raise ArtifactError("Model versions are immutable; choose a new version")
    if not isinstance(trained_pipeline, Pipeline) or [name for name, _ in trained_pipeline.steps] != ["features", "model"]:
        raise ArtifactError("Expected fitted features/model pipeline")
    preprocessor, forest = trained_pipeline.steps[0][1], trained_pipeline.steps[1][1]
    if type(forest) is not RandomForestClassifier:
        raise ArtifactError("Production export requires RandomForestClassifier")
    check_is_fitted(forest)
    if forest.n_outputs_ != 1 or not np.array_equal(forest.classes_, [0, 1, 2]):
        raise ArtifactError("Expected single-output ownership classes 0, 1, 2")
    if not validation_games or len(validation_games) != len(reference_features):
        raise ArtifactError("Provide paired raw games and reference features")
    games = [g if isinstance(g, GameInput) else GameInput.model_validate(g) for g in validation_games]
    if any(g.as_of_date != training_observation_date for g in games):
        raise ArtifactError("Validation examples must use training observation date")
    records = [g.model_dump() for g in games]
    features = GameFeatureTransformer().transform(records)
    spec = preprocessing_spec(preprocessor)
    consumed_columns = spec.numeric_columns + ["Genres", "Tags"]
    try:
        pd.testing.assert_frame_equal(features[consumed_columns], reference_features[consumed_columns].reset_index(drop=True),
                                      check_dtype=False, check_exact=False, atol=1e-12, rtol=1e-12)
    except (AssertionError, KeyError) as exc:
        raise ArtifactError("Training/serving feature mismatch in consumed model inputs") from None
    expected_matrix = preprocessor.transform(reference_features)
    if hasattr(expected_matrix, "toarray"):
        expected_matrix = expected_matrix.toarray()
    matrix = transform_features(features, spec)
    np.testing.assert_allclose(matrix, np.asarray(expected_matrix, dtype=np.float32), atol=1e-6, rtol=1e-6)
    graph = convert_sklearn(forest, initial_types=[("features", FloatTensorType([None, spec.width]))],
                           target_opset=17, options={id(forest): {"zipmap": False}})
    onnx.checker.check_model(graph)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".onnx-export-", dir=destination.parent))
    try:
        model_file, spec_file = temporary / "model.onnx", temporary / "preprocessing.json"
        model_file.write_bytes(graph.SerializeToString())
        spec_file.write_text(spec.model_dump_json(indent=2))
        expected = trained_pipeline.predict_proba(reference_features)
        actual = checked_probabilities(OnnxPredictor(model_file, spec), records)
        max_error = float(np.max(np.abs(expected - actual)))
        if max_error > 2e-5 or not np.array_equal(np.argmax(expected, axis=1), np.argmax(actual, axis=1)):
            raise ArtifactError("ONNX probability/class parity failed; investigate float32 split differences")
        manifest = Manifest(model_version=model_version, created_at=datetime.now(timezone.utc),
            training_observation_date=training_observation_date, runtime_versions=runtime_versions(),
            training_versions={p: importlib.metadata.version(p) for p in ["scikit-learn", "skl2onnx", "onnx"]},
            model_sha256=sha256(model_file), preprocessing_sha256=sha256(spec_file), class_ids=[0, 1, 2],
            input_width=spec.width, parity_examples=len(games), max_probability_error=max_error,
            provenance=provenance or {})
        (temporary / "manifest.json").write_text(manifest.model_dump_json(indent=2))
        loaded, _ = load_model(temporary)
        np.testing.assert_allclose(checked_probabilities(loaded, records), expected, atol=2e-5, rtol=0)
        for file in temporary.iterdir():
            file.chmod(0o644)
        temporary.chmod(0o755)
        os.rename(temporary, destination)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    return destination
