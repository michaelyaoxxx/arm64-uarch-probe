# Results

- `runs/` contains temporary local executions and is ignored by Git.
- `.locks/` and `.recovery/` contain runtime coordination and recovery state.
- `baselines/<version>/` contains reviewed evidence committed for a release.

Do not promote a run by copying every generated file. Select the manifest,
structured results, raw logs needed for traceability, anomalies, and limitations
during review.
