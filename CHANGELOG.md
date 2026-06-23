# Changelog

## 5.3 (2026-06)

### 包结构

- 子模块拆分：`core/`（计算引擎、DAG、任务调度）、`io/`（POSCAR/INCAR/POTCAR/CP2K 解析）、`analysis/`（数据分析）
- `calc_runner.py` → `core/calc.py`，`task_scheduler.py` → `run.py`，`task_submit.py` → `submit.py`

### 调度与执行

- 新增 `dag.py`：DAG 算法（依赖解析、连通分量、拓扑排序）抽离为纯函数
- `Calculation.__init__` 改为零副作用，`prepare()` 负责建目录、预处理、状态检查。Calculation不再加锁，由Task.run进行加锁
- 依赖关系改用对象引用，不再往 dict 塞 `_dep` 等临时键
- 术语 `group` → `component`（连通分量），`--print-groups` → `--print-comps`
- `root_dir` 未指定时默认取配置文件所在目录

### CLI

- `submit.py` / `run.py` 改为 `main(argv)` 函数式入口，不再依赖 `sys.argv` 操作
- 版本号统一到 `vaspauto.__version__`
- shell 补全脚本（bash / zsh）
- 集群 CPU 核数从 `[partitions]` 表读取，不再设顶层字段

### 计算引擎

- NEB 断点续跑：从 INCAR 读取 `IMAGES`，将中间态 CONTCAR 复制为 POSCAR

### 分析模块

- 新增 `vaspauto analysis` 子命令（energy 汇总、interp 路径插值）
- `analysis interp`：三次样条插值 + 逐对插值，支持路径描述语句 DSL

### Python 版本

- 最低 Python 要求 ≥ 3.10
- 类型注解：`typing.Self` → `'Incar'`，`typing.Generator` → `collections.abc.Generator`

### Bug 修复

- `~` 路径展开改为仅展开行首（符合 Unix shell 语义）

---

## 5.2 (2026-06)

对项目进行大范围重构，使其更加现代化、更易用

### 包结构

- 重组为 `vaspauto` Python 包，支持 `pip install -e .`
- 新增 `pyproject.toml`，声明依赖和 `vaspauto` 命令行入口
- 三种使用方式：`vaspauto submit` / `python3 -m vaspauto submit` / `python3 -m vaspauto.task_submit`

### 集群配置

- `host_info.py` 改为纯配置文件驱动，零硬编码集群信息
- 配置文件为 `~/.config/vaspauto/host.toml`（单集群单文件），示例见 `host.example.toml`
- 计算节点通过 `$VASPAUTO_HOSTS_FILE` 环境变量直接定位配置，不依赖 hostname 检测

### 资源推导

- 重构 `task_submit.py` 的 `-N/-n/--nt/--nc` 推导逻辑，消除变量遮蔽隐患
- 编写八种情况真值表文档 (`docs/resource-allocation-logic.md`)

### INCAR 解析

- 支持 VASP 6 嵌套标签（如 `KERNEL_TRUNCATION { LTRUNCATE = T }`）
- 使用 `/` 作为路径分隔符扁平存储：`KERNEL_TRUNCATION/LTRUNCATE`
- 读写 round-trip 保真，`get()`/`set()`/`del_key()` API 不变

### 配置文件

- 新增 glob 变量：`{ glob = "*.vasp", dir = "structures", strip_ext = true }`
- 移除编译模式（compile mode）
- `--write-expanded-config` 在缺少 `tomli_w` 时给出安装提示
- `root_dir` 未指定时默认取配置文件所在目录（而非 CWD）

---

## 5.1

- 多维数组语法：`{var1:var2,var3}` 按索引逐层取值
- 新增 `--write-expanded-config` 选项（输出变量展开后的配置文件，调试用）

## 5.0

- 文件锁多进程支持（filelock），同一配置可多 Slurm 作业并行
- 移除 `--idx-group` / `--num-groups` 选项
- `run_vasp.py` 重命名为 `task_scheduler.py`，配套 `task_submit.py`
- 新增 `--rm-locks` 选项（手动取消任务后清理锁文件）
- 支持 postprocess（计算完成后执行 shell 命令或内置函数）

## 4.2

- 新增编译模式：将计算流程编译为独立 shell 脚本。但不支持任务状态检测，如自动跳过已完成任务
- 移除 dry run 模式

## 4.1

- `~` 在路径中自动展开为超算 home 目录
- 新增 `-d` / `--dir` 参数指定计算根目录
- 初步支持 CP2K 计算

## 4.0

- 脚本重命名为 `run_vasp.py`
- 新增 `host_info.py`，自动检测超算并配置环境
- 赝势目录自动设置（基于 host_info）
- 并行参数移至 `-n` / `--nc`
- 选项重命名：`--idx-task` → `--idx-group`，`--num-tasks` → `--num-groups`，`--print-num-parallel` → `--print-num-groups`

## 3.1

- 仅支持 `run_vasp` 4.1 和 `run_cp2k` 5.0

## 3.0

- 支持嵌套循环遍历变量
- 新增 `{var1:var2}` 索引替换语法
- 新增 `print` 预处理命令
- dry run 模式（调试用）
- 不再支持老的配置文件格式（2.0），跳出警告
- 支持跳过已完成任务，以及当前置任务未完成时跳过任务
- 检查重复计算名
- 支持 OpenMP（`global.ntask`）

## 2.0 (2024-02)

- 最初稳定版本

