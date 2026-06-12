# Legacy Evidence

The versioned `runner/run_pmu*.sh` scripts and tracked `data/**/*.txt` files
are frozen evidence from the pre-v1.0 GB10 investigation.

- Do not modify them for v1.0 features.
- Verify integrity with `python3 scripts/legacy_manifest.py verify`.
- Keep files in their historical paths until a reviewed compatibility migration
  can preserve traceability.
- New runs belong under ignored `results/runs/`; reviewed release evidence
  belongs under `results/baselines/<version>/`.

The canonical manifest's `source_commit` identifies the frozen historical
baseline and must remain an ancestor of the current checkout. Its hashes cover
the preserved files in the current working tree.

Canonical verification proves schema, provenance, exact tracked inventory,
path scope, and file digests. For a review-only mutation check, an external
manifest may be verified explicitly:

```sh
python3 scripts/legacy_manifest.py verify \
  --manifest /absolute/path/to/manifest.json \
  --allow-custom-manifest
```

Custom verification accepts only a non-empty subset of normalized, tracked
legacy paths. It checks their digests but does not certify canonical inventory
completeness or provenance.
