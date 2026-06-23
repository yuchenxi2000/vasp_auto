# 计算资源分配逻辑

> `submit.py` 中 `-N` / `-n` / `--nt` / `--nc` 四个参数的推导关系

---

## 1. 参数定义

| 命令行参数 | Slurm 指令 | 变量名 | 含义 |
|-----------|-----------|--------|------|
| `-N, --nodes` | `--nodes` | `nodes` | **节点数**。必填。 |
| `-n` | `--ntasks` | `num_tasks` | **总 MPI 任务数**（跨所有节点）。同时也是传给 `mpirun -n` 的值。 |
| `--nt` | `--ntasks-per-node` | `tasks_per_node` | **每节点任务数**。 |
| `--nc` | `--cpus-per-task` | `cpus_per_task` | **每任务 CPU 数**（即 OpenMP 线程数 `OMP_NUM_THREADS`）。 |

Slurm 分配的总 CPU 数：

```
总 CPU 数 = (总任务数) × cpus_per_task
每节点 CPU 数 ≤ tasks_per_node × cpus_per_task
```

---

## 2. 约束条件

设 `P = phys_cpus_per_node`（物理核数），`L = cpus_per_node`（逻辑核数），`N = nodes`：

| 编号 | 约束 | 说明 |
|------|------|------|
| C1 | `cpus_per_task ≤ L` | 单个任务不能超过单节点总核数 |
| C2 | `cpus_per_task ≥ 1` | 不能为 0 |
| C3 | `tasks_per_node × cpus_per_task ≤ L` | **硬限制**：每节点核数不超逻辑核，超了抛异常 |
| C4 | `tasks_per_node × cpus_per_task ≤ P` | **软限制**：超过物理核打印 warning（允许超线程） |
| C5 | `num_tasks ≤ N × tasks_per_node` | 总任务数不能超过最大槽位数 |

C3 和 C5 联合保证总 CPU 数不超集群可用资源。

---

## 3. 物理核 vs 逻辑核

- **物理核** (`phys_cpus_per_node`)：CPU 物理核心数
- **逻辑核** (`cpus_per_node`)：含超线程的虚拟核心数，`L ≥ P`

推导时优先使用物理核计算，结果截断为 0 时 fallback 到逻辑核。验证时，超过逻辑核抛异常，超过物理核但未超逻辑核给 warning。

```
# 优先用物理核
cpus_per_task = P // tasks_per_node
if cpus_per_task == 0:
    cpus_per_task = L // tasks_per_node   # fallback
```

P 和 L 的具体值由 `~/.config/vaspauto/host.toml` 的 `[partitions]` 表决定。`--partition` 通过 `host.use_partition()` 切换分区时更新这两个值。

---

## 4. 推导流程

推导按顺序执行：

```
Step 1: 确定 cpus_per_task (--nc)
Step 2: 确定 tasks_per_node (--nt)
Step 3: 验证约束 C1~C5
Step 4: 确定 ntasks (-n) 并写入 Slurm 脚本
```

### Step 1 — 确定 `cpus_per_task`

```
if --nc 给出:
    cpus_per_task = --nc 的值
elif --nt 给出:
    cpus_per_task = P // nt          (优先物理核)
    if == 0: cpus_per_task = L // nt
elif -n 给出:
    tasks_per_node = ceil(n / N)     ← 临时计算
    cpus_per_task = P // tasks_per_node
    if == 0: cpus_per_task = L // tasks_per_node
else:
    cpus_per_task = 1
```

验证 C1, C2：`cpus_per_task > L` → 异常；`cpus_per_task == 0` → 异常。

### Step 2 — 确定 `tasks_per_node`

```
if --nt 给出:
    tasks_per_node = --nt 的值
elif -n 给出:
    tasks_per_node = ceil(n / N)
else:
    tasks_per_node = P // cpus_per_task    (优先物理核)
    if == 0: tasks_per_node = L // cpus_per_task
```

验证 C3, C4：`tasks_per_node × cpus_per_task > L` → 异常；`> P` → warning。

### Step 3 — 确定 `ntasks`

```
if -n 给出:
    ntasks = n
    验证 C5: ntasks > N × tasks_per_node → 异常
    写入 #SBATCH --ntasks={ntasks}
else:
    ntasks = N × tasks_per_node
    (不写 --ntasks，Slurm 默认取 N × tasks_per_node)
```

---

## 5. 八种情况真值表

T = 用户提供，F = 未提供。表中数字 `(1)` `(2)` `(3)` 表示该列的值在计算方法中被引用。

| # | -n | — | --nt | — | --nc | — | 推导结果 |
|---|----|---|------|---|------|---|---------|
| 1 | T | - | T | - | T | - | `nc`=用户, `nt`=用户, `n`=用户 |
| 2 | T | - | T | - | F | P/(2), L/(2) | `nc`=P÷nt(→L÷nt), `nt`=用户, `n`=用户 |
| 3 | T | - | F | P/(3), L/(3) | T | - | `nc`=用户, `nt`=ceil(n/N), `n`=用户 |
| 4 | T | - | F | (1)/N | F | P/(2), L/(2) | `nc`=P÷ceil(n/N)(→L÷ceil(n/N)), `nt`=ceil(n/N), `n`=用户 |
| 5 | F | N×(2) | T | - | T | - | `nc`=用户, `nt`=用户, `n`=N×nt |
| 6 | F | N×(2) | T | - | F | P/(2), L/(2) | `nc`=P÷nt(→L÷nt), `nt`=用户, `n`=N×nt |
| 7 | F | N×(2) | F | P/(3), L/(3) | T | - | `nc`=用户, `nt`=P÷nc(→L÷nc), `n`=N×nt |
| 8 | F | N×(2) | F | P | F | 1 | `nc`=1, `nt`=P(→L), `n`=N×P |
