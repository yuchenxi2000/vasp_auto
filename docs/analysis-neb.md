# neb — NEB 路径能量分析

从 NEB 计算目录读取所有中间图像的能量和结构信息，输出为 CSV 文件，并可收集所有结构文件。

## 用法

```bash
# 输出能量-路径参数曲线到 CSV
vaspauto analysis neb -d /path/to/neb/calc -o neb.csv

# 同时收集所有中间结构
vaspauto analysis neb -d /path/to/neb/calc --struct structures/
```

## 选项

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `-d, --dir` | `.` | NEB 计算根目录，应包含 `INCAR` 和 `00/`、`01/`、... 子目录 |
| `--pbc-method` | `Wigner_Sitz` | 周期镜像修正方法。`Wigner_Sitz`（默认，基于最小距离修正）、`Old_Simple`（旧版 ±1 修正）、`None`（不修正） |
| `--fix` | — | 等价于 `--pbc-method Wigner_Sitz` |
| `--old-fix` | — | 等价于 `--pbc-method Old_Simple` |
| `-o, --output` | `neb.csv` | 输出的 CSV 文件路径 |
| `-s, --struct` | — | 收集所有图像的结构文件到指定目录 |

## 输出格式

CSV 文件包含三列，无表头行：

```csv
index,param,energy
0,0.0,-478.1234
1,0.0589,-477.2345
2,0.1177,-476.3456
...
```

| 列 | 说明                                                                                |
|----|-----------------------------------------------------------------------------------|
| `index` | 镜像序号。`0` = 起点（POSCAR），`1` ~ `n` = 中间图像（CONTCAR），`n+1` = 终点（POSCAR）                |
| `param` | 路径参数 *t*，范围 [0, 1]。基于所有图像的高维特征向量（晶格参数 + 原子坐标）计算弧长后归一化得到，反映结构沿路径的"自然进度"，与图像序号不一定等距 |
| `energy` | 从 OSZICAR 最后一离子步提取的总能量。若无 OSZICAR 文件则为 `NaN`                                      |

## 结构收集

使用 `-s / --struct` 参数可将 NEB 路径上所有图像的结构收集到指定目录：

```bash
vaspauto analysis neb -d neb_calc/ --struct structures/
```

收集后的目录结构：

```
structures/
  0.vasp      # 起点 POSCAR
  1.vasp      # 中间图像 01 的 CONTCAR
  2.vasp      # 中间图像 02 的 CONTCAR
  ...
  7.vasp      # 终点 POSCAR
```

可用于 VESTA 等可视化工具一次性加载整个路径的结构演化。

## 路径参数说明

`param` 列的值由 `PathInterpolator` 计算得出，过程：

1. **PBC 修正** — 按 `--pbc-method` 指定的方法对相邻结构的分数坐标做周期镜像修正
2. **特征向量化** — 将每个结构展平为高维向量（6 个晶格参数 + 3*n_atoms 个原子坐标）
3. **弧长归一化** — 计算相邻特征向量的欧氏距离，累积后归一化到 [0, 1]

由于基于弧长而非等间距，参数 *t* 在结构变化快的区域更密集，变化慢的区域更稀疏，更真实地反映反应坐标的进度。
