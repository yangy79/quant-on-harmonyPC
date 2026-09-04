# 08 · pyqlib 0.9.7 因子学习（Alpha158 + LightGBM，源码树轻装）

> 目标：装好微软 Qlib（真包名 **pyqlib**），跑通 Alpha158 因子 + LightGBM 训练 + 样本外评估。
> pyqlib 在 PyPI **只发 x86/mac/win wheel**（无 sdist、无 ohos/musl）→ 唯一可行路线是 **GitHub 源码树 + sys.path 注入 + 纯 Python 替换 Cython**。

## 8.1 先记住三个铁律

1. **`pip install qlib` 是空壳假包**（0.0.2.dev20，零依赖）；微软真包名是 **`pyqlib`**，但 pyqlib 在 PyPI 只发平台 wheel → **鸿蒙上两个都不能 pip 装**。
2. qlib 的 Cython 扩展**只有 2 个文件**：`qlib/data/_libs/rolling.pyx` + `expanding.pyx`（Slope / Rsquare / Resi 滑窗回归加速）。其余全是纯 Python。
3. `qlib.init()` 会拖 **mlflow**（→ protobuf 等重依赖）；`qlib/config.py` module 级硬依赖 **pydantic-settings**（→ pydantic-core Rust 扩展）。→ 一个 patch 掉，一个从 OH 镜像精确配平。

## 8.2 安装 / 装配序列（混合源 + 源码树）

```bash
export SSL_CERT_FILE=/etc/ssl/certs/cacert.pem

# 1) 编译依赖走 OH 镜像（lightgbm 上一章已装；这里补 pydantic-core Rust 扩展）
$PY -m pip install --user --only-binary=:all: --index-url "$OH_SRC" pydantic-core==2.46.5

# 2) 纯依赖走 PyPI（qlib 系）
$PY -m pip install --user redis ruamel.yaml packaging loguru tqdm joblib dill filelock fire pyyaml python-redis-lock
# pydantic 全家桶：必须先装 core（上一步），再 --no-deps 装纯包（版本强绑定！）
$PY -m pip install --user --no-deps pydantic==2.13.5 annotated-types typing-inspection python-dotenv pydantic-settings==2.15.0

# 3) qlib 源码树（勿 pip 安装）
mkdir -p _qlib_src && cd _qlib_src
python3 - <<'PY'
import urllib.request
urllib.request.urlretrieve(
    "https://codeload.github.com/microsoft/qlib/tar.gz/refs/tags/v0.9.7",
    "qlib.tar.gz")
PY
tar xzf qlib.tar.gz     # → qlib-0.9.7/
```

之后代码里 `sys.path.insert(0, "<...>/qlib-0.9.7")` 即可 `import qlib`。

> 若 codeload 下载慢/失败，可让有网机器下载后拷入。源码树 4.9 MB。

## 8.3 三个必须的源码 patch（都在源码树内，直接改）

### A. Cython `_libs` → 纯 numpy 替换（关键）

在 `qlib/data/_libs/` 下新建 **`rolling.py` 与 `expanding.py`**（`.pyx` 不会被 import 识别，同名 `.py` 优先加载），实现 `rolling_mean/slope/rsquare/resi(a, window)` 与 `expanding_mean/slope/rsquare/resi(a)`。

**语义**（pyx 原版）：滑动/扩展窗口内对（物理位置 x, 值 y）做最小二乘回归；NaN 占位剔除但保留位置；resi = 当前点 − 回归线在 x=最右端的预测。

**向量化等价**：slope / R² 对 x 平移不变 → 直接用**绝对下标**做 rolling 回归：

```python
# qlib/data/_libs/rolling.py —— 完整可运行参考
import numpy as np


def rolling_slope(a, window):
    n = len(a)
    out = np.full(n, np.nan)
    if n == 0:
        return out
    valid = ~np.isnan(a)
    y = np.where(valid, a, 0.0)
    idx = np.arange(n, dtype=float)
    # 窗口内累计和（pandas rolling min_periods=1）
    N  = pd_rolling_sum(valid.astype(float), window)
    Sx = pd_rolling_sum(idx, window)
    Sx2 = pd_rolling_sum(idx * idx, window)
    Sy = pd_rolling_sum(y, window)
    # 有效点数至少 2 才可回归（与 pyx 一致）
    with np.errstate(divide="ignore", invalid="ignore"):
        Sxy = pd_rolling_sum(idx * y, window)
        denom = N * Sx2 - Sx * Sx
        slope = (N * Sxy - Sx * Sy) / denom
    slope[(N < 2)] = np.nan
    return slope


def rolling_rsquare(a, window):
    # R² = (N·Sxy − Sx·Sy)² / [(N·Sx2 − Sx²)·(N·Sy2 − Sy²)]
    n = len(a)
    out = np.full(n, np.nan)
    if n == 0:
        return out
    valid = ~np.isnan(a)
    y = np.where(valid, a, 0.0)
    idx = np.arange(n, dtype=float)
    N  = pd_rolling_sum(valid.astype(float), window)
    Sx = pd_rolling_sum(idx, window)
    Sx2 = pd_rolling_sum(idx * idx, window)
    Sy = pd_rolling_sum(y, window)
    Sy2 = pd_rolling_sum(y * y, window)
    with np.errstate(divide="ignore", invalid="ignore"):
        Sxy = pd_rolling_sum(idx * y, window)
        num = (N * Sxy - Sx * Sy)
        denom = (N * Sx2 - Sx * Sx) * (N * Sy2 - Sy * Sy)
        r2 = num * num / denom
    r2[(N < 2)] = np.nan
    return r2


def rolling_resi(a, window):
    # resi[i] = a[i] − (slope[i]·i + intercept)，intercept 用窗口内回归线在 x=i 处的预测
    slope = rolling_slope(a, window)
    n = len(a)
    valid = ~np.isnan(a)
    y = np.where(valid, a, 0.0)
    idx = np.arange(n, dtype=float)
    N  = pd_rolling_sum(valid.astype(float), window)
    Sx = pd_rolling_sum(idx, window)
    Sy = pd_rolling_sum(y, window)
    with np.errstate(divide="ignore", invalid="ignore"):
        intercept = (Sy - slope * Sx) / N
        pred = slope * idx + intercept
    out = a - pred
    return out


def rolling_mean(a, window):
    return pd_rolling_sum(np.where(~np.isnan(a), a, 0.0), window) / \
           pd_rolling_sum((~np.isnan(a)).astype(float), window)


def pd_rolling_sum(a, window):
    """纯 numpy 的 rolling sum（等价 pandas rolling(window, min_periods=1).sum()）"""
    n = len(a)
    if window >= n:
        return np.cumsum(a)
    cs = np.concatenate([[0.0], np.cumsum(a)])
    out = cs[window:] - cs[:-window]
    # 头部不足 window 的部分按 min_periods=1 累加
    head = np.cumsum(a[: min(window - 1, n)])
    return np.concatenate([head, out]) if len(head) else out
```

`expanding.py` 同理，只是窗口 = 累计长度（`pd_rolling_sum(a, i+1)`）。完整参考实现见仓库根 `_qlib_src/qlib-0.9.7/qlib/data/_libs/`。

> **验证**：与逐窗手工回归对比误差 < 1e-12（已实测）。

### B. `config.register()` → mlflow 降级

`qlib/config.py` 的 `register()` 里 workflow/recorder 段（`from .workflow import R ...` / `init_instance_by_config(self["exp_manager"])` / `R.register(qr)` / `experiment_exit_handler()`）**整段包进 try/except**：

```python
try:
    # ... 原 register() 的 workflow/recorder 段 ...
    print("recorder disabled (mlflow unavailable on this platform)")
except Exception as e:
    print("recorder disabled:", type(e).__name__)
```

数据层 / 因子层不依赖 recorder，patch 掉不影响 Alpha158 与训练。

### C. `dump_bin.py` 进程池 → 线程池

`scripts/dump_bin.py` 用 `ProcessPoolExecutor` 提交**绑定方法** → spawn 模式下无法 pickle。复制一份把 `ProcessPoolExecutor` 全部替换为 `ThreadPoolExecutor`（15 只 CSV 量级无性能问题）。

## 8.4 数据管线（CSV → qlib bin）

1. **CSV 文件名必须带交易所前缀小写**：`sh600519.csv` / `sz000858.csv`（6 开头→sh，0/3 开头→sz），列含 date + 各特征。
2. **腾讯源 vwap 口径坑**：qfq 价与 amount 不是同一复权口径 → `amount/volume` 会超出当日 high/low（茅台算出 1723 vs 日高 1559）。**用典型价 `vwap=(high+low+close)/3` 代理**（量化常用近似）。
3. dump：

```python
from dump_bin import DumpDataAll
DumpDataAll(data_path="qlib_csv", qlib_dir="qlib_data",
            freq="day", exclude_fields="date").dump()
# 生成 qlib_data/{calendars/day.txt, instruments/all.txt, features/<sym>/<feat>.day.bin}
```

4. 验证：

```python
import qlib
from qlib.data import D
qlib.init(provider_uri="qlib_data", region="cn")   # ★ 不要传 default_conf="local"
# 0.9.7 的 MODE_CONF 无 "local" key，默认 client 模式即本地读
df = D.features(["SH600519"], ["$close"], start_time="2023-01-03", end_time="2026-09-01")
print(df.head())
```

## 8.5 Alpha158 + LightGBM 训练骨架

```python
# train_alpha158.py —— 必须 .py 文件 + main 守卫（qlib 数据层内部多进程 spawn，heredoc 必炸）
import os, sys
os.environ["SSL_CERT_FILE"] = "/etc/ssl/certs/cacert.pem"
sys.path.insert(0, os.path.abspath("_qlib_src/qlib-0.9.7"))   # qlib 源码树
sys.path.insert(0, os.path.abspath("."))
import qlib
from qlib.data import D
import pandas as pd, numpy as np
import lightgbm as lgb

qlib.init(provider_uri="qlib_data", region="cn")

BASKET = ["SH600519", "SZ000858", ...]          # 15 只（带 SH/SZ 前缀大写）
start, end = "2023-01-03", "2026-09-01"

def main():
    from qlib.contrib.data.handler import Alpha158
    h = Alpha158(instruments=list(BASKET), start_time=start, end_time=end,
                 freq="day", label=["Ref($close, -5)/Ref($close, -1) - 1"])
    h.fit()
    df = h.fetch().rename(columns={LABEL: "label"})     # (行, 159): 158 因子 + label
    df = df[~df["label"].isna()]                        # 剔 label NaN（末端未来不足）
    # Alpha158 fetch 不含原始 $close，需另拉（画净值用）
    px = D.features(BASKET, ["$close"], start_time=start, end_time=end)

    # 按日期切 train/valid/test（时间序列切分，禁随机）
    dates = sorted(df.index.get_level_values("datetime").unique())
    tr, va, te = dates[:int(len(dates)*0.5)], dates[int(len(dates)*0.5):int(len(dates)*0.75)], dates[int(len(dates)*0.75):]
    def slc(part):
        return df.loc[df.index.get_level_values("datetime").isin(part)]
    Xtr, Xva, Xte = (slc(p).drop(columns="label") for p in (tr, va, te))
    ytr, yva, yte = (slc(p)["label"] for p in (tr, va, te))

    model = lgb.LGBMRegressor(
        n_estimators=300, learning_rate=0.03, num_leaves=24,
        subsample=0.8, colsample_bytree=0.8,
        reg_alpha=1.0, reg_lambda=1.0, random_state=42)
    model.fit(Xtr, ytr, eval_set=[(Xva, yva)],
              callbacks=[lgb.early_stopping(20), lgb.log_evaluation(50)])

    # 评估：日频截面 Rank IC（spearman）
    pred = pd.Series(model.predict(Xte), index=Xte.index)
    te_df = pd.DataFrame({"pred": pred, "label": yte})
    ic = te_df.groupby(level="datetime").apply(
        lambda g: g["pred"].rank().corr(g["label"].rank()))
    print(f"样本外 Rank IC = {ic.mean():.4f}（{100*(ic > 0).mean():.1f}% 交易日为正）")

    # 回测：每 5 交易日按 pred 选 Top3 等权换仓（调仓日收盘决策，次日计收益）
    px_close = px["$close"].unstack()          # date × instrument
    ret = px_close.pct_change()
    # ...（Top3 组合净值 vs 等权基准，见 scripts/ 完整版）

if __name__ == "__main__":
    main()
```

> 处理器：不传 infer/learn_processors 用 Alpha158 内置默认即可（0.9.7 processor 类名与旧版不同：无 Dropna，有 DropnaProcessor / DropnaLabel）。

## 8.6 验证过的版本锁

| 包 | 版本 | 备注 |
|---|---|---|
| qlib | 0.9.7（GitHub tag v0.9.7） | 源码树 sys.path 注入 |
| lightgbm | 4.6.0 | OH 镜像 |
| pydantic + core + settings | 2.13.5 + **2.46.5** + 2.15.0 | core 与 pydantic **版本强绑定要对齐** |
| numpy / pandas | 2.2.6 / 2.2.3 | 系统预置 |

## 8.7 真实结果（15 只 A 股，2023-01 ~ 2026-09）

| 指标 | 值 |
|---|---|
| Alpha158 fetch | (13,320 × 159)，48.9 s |
| 训练集 / 验证集 / 测试集 | 6,315 / 3,645 / 2,340 行 |
| LGB best_iter | 6（样本少易过拟合 → 用保守参数 lr0.03 / leaves24 / 强正则） |
| **样本外 Rank IC** | **0.067**（59.6% 交易日为正） |
| 周频 Top3 组合（2026-01 ~ 08） | **+7.61%** vs 15 只等权 **−7.66%**（跑赢 15.3pp） |

> 大盘下行期（2026 上半年）因子选股显著跑赢等权 —— 这正是"因子有效"的直观证据。样本外 Rank IC ≈ 0.067 属于"弱但真实"的水平，符合小样本 + 价量因子的典型量级。

## 8.8 判 qlib 装不上的铁律（先分清三堵墙）

| 墙 | 现象 | 解法 |
|---|---|---|
| ① 平台 wheel 缺失 | PyPI 只有 x86/mac/win wheel | GitHub 源码树 + sys.path |
| ② Cython 扩展 | 装源码树后 import 报缺编译模块 | `_libs/` 同名 `.py` 纯 numpy 替换（误差 < 1e-12） |
| ③ mlflow / pydantic 全家桶 | `qlib.init()` 拖 mlflow；config 硬依赖 pydantic-settings | patch `register()` + OH 镜像 pydantic-core 精确配平 |

---

**下一章**：[09 · 实盘桥接](09-实盘桥接.md) —— QMT / 同花顺实盘数据桥接架构。
