# Steam ownership prediction — assessment submission

Predict **cumulative estimated-owner bands**, not measured downloads or pre-launch sales. The selected production model is the **fixed Random Forest**, served with **FastAPI + ONNX Runtime**. Azure deployment is a blueprint only; no cloud resources have been deployed.

| Assessment | Location | Deliverables |
| --- | --- | --- |
| **1. Assess and improve modeling** | [assessment_1_modeling](assessment_1_modeling/README.md) | Original/extended preprocessing, EDA, five-fold experiments, per-category evaluation, improvement plans and an offline forest refit/export recipe. |
| **2. Prepare for production (30%)** | [assessment_2_production](assessment_2_production/README.md) | Validated prediction API, ONNX/JSON release artifacts, parity gates, Entra authorization, Docker packaging and tests. |
| **3. Infrastructure blueprint (10%)** | [assessment_3_infrastructure](assessment_3_infrastructure/azure-blueprint.md) | Private Azure Container Apps design, presentation-ready Mermaid diagram, capacity/security/operations decisions and a configuration template. |
| **4. Management presentation (30%)** | [assessment_4_presentation](assessment_4_presentation/README.md) | Minimal 15-minute PowerPoint/PDF with EDA, model results, architecture, improvement plans and timed speaker notes. |

Shared data stays in `data/`; experiment evidence stays in `artifacts/steam_experiments/`. `steam_data.py` defines ownership bounds/midpoints and labels for offline preprocessing. Tests are separated into `tests/modeling/` and `tests/production/`. Generated immutable model bundles go in ignored `models/`.

## Environment

From the repository root, using Python 3.12:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pip install -r assessment_2_production/requirements-service.txt
python -m pip install pytest httpx
```

`requirements.txt` also installs `assessment_2_production` as an editable package. Its import name remains `steam_service`; the assessment folder is its source location, not an import prefix. After changing environments or moving this checkout, rerun the setup commands.

The training/export environment includes sklearn, skl2onnx and ONNX. The Docker runtime lock contains **ONNX Runtime and the API dependencies**, with no sklearn, CatBoost, conversion tools or pickle loader. Export and runtime use the recorded compatible inference package versions.

## Production workflow

Export the fitted forest from section 14 of [the experiment notebook](assessment_1_modeling/notebooks/steam_model_experiments.ipynb), or reproduce the recorded fixed forest without using test rows:

```bash
python assessment_1_modeling/scripts/export_random_forest.py --model-version steam-rf-onnx-v1
```

This writes `model.onnx`, `preprocessing.json` and `manifest.json` in `models/steam-rf-onnx-v1/`. Existing versions cannot be overwritten. This reproduces the current **quick-search** selection on all recorded non-test refit rows; it does not turn exploratory model selection into full-search evidence. See the production guide for packaging, local serving, authentication and release checks.

```bash
python -m pytest tests -q
```

The notebooks were moved from `notebooks/` into assessment 1. Open the new paths; saved historical notebook outputs may still show their old paths. Data files and measured experiment scores were not rewritten.
