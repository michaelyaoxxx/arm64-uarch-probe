# Legacy Evidence

The versioned `runner/run_pmu*.sh` scripts and tracked `data/**/*.txt` files
are frozen evidence from the pre-v1.0 GB10 investigation.

- Do not modify them for v1.0 features.
- Verify integrity with `python3 scripts/legacy_manifest.py verify`.
- Keep files in their historical paths until a reviewed compatibility migration
  can preserve traceability.
- New runs belong under ignored `results/runs/`; reviewed release evidence
  belongs under `results/baselines/<version>/`.

The canonical manifest's `source_commit` is the immutable full commit OID for
the frozen historical baseline and must remain an ancestor of the current
checkout. Every listed digest must match both a regular-file blob in that
commit's Git tree and the corresponding regular file in the current working
tree. Symlinks, non-regular entries, and repository path escapes are rejected.

Canonical verification proves schema, provenance, exact tracked inventory,
normalized repo-relative path scope, and file digests. It is the repository
integrity contract.

A caller-supplied external manifest is instead an ad hoc digest-check input. It
may reference absolute paths and does not certify repository inventory or
provenance:

```sh
python3 scripts/legacy_manifest.py verify \
  --manifest /absolute/path/to/manifest.json
```

External verification still validates the manifest schema and checks every
listed file digest.

`write` resolves the requested source commit to its full OID and refuses to
generate a manifest unless the current frozen inventory and bytes match that
commit tree.
