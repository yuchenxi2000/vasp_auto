# VaspAuto

A framework for automating VASP and CP2K calculations on HPC clusters (Slurm).
Submit once, run many tasks — the framework handles dependency ordering, parameter
filling, and restart-on-failure so you don't have to.

> [中文版本](README.md)

## Features

- **TOML-based configuration** — declare your entire workflow (relax → SCF → DOS) in a
  single file, with variable expansion and glob patterns to sweep over dozens of structures.
- **Automatic dependency ordering** — topological sort ensures relax runs before SCF, SCF
  before DOS, and so on.
- **Concurrent job-safe** — file locks allow multiple Slurm jobs to share one config file;
  each picks up the next available task.
- **Crash recovery** — finished tasks are automatically skipped; unconverged ionic
  relaxations restart from CONTCAR.
- **Dynamic INCAR editing** — set or delete INCAR tags at runtime via the config file,
  including VASP 6 nested tags such as `KERNEL_TRUNCATION { LTRUNCATE = T }`.
- **Cluster-agnostic** — cluster details live in a single `host.toml` config file;
  no hardcoded paths or module commands in the codebase.

## Quick Start

### 1. Install

```bash
pip install -e .          # editable install (recommended for development)
# or
pip install .             # regular install
```

Requirements: Python ≥ 3.10, `filelock`, `tomli` (only needed on Python < 3.11).

### 2. Configure your cluster

```bash
mkdir -p ~/.config/vaspauto
cp host.example.toml ~/.config/vaspauto/host.toml
# edit host.toml — set core counts, partition names, module commands, etc.
```

### 3. Write a calculation config

```toml
# my_calc.toml
version = '5.2'

[global]
root_dir = "~/my_project"
[global.vars]
label = { glob = "*.vasp", dir = "structures", strip_ext = true }

[[calculation]]
name = "{label}/relax"
calc_dir = "result/{label}/relax"
preprocess = [
    {func = "copy", src = {file = "structures/{label}.vasp"}, dest = "POSCAR"},
    {func = "copy", src = {file = "INCAR_relax"}, dest = "INCAR"},
    {func = "set_label_incar", label = "KPAR", value = 1},
    {func = "write_potcar", type = "pbe"},
]

[[calculation]]
name = "{label}/scf"
calc_dir = "result/{label}/scf"
dependence = ["{label}/relax"]
preprocess = [
    {func = "copy", src = {file = "result/{label}/relax/CONTCAR"}, dest = "POSCAR"},
    {func = "copy", src = {file = "INCAR_scf"}, dest = "INCAR"},
    {func = "write_potcar", type = "pbe"},
]
```

### 4. Submit or run

```bash
# generate a Slurm script and submit
vaspauto submit -c my_calc.toml -N 2 -n 112 -J my_job -s

# only generate the script (don't submit)
vaspauto submit -c my_calc.toml -N 2 -n 112 -o run.sh

# dry-run: see what tasks will be created
vaspauto run -c my_calc.toml --print-groups -n 1
```

## Usage

| Method | Command | When to use |
|--------|---------|-------------|
| Installed entry point | `vaspauto submit ...` / `vaspauto run ...` | After `pip install` |
| `-m` invocation | `python3 -m vaspauto submit ...` | Without install; PYTHONPATH must include the project root |
| Direct module call | `python3 -m vaspauto.task_scheduler ...` | Inside generated Slurm scripts (PYTHONPATH is set automatically) |

## CLI Reference

### `vaspauto submit` — Generate / submit a Slurm job script

| Option | Description |
|--------|-------------|
| `-c, --config` | Calculation config file (TOML) |
| `-d, --dir` | Calculation root directory |
| `-N, --nodes` | Number of nodes (required) |
| `-n` | Total MPI tasks |
| `--nt` | Tasks per node |
| `--nc` | CPUs per task (OpenMP threads) |
| `-J, --job-name` | Job name |
| `-p, --partition` | Slurm partition |
| `-t, --task` | Task type: `vasp+py` (default), `vasp`, `cp2k+py`, `cp2k` |
| `-s, --submit` | Submit immediately instead of writing a script |
| `-o, --output` | Path for the generated script |

`-n`, `--nt`, and `--nc` can be omitted — the framework derives them automatically.
See [resource allocation docs](docs/resource-allocation-logic.md) for the derivation logic.

### `vaspauto run` — Execute calculations (called inside a Slurm job)

| Option | Description |
|--------|-------------|
| `-c, --config` | Calculation config file |
| `-d, --dir` | Calculation root directory |
| `-n` | Total MPI tasks (required) |
| `--nc` | CPUs per task |
| `--print-num-groups` | Print number of independent task groups, then exit |
| `--print-groups` | Print task group details, then exit |
| `--rm-locks` | Remove all lock files (use after cancelling a job) |
| `--write-expanded-config` | Export the expanded config (debug; requires `tomli_w`) |

## Documentation

| Document | Language |
|----------|----------|
| [Config file format (v5.x)](docs/config-file-specification-v5-en.md) | English |
| [Config file format (v5.x)](docs/config-file-specification-v5.md) | 中文 |
| [Config file format (v2.0, deprecated)](docs/config-file-specification-v2-archive.md) | 中文 |
| [Resource derivation logic](docs/resource-allocation-logic.md) | 中文 |

## License

MIT License
