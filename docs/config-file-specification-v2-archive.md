# `run_vasp.py` Config File Specification

## Overview

Config file is in toml format.

## Psedopotential

VASP psedopotential directory.

```toml
[pseudo_pot]
pbe = "/path/to/PBE/potential/directory/"
lda = "/path/to/PBE/potential/directory/"
```

## Task

Task information. Currently there is only one property `ncore`, gives the number of cores running this calculation.

```toml
[task]
ncore = 112
```

## Calculation

Input directory stores input files.

Result directory stores calculation output files.

```toml
[calculation]
input_dir = "/path/to/input/directory/"
result_dir = "/path/to/result/directory/"
```

## System

An array storing the information of structures to be calculated and calculation steps.

Each element in the array contains the information for a structure and calculation steps.

The `name` of the system is an unique identifier, which is used to name the calculation directory.

```toml
[[system]]
name = "name-of-your-calculation"
```

### Stage

One calculation contains several stages. `stage` is an array containing several stages, or calculation steps. These calculation steps are performed in their order in the array.

```toml
[[system.calculation.stage]]
name = "scf"
require = [
    { file = "structures/Ir_vac_o_c.vasp", dest = "POSCAR" },
]
write_label_incar = [
    { label = "NPAR", value = 8 },
]
incar = "INCAR_scf"
generate_kpoints = [4, 4, 1]

[system.calculation.stage.generate_metagga_kpoints]
ibzkpt = {file = "IBZKPT", stage = "relax"}
kpoints_in = {file = "KPOINTS_metaGGA"}

[system.calculation.stage.pseudo_pot]
type = "lda"
value = [
    "Bi_d_GW",
    "Se_GW",
    "O_GW",
]
```

* `name`: an unique identifier for the stage, used to name the stage directory.
* `require`: an array of files required in this stage. For format of each element please refer to File section.
* `incar`: INCAR file. The file path is relative to `calculation.input_dir`
* `write_label_incar`: extra labels to write into INCAR file. For each label to write, specify the `label` name and `value` to write.
* `generate_kpoints`: generate KPOINTS file by number of kpoints in each direction.
* `generate_metagga_kpoints`: generate KPOINTS file for meta-GGA calculation of the band structure. This property and the above `generate_kpoints` property cannot co-exist. Specify `ibzkpt` and `kpoints_in`  according to the format given in the File section.
* `pseudo_pot`: psedopotential used in this calculation. 'lda' for LDA type psedopotential and 'pbe' for PBE type psedopotential. `value` is the name for the psedopotential.

### File

```toml
file-format-examples = [
    { file = "structures/Ir_vac_o_c.vasp", dest = "POSCAR" },
    { file = "CONTCAR", stage = "relax", dest = "POSCAR" },
    { file = "structures/Ir_vac_o_c.vasp"},
    { file = "CONTCAR", stage = "relax"},
]
```

`file` is the path of the file. If `stage` not exist, file path is relative to `calculation.input_dir`. Else, file path is relative to stage directory. `dest` is the file name of the destination file, if this operation is a copy operation.

