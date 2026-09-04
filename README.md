# Quant on HarmonyOS PC —— 在纯血鸿蒙电脑上搭起完整的量化交易研究栈

> **English Abstract** — This repository is a **step-by-step, zero-compilation setup guide** for building a complete quantitative-trading research stack on **HarmonyOS PC / OpenHarmony** (aarch64, musl, no package manager, no gcc/gfortran). Everything here was verified on a real HUAWEI MateBook Pro (Python 3.12.9, platform tag `cp312-cp312-ohos_aarch64`).
>
> Covered, all without a compiler: **numpy / pandas / scipy / matplotlib / Pillow / h5py**, **lightgbm / scikit-learn / numba / llvmlite / torch (CPU)**, market data via **akshare (Tencent source)** or a dependency-free `urllib` fetcher, backtesting with **backtrader / vectorbt / rqalpha 6.3** (custom mod feeding local CSV, bypassing rqdatac), and factor learning with **pyqlib 0.9.7 Alpha158 + LightGBM** (source-tree install with pure-numpy replacements for 2 Cython extensions). Real results included: out-of-sample Rank IC 0.067; weekly Top-3 portfolio +7.61% vs. equal-weight −7.66% (2026-01→08).
>
> Each doc gives the exact package versions, mirror URLs (OpenHarmony / cnb.cool / PyPI), `.so` code-signing commands, and every pitfall encountered. **If your machine shares this architecture, you can reproduce the whole stack without compiling anything.** Chinese is the main language; `docs/01` explains the "three-step feasibility rule" for installing any package on this platform.

> **给「和我一样架构」的机器的免编译安装手册。**
> 一台没有 gcc / gfortran / 包管理器的 HarmonyOS PC（ohos-aarch64, musl），能不能跑 numpy / scipy / matplotlib / torch / lightgbm / akshare / backtrader / vectorbt / rqalpha / pyqlib？
> **能。全部能，而且一行编译器都不用装。**

本仓库记录了一次完整的真机实测：从拿到纯血鸿蒙 PC 开始，到跑通 **rqalpha 事件驱动回测** 与 **pyqlib Alpha158 + LightGBM 因子学习** 的每一步——包括每个包的准确版本、镜像源、安装命令、`.so` 签名、以及所有踩过的坑。**同架构机器照着做即可，不需要再编译任何东西。**

---

## 目标机器（实测环境）

| 项目 | 值 |
|---|---|
| 设备 | HUAWEI MateBook Pro（HarmonyOS PC） |
| 系统 | HarmonyOS PC / OpenHarmony（纯血鸿蒙，非双框架） |
| 内核 libc | musl（`ld-musl-aarch64`） |
| 架构 | aarch64（平台标签 `ohos_aarch64`） |
| Python | 3.12.9（系统预置 `/data/storage/el1/bundle/libs/arm64/python/bin/python3`） |
| pip | 26.2.1（`get-pip.py --user` 安装） |
| CPU | 20 核；RAM 31 GB |

**硬性约束（不理解这些，后面的操作都无法解释）：**

1. 无 `apt`/`yum`/`dnf`，无 gcc / g++ / gfortran（NDK 只有 clang 系）
2. **禁止符号链接**（任何位置），`venv` 创建失败 → 用 `--user` 用户级安装
3. 无 `/usr/bin/env`；`/tmp` 只读
4. **所有 `.so` 必须代码签名**，否则 `dlopen` 报 `signature verification failed`
5. 编译型 wheel 平台标签必须是 `cp312-cp312-ohos_aarch64` —— **PyPI 的 manylinux/musllinux 一律装不上**，这是整个仓库的根源问题

> 结论先行：**这台机器上"装不上某个包"几乎永远不是因为它要编译，而是因为你没找对源。** 判定铁律：先查 OpenHarmony 社区镜像的 simple 索引 → 有 `ohos_aarch64` wheel 就能装；索引没有但包是纯 Python → 从 PyPI 装；两者都不行（个别 Rust/Cython 扩展）→ 用本仓库的"源码树 + 纯 Python 替换"方案。

---

## 成果一览（全部真机跑通）

```
鸿蒙量化研究栈（HarmonyOS PC, Python 3.12.9, 免编译）
│
├─ 数据层    akshare 1.18.94（腾讯源直连，~2s/只，qfq 日线，CSV 缓存）
│
├─ 计算层    numpy 2.2.6 · pandas 2.2.3 · scipy 1.16.3 · matplotlib 3.10.0
│            Pillow 12.2.0 · h5py 3.16.0
│
├─ ML 层     lightgbm 4.6.0 · scikit-learn 1.8.0 · numba 0.67 + llvmlite 0.49
│            torch 2.11.0（CPU, import 3.3s, DataLoader 多进程可用）
│
├─ 回测层    backtrader 1.9.78.123 · vectorbt 0.28.5
│            rqalpha 6.3.0（自定义 mod 喂本地 CSV，绕开 rqdatac/h5 bundle）
│
└─ 因子层    pyqlib 0.9.7（GitHub 源码树 + Cython→纯 numpy 替换）
             Alpha158 + LightGBM：样本外 Rank IC 0.067，周频 Top3 跑赢基准 15.3pp
```

**真实回测结果（教学用，非投资建议）：**

| 案例 | 结果 |
|---|---|
| 600519 双均线（MA20/50 金叉），2023-01 ~ 2026-09 | **−23.78%**（同期买入持有 −16.19%） |
| 15 只横截面动量轮动，同区间 | **−9.7%**（同期等权 +34.8%） |
| Alpha158 + LightGBM 周频 Top3，2026-01 ~ 08 | **+7.61%**（同期 15 只等权 −7.66%） |

> 三个案例两亏一赚 —— 这正是量化最真实的样子，也说明"能跑通工具链"与"能赚钱"是两件事。本仓库只解决前者。

---

## 目录

| 路径 | 内容 |
|---|---|
| [docs/01-环境与硬约束.md](docs/01-环境与硬约束.md) | 系统约束、目录布局、签名机制、判定铁律 |
| [docs/02-基础准备.md](docs/02-基础准备.md) | get-pip、SSL 证书、镜像源清单、包安装规范 |
| [docs/03-科学计算栈.md](docs/03-科学计算栈.md) | numpy/pandas/scipy/matplotlib/pillow/h5py + scipy 选镜像血泪坑 |
| [docs/04-机器学习与深度学习.md](docs/04-机器学习与深度学习.md) | lightgbm/sklearn/numba/llvmlite/**torch 2.11 部署** |
| [docs/05-数据获取.md](docs/05-数据获取.md) | akshare 安装与数据源实测（东财拒连 / 新浪缺 JS / **腾讯可用**） |
| [docs/06-回测引擎.md](docs/06-回测引擎.md) | backtrader / vectorbt 实装与双均线回测 |
| [docs/07-rqalpha事件驱动回测.md](docs/07-rqalpha事件驱动回测.md) | rqalpha 6.3 + 自定义 mod 喂 CSV（含 12 位 datetime 致命坑） |
| [docs/08-pyqlib因子学习.md](docs/08-pyqlib因子学习.md) | pyqlib 源码树装配 + 三堵墙解法 + Alpha158 实跑 |
| [docs/09-实盘桥接.md](docs/09-实盘桥接.md) | QMT/同花顺实盘数据桥接架构（VM 方案，标注验证状态） |
| [docs/10-验证与成果.md](docs/10-验证与成果.md) | 分层验证清单 + 真实数字证据 |
| [docs/11-踩坑大全FAQ.md](docs/11-踩坑大全FAQ.md) | 按症状索引的全部坑与对策 |
| [scripts/](scripts/) | 可复用脚本（安装/签名/验证/抓数/修复） |

---

## 快速开始（约 15 分钟）

```bash
# 0) 每一条网络命令前都要带证书（鸿蒙无系统 CA 库）
export SSL_CERT_FILE=/etc/ssl/certs/cacert.pem

# 1) 装 pip（系统 Python 无 pip）
python3 get-pip.py --user          # get-pip.py 从 bootstrap.pypa.io 下载

# 2) 科学计算栈：全部走 OpenHarmony 社区镜像（有 ohos_aarch64 预编译 wheel）
OH_SRC="https://pypi.repo.openharmony.cn/artifactory/api/pypi/openharmony-pypi-local/simple/"
python3 -m pip install --user --only-binary=:all: --index-url "$OH_SRC" \
    numpy==2.2.6 pandas==2.2.3 h5py matplotlib pillow

# 3) scipy 必须用 cnb.cool 的 NOFORTRAN 构建（volces 的 1.17.1 捆绑 libgfortran 会段错误！）
CNB="https://pypi.cnb.cool/OpenHarmonyPCDeveloper/pypi/-/packages/simple"
python3 -m pip install --no-deps --index-url "$CNB" scipy==1.16.3

# 4) 逐个给所有 .so 签名（不签 = dlopen 报 signature verification failed）
SIG=/data/service/hnp/ohos-sdk.org/ohos-sdk_26.0.0.18/ohos/toolchains/lib/binary-sign-tool
find ~/.local/lib/python3.12/site-packages -name '*.so' -o -name '*.so.*' | while read s; do
  "$SIG" sign -inFile "$s" -outFile "$s" -selfSign 1 >/dev/null 2>&1
done

# 5) 冒烟验证
python3 -c "import numpy, pandas, scipy, matplotlib, PIL, h5py; print('sci-stack OK')"
```

详细的分层步骤、版本锁、坑与修复，见 [docs/](docs/) 各章；想一键复现用 [scripts/](scripts/)。

---

## 设计取舍与诚实边界

- **为什么能免编译？** OpenHarmony 社区镜像（`pypi.repo.openharmony.cn`）已经为绝大多数科学计算/量化包构建了 `cp312-cp312-ohos_aarch64` 预编译 wheel —— 这条生态在 2026 年已经相当完整。本仓库全部命令都指向**预编译 wheel 或纯 Python 包**，不需要任何编译器。
- **torch 只有 CPU**：鸿蒙无 CUDA，`torch 2.11.0` CPU 版实测可用（详见 docs/04），深度学习训练请按需评估规模。
- **rqalpha/pyqlib 均为"社区改造版"用法**：rqalpha 用自定义 mod 喂本地 CSV（绕开需 license 的 rqdatac 和 h5 bundle）；pyqlib 用 GitHub 源码树 + 纯 numpy 替换 2 个 Cython 扩展（误差 < 1e-12）。**不修改任何算法逻辑**，只替换加速实现。
- **实盘是唯一缺口**：券商 miniQMT 客户端只能跑 Windows，本机方案为「Oseasy Win ARM64 VM 内跑 xtquant + 共享文件夹 CSV 桥接」，方案与脚本已就绪并 smoke 通过，但**待券商开通 miniQMT 权限后实机验证**（见 docs/09）。
- 本仓库所有回测数字均为真实运行结果，用于**教学与工具链验证**，不构成任何投资建议。

---

## 环境信息（复现所需）

- Python 二进制：`/data/storage/el1/bundle/libs/arm64/python/bin/python3`
- 用户级包目录：`~/.local/lib/python3.12/site-packages`（编译型包必须装这里，工作区挂在 noexec 上）
- 签名工具：`/data/service/hnp/ohos-sdk.org/ohos-sdk_26.0.0.18/ohos/toolchains/lib/binary-sign-tool`
- 系统中文字体：`/system/fonts/FZHeiT-SC-Regular.ttf` 等（matplotlib 绘图需显式注册）

> 不同设备/系统版本的 SDK 路径可能不同，用 `find /data/service/hnp -name binary-sign-tool` 定位签名工具；Python 路径同理。

---

*记录于 2026-09，HarmonyOS MateBook Pro 真机。所有命令均在本机验证通过。*
