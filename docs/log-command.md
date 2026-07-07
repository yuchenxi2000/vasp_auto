# `vaspauto log` — 作业状态查看

## 概述

`vaspauto log` 从全局历史日志（`~/.config/vaspauto/history.jsonl`）中读取所有提交记录，并查询 Slurm 获取当前作业状态，统一展示。

**默认显示最近 5 条**（避免输出过长），可通过 `-a` / `--all` 查看全部。

## 用法

```bash
vaspauto log                  # 最近 5 条
vaspauto log -a               # 全部记录
vaspauto log --recent 10      # 最近 10 条
vaspauto log --running        # 仅显示正在运行/排队的作业
vaspauto log --failed         # 仅显示失败/异常退出的作业
vaspauto log --json           # JSON 格式输出（方便脚本处理）
```

### 参数说明

| 参数 | 说明 |
|------|------|
| `-a`, `--all` | 显示全部记录（默认只显示最近 5 条） |
| `--recent N` | 显示最近 N 条 |
| `--running` | 过滤：仅显示 Slurm 状态为 RUNNING / PENDING 的作业 |
| `--failed` | 过滤：仅显示失败、超时、异常退出的作业 |
| `--json` | 以 JSON 数组格式输出 |

## 输出示例

```
Job ID    Name          Submit     Slurm      VA State        Results  Elap  Work Dir
--------  ------------  ---------  ---------  ------------    -------  ----  --------
12345     HfO2_relax    07-06 15:30  RUNNING    running         -        -     /home/user/proj
12344     test_job      07-05 09:00  COMPLETED  completed       8/10     58m   /home/user/test
12343     old_job       07-04 22:00  COMPLETED  unexpected exit -        -     /home/user/old
12342     bad_job       07-04 20:00  FAILED     failed          -        -     /home/user/bad
12341     script_only   07-03 12:00  -          script only     -        -     /home/user/tmp
```

### 列说明

| 列 | 说明 |
|----|------|
| Job ID | Slurm 作业 ID。若仅生成脚本未提交（`-o` 模式），显示 `-` |
| Name | 作业名称（`-J` 参数） |
| Submit | 提交时间 |
| Slurm | Slurm 报告的作业状态（通过 `squeue` / `sacct` 查询）。若无 Slurm 客户端，显示 `(no slurm)` |
| VA State | VaspAuto 综合判定的状态（见下方状态判定逻辑） |
| Results | 完成/失败的计算数，如 `8/10` 表示 10 个计算中完成 8 个 |
| Elap | 总耗时 |
| Work Dir | 工作目录 |

## 状态判定逻辑

`va_state`（VaspAuto 状态）是综合 Slurm 查询结果和历史日志得出的：

| Slurm 状态 | 历史日志中有 `job_end`？ | VA State | 含义 |
|-----------|------------------------|----------|------|
| RUNNING / PENDING / CONFIGURING | — | `running` | 正在运行或排队等待 |
| COMPLETED | ✓ 有 | `completed` | 正常完成 |
| COMPLETED | ✗ 无 | `unexpected exit` | Slurm 作业本身成功结束，但 VaspAuto 框架未正常退出（可能是 Python 崩溃、被 OOM kill 等） |
| FAILED | — | `failed` | 作业执行失败（非零退出码） |
| TIMEOUT | — | `timeout` | 超过时间限制被 Slurm 终止 |
| CANCELLED | — | `cancelled` | 被手动取消（`scancel`） |
| NODE_FAIL | — | `node fail` | 计算节点故障 |
| OUT_OF_MEMORY | — | `out of memory` | 内存不足 |
| (Slurm 数据库中找不到) | ✓ 有 job_end | `completed` | Slurm 数据库已清理该记录，但历史日志中有完整的结束记录，推断为正常完成 |
| (Slurm 数据库中找不到) | 有 job_start 无 job_end | `unknown` | 作业在 Slurm 数据库已不可查，且历史日志中没有结束记录，无法判定最终状态 |
| (Slurm 数据库中找不到) | 仅 submit | `unknown` | 作业可能尚未被调度，或 Slurm 数据库已清理 |
| — (仅生成脚本) | — | `script only` | `-o` 模式生成的脚本，未通过 `-s` 提交 |

## 全局历史日志

状态查看命令依赖全局历史日志 `~/.config/vaspauto/history.jsonl`。

此文件由以下时机自动写入：
- **`vaspauto submit`** — 每次提交/生成脚本时记录 `submit` 事件
- **`vaspauto run`**（Slurm 作业内） — 作业开始和结束时分别记录 `job_start` / `job_end` 事件

每条记录为 JSONL 格式，一行一条事件。示例：

```jsonl
{"event":"submit","ts":"2026-07-06T15:30:00+08:00","job_id":"12345","job_name":"HfO2","config":"/home/user/proj/config.toml","work_dir":"/home/user/proj","task_type":"vasp+py","partition":"cpu","nodes":2,"ntasks":112,"cpus_per_task":2,"host":"cluster1","version":"5.3"}
{"event":"job_start","ts":"2026-07-06T15:32:01+08:00","job_id":"12345","work_dir":"/home/user/proj"}
{"event":"job_end","ts":"2026-07-06T17:10:05+08:00","job_id":"12345","work_dir":"/home/user/proj","elapsed_s":5884.0,"results":{"total":10,"finished":8,"unconverged":1,"failed":0,"skipped":1,"not_calculated":0}}
```

## 依赖

- **Slurm 客户端**（`squeue`、`sacct`）：仅在集群登录节点上可用，用于查询实时状态。在本地机器上执行时 Slurm 列显示 `(no slurm)`，但历史日志中的记录仍可正常展示。
- **Python 标准库**：无额外 Python 依赖。
