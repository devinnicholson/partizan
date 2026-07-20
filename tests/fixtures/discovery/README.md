# Discovery Contract Fixtures

Every JSON and JSONL file in this directory is synthetic and exists only to
exercise Partizan's discovery contracts. These rows are not native Astralbase
outputs, are not experimental observations, and must not be cited or promoted
as research evidence. Commit-shaped values test immutable-provenance fields;
they do not claim that a target-verification adapter existed at those commits.

Native evidence must be produced separately from clean, committed checkouts and
a manifest frozen from the real proposal artifact. The explicit verification
command is:

```sh
python3 engine/orchestrator.py discovery-verify-pool \
  --target "$TARGET_JSON" \
  --proposals "$FROZEN_PROPOSALS_JSONL" \
  --manifest "$FROZEN_POOL_MANIFEST" \
  --output "$NATIVE_RESULTS_JSONL" \
  --astralbase-dir "$ASTRALBASE_REPO" \
  --bitmesh-dir "$BITMESH_REPO" \
  --thermograph-dir "$THERMOGRAPH_REPO"
```

The command refuses dirty repositories or commit mismatches. It also supplies
absolute Cargo patches for the two local dependency checkouts and uses a
temporary `CARGO_TARGET_DIR`. A successful native run, its frozen manifest, and
the resulting lossless `verifier_io` envelopes form the evidence trail; these
fixtures do not.
