# Partizan visualizer

An interactive, evidence-backed presentation of Partizan's checked
fixed-value crossing. Two KQK positions animate their immediate mating
witnesses while the interface reveals their different literal game trees and
shared combinatorial-game value.

The committed evidence is rebuilt from the native chess adapter and exact
recursive-order verifier:

```bash
PYTHONPATH=../python python3 ../scripts/build_visualizer_evidence.py --check
```

The visualizer is a vinext application packaged for OpenAI Sites.
