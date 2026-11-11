"""Load ONNX + declarative preprocessing; never unpickle Python model objects."""
import hashlib
import importlib.metadata
from datetime import date, datetime
from pathlib import Path
from typing import Literal

import numpy as np
import onnxruntime as ort
from pydantic import BaseModel, ConfigDict, Field, model_validator

from steam_service import FEATURE_SCHEMA_VERSION
from steam_service.features import BASE_NUMERIC, ENGINEERED, GameFeatureTransformer, split_labels
from steam_service.schemas import GameInput

ort.disable_telemetry_events()

RUNTIME_PACKAGES = ("numpy", "pandas", "onnxruntime", "pydantic")

class ArtifactError(RuntimeError):
    pass

class PreprocessingSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    format_version: Literal[1] = 1
    numeric_columns: list[str] = Field(min_length=1)
    medians: list[float]
    genre_vocabulary: list[str]
    tag_vocabulary: list[str]

    @model_validator(mode="after")
    def valid_contract(self):
        if (len(self.numeric_columns) != len(self.medians)
                or len(set(self.numeric_columns)) != len(self.numeric_columns)
                or not set(self.numeric_columns) <= set(BASE_NUMERIC + ENGINEERED)
                or not np.isfinite(self.medians).all()):
            raise ValueError("Invalid numeric preprocessing contract")
        for vocab in [self.genre_vocabulary, self.tag_vocabulary]:
            if len(vocab) != len(set(vocab)) or any(not token for token in vocab):
                raise ValueError("Invalid vocabulary")
        return self

    @property
    def width(self):
        return len(self.numeric_columns) + len(self.genre_vocabulary) + len(self.tag_vocabulary)

class Manifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    format_version: Literal[2] = 2
    artifact_format: Literal["onnx-random-forest"] = "onnx-random-forest"
    feature_schema_version: Literal[FEATURE_SCHEMA_VERSION] = FEATURE_SCHEMA_VERSION
    model_version: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
    model_type: Literal["RandomForestClassifier"] = "RandomForestClassifier"
    created_at: datetime
    training_observation_date: date
    runtime_versions: dict[str, str]
    training_versions: dict[str, str]
    model_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    preprocessing_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    class_ids: list[int]
    input_width: int = Field(gt=0)
    parity_examples: int = Field(gt=0)
    max_probability_error: float = Field(ge=0, le=0.00002)
    provenance: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def ordered_classes(self):
        if self.class_ids != [0, 1, 2]:
            raise ValueError("Expected class column order 0, 1, 2")
        return self


def runtime_versions():
    return {name: importlib.metadata.version(name) for name in RUNTIME_PACKAGES}


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def transform_features(features, spec):
    numeric = features[spec.numeric_columns].to_numpy(dtype=np.float64, copy=True)
    numeric = np.where(np.isnan(numeric), np.asarray(spec.medians), numeric)
    parts = [numeric.astype(np.float32)]
    for column, vocabulary in [("Genres", spec.genre_vocabulary), ("Tags", spec.tag_vocabulary)]:
        indices = {token: i for i, token in enumerate(vocabulary)}
        encoded = np.zeros((len(features), len(vocabulary)), dtype=np.float32)
        for row, text in enumerate(features[column]):
            for token in split_labels(text):
                index = indices.get(token)
                if index is not None:
                    encoded[row, index] = 1
        parts.append(encoded)
    result = np.ascontiguousarray(np.concatenate(parts, axis=1), dtype=np.float32)
    if not np.isfinite(result).all():
        raise ArtifactError("Preprocessing produced nonfinite values")
    return result


class OnnxPredictor:
    def __init__(self, model_file, spec):
        self.spec = spec
        options = ort.SessionOptions()
        options.intra_op_num_threads = 1
        options.inter_op_num_threads = 1
        options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        self.session = ort.InferenceSession(str(model_file), sess_options=options,
                                            providers=["CPUExecutionProvider"])
        inputs, outputs = self.session.get_inputs(), self.session.get_outputs()
        if (len(inputs) != 1 or inputs[0].type != "tensor(float)"
                or inputs[0].shape != [None, spec.width]
                or len(outputs) != 2 or outputs[1].type != "tensor(float)"):
            raise ArtifactError("Unsupported ONNX graph input/output contract")
        self.input_name, self.probability_name = inputs[0].name, outputs[1].name

    def predict_proba(self, games):
        features = GameFeatureTransformer().transform(games)
        matrix = transform_features(features, self.spec)
        return self.session.run([self.probability_name], {self.input_name: matrix})[0]


def checked_probabilities(estimator, games):
    probabilities = np.asarray(estimator.predict_proba(games), dtype=float)
    if (probabilities.shape != (len(games), 3) or not np.isfinite(probabilities).all()
            or (probabilities < -1e-6).any() or (probabilities > 1 + 1e-6).any()
            or not np.allclose(probabilities.sum(axis=1), 1.0, atol=2e-5, rtol=0)):
        raise ArtifactError("Model produced invalid class probabilities")
    # Float32 tree aggregation may differ by a few ulps. Return a valid simplex.
    probabilities = np.clip(probabilities, 0, 1)
    return probabilities / probabilities.sum(axis=1, keepdims=True)


def load_model(directory):
    """Only trusted, immutable release artifacts. Checksums are not publisher signatures."""
    directory = Path(directory)
    try:
        manifest = Manifest.model_validate_json((directory / "manifest.json").read_text())
        if manifest.runtime_versions != runtime_versions():
            raise ArtifactError("Artifact runtime dependencies differ; rebuild/revalidate the release")
        model_file, spec_file = directory / "model.onnx", directory / "preprocessing.json"
        if sha256(model_file) != manifest.model_sha256 or sha256(spec_file) != manifest.preprocessing_sha256:
            raise ArtifactError("Artifact checksum mismatch")
        spec = PreprocessingSpec.model_validate_json(spec_file.read_text())
        if spec.width != manifest.input_width:
            raise ArtifactError("Preprocessing width mismatch")
        estimator = OnnxPredictor(model_file, spec)
        probe = GameInput(release_date=date(2020, 1, 1), as_of_date=date(2023, 7, 5))
        checked_probabilities(estimator, [probe.model_dump()])
        return estimator, manifest
    except ArtifactError:
        raise
    except Exception as exc:
        raise ArtifactError("Could not load compatible ONNX artifact") from exc
