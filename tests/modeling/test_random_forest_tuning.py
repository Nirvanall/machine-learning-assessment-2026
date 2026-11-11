import ast
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
from sklearn.base import clone
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import RandomizedSearchCV, StratifiedKFold
from sklearn.pipeline import Pipeline


def rf_section():
    notebook = json.loads(Path("assessment_1_modeling/notebooks/steam_model_experiments.ipynb").read_text())
    return ast.parse(next("".join(c["source"]) for c in notebook["cells"]
        if c["cell_type"] == "code" and "rf_parameters = {" in "".join(c["source"])))


def test_random_forest_search_parameters_fit_five_folds():
    assignments = [node for node in rf_section().body if isinstance(node, ast.Assign)
                   and any(isinstance(t, ast.Name) and t.id in {"RF_SEARCH_ITER", "rf_parameters"}
                           for t in node.targets)]
    scope = {"SMOKE_TEST": True, "QUICK_RUN": True}
    exec(compile(ast.Module(body=assignments, type_ignores=[]), "<forest search space>", "exec"), scope)
    X = np.random.default_rng(42).normal(size=(60, 6))
    y = np.repeat([0, 1, 2], [30, 20, 10])
    pipeline = Pipeline([("model", RandomForestClassifier(bootstrap=True, random_state=42, n_jobs=1))])
    search = RandomizedSearchCV(pipeline, scope["rf_parameters"], n_iter=scope["RF_SEARCH_ITER"],
        cv=StratifiedKFold(n_splits=5, shuffle=True, random_state=42), random_state=42,
        scoring="f1_macro", error_score="raise", n_jobs=1).fit(X, y)
    assert search.n_splits_ == 5 and len(search.cv_results_["params"]) == 2
    assert np.isfinite(search.cv_results_["mean_test_score"]).all()
    assert search.best_estimator_.predict_proba(X[:2]).shape == (2, 3)


@pytest.mark.parametrize("winner,tuned_f1,expected_trees,expected_name", [
    ("Random forest", .65, 40, "Tuned random forest"),
    ("Random forest", .55, 20, "Random forest"),
    ("CatBoost core", .65, None, "Tuned CatBoost core"),
])
def test_only_upgrade_validation_winning_forest_when_cv_improves(winner, tuned_f1, expected_trees, expected_name):
    nodes = rf_section().body
    selection = next(node for node in nodes if isinstance(node, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "rf_configuration" for t in node.targets))
    branch = next(node for node in nodes if isinstance(node, ast.If)
                  and "pre_tuning_winner" in ast.unparse(node.test))
    previous = Pipeline([("model", DummyClassifier())])
    comparison = pd.DataFrame({"cv_mean_macro_f1": [.60, tuned_f1],
        "cv_mean_ordinal_rmse": [.5, .5], "cv_mean_inference_ms_per_game": [.1, .1]},
        index=["Fixed random forest", "Tuned random forest"])
    scope = dict(clone=clone, final_tuning_comparison=comparison, pre_tuning_winner=winner,
        forest=Pipeline([("model", RandomForestClassifier(n_estimators=20))]),
        rf_search=SimpleNamespace(best_estimator_=Pipeline([("model", RandomForestClassifier(n_estimators=40))])),
        final_template=previous, final_name="Tuned CatBoost core")
    exec(compile(ast.Module(body=[selection, branch], type_ignores=[]), "<final forest selection>", "exec"), scope)
    assert scope["final_name"] == expected_name
    if expected_trees is None:
        assert scope["final_template"] is previous
    else:
        assert scope["final_template"].named_steps["model"].n_estimators == expected_trees
