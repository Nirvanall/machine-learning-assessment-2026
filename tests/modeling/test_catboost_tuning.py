"""Exercise every weighting option from the notebook, not one random candidate."""

import ast
import json
from pathlib import Path

import numpy as np
from catboost import CatBoostClassifier
from sklearn.model_selection import RandomizedSearchCV, StratifiedKFold
from sklearn.pipeline import Pipeline


def test_all_final_tuning_class_weight_options_fit():
    notebook = json.loads(Path("assessment_1_modeling/notebooks/steam_model_experiments.ipynb").read_text())
    source = next("".join(cell["source"]) for cell in notebook["cells"]
                  if cell["cell_type"] == "code" and "cat_parameters = {" in "".join(cell["source"]))
    assignment = next(node for node in ast.parse(source).body if isinstance(node, ast.Assign)
                      and any(isinstance(target, ast.Name) and target.id == "cat_parameters" for target in node.targets))
    scope = {"SMOKE_TEST": False, "QUICK_RUN": True}
    exec(compile(ast.Module(body=[assignment], type_ignores=[]), "<final tuning parameters>", "exec"), scope)
    weights = scope["cat_parameters"]["model__auto_class_weights"]
    assert weights == ["None", "Balanced", "SqrtBalanced"]
    rng = np.random.default_rng(42)
    X = rng.normal(size=(60, 4))
    y = np.repeat([0, 1, 2], [30, 20, 10])
    pipeline = Pipeline([("model", CatBoostClassifier(iterations=3, depth=2,
        loss_function="MultiClass", random_seed=42, verbose=False, thread_count=1,
        allow_writing_files=False))])
    search = RandomizedSearchCV(pipeline, {"model__auto_class_weights": weights}, n_iter=len(weights),
        cv=StratifiedKFold(n_splits=5, shuffle=True, random_state=42), scoring="f1_macro",
        error_score="raise", n_jobs=1, random_state=42).fit(X, y)
    assert {row["model__auto_class_weights"] for row in search.cv_results_["params"]} == set(weights)
    assert np.isfinite(search.cv_results_["mean_test_score"]).all()
    assert search.best_estimator_.predict_proba(X[:3]).shape == (3, 3)
