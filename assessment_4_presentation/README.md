# Assessment 4 — management presentation

A minimal 16:9 deck for Valve managers with limited technical background.

- [PowerPoint](steam_management_presentation_dev_prod.pptx): editable text, charts and architecture diagram; speaker notes embedded.
- [PDF](steam_management_presentation_dev_prod.pdf): matching slide design for easy viewing/sharing.
- [Timed speaker notes](speaker_notes.md): reasoning, talking points, limitations and sources.
- [Preview: slides 1–7](previews/contact-sheet-1.png) and [slides 8–14](previews/contact-sheet-2.png), plus [the supplied reference image on slide 15](previews/contact-sheet-3.png).

Present slides **1–11 in 12 minutes 30 seconds** and reserve **2 minutes 30 seconds for questions**. Slides 12–15 are optional backup, not part of the timed talk.

The narrative covers the business objective, EDA, experiment logic, measured model and high-owner results, simple ONNX API packaging, private DEV/PROD Azure architecture, local verification, future development and a gated pilot recommendation. Slide 8 now shows **CI → private DEV → debugging/tests → independent approval → same-release PROD promotion**. Slide 9 lists the DEV acceptance and approval gates; slide 11 assigns DEV testing and PROD approval owners. The supplied architecture PNG is preserved unchanged as backup slide 15, with explicit implementation adaptations in the notes. It distinguishes owner estimates from downloads, exploratory selection from full validation, and local execution from a real cloud deployment. It does not claim additional partnership revenue or a proven forecasting capability.

All evidence comes from assessments 1–3 and the saved `artifacts/steam_experiments/quick/` results. `evidence_manifest.json` records source paths and SHA-256 hashes. Values such as example JSON probabilities are explicitly labeled illustrative. No models were retrained to create the presentation.

## Regenerate

From the repository root:

```bash
python -m pip install -r assessment_4_presentation/requirements.txt
python assessment_4_presentation/scripts/build_presentation.py
python assessment_4_presentation/scripts/render_previews.py
```

The build uses Linux Liberation Sans and DejaVu Sans Mono fonts; adjust the font paths if rebuilding elsewhere. PowerPoint text uses Arial for common desktop compatibility. PDF/PPTX share the same layout instructions; chart data is rendered as editable native shapes in the PowerPoint. The PDF is generated directly without requiring Office or LibreOffice.

The authored narrative describes the current evidence snapshot. The build stops if key source results change, so review and update the claims before presenting new experiments. Estimated timings assume a rehearsed delivery; the notes explain the reasoning without putting technical detail on the slides.

## DEV-first architecture update

The proposal uses separate DEV/PROD resource groups, networks, identities, private registries/model archives and monitoring. Failed DEV checks block promotion; production receives the same tested image/model digest without rebuilding. The reference's Blob mount and joblib labels are not implemented literally: Container Apps lacks native Blob mounts, and the working service uses JSON preprocessing and model files bundled in its image. Blob is the versioned release archive; a future startup downloader would need new implementation/testing.

See [the infrastructure blueprint](../assessment_3_infrastructure/azure-blueprint.md), [promotion plan](../assessment_3_infrastructure/release-promotion.md), and [original supplied diagram](Azure%20ML%20Production%20Deployment%20Architecture.png). The 11-slide talk remains 12:30 plus 2:30 for questions. Model scores and assessment 2 local test results are unchanged; no Azure resources or CI/CD jobs have been created.

Use the `steam_management_presentation_dev_prod` files for this revision. The earlier PDF was open/locked during the update and remains a historical export; the links above point to the updated DEV/PROD pair.
