import ast
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from sklearn.metrics import confusion_matrix


@pytest.fixture
def category_report():
    notebook = json.loads(Path("assessment_1_modeling/notebooks/steam_model_experiments.ipynb").read_text())
    source = next("".join(c["source"]) for c in notebook["cells"]
                  if c["cell_type"] == "code" and "def per_category_report" in "".join(c["source"]))
    function = next(node for node in ast.parse(source).body if isinstance(node, ast.FunctionDef)
                    and node.name == "per_category_report")
    scope = dict(np=np, pd=pd, confusion_matrix=confusion_matrix, CLASSES=[0, 1, 2],
                 CLASS_NAMES=["0–<20k owners", "20k–<100k owners", "100k–200m owners"])
    exec(compile(ast.Module(body=[function], type_ignores=[]), "<category report>", "exec"), scope)
    return scope["per_category_report"]


def test_high_owner_metrics_match_confusion_counts(category_report):
    truth = [0, 0, 1, 1, 2, 2, 2]
    predicted = [0, 2, 1, 2, 0, 2, 2]
    report, counts = category_report(truth, predicted)
    np.testing.assert_array_equal(counts, [[1, 0, 1], [0, 1, 1], [1, 0, 2]])
    high = report.set_index("class_id").loc[2]
    assert high["support"] == 3 and high["predicted_count"] == 4
    assert high["true_positive"] == 2 and high["false_negative"] == 1
    assert high["false_positive"] == 2
    assert high["precision"] == pytest.approx(.5)
    assert high["recall"] == pytest.approx(2 / 3)
    assert high["f1"] == pytest.approx(4 / 7)
    assert report["support"].sum() == len(truth)


def test_absent_or_never_predicted_categories_are_explicit(category_report):
    report, counts = category_report([0, 0, 2], [0, 0, 0])
    classes = report.set_index("class_id")
    assert counts.shape == (3, 3)
    assert classes.loc[1, "support"] == 0 and np.isnan(classes.loc[1, "recall"])
    assert classes.loc[2, "precision"] == 0 and classes.loc[2, "recall"] == 0
    assert classes.loc[2, "false_negative"] == 1


@pytest.mark.parametrize("truth,prediction", [([0, 1], [0]), ([0, 3], [0, 1]), ([0, 1], [0, 3])])
def test_category_report_rejects_invalid_labels_or_lengths(category_report, truth, prediction):
    with pytest.raises(ValueError):
        category_report(truth, prediction)
