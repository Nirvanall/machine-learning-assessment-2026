# Project setup

See [README.md](README.md#environment) for the current Python environment setup and assessment layout.

Notebooks now live in `assessment_1_modeling/notebooks/`; open them with the project `.venv` kernel.
The production service and Docker instructions are in `assessment_2_production/README.md`.
The fictional private Azure deployment design is in `assessment_3_infrastructure/azure-blueprint.md`.

The root requirements install the relocated `steam_service` package in editable mode automatically:

```bash
python -m pip install -r requirements.txt
python -m pip install -r assessment_2_production/requirements-service.txt
```

Keep the model export/runtime inference dependency versions aligned. Re-export and test each model release after intentional dependency upgrades. No Azure account or deployment is required for local development.

If you already have the dependencies and only need to repair the package registration, run from the repository root:

```bash
python -m pip install -e ./assessment_2_production --no-deps
python -c "import steam_service; print(steam_service.__file__)"
```

Use imports such as `from steam_service.export import export_model`, not `from assessment_2_production.steam_service...`. The editable install resolves the source location. Poetry users get the same editable package through the local path dependency in the root `pyproject.toml`. Restart an existing Jupyter kernel after first installation; select this project's `.venv` in VS Code.
