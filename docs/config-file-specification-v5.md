# VaspAuto Config File Specification v5.2

> **适用版本**: VaspAuto 5.x
>
> **旧版存档**: `config-file-specification-v2-archive.md`（v2.0 格式，已废弃）

---

## 目录

1. [概述](#概述)
2. [顶层字段](#顶层字段)
3. [`[global]` — 全局配置](#global--全局配置)
4. [`[[calculation]]` — 计算任务](#calculation--计算任务)
5. [变量替换语法](#变量替换语法)
6. [预处理/后处理动作](#预处理后处理动作)
7. [文件路径写法](#文件路径写法)
8. [依赖关系与调度](#依赖关系与调度)
9. [完整示例](#完整示例)
10. [命令行用法](#命令行用法)
11. [版本历史](#版本历史)

---

## 概述

配置文件为 **TOML** 格式，描述一组 VASP（或 CP2K）计算任务及其依赖关系。框架会自动：

1. **展开变量循环** — 一个 `[[calculation]]` 条目可通过 `{var}` 语法自动展开为多个独立计算
2. **拓扑排序** — 按依赖关系确定执行顺序
3. **文件锁并行** — 同一配置文件可同时提交多个 Slurm 任务，文件锁保证不会重复跑同一个子任务
4. **断点续跑** — 已完成的任务自动跳过；未收敛的任务自动从 CONTCAR 续跑

---

## 顶层字段

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `version` | string | **是** | 配置格式版本号。当前为 `"5.2"`。 |

```toml
version = '5.2'
```

---

## `[global]` — 全局配置

### root_dir

计算根目录。所有相对路径（除非另外指定 `relative_to`）都相对于此目录。

支持 `~` 表示用户 home 目录（由 `host_info.py` 根据超算节点自动确定）。

```toml
[global]
root_dir = "~/2026/05-07/my_calculation"
```

### vars — 变量定义

`[global.vars]` 下定义所有变量。变量值可以是：

- **标量**（字符串或数字）：直接替换
- **一维列表**：当变量以 `{var}` 形式出现在 `name` 字段中时，会展开为循环，每个元素生成一个独立计算
- **多维嵌套列表**：通过 `{var:a,b}` 语法按索引访问
- **glob 模式** (v5.2+)：自动匹配目录下的文件，展开为文件路径列表

```toml
[global.vars]
# 标量 — 直接替换
ncore = 112

# 一维列表 — name 中出现 {label} 时展开循环
label = ["HfO2", "LaHfO", "TiO2"]

# 多维列表 — 通过 {magmom:vo_type,axis} 语法访问
magmom = [
    ["0.0 1.0 -1.0", "0.0 -1.0 1.0"],   # vo_type=3 的两种磁矩
    ["0.0 1.0 1.0",  "0.0 -1.0 -1.0"],   # vo_type=4 的两种磁矩
]

# glob 模式 — 自动匹配文件
label = { glob = "**/*.vasp", dir = "structures", strip_ext = true }
```

### glob 变量 (v5.2+)

当变量值为包含 `glob` 键的字典时，自动匹配指定目录下的文件并展开为列表。字段：

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `glob` | string | **必填** | fnmatch 模式，支持 `**` 递归匹配 |
| `dir` | string | `"."` | 搜索目录，相对于 `root_dir`。结果路径也相对于此目录 |
| `strip_ext` | bool | `false` | 是否去掉扩展名。默认不去——优先保证路径正确性 |

结果按字母排序，保证确定性。

```toml
# 匹配 structures/ 下所有 .vasp 文件（不含子目录），保留扩展名
label = { glob = "*.vasp", dir = "structures" }
# → ["HfO2.vasp", "LaHfO.vasp"]

# 递归匹配，去掉扩展名
label = { glob = "**/*.vasp", dir = "structures", strip_ext = true }
# → ["HfO2", "subdir/LaHfO"]

# 不指定 dir，路径相对于 root_dir
label = { glob = "structures/*/*.vasp" }
# → ["structures/a/HfO2.vasp", "structures/b/LaHfO.vasp"]
```

---

## `[[calculation]]` — 计算任务

每个 `[[calculation]]` 定义一个（或一组）计算任务。框架先展开变量循环，生成具体的任务列表，再按依赖关系排序。

### 字段一览

| 字段 | 类型 | 必需 | 默认值 | 说明 |
|------|------|------|--------|------|
| `name` | string | **是** | — | 任务名称（唯一标识）。可含 `{var}` 替换。 |
| `calc_dir` | string | **是** | — | 计算工作目录，相对于 `root_dir`。 |
| `dependence` | array | 否 | `[]` | 依赖的任务名列表，必须全部完成后本任务才开始。 |
| `executable` | string | 否 | `"vasp_std"` | 可执行文件。以 `vasp` 开头→VASP 模式，以 `cp2k` 开头→CP2K 模式。 |
| `preprocess` | array | 否 | `[]` | 预处理动作列表，在计算前按顺序执行。 |
| `postprocess` | array | 否 | `[]` | 后处理动作列表，在计算完成后按顺序执行。 |

### name — 命名与变量展开

`name` 是任务的唯一标识符，也用于依赖匹配。其中 `{var}` 会被替换为变量的实际值。

**循环展开规则**：`name` 中所有以 `{var}` 形式出现的一维列表变量会做笛卡尔积展开。

```toml
[global.vars]
label = ["a", "b"]
spin = ["up", "dn"]

[[calculation]]
name = "{label}/{spin}/scf"      # 展开为 2×2=4 个任务:
calc_dir = "result/{label}/{spin}/scf"
# → a/up/scf, a/dn/scf, b/up/scf, b/dn/scf
```

**不展开的情况**：如果变量仅在 `preprocess` 的 value 中使用但不在 `name` 中以 `{var}` 形式出现，需要借助 `{var:other_var}` 语法指定索引来源。

### calc_dir — 计算目录

任务的工作目录，相对于 `root_dir`。框架会自动创建该目录。同样支持 `{var}` 替换。

### dependence — 依赖声明

字符串数组，每项是一个已完成任务的 `name`（展开后的值）。依赖关系形成有向无环图 (DAG)，调度器按拓扑序执行。

```toml
[[calculation]]
name = "{label}/relax"
calc_dir = "result/{label}/relax"

[[calculation]]
name = "{label}/scf"
calc_dir = "result/{label}/scf"
dependence = ["{label}/relax"]     # scf 必须在 relax 之后运行
```

### executable — 计算类型

| 值 | 模式 | 说明 |
|----|------|------|
| `"vasp_std"`（默认） | VASP | 标准 VASP 计算，自动检查收敛状态 |
| `"vasp_gam"` 等 | VASP | 其他 VASP 可执行文件 |
| `"cp2k.psmp"` 等 | CP2K | CP2K 计算，自动检测断点续跑 |

---

## 变量替换语法

变量替换使用 `{...}` 语法，在整个 `calculation` 对象中深度递归替换（字符串、列表元素、字典 value 均会替换）。

### 基本替换

```
{var}
```

- `var` 为标量 → 直接替换为标量值
- `var` 为一维列表且在 `name` 中 → 触发循环展开，替换为当前元素值
- `var` 为一维列表但不在 `name` 中 → **报错**，需要改用 `{var:other}` 语法

### 索引替换

```
{var1:var2}
```

`var1` 必须是一维列表，取其第 _i_ 个元素，其中 _i_ 是 `var2` 在当前循环中的索引。

```toml
[global.vars]
nupdown = ["0", "2"]
magmom  = ["0.0 1.0 -1.0 ...", "0.0 -1.0 1.0 ..."]   # 长度与 nupdown 一致

[[calculation]]
name = "scf/{nupdown}"                   # nupdown 触发循环
preprocess = [
    {func = "set_label_incar", label = "MAGMOM", value = "{magmom:nupdown}"},
    # 当 nupdown="0" 时取 magmom[0]，当 nupdown="2" 时取 magmom[1]
]
```

### 多维数组索引 (v5.1+)

```
{var1:var2,var3,...}
```

`var1` 是多维列表，按 `var2, var3, ...` 的当前循环索引逐层取值。索引也可以是整数常量。

```toml
[global.vars]
axis    = ["a", "b", "c"]
vo_type = ["3", "4"]
# magmom[vo_type][axis]  形状为 2×3
magmom  = [
    ["...axis_a_vo3...", "...axis_b_vo3...", "...axis_c_vo3..."],
    ["...axis_a_vo4...", "...axis_b_vo4...", "...axis_c_vo4..."],
]

[[calculation]]
name = "{axis}_{vo_type}/scf"
preprocess = [
    {func = "set_label_incar", label = "MAGMOM", value = "{magmom:vo_type,axis}"},
    # vo_type="3", axis="a" → magmom[0][0]
    # vo_type="4", axis="c" → magmom[1][2]
]
```

整数常量索引也支持：

```toml
{magmom:0,2}   # magmom[0][2]，与循环变量无关
```

### 花括号转义

如果变量值本身需要包含花括号，用反斜杠转义：`\{`、`\}`。

### 替换作用域

替换递归作用于 `name`、`calc_dir`、`dependence`、`preprocess` 中所有字符串字段。TOML 的整数、浮点数不会被替换。

---

## 预处理/后处理动作

`preprocess` 和 `postprocess` 是动作数组，按顺序执行。每个动作用 `cmd` 或 `func` 指定：

### Shell 命令

```toml
{cmd = "echo hello"}
{cmd = "cp file1 file2"}
```

直接调用 shell 执行（`subprocess.call(cmd, shell=True)`）。

### 内置函数

#### copy — 复制文件

```toml
{func = "copy", src = {file = "structures/POSCAR_template"}, dest = "POSCAR"}
```

- `src`: 源文件（文件路径写法见下节）
- `dest`: 目标文件，默认相对 `calc_dir`

#### move — 移动文件

```toml
{func = "move", src = {file = "old_file"}, dest = "new_file"}
```

参数同 `copy`。

#### print — 打印信息

```toml
{func = "print", str = "Starting calculation {label}..."}
```

在 stdout 输出字符串，支持变量替换。

---

### VASP 专用函数

以下函数仅在 VASP 模式（`executable` 以 `vasp` 开头，或无 `executable` 字段）下有效。

#### write_potcar — 生成 POTCAR

```toml
# 手动指定赝势
{func = "write_potcar", type = "pbe", value = ["Bi_d_GW", "Se_GW", "O_GW"]}

# 自动从 POSCAR 推断推荐赝势
{func = "write_potcar", type = "pbe"}
```

- `type`: `"pbe"` 或 `"lda"`
- `value`: 可选，赝势名称列表。省略时从 POSCAR 的元素行自动推断（使用 VASP wiki 推荐的赝势映射）
- `pot_map`: 可选，元素到赝势的映射表。只在自动推断时生效，如果元素在这个表里会优先使用该表设置的赝势而不是VASP推荐赝势。

POTCAR 会被写入 `calc_dir/POTCAR`。

#### set_label_incar — 设置 INCAR 标签

```toml
{func = "set_label_incar", label = "KPAR", value = 1}
{func = "set_label_incar", label = "ISPIN", value = 2}
{func = "set_label_incar", label = "MAGMOM", value = "{magmom:vo_type,axis}"}
```

- `label`: INCAR 标签名（大小写敏感）
- `value`: 标签值，支持变量替换。类型为字符串或数字。

INCAR 文件来自 `calc_dir/INCAR`（通常由 `copy` 或 `cp2k_input` 等前置动作放入）。设置操作在内存中修改 INCAR 对象，所有 `set_label_incar` / `del_label_incar` 执行完后一次性写入文件。

#### del_label_incar — 删除 INCAR 标签

```toml
{func = "del_label_incar", label = "NPAR"}
```

#### new_blank_incar — 创建空白 INCAR

```toml
{func = "new_blank_incar"}
```

初始化一个空的 INCAR 对象（替代从文件读取），后续用 `set_label_incar` 添加所有标签。

#### generate_kpoints — 生成 KPOINTS

```toml
{func = "generate_kpoints", kp = [4, 4, 1]}
```

生成自动 K 点网格（Gamma-centered），写入 `calc_dir/KPOINTS`。

---

### CP2K 专用函数

仅在 `executable` 以 `cp2k` 开头时有效。

#### cp2k_input — 加载输入文件

```toml
{func = "cp2k_input", value = {file = "templates/cp2k.inp"}}
```

#### cp2k_input_update — 更新输入参数

```toml
{func = "cp2k_input_update", value = {MOTION: {MD: {STEPS: 1000}}}}
{func = "cp2k_input_update", path = "FORCE_EVAL/DFT", value = {UKS: "T"}}
```

- `value`: 以嵌套 dict 形式给出的 CP2K section 更新内容
- `path`: 可选，指定更新的子 section 路径（以 `/` 分隔）

---

## 文件路径写法

文件信息可以是**字符串**或**字典**两种形式：

### 字符串形式

```toml
{func = "copy", src = "structures/POSCAR_template", dest = "POSCAR"}
```

默认相对于 `root_dir`。

### 字典形式

```toml
{func = "copy", src = {file = "CONTCAR", relative_to = "calc_dir"}, dest = "POSCAR"}
```

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `file` | string | **是** | 文件路径 |
| `relative_to` | string | 否 | 相对基准：`"root_dir"`（默认）或 `"calc_dir"` |

绝对路径（以 `/` 或 `~` 开头）不受 `relative_to` 影响。

### dest 的特殊规则

`dest` 字段总是相对于 `calc_dir`（除非是绝对路径）。

---

## 依赖关系与调度

### 依赖图构建

1. 框架遍历所有 `[[calculation]]` 条目，展开变量循环，生成具体的任务列表
2. 解析每个任务的 `dependence` 字段，将任务名（展开后）匹配到对应的任务索引
3. 构建有向图，检查是否存在循环依赖（有环则报错）

### 分组与排序

1. 找出图中的所有连通分量（connected components）
2. 每个连通分量内部执行**拓扑排序**（rank = 最长依赖链长度）
3. 同一连通分量内按 rank 升序执行

### 文件锁并行

- 每个任务的 `calc_dir` 下有一个 `.lock` 文件
- 任务执行前获取 `SoftFileLock`（非阻塞），获取失败表示其他进程正在跑该任务，**跳过整个连通分量**
- 这样同一个配置文件可以向超算提交多个 Slurm 任务，各自认领未跑的子任务

### 状态检查与续跑

在获取锁之后，框架检查任务状态：

| 状态 | 处理 |
|------|------|
| `NOT_CALCULATED` | 正常执行 |
| `FINISHED` | 跳过（打印 skip 信息） |
| `NEEDS_RERUN` | 重新执行（VASP: 直接重跑；CP2K: 从断点续跑） |
| `UNCONVERGED` | 将 CONTCAR 复制为 POSCAR 后继续跑（仅 VASP 离子弛豫） |

### 依赖未完成处理

运行时如果某个任务的依赖未完成（状态不是 `FINISHED`），该任务被跳过并标记为 `NOT_CALCULATED`。

---

## 完整示例

### 基本示例：弛豫 + 自洽计算

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

展开后生成 3×2=6 个任务：`HfO2/relax` → `HfO2/scf`, `LaHfO/relax` → `LaHfO/scf`, `TiO2/relax` → `TiO2/scf`。每对 `relax`/`scf` 在同一连通分量内串行执行，三个分量之间可并行。

### 高级示例：多维变量 + 磁性计算

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

展开：`axis`(3) × `vo_type`(2) = 6 个 relax 任务；每个 relax 对应 `nupdown`(2) = 2 个 scf 任务，共 18 个任务。

