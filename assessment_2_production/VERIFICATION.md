# Current API verification — CSV-record contract

The API now accepts the original games.csv field names and returns only `is_success`, `predicted_owner_range`, `probability`, and `model_version`. The ONNX model and its preprocessing artifact remain unchanged; the request adapter and response contract changed.

- Updated automated suite: **79 passed**; retains modeling, ONNX parity, authorization, invalid-input and capacity checks and adds CSV normalization, full-record acceptance, outcome/identity exclusion and winning-class probability checks.
- Image: `steam-rf:3.0.0-steam-rf-onnx-v1`.
- Image ID: `sha256:6035c22b96fdfd4515507319df3e65d92d55cb99ca50b3f4f629d1d030ce335b`.
- Full real CSV record accepted; modifying AppID, Name and known ownership/review outcomes did not change the prediction.
- **100/100 predictions succeeded**, concurrency 2, **1.039 seconds**, loopback p50 **17.45 ms**, p95 **34.15 ms**.
- Invalid record returned 422 with `is_success: false`.
- Real artifact, UID 10001, read-only filesystem, network disabled and no published ports; explicit local-only authentication bypass. Authorization tests remain separate.
- The three trained ranges remain `0 - 20000`, `20000 - 100000`, `100000 - 200000000`; the model does not predict the narrower source intervals.
- Temporary test container stopped/removed after the check. No cloud deployment or registry push performed.

These are local execution checks, not evidence of an Azure SLO, live Entra configuration or changed predictive accuracy. The earlier report below records the same model conversion and previous API image for traceability; its image ID and response shape do not describe this updated release.

---

# Previous API verification — 28 October 2026

These results verify packaging and execution locally, not an Azure deployment or production SLO.

## Model release

- Bundle: `models/steam-rf-onnx-v1/` at repository root (generated, ignored by Git).
- Recipe: fixed Random Forest, 200 trees, saved quick-mode development selection.
- Refitted on 46,891 recorded non-test games; zero test rows used for fitting.
- ONNX input: 477 float32 features from fitted numeric medians and genre/tag vocabularies.
- Parity: 1,500 stratified non-test examples, matching class predictions.
- Maximum absolute probability difference versus scikit-learn: **2.4152e-7**.
- ONNX SHA-256: `0138ab35b7a08ebd2b50a1ea11007526d18e0b0d3562410e2c0ca7f21b072271`.
- Full provenance and inference dependency versions: the release's `manifest.json`.

The representative parity gate is not a proof of equality for every possible input; the ONNX exporter also has synthetic missing/unseen-input tests. No new predictive performance estimate was measured during this refit/export.

## Automated checks

`python -m pytest tests -q`: **74 passed**. Covers modeling contracts and production behavior, ONNX conversion, fresh-process loading without training imports, corruption/schema/version rejection, schema validation, concurrency/body limits, signed JWT verification and protected endpoints. The test client reports an upstream httpx deprecation warning; checks pass.

All moved notebook files validate with nbformat, and the experiment code cells parse. Their saved model evaluation outputs remain intact; the optional export cell was updated and its previous export output cleared.

## Real-model container smoke/burst test

- Image: `steam-rf:steam-rf-onnx-v1`.
- Local image ID: `sha256:0013ea00372636709b05755428bf9d88fe5899bbac815500bb87a68cb4eef438`.
- Base-image digest is pinned in `Dockerfile`.
- Linux container, UID 10001, read-only filesystem, temporary `/tmp`, capabilities dropped.
- One CPU, 2 GiB memory limit, network disabled, no published host ports.
- Explicit `AUTH_MODE=disabled` only for isolated local HTTP checks; JWT/auth failure paths are covered separately by automated tests.
- Readiness and prediction response contracts passed with the real ONNX artifact.
- **100/100 HTTP predictions succeeded** at concurrency 2 in **1.098 seconds**.
- End-to-end container-loopback p50: **17.81 ms**; p95: **42.57 ms**.
- Invalid input returned 422.
- sklearn, CatBoost, skl2onnx, ONNX conversion library and joblib were absent from the runtime.
- Temporary verification container stopped and removed after testing; no Azure resources created or images pushed.

This is a short local burst, not a representative traffic distribution, single-replica failure test, authenticated Entra integration test, or Azure autoscaling test. Confirm those environment-specific behaviors before release. Future dependency/model changes require re-export, rebuild and repeat verification; these figures describe this artifact/image pair only.
