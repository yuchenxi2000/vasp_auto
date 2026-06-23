# energy — 计算结果汇总

读取配置文件，遍历所有计算任务，将每个任务的名称、能量、状态、目录输出为 CSV 文件。

## 用法

```bash
vaspauto analysis energy -c config.toml -o energy.csv
```

## 选项

| 参数 | 说明 |
|------|------|
| `-c, --config` | 计算配置文件，默认 `config.toml` |
| `-d, --dir` | 计算根目录（覆盖配置文件中的 `root_dir`） |
| `-o, --output` | 输出 CSV 文件路径，默认 `energy.csv` |

## 输出格式

```csv
name,energy,status,dir
HfO2/relax,-123.456,FINISHED,result/HfO2/relax
HfO2/scf,-124.789,FINISHED,result/HfO2/scf
```

- `energy` — 从 OSZICAR 中提取的最后一步能量；计算未完成时为空
- `status` — `FINISHED` / `NOT_CALCULATED` / `NEEDS_RERUN` / `UNCONVERGED`
