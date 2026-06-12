# Legacy Evidence

The versioned `runner/run_pmu*.sh` scripts and tracked `data/**/*.txt` files
are frozen evidence from the pre-v1.0 GB10 investigation.

- Do not modify them for v1.0 features.
- Verify integrity with `python3 scripts/legacy_manifest.py verify`.
- Keep files in their historical paths until a reviewed compatibility migration
  can preserve traceability.
- New runs belong under ignored `results/runs/`; reviewed release evidence
  belongs under `results/baselines/<version>/`.
