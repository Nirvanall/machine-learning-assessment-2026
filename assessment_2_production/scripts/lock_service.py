"""Pin the service dependency closure to the currently installed training environment.

Run from the project root after installing service + model dependencies. Commit the
result alongside each model release; Docker and training must use matching locks.
"""
from importlib.metadata import distribution
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

pending = ["fastapi", "uvicorn", "numpy", "pandas", "onnxruntime", "PyJWT", "cryptography"]
versions = {}
while pending:
    name = canonicalize_name(pending.pop())
    if name in versions:
        continue
    package = distribution(name)
    versions[name] = package.version
    for item in package.requires or []:
        requirement = Requirement(item)
        if requirement.marker is None or requirement.marker.evaluate({"extra": ""}):
            installed = distribution(requirement.name)
            if installed.version not in requirement.specifier:
                raise RuntimeError(f"Installed {requirement.name} does not satisfy {requirement}")
            pending.append(requirement.name)
output = Path(__file__).resolve().parents[1] / "requirements-service.txt"
output.write_text("# Runtime lock from the model training environment; regenerate with assessment_2_production/scripts/lock_service.py.\n"
                  + "\n".join(f"{name}=={version}" for name, version in sorted(versions.items())) + "\n")
print(f"Pinned {len(versions)} runtime packages in {output.name}")
