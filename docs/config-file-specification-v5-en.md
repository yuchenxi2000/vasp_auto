# VaspAuto Config File Specification v5.2

> **Version**: VaspAuto 5.x
>
> [中文版](config-file-specification-v5.md)

---

## Table of Contents

1. [Overview](#overview)
2. [Top-level Fields](#top-level-fields)
3. [`[global]` — Global Settings](#global--global-settings)
4. [`[[calculation]]` — Calculation Tasks](#calculation--calculation-tasks)
5. [Variable Substitution](#variable-substitution)
6. [Preprocess / Postprocess Actions](#preprocess--postprocess-actions)
7. [File Paths](#file-paths)
8. [Dependencies and Scheduling](#dependencies-and-scheduling)
9. [Full Examples](#full-examples)

---

## Overview

The config file uses **TOML** to describe a set of VASP (or CP2K) calculations and
their dependencies. The framework takes care of:

1. **Variable-loop expansion** — one `[[calculation]]` block can expand into many
   tasks through `{var}` substitution and Cartesian-product looping.
2. **Topological ordering** — runs tasks in dependency order.
3. **File-lock parallelism** — multiple Slurm jobs can share one config file safely.
4. **Restart on failure** — completed tasks are skipped; unconverged relaxations
   resume from CONTCAR automatically.

---

## Top-level Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `version` | string | **yes** | Config format version. Current is `"5.2"`. |

```toml
version = '5.2'
```

---

## `[global]` — Global Settings

### root_dir

The calculation root directory. All relative paths (unless a `relative_to` is
explicitly given) are resolved against this directory.

The tilde `~` is expanded to the cluster home directory (read from the host config).

```toml
[global]
root_dir = "~/2026/05-07/my_calculation"
```

### vars — Variable Definitions

Define variables under `[global.vars]`. Supported value types:

- **Scalar** (string or number) — substituted literally.
- **One-dimensional list** — triggers loop expansion when `{var}` appears in `name`.
- **Multi-dimensional nested lists** — accessed with `{var:a,b}` syntax.
- **Glob pattern** (v5.2+) — matches files in a directory and expands to a list of paths.

```toml
[global.vars]
# scalar
ncore = 112

# 1-D list — {label} in name triggers expansion
label = ["HfO2", "LaHfO", "TiO2"]

# nested list — {magmom:vo_type,axis} indexes into it
magmom = [
    ["0.0 1.0 -1.0", "0.0 -1.0 1.0"],
    ["0.0 1.0 1.0",  "0.0 -1.0 -1.0"],
]

# glob pattern — auto-discover files
label = { glob = "**/*.vasp", dir = "structures", strip_ext = true }
```

### Glob Variables (v5.2+)

When a variable value is a dict with a `glob` key, the framework scans the given
directory and expands it to a sorted list of matching paths.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `glob` | string | *(required)* | fnmatch pattern; `**` for recursive matching |
| `dir` | string | `"."` | Search directory, relative to `root_dir`. Results are also relative to this directory. |
| `strip_ext` | bool | `false` | Whether to strip the file extension. Default keeps it — be explicit if you need the extension removed. |

```toml
# match *.vasp in structures/ (one level), keep extension
label = { glob = "*.vasp", dir = "structures" }
# → ["HfO2.vasp", "LaHfO.vasp"]

# recursive match, strip extension
label = { glob = "**/*.vasp", dir = "structures", strip_ext = true }
# → ["HfO2", "subdir/LaHfO"]

# no explicit dir — paths relative to root_dir
label = { glob = "structures/*/*.vasp" }
# → ["structures/a/HfO2.vasp", "structures/b/LaHfO.vasp"]
```

---

## `[[calculation]]` — Calculation Tasks

Each `[[calculation]]` block defines one (or a family of) calculation tasks.
The framework first expands variable loops, then orders tasks by dependency.

### Field Summary

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `name` | string | **yes** | — | Unique task name. May contain `{var}` placeholders. |
| `calc_dir` | string | **yes** | — | Working directory, relative to `root_dir`. Created automatically. |
| `dependence` | array | no | `[]` | Names of tasks that must finish before this one starts. |
| `executable` | string | no | `"vasp_std"` | Executable name. Starts with `vasp` → VASP mode; starts with `cp2k` → CP2K mode. |
| `preprocess` | array | no | `[]` | Actions to run before the calculation (in order). |
| `postprocess` | array | no | `[]` | Actions to run after the calculation. |
| `parallel` | table | no | `{type = "ncore"}` | Auto parallel tuning (v5.4+). `type = "ncore"` auto-sets NCORE. `type = "off"` for manual. |

### name — Naming and Variable Expansion

The `name` serves as a unique identifier and is used for dependency matching.
`{var}` placeholders are substituted with variable values.

**Loop expansion**: all 1-D list variables appearing in `name` as `{var}` are
expanded as a Cartesian product.

```toml
[global.vars]
label = ["a", "b"]
spin = ["up", "dn"]

[[calculation]]
name = "{label}/{spin}/scf"
calc_dir = "result/{label}/{spin}/scf"
# → a/up/scf, a/dn/scf, b/up/scf, b/dn/scf
```

If a 1-D list variable appears only in `preprocess` values but not in `name`,
use `{var:other_var}` to specify which loop variable provides the index.

### dependence — Declaring Dependencies

An array of task names (after expansion) that must complete first.
Dependencies form a DAG; the scheduler topologically sorts within each connected
component and runs independent components in parallel.

```toml
[[calculation]]
name = "{label}/relax"
calc_dir = "result/{label}/relax"

[[calculation]]
name = "{label}/scf"
calc_dir = "result/{label}/scf"
dependence = ["{label}/relax"]
```

---

## Variable Substitution

The `{...}` syntax is applied recursively through the entire `calculation` object
(strings, list elements, and dict values are all substituted).

### Basic substitution: `{var}`

- Scalar → literal replacement.
- 1-D list appearing in `name` → triggers loop expansion; replaced with the current element.
- 1-D list not in `name` → **error**. Use `{var:other}` instead.

### Indexed substitution: `{var1:var2}`

`var1` must be a 1-D list. Takes the *i*-th element, where *i* is the current
loop index of `var2`.

```toml
nupdown = ["0", "2"]
magmom  = ["...spin0...", "...spin2..."]   # same length

name = "scf/{nupdown}"
preprocess = [
    {func = "set_label_incar", label = "MAGMOM", value = "{magmom:nupdown}"},
]
```

### Multi-dimensional indexing (v5.1+): `{var1:var2,var3,...}`

`var1` is a nested list; indexes drill down by the current loop indices of
`var2, var3, ...`. Integer constants are also allowed.

```toml
axis    = ["a", "b", "c"]
vo_type = ["3", "4"]
magmom  = [          # shape: [vo_type][axis]
    ["...a_vo3...", "...b_vo3...", "...c_vo3..."],
    ["...a_vo4...", "...b_vo4...", "...c_vo4..."],
]

name = "{axis}_{vo_type}/scf"
preprocess = [
    {func = "set_label_incar", label = "MAGMOM", value = "{magmom:vo_type,axis}"},
]
# vo_type="3", axis="a" → magmom[0][0]
# vo_type="4", axis="c" → magmom[1][2]
```

Integer index: `{magmom:0,2}` — `magmom[0][2]`, independent of loop variables.

### Escaping braces

Use backslash: `\{`, `\}`.

### Substitution scope

All string fields in `name`, `calc_dir`, `dependence`, `preprocess`, and
`postprocess` are substituted. TOML integers and floats are left untouched.

---

## Preprocess / Postprocess Actions

`preprocess` and `postprocess` are ordered arrays of actions. Each action is
specified with either `cmd` or `func`.

### Shell commands

```toml
{cmd = "echo hello"}
{cmd = "cp file1 file2"}
```

Executed via `subprocess.call(cmd, shell=True)`.

### Built-in functions

#### copy

```toml
{func = "copy", src = {file = "structures/POSCAR_template"}, dest = "POSCAR"}
```

- `src` — source file (see [File Paths](#file-paths)).
- `dest` — destination, defaults to relative-to-`calc_dir`.

#### move

```toml
{func = "move", src = {file = "old_file"}, dest = "new_file"}
```

Same as `copy` but moves instead.

#### print

```toml
{func = "print", str = "Starting calculation {label}..."}
```

Prints to stdout. Supports variable substitution.

---

### VASP-specific functions

These only apply when `executable` starts with `vasp` (or when `executable` is
not set, which defaults to `vasp_std`).

#### write_potcar

```toml
# explicit potential list
{func = "write_potcar", type = "pbe", value = ["Bi_d_GW", "Se_GW", "O_GW"]}

# auto-detect from POSCAR
{func = "write_potcar", type = "pbe"}
```

Writes POTCAR to `calc_dir/POTCAR`.

- `type` — `"pbe"` or `"lda"`.
- `value` — optional list of potential names. If omitted, the recommended
  potentials are inferred from the POSCAR element line.
- `pot_map` — optional mapping from element to potential name; overrides the
  VASP-recommended default when auto-detecting.

#### set_label_incar

```toml
{func = "set_label_incar", label = "KPAR", value = 1}
{func = "set_label_incar", label = "KERNEL_TRUNCATION/LTRUNCATE", value = "T"}
```

Sets an INCAR tag in memory. Tags are written to file after all
`set_label_incar` / `del_label_incar` actions have been applied.

VASP 6 nested tags are supported with `/` as a path separator (e.g.
`KERNEL_TRUNCATION/LTRUNCATE`). The parser stores them as flat keys and
reconstructs the `{ }` block structure when writing.

#### del_label_incar

```toml
{func = "del_label_incar", label = "NPAR"}
```

Deletes a tag.

#### new_blank_incar

```toml
{func = "new_blank_incar"}
```

Starts with an empty INCAR instead of reading from a file. Useful when all
tags are set via `set_label_incar`.

#### generate_kpoints

```toml
{func = "generate_kpoints", kp = [4, 4, 1]}
```

Writes a Gamma-centered automatic k-point mesh to `calc_dir/KPOINTS`.

---

### CP2K-specific functions

Only apply when `executable` starts with `cp2k`.

#### cp2k_input

```toml
{func = "cp2k_input", value = {file = "templates/cp2k.inp"}}
```

Loads a CP2K input file.

#### cp2k_input_update

```toml
{func = "cp2k_input_update", value = {MOTION: {MD: {STEPS: 1000}}}}
{func = "cp2k_input_update", path = "FORCE_EVAL/DFT", value = {UKS: "T"}}
```

Updates sections of the loaded CP2K input.

- `value` — nested dict representing the CP2K section to merge.
- `path` — optional subsection path (slash-separated).

---

## File Paths

A file can be given as a **string** or a **dict**.

### String form

```toml
{func = "copy", src = "structures/POSCAR_template", dest = "POSCAR"}
```

Relative to `root_dir` by default.

### Dict form

```toml
{func = "copy", src = {file = "CONTCAR", relative_to = "calc_dir"}, dest = "POSCAR"}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `file` | string | **yes** | File path |
| `relative_to` | string | no | Base for relative paths: `"root_dir"` (default) or `"calc_dir"` |

Absolute paths (starting with `/` or `~`) ignore `relative_to`.

The `dest` field is always relative to `calc_dir` unless absolute.

---

## Dependencies and Scheduling

### Building the dependency graph

1. All `[[calculation]]` blocks are expanded (variable loop expansion).
2. `dependence` entries are resolved to their expanded task indices.
3. The graph is checked for cycles (an error is raised if any exist).

### Grouping and ordering

1. Connected components of the dependency graph are found.
2. Within each component tasks are topologically sorted (rank = longest
   dependency chain).
3. Tasks execute in ascending rank order within their component.

### File-lock parallelism

- Each task has a `.lock` file in its `calc_dir`.
- Before running, the scheduler acquires a non-blocking `SoftFileLock`.
  If acquisition fails another process is working on the task, and the
  **entire connected component** is skipped.
- This allows multiple Slurm jobs to share one config file safely.

### Status checking and restart

After acquiring the lock, the framework checks each task's status:

| Status | Action |
|--------|--------|
| `NOT_CALCULATED` | Run normally. |
| `FINISHED` | Skip (already done). |
| `NEEDS_RERUN` | Re-run (VASP restarts from scratch; CP2K resumes from the last step). |
| `UNCONVERGED` | Copy CONTCAR → POSCAR and continue (VASP ionic relaxation only). |

If a dependency has not finished, the dependent task is skipped and marked
`NOT_CALCULATED`.

---

## Full Examples

### Basic: relaxation + SCF

```toml
version = '5.2'

[global]
root_dir = "~/2026/05-07/my_project"
[global.vars]
labels = ["HfO2", "LaHfO", "TiO2"]

[[calculation]]
name = "{labels}/relax"
calc_dir = "result/{labels}/relax"
preprocess = [
    {func = "copy", src = {file = "structures/{labels}.vasp"}, dest = "POSCAR"},
    {func = "copy", src = {file = "INCAR_relax"}, dest = "INCAR"},
    {func = "set_label_incar", label = "KPAR", value = 1},
    {func = "set_label_incar", label = "NPAR", value = 8},
    {func = "set_label_incar", label = "ISIF", value = 2},
    {func = "write_potcar", type = "pbe"},
]

[[calculation]]
name = "{labels}/scf"
calc_dir = "result/{labels}/scf"
dependence = ["{labels}/relax"]
preprocess = [
    {func = "copy", src = {file = "result/{labels}/relax/CONTCAR"}, dest = "POSCAR"},
    {func = "copy", src = {file = "INCAR_scf"}, dest = "INCAR"},
    {func = "set_label_incar", label = "KPAR", value = 1},
    {func = "set_label_incar", label = "NPAR", value = 8},
    {func = "write_potcar", type = "pbe"},
]
```

This produces 3 × 2 = 6 tasks: `HfO2/relax` → `HfO2/scf`, `LaHfO/relax` →
`LaHfO/scf`, `TiO2/relax` → `TiO2/scf`. Each relax → SCF chain runs
sequentially within its component; the three components can run in parallel.

### Advanced: multi-dimensional variables + magnetism

```toml
version = '5.2'

[global]
root_dir = "~/2026/04-09/LaHfO-VO-spin"
[global.vars]
axis    = ["a", "b", "c"]
vo_type = ["3", "4"]
nupdown = ["0", "2"]
magmom  = [
    [  # vo_type=3
        ["...mag_a_nupdown0...", "...mag_a_nupdown2..."],
        ["...mag_b_nupdown0...", "...mag_b_nupdown2..."],
        ["...mag_c_nupdown0...", "...mag_c_nupdown2..."],
    ],
    [  # vo_type=4
        ["...mag_a_nupdown0...", "...mag_a_nupdown2..."],
        ["...mag_b_nupdown0...", "...mag_b_nupdown2..."],
        ["...mag_c_nupdown0...", "...mag_c_nupdown2..."],
    ],
]

[[calculation]]
name = "{axis}_{vo_type}/relax"
calc_dir = "result/{axis}_{vo_type}/relax"
preprocess = [
    {func = "copy", src = {file = "structures/m-2La-2VO-{axis}-{vo_type}.vasp"}, dest = "POSCAR"},
    {func = "copy", src = {file = "INCAR_relax"}, dest = "INCAR"},
    {func = "set_label_incar", label = "ISPIN", value = 1},
    {func = "write_potcar", type = "pbe"},
]

[[calculation]]
name = "{axis}_{vo_type}/scf/{nupdown}"
calc_dir = "result/{axis}_{vo_type}/scf/{nupdown}"
dependence = ["{axis}_{vo_type}/relax"]
preprocess = [
    {func = "copy", src = {file = "result/{axis}_{vo_type}/relax/CONTCAR"}, dest = "POSCAR"},
    {func = "copy", src = {file = "INCAR_scf"}, dest = "INCAR"},
    {func = "set_label_incar", label = "ISPIN", value = 2},
    {func = "set_label_incar", label = "NUPDOWN", value = "{nupdown}"},
    {func = "set_label_incar", label = "MAGMOM", value = "{magmom:vo_type,axis,nupdown}"},
    {func = "write_potcar", type = "pbe"},
]
```

Expansion: 3 axes × 2 VO types = 6 relax tasks; each relax spawns 2 SCF tasks
(nupdown), giving 18 tasks total.
