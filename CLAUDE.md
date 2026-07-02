# CLAUDE.md

## Project

VaspAuto — automated VASP/CP2K calculation framework for Slurm HPC clusters.
Declares workflows in TOML configs; handles dependency ordering, parameter
auto-filling, and restart-on-failure.

Targets Python 3.10.

## Package structure

```
vaspauto/
  cli.py, submit.py, run.py       # CLI and Slurm integration
  core/                           # Calculation engine, DAG scheduling, host config
  io/                             # VASP/CP2K input file format parsers
  analysis/                       # Post-processing (energy, NEB interpolation, NEB analysis)
tests/
docs/
```

## Key design decisions

### Calculation objects
- `__init__` has no side effects; `prepare()` does all setup
- DAG attributes (`deps`, `neighbors`, `comp`, `rank`) live on Calculation instances

### Dependency scheduling
- `dag.py`: resolve dependencies → build neighbors → find connected components → topological sort
- `SoftFileLock` per calculation directory allows multiple Slurm jobs to share one config

### Cluster config
- `~/.config/vaspauto/host.toml` — one file per cluster, no hardcoded cluster info in code
- Compute nodes locate it via `$VASPAUTO_HOSTS_FILE` env var

### Config file format (TOML)
- `[global.vars]` supports scalar, list, nested list, and glob patterns
- `{var}` substitution with Cartesian-product loop expansion
- Full spec: `docs/config-file-specification-v5.md`

### Auto parallelization
- `parallel = { type = "ncore" }` per-calculation; auto-sets NCORE, deletes NPAR, sets KPAR=1
- For NEB: NCORE computed per intermediate image

### INCAR parser
- VASP 6 nested tags stored as flat `/`-separated keys; `iter_lines()` reconstructs `{ }` blocks

### Analysis: path interpolation DSL
- `[anchors:method]` with optional brackets controlling endpoint inclusion
- Full spec: `docs/analysis-interp.md`
