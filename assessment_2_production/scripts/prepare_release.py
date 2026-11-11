"""Stage a minimal Docker context containing one validated ONNX artifact. No cloud writes."""
import argparse
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    import sys
    sys.path.insert(0, str(ROOT))
    from steam_service.artifacts import load_model
    _, manifest = load_model(args.model_dir)
    args.output.mkdir(parents=True, exist_ok=False)
    shutil.copytree(ROOT / "steam_service", args.output / "steam_service",
                    ignore=shutil.ignore_patterns("__pycache__", "export.py"))
    (args.output / "model").mkdir()
    for name in ["model.onnx", "preprocessing.json", "manifest.json"]:
        shutil.copy2(args.model_dir / name, args.output / "model" / name)
    for name in ["Dockerfile", "requirements-service.txt"]:
        shutil.copy2(ROOT / name, args.output / name)
    (args.output / ".dockerignore").write_text("__pycache__/\n*.pyc\n")
    print(f"Staged {manifest.model_version} in {args.output}; build with docker build -t steam-rf:3.0.0-{manifest.model_version} {args.output}")

if __name__ == "__main__":
    main()
