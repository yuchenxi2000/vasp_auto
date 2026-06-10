# VaspAuto

自动化 VASP / CP2K 计算框架，面向超算集群（Slurm）设计。一次提交跑多个任务，自动管理依赖顺序，自动填充参数，避免手误导致任务中断重新排队。

> [English version](README_en.md)

## 功能

- **TOML 配置文件** — 声明式描述计算流程，配合变量替换和 glob 匹配，一个配置文件覆盖多个结构
- **依赖排序** — 自动解析弛豫→自洽→DOS 等依赖链，拓扑排序后按序执行
- **文件锁并行** — 同一配置文件可向 Slurm 提交多个作业，文件锁保证不同进程不跑同一个子任务
- **断点续跑** — 已完成任务自动跳过；未收敛的离子弛豫自动从 CONTCAR 续跑
- **INCAR 动态编辑** — 支持 VASP 6 嵌套标签（如 `KERNEL_TRUNCATION { LTRUNCATE = T }`），运行时通过配置文件增删标签
- **集群无关** — 集群信息由 `~/.config/vaspauto/host.toml` 配置文件描述，代码零硬编码

## 快速开始

### 1. 安装

```bash
pip install -e .          # 开发模式安装（推荐）
# 或
pip install .             # 正式安装
```

依赖：Python ≥ 3.10、`filelock`、`tomli`（Python < 3.11 时需要）。

### 2. 配置集群信息

```bash
mkdir -p ~/.config/vaspauto
cp host.example.toml ~/.config/vaspauto/host.toml
# 编辑 host.toml，填入你的集群的核数、分区、module 命令等
```

### 3. 编写计算配置

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

### 4. 提交 / 运行

```bash
# 生成 Slurm 脚本并提交
vaspauto submit -c my_calc.toml -N 2 -n 112 -J my_job -s

# 仅生成脚本不提交
vaspauto submit -c my_calc.toml -N 2 -n 112 -o run.sh

# 本地调试：查看会展开成哪些任务
vaspauto run -c my_calc.toml --print-groups -n 1
```

## 三种使用方式

| 方式 | 命令 | 适用场景 |
|------|------|---------|
| 安装后的命令 | `vaspauto submit ...` / `vaspauto run ...` | `pip install` 后直接使用 |
| `-m` 模块方式 | `python3 -m vaspauto submit ...` | 未安装时，PYTHONPATH 需指向项目根 |
| 直接调模块 | `python3 -m vaspauto.task_scheduler ...` | Slurm 脚本内部调用（自动设置 PYTHONPATH） |

## 命令行参考

### `vaspauto submit` — 生成 / 提交 Slurm 脚本

| 参数 | 说明 |
|------|------|
| `-c, --config` | 计算配置文件（TOML） |
| `-d, --dir` | 计算根目录 |
| `-N, --nodes` | 节点数（必填） |
| `-n` | 总 MPI 任务数 |
| `--nt` | 每节点任务数 |
| `--nc` | 每任务 CPU 数（OpenMP 线程数） |
| `-J, --job-name` | 作业名称 |
| `-p, --partition` | Slurm 分区 |
| `-t, --task` | 任务类型：`vasp+py`（默认）、`vasp`、`cp2k+py`、`cp2k` |
| `-s, --submit` | 直接提交（否则只写脚本文件） |
| `-o, --output` | 输出脚本路径 |

`-n`、`--nt`、`--nc` 三个参数可省略，框架自动推导。详见 [资源分配逻辑文档](docs/resource-allocation-logic.md)。

### `vaspauto run` — 执行计算（Slurm 脚本内调用）

| 参数 | 说明 |
|------|------|
| `-c, --config` | 计算配置文件 |
| `-d, --dir` | 计算根目录 |
| `-n` | 总 MPI 任务数（必填） |
| `--nc` | 每任务 CPU 数 |
| `--print-num-groups` | 打印独立任务组数后退出 |
| `--print-groups` | 打印任务组详情后退出 |
| `--rm-locks` | 清除所有锁文件（手动取消任务后使用） |
| `--write-expanded-config` | 输出变量展开后的配置文件（调试用，需 `tomli_w`） |

## 配置文件格式

详细规范见 `docs/` 目录：

| 文档 | 语言 |
|------|------|
| [config-file-specification-v5.md](docs/config-file-specification-v5.md) | 配置文件格式规范（v5.x）— 中文 |
| [config-file-specification-v5-en.md](docs/config-file-specification-v5-en.md) | 配置文件格式规范（v5.x）— English |
| [config-file-specification-v2-archive.md](docs/config-file-specification-v2-archive.md) | 旧版格式存档（v2.0） |
| [resource-allocation-logic.md](docs/resource-allocation-logic.md) | `-N/-n/--nt/--nc` 资源推导逻辑 |

## License

MIT License
