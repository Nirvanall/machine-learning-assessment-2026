# Steam management presentation — speaker notes

11 main slides: **12:30**. Discussion: **2:30**. Slides 12–15 are backup only.

Design: 16:9, minimal typography, one green accent, editable vector charts and diagrams.

## 01. Recommend a controlled internal pilot

**Timing:** 00:00–00:45

Open with the decision: use the fixed Random Forest as a decision-support tool for an internal pilot. The goal is to help approved teams prioritize games for partnership review. On the held-out sample, it identifies roughly two thirds of games above 100,000 estimated owners, versus about one fifth with the original KNN. This is evidence of better classification, not an estimate of extra partnerships or downloads. We have also packaged the model and designed private Azure hosting with DEV testing and approval before any PROD promotion. The choice was fixed from development results before the final comparison. I will cover what the data tells us, the business tradeoff, and what remains before a real release. The first 11 slides take 12 minutes 30 seconds, leaving 2 minutes 30 seconds for questions.

**Evidence:** S2, S3, S4, S5, S6

## 02. Define exactly what we can predict

**Timing:** 00:45–02:00

The source contains 85,103 games. The preprocessing policy retains 58,614 games that are at least one year old at 5 July 2023 and have positive ownership midpoints. This gives titles time to accumulate ownership, but it excludes the use case of predicting a game before launch. The original owner intervals are mapped into three broad categories. The midpoint is the average of the source lower and upper bounds, used for auditing and eligibility; none of those ownership fields is a predictor. Around 71 percent of games fall in the lowest category and only 11 percent in the highest. A classifier can therefore look accurate simply by predicting low ownership. These are estimated cumulative owners, not measured downloads, unique players or revenue. The high category spans 100,000 to 200 million owners and cannot distinguish blockbusters within that group.

**Evidence:** S1, S4

## 03. Translate EDA into model decisions

**Timing:** 02:00–03:00

Three EDA findings shape the approach. First, higher-owner games tend to have been on sale longer: median ages are 3.54, 5.14 and 6.64 years across the three bands. That is an association with accumulated ownership, not proof that age causes success. Second, prices and achievement counts are skewed, so raw numeric distances are a poor starting point for nearest neighbors. Third, the selected baseline fields have no missing values and duplicate checks pass, but clean data is not enough: we must exclude ownership and engagement outcomes from predictors and learn data-dependent preprocessing only within training folds. Missing Steam scores exist but are excluded. Together with imbalance, these findings explain why we use class-balanced reporting and compare tree models rather than trust headline accuracy. The historical split still cannot validate performance on future releases.

**Evidence:** S1

## 04. Explain the experiment logic

**Timing:** 03:00–04:15

We first reproduce the default KNN and compare it with a majority-class reference. Then we tune and scale KNN to check whether the original algorithm can improve. KNN votes using the most similar games. Random Forest averages many decision-rule trees, testing nonlinear interactions without relying on numeric distance. CatBoost builds trees sequentially to reduce errors, giving us a different learning strategy. Its fixed-setting feature ladder adds engineered metadata, then tags and description text. Hyperparameter searches follow so we can distinguish representation changes from tuning. Every learned imputer and vocabulary is fitted within the training folds. Five-fold evaluation repeats the check: in each round the model learns from four portions and is evaluated on the remaining portion. Keeping the category mix similar checks consistency without rewarding only the largest class. Selection was exploratory: development was capped at 6,000 games, with 4,500 initial training and 1,500 validation games. Final candidate models were refitted on all 46,891 non-test games, then reported on the same 11,723 test games. The frozen Random Forest family won the earlier validation comparison; tuning did not improve its paired development CV macro F1.

**Evidence:** S2, S4, S7

## 05. Present the model comparison without overstating the winner

**Timing:** 04:15–05:30

This is the final held-out comparison, not the smaller development-fold comparison. Macro F1 summarizes the balance of precision and recall across categories, giving each category equal weight. The fixed Random Forest improves from 0.467 for default KNN to 0.639, an absolute gain of 0.172. Tuned CatBoost with engineered features and tags also rounds to 0.639, while tuned Random Forest scores 0.633. We should not claim that the tiny forest/CatBoost difference proves a superior family. We retain the forest chosen from development evidence and keep CatBoost as a credible challenger. In the saved notebook benchmark, forest batch prediction costs about 0.016 milliseconds per game versus 0.883 for KNN, roughly 55 times lower. That benchmark includes pipeline preprocessing, but is not single-request HTTP latency or ONNX deployment performance. Adding TF-IDF descriptions reduced development CV macro F1 and increased cost, so more features were not automatically helpful.

**Evidence:** S2, S4

## 06. Make the high-owner tradeoff explicit

**Timing:** 05:30–07:00

The business priority changes the interpretation. Among 1,243 actual high-owner test games, default KNN finds 263, or 21 percent. The fixed forest finds 822, or 66 percent, identifying 559 additional high-owner games in this sample. But it also creates 505 false high-owner flags, compared with 90 for KNN; precision falls from about 75 to 62 percent. This is a more useful discovery tool only if the review team can absorb that workload. Tuned CatBoost finds 837 with 517 false flags. Tuned Random Forest finds 844 but produces 646 false flags. Compared with the fixed forest, tuning buys 22 extra correct flags at the cost of 141 extra false flags. The key management input is the acceptable balance between missed popular games and unnecessary review. These are classification opportunities, not measured lost partnerships or conversion revenue. Define any revised decision rule on development data, then verify it on a fresh untouched holdout.

**Evidence:** S3

## 07. Show the simple product interface and packaging

**Timing:** 07:00–08:15

A business application submits a JSON record using the original CSV field names, such as AppID, Name, Release date, Price, Genres and Tags. Python preprocessing parses those values, validates eligibility and uses the fitted medians and vocabularies. AppID, Name and ownership/engagement fields do not enter classification; media URLs are not fetched. The ONNX Random Forest returns a compact JSON response with success, predicted owner band, the winning class probability and model version. The example values on the slide are illustrative. The probability is not automatically a calibrated confidence guarantee. We package the ONNX graph, preprocessing JSON and version/checksum manifest with FastAPI in a Docker image. No training or Python pickle loading happens in serving. The model only supports the three trained broad bands: it cannot truthfully return the narrower 20,000 to 50,000 source interval. Game age defaults to the model's historical observation date unless a reference date is explicitly supplied.

**Evidence:** S5

## 08. Deploy to DEV, then promote the approved release

**Timing:** 08:15–09:45

The supplied architecture introduces a deliberate separation between development and production. We adopt that lifecycle: local model work goes through protected source and CI tests, ONNX parity checks, one image build and a security scan. Publish the candidate to private DEV ACR and its bundle to DEV Blob, then deploy to a separate internal DEV Container Apps environment. ML engineers debug through DEV-authorized clients. Acceptance checks include preprocessing/predictions, invalid inputs, identity restrictions, private reachability, load, replica failure and rollback. Any fix produces a new candidate and repeats DEV checks. Only a successful report and independent manual approval unlock production deployment credentials. Promote the same tested image digest and model bytes; do not rebuild or retrain between environments. PROD has separate resource group/network, clients, runtime identity, private registry, artifact archive and monitoring. It starts with two replicas and can scale to four. The implementation bundles the model into the image; Blob is the versioned release archive, not a natively mounted runtime filesystem. Keep JSON preprocessing, not the reference picture's joblib. No cloud environment or pipeline is actually deployed.

**Evidence:** S6, S8

## 09. Separate local verification from cloud readiness

**Timing:** 09:45–10:45

The implementation is more than an architecture sketch. Seventy-nine tests passed, including the CSV input contract, ONNX behavior, validation, authorization and artifact rejection. The forest was refitted on the recorded 46,891 non-test games and converted; 1,500 representative non-test examples matched its original class predictions, with a maximum probability difference around 0.00000024. The container ran as a non-root user with a read-only filesystem and no external network or published ports. All 100 local prediction calls succeeded at concurrency two; p95 HTTP loopback latency was about 34 milliseconds. These numbers do not establish an Azure SLO or live Entra integration: authentication was explicitly disabled for that isolated container check, while auth behavior was tested separately. Before a business pilot, provision the separate private environments and identities, deploy into DEV, run debugging/integration/burst/failover checks, and require independent approval. Then promote the same image/model to PROD and verify readiness, monitoring and rollback. Local tests are not evidence that those cloud stages have already run.

**Evidence:** S5, S6

## 10. Prioritize future development by value and cost

**Timing:** 10:45–11:45

First improve the use of current data. Full-development learning curves/tuning can test whether quick-mode selection left performance on the table. Agree on the cost of missed popular games versus false flags, then use properly separated development data for probability calibration and the high-owner decision rule. Diagnose errors, especially the middle category, and test existing engineered inputs in the forest plus the additional metadata candidates. A small RF/CatBoost ensemble is worth trying only if out-of-fold errors are complementary. Then consider frozen screenshot embeddings cached offline, followed by sampled trailer frames and video encoders only if they add repeatable value relative to extraction/storage costs. For the product, keep humans in the review loop and collect delayed owner outcomes to monitor quality. Since current test results have now informed improvements, obtain a fresh holdout and chronological/grouped validation before stronger forecasting claims.

**Evidence:** S7, S6

## 11. Ask managers for concrete decisions

**Timing:** 11:45–12:30

Close with a bounded recommendation rather than a claim that the system is finished. The fixed forest offers a substantially better starting point for finding high-owner games than KNN, with a simple and tested serving path. Ask managers to agree on the acceptable false-flag workload and missed-opportunity rate, name owners for DEV testing, independent release approval and ongoing model monitoring, and require the DEV acceptance and fresh-validation gates before PROD business use. Treat this as review support; do not promise more downloads or successful partnerships from offline classification metrics. The CatBoost challenger and staged roadmap remain available if new evidence justifies a change. Pause here for questions. Backup slides contain exact metrics, per-category errors and evidence sources. Budget two minutes thirty seconds for questions within the fifteen-minute meeting.

**Evidence:** S2, S3, S5, S6, S7

## 12. Backup — exact test metrics

**Timing:** Backup — use only if asked

Use only if asked. These are the same held-out games, with quick-mode development selection and full non-test refitting. Macro F1 gives equal weight to all three classes. Balanced accuracy averages class recalls. Inference milliseconds per game are amortized across the 11,723-row batch in the saved sklearn pipeline benchmark, not ONNX HTTP serving. The forest/CatBoost macro-F1 difference is approximately 0.00012 and should not be treated as evidence of a meaningful superiority. The bootstrap interval for the selected forest's macro F1 is roughly 0.628 to 0.649; its paired improvement versus KNN is roughly 0.159 to 0.187. These intervals condition on the fitted models and this random test sample, not retraining or future data shift.

**Evidence:** S2, S3, S4

## 13. Backup — forest confusion matrix

**Timing:** Backup — use only if asked

Rows are actual categories; columns are predicted categories. The forest identifies 7,344 of 8,308 low-owner games, 816 of 2,172 middle-owner games, and 822 of 1,243 high-owner games. The middle class remains hardest, with recall about 37.6 percent. In the high-owner row, 188 games are severely underestimated into the lowest band and 233 into the middle band. Thus 421 high-owner games are missed in total. Of 1,327 high-owner predictions, 505 are false flags, producing 61.9 percent precision. Category distances are not errors in owner counts, since bands have unequal widths. This matrix helps target development error analysis, but after examining it we need fresh evaluation for follow-up changes.

**Evidence:** S3

## 14. Backup — evidence and limits

**Timing:** Backup — use only if asked

All numerical claims come from saved local artifacts or the documented local verification. No model was retrained for this presentation. EDA coverage and class balance come from the baseline assessment; experiment metrics, high-owner counts and selection provenance come from the quick experiment outputs. Packaging and local HTTP claims come from the current CSV API verification report. The cloud architecture is a fictional proposal, based on the assessment 3 blueprint and its Microsoft documentation links. Important constraints are the historical snapshot, three broad cumulative-owner categories, quick-mode selection and random holdout. The existing test results have been inspected; use fresh data for confirming future changes. These results do not establish causality, measured downloads, production cloud availability or additional partnership revenue.

**Evidence:** S1, S2, S3, S4, S5, S6, S7

## 15. Backup — supplied Azure architecture reference

**Timing:** Backup — use only if asked

This is the user's supplied reference, preserved unchanged for detailed discussion. The adopted architecture follows its DEV-before-PROD lifecycle, separate environments/access, CI/CD, versioned model artifacts and monitoring. The working runtime differs in two explicit respects: preprocessing is declarative JSON rather than joblib, and model files are bundled into the tested image. Private Blob accounts archive candidate/approved bundles for the release pipeline; Container Apps does not provide a native Blob mount. A future startup downloader would require additional code and tests. The reference also shows direct user SSO; our business application authorizes teams while FastAPI validates approved machine clients. See the assessment 3 adaptation table and promotion plan for these boundaries. This image is a design reference, not deployed infrastructure.

**Evidence:** S6, S8

## Evidence map

- **S1:** [steam_eda_baseline_assessment.ipynb](../assessment_1_modeling/notebooks/steam_eda_baseline_assessment.ipynb)
- **S2:** [final_test_metrics.csv](../artifacts/steam_experiments/quick/final_test_metrics.csv), [five_fold_comparison.csv](../artifacts/steam_experiments/quick/five_fold_comparison.csv), [validation_comparison.csv](../artifacts/steam_experiments/quick/validation_comparison.csv)
- **S3:** [final_test_high_owner_summary.csv](../artifacts/steam_experiments/quick/final_test_high_owner_summary.csv), [final_test_category_metrics.csv](../artifacts/steam_experiments/quick/final_test_category_metrics.csv), [final_test_confusion_matrices.csv](../artifacts/steam_experiments/quick/final_test_confusion_matrices.csv)
- **S4:** [run_manifest.json](../artifacts/steam_experiments/quick/run_manifest.json), [bootstrap_intervals.csv](../artifacts/steam_experiments/quick/bootstrap_intervals.csv)
- **S5:** [README.md](../assessment_2_production/README.md), [VERIFICATION.md](../assessment_2_production/VERIFICATION.md)
- **S6:** [azure-blueprint.md](../assessment_3_infrastructure/azure-blueprint.md), [release-promotion.md](../assessment_3_infrastructure/release-promotion.md), [containerapp.dev.template.yaml](../assessment_3_infrastructure/containerapp.dev.template.yaml), [containerapp.template.yaml](../assessment_3_infrastructure/containerapp.template.yaml)
- **S8:** [Azure ML Production Deployment Architecture.png](../assessment_4_presentation/Azure%20ML%20Production%20Deployment%20Architecture.png)
- **S7:** [steam_model_experiments.ipynb](../assessment_1_modeling/notebooks/steam_model_experiments.ipynb)
