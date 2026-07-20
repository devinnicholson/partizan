# Wave 69 target-registry selection report

Status: preregistered target selection, not publication evidence.

The clean reference atlas is checked in as a byte-exact gzip artifact. Its replay
replay attestation is checked in beside it. Selection is accepted only for the
bound atlas and attestation hashes below; a missing selected row is not replaced.

## Source boundary

- Checked-in atlas: `data/discovery/wave_69/reference-atlas.jsonl.gz` (108 rows)
- Compressed atlas SHA-256: `471d40092d508e52fcf14d3e292818304fc7cea649c069c96d648ea8deb5ada1`
- Decompressed atlas SHA-256: `58046bbcbb4644018d4bf31907fcd555220d2bb8e2a5f67607beb6f515883dbf`
- Replay-attestation SHA-256: `bc6de682ffc4fe0f155ef4b130a3edcd3b43595552ed67a664b93621fb5d9a7f`
- Checked-in replay attestation: `data/discovery/wave_69/reference-atlas-replay.json`
- Source-boundary SHA-256: `5fdb47d5cb5a9dfd8a6f2eb11265da60d66ec0c74d032339551e2fb51c692cf7`
- Registry ID: `registry-sha256:e7383432360d848b0fd2996a8d4b3c2bf85ebd1492c6e4fff596f7b3391fb4a5`
- Replay summary: 108 exact rows checked; zero rejected or non-target rows skipped.

Clean commits: astralbase `1434fca1fc04d97798ec1b820c56f52f8014ccc7`, bitmesh `ade3417a007b9c8392d8a153abc4b3ed23edf0aa`, partizan `89c325d52a67bde4d6ac997f4527b7c56a119cf7`, thermograph `1d9b6b01c3921aca8c2a8fb13972fee8a4de5041`.

## Frozen rule

Rows 012 and 090 are excluded. Eligible rows must be exact/verified, carry a
lowercase SHA-256 structural identity, have exactly two components certified by
`bitmesh:conservative_legal_independence:v0`, and belong to one of the three named topology families.
Each family is sorted by recursive
nodes, identity, then row ID; split into six contiguous size-balanced bins; and
the smallest identity in each bin is selected. Bins 0/3 are Stage A, 1/4 are
Stage B, and 2/5 are reserved for Wave 70. Substitution is forbidden.

Every target contract fixes a pool cap of 4096, 4096 verifier calls, and a
100000-node per-candidate budget.

## Selected targets

| Family | Bin | Stage | Row | Nodes | Structural identity | Selection SHA-256 |
|---|---:|---|---:|---:|---|---|
| `dfile_two_component_depth2_asymmetric_fan_v0` | 0 | `stage_a` | 046 | 73 | `2ee555faee667f194ec049d392780afabc3b90d960431f4ad84e5682b2482e0d` | `f041a938f19b9ce5cd2b6c13c0a944ea593ae3d372d92e63046630374ea02f0a` |
| `dfile_two_component_depth2_asymmetric_fan_v0` | 1 | `stage_b` | 085 | 125 | `47c788a5fded022f0a284f69d339d0e62fae6e6cefa3463b3a2bee720bfa1ea2` | `d3602c54964f00352c41976589f3e2c40cc7c1ba840a9f90715a7924e50c80f5` |
| `dfile_two_component_depth2_asymmetric_fan_v0` | 2 | `wave_70` | 040 | 151 | `06b60137f7f2e1924fb235d9df59c09f507df413d329f0332d1e4650ada55b4d` | `a9121e508cf7f7463a4f083028ad253083357253cefc71337dc9544e9573c531` |
| `dfile_two_component_depth2_asymmetric_fan_v0` | 3 | `stage_a` | 067 | 172 | `07500ad23660d03a0c2e87b353a9c0627100c1758b08b3a3bd53455cfe60e634` | `de12993fd6b333deee27788f73ec5e0091d69f8f685c190f6234628c1628e297` |
| `dfile_two_component_depth2_asymmetric_fan_v0` | 4 | `stage_b` | 115 | 227 | `4d1c8d4e642b98bc8c4e3f3f67cb344193b34c2d545728e7296be9e83fdc0055` | `a72cb18cc4994747752dba5a4ed8ae344d0814ed781d74604e60ad17f5eaa550` |
| `dfile_two_component_depth2_asymmetric_fan_v0` | 5 | `wave_70` | 091 | 257 | `0b963c436859e15f647a7824f9fddad1d9cb79bdc3bf64b3b10a1b99970542d6` | `0279ad0f615925a575c0e156c3c4570a748d97fc2b91d72ccffa029c6f14e2b0` |
| `dfile_two_component_depth2_local_move_v0` | 0 | `stage_a` | 048 | 41 | `0cc81ababe672c4f05bef1e6f4a9a3aeaf3d4bd81b5cd93650f649fac54e8b60` | `8f05c6b8344da2a4c54fa4183a358a5d27c6d449358597dc8fe6e861f32ca744` |
| `dfile_two_component_depth2_local_move_v0` | 1 | `stage_b` | 075 | 82 | `7331a9f85ff1440986b0c2ddef95e210d2fc7cc9185c7f5289629d559f45c701` | `9c0c6eb8fde88f8c53c6e2ef3bcdd4fcce76c35e5868cf04952d1f5ca671dc59` |
| `dfile_two_component_depth2_local_move_v0` | 2 | `wave_70` | 027 | 129 | `4cdf4f46373b9e426fc19cca82edb583c5e73c9975a3206fc73c4e6070522e8c` | `83554c2166a0aa35659f9661be1a48e9ec0c41cde8e8b185c32a78455fa6f70f` |
| `dfile_two_component_depth2_local_move_v0` | 3 | `stage_a` | 081 | 155 | `0b6c52116f9feeb0c171bb66f5322ecf77fc0bdba7d163b189a0a9d316b1475e` | `638747900eab33f11af8ecf252e2172ac6aba88722f0129de667266c01a55aaf` |
| `dfile_two_component_depth2_local_move_v0` | 4 | `stage_b` | 087 | 208 | `1b21c1827366d6aa9f81489da58e91802b81b3ea32657638dcba656f484d6d38` | `23ceff04a8324d33627a0838de9102866a327e7040dd430e642ef75cfe03470e` |
| `dfile_two_component_depth2_local_move_v0` | 5 | `wave_70` | 093 | 286 | `050692e59cacc1527b70da89d64db6ee6e46363943d3a20fb86b6c0197a3a18c` | `a8e48c30cf4457d825358d28c21b56d0620d86a99c052343b27234d39e871e5b` |
| `dfile_two_component_depth2_pawn_phalanx_v0` | 0 | `stage_a` | 038 | 48 | `0493350aa35ede04f1957887a6591f4fd836275af202adb182a3d84f2876e0ae` | `986cc3b6ca0b9ddb448e4ada1391851b417fbaccc1b29c6bc7bd9823c4cb3f16` |
| `dfile_two_component_depth2_pawn_phalanx_v0` | 1 | `stage_b` | 056 | 95 | `01cb0d4287bda28ca0c12bdf3845f05a719b037497394ff5a077b8cc0532eee1` | `f5dcd64539d3b7159128dc0ffe5bab26af0f71c785dfc8d24bcf5dc86991ce43` |
| `dfile_two_component_depth2_pawn_phalanx_v0` | 2 | `wave_70` | 083 | 131 | `03198ae2933def119ada670e390b9f0c236d364ebbc7e8d832535fd6809cd166` | `07017c863aeb505796d00302b254147c64b84ce7cef846b5cf37392fd40e82e5` |
| `dfile_two_component_depth2_pawn_phalanx_v0` | 3 | `stage_a` | 113 | 168 | `5e246529ea4c824d983f1bf64403c79e574b64ac09740528aeecfbe50f43c477` | `db790236803b7103364d17ef889b93dce220cbc93c6b2403bb47e7c34fa1a6e6` |
| `dfile_two_component_depth2_pawn_phalanx_v0` | 4 | `stage_b` | 041 | 199 | `13555a21b8a3b9510744ca95285c61117382cc42b7e05ccd12a44e049069aafd` | `cedb23f3a67cad1ad9c9f9d2abd837c7284807a80e4a55e412a5965fc008a94d` |
| `dfile_two_component_depth2_pawn_phalanx_v0` | 5 | `wave_70` | 032 | 251 | `3cf7a7e91db532eabd84419f2b8486e51499d58eec24ef7d352442c3c41ee05e` | `c6ad30180512c4d9a95e3920ac7124104d91da64fcddc89c4ae55acc08cb227b` |

## Replay

```bash
python3 scripts/select_wave69_targets.py \
  --atlas data/discovery/wave_69/reference-atlas.jsonl.gz \
  --check
```

The command verifies the checked-in compressed and decompressed atlas hashes,
plus the checked-in replay-attestation hash, before recomputing both artifacts.
