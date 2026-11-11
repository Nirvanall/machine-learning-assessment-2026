# Assessment 1 — data, EDA and model experiments

The original work is retained in `notebooks/` here:

1. `mle-process-data.ipynb`: original processed `data/games.parquet`.
2. `mle-exercise.ipynb`: original KNN exercise.
3. `steam_eda_baseline_assessment.ipynb`: processed-data EDA, baseline and written assessment.
4. `mle-proccess-data-extra.ipynb`: extended cleaning/feature export to `games-extra.parquet`, with reasons for added features. The existing filename spelling is preserved.
5. `steam_model_experiments.ipynb`: common splits, five-fold CV, KNN/forest/CatBoost comparisons, final category metrics, board summary, optional ONNX forest export and future plans.

Open notebooks from this directory or the repository root; data discovery walks parent directories. The root requirements install the shared `steam_service` package from `assessment_2_production` in editable mode; its import name stays `steam_service`. The experiment notebook also supports a direct source checkout through a guarded path setup. All ownership bounds and midpoint describe outcomes and stay outside model inputs. The 13 extra metadata candidates are not automatically selected by existing models.

The shared offline ownership helper is at repository-root `steam_data.py`. Experiment outputs remain at root `artifacts/steam_experiments/`; generated models are at root `models/`. Historical outputs remain evidence of the original runs, including their old absolute paths.

## Reproduce the approved production family

`scripts/export_random_forest.py` checks the saved experiment and dataset checksums, uses `split_manifest.csv` to exclude test games, refits the fixed forest configuration, and invokes the assessment 2 ONNX exporter. It performs no tuning or new test evaluation. The existing quick run uses 200 trees; the full-mode fixed recipe uses 500. It rejects a smoke run or a selection other than the fixed forest rather than guessing a model configuration.

```bash
python assessment_1_modeling/scripts/export_random_forest.py --model-version steam-rf-onnx-v1
```

Run the command from the root and choose a new version for later releases. Prefer the notebook export if its fitted final forest is already in memory; it avoids refitting. The cloud blueprint is in assessment 3, and API/container instructions are in assessment 2.
