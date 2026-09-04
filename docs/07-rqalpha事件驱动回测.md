# 07 · rqalpha 6.3 事件驱动回测（本地 CSV 喂数据，绕开 rqdatac）

> 目标：装好米筐 rqalpha 6.3.0，**不用 rqdatac（需 license）、不用 h5 bundle**，用腾讯源 CSV 跑通真实事件驱动回测。
> rqalpha 与 backtrader 的差别：券商级框架、内置涨跌停/停牌/撮合/滑点/费率模型，更接近真实交易。

## 7.1 为什么能绕开 rqdatac

rqalpha 6.3.0 默认数据源是 `BaseDataSource`（绑 h5 bundle 文件），生产数据来自 rqdatac（米筐，需 license）。
**但它支持自定义 mod 注入数据源**：`main.run()` 的装配顺序是 `mod_handler.start_up()` → **仅当此时尚无 `env.data_source` 才构造默认 BaseDataSource**。
所以在 `start_up()` 阶段调用 `env.set_data_source(自定义源)`，就能全程绕开 rqdatac / bundle。

## 7.2 安装（混合源，无需编译器）

rqalpha 6.3.0 是**纯 Python sdist**（无 bcolz 依赖——旧版本的 bcolz 拦路虎在 6.3 已移除；无 Cython），PyPI 只发 sdist 无 wheel，但纯 Python 所以直接装：

```bash
export SSL_CERT_FILE=/etc/ssl/certs/cacert.pem

# 1) 编译/ohos wheel 依赖 → OH 镜像（numpy/pandas/matplotlib/h5py 等已就位，这里补几个小的）
$PY -m pip install --user --only-binary=:all: --index-url "$OH_SRC" logbook simplejson wrapt

# 2) 纯 Python 依赖 → PyPI（OH 镜像未收录）
$PY -m pip install --user six jsonpickle tabulate more-itertools methodtools rqrisk typing-extensions

# 3) rqalpha 本体（sdist 纯 Python，--no-deps）
$PY -m pip install --user --no-deps rqalpha==6.3.0

python3 -c "import rqalpha; print(rqalpha.__version__)"   # 6.3.0，首次 import 约 1~2s
```

## 7.3 自定义 mod 包：喂本地 CSV 的 4 个关键文件

```
rqalpha_mod_csvds/
├── __init__.py    # __config__ = {"data_dir": None}; def load_mod(): return CsvDataMod()
├── mod.py         # class CsvDataMod(AbstractMod): start_up 里 env.set_data_source(内存源)
└── datasource.py  # class CsvDataSource(BaseDataSource): 不调文件型 __init__，手动铺内存 store
```

### 7.3.1 `__init__.py`

```python
# -*- coding: utf-8 -*-
__config__ = {"data_dir": None}

def load_mod():
    from .mod import CsvDataMod
    return CsvDataMod()
```

### 7.3.2 `mod.py` —— 注入点

```python
# -*- coding: utf-8 -*-
from rqalpha.mod import mod
from rqalpha.interface import AbstractMod
from .datasource import CsvDataSource


@mod.config
class CsvDataModConfig(object):
    data_dir = None


@mod.register
class CsvDataMod(AbstractMod):
    def __init__(self):
        self._ds = None

    def start_up(self, env, mod_config):
        from rqalpha.data.base_data_source import BaseDataSource
        self._ds = CsvDataSource(env, mod_config.data_dir)
        env.set_data_source(self._ds)      # ★ 关键：抢在默认 BaseDataSource 之前注入

    def tear_down(self, env, mod_config):
        pass
```

### 7.3.3 `datasource.py` —— 核心

**要点：继承 `BaseDataSource` 但不调 `super().__init__()`**（文件型构造会强制读 h5 bundle）。手动铺好基类方法消费的全部属性：

```python
# -*- coding: utf-8 -*-
import os
import numpy as np
import pandas as pd
from rqalpha.const import INSTRUMENT_TYPE, MARKET, TRADING_CALENDAR_TYPE
from rqalpha.data.base_data_source import BaseDataSource
from rqalpha.interface import AbstractDataSource
from rqalpha.utils.datetime_func import convert_date_to_int   # ★ 12 位编码在这
from rqalpha.model.instrument import Instrument


class _Dummy(object):
    """兜底：基类调 get_dividend/get_split 等时返回 None（安全）"""
    def __getattr__(self, name):
        return lambda *a, **kw: None


class CsvDataSource(BaseDataSource):
    def __init__(self, env, data_dir):
        # 不调 super().__init__() —— 文件型 bundle 构造会 raise
        self._env = env
        self._data_dir = data_dir
        self._day_bar_stores = {}
        self._calendar_stores = {}
        self._instrument_stores = _Dummy()
        self._split_stores = {}
        self._dividend_stores = {}
        self._ex_cum_factor_stores = {}
        self._trading_dates = None
        self._load_all()
        self._id_map = {}
        self._sym_map = {}
        for ins in self._instruments:
            self._id_map[ins.order_book_id] = ins
            self._sym_map[ins.symbol] = ins
        from collections import ChainMap
        self._id_or_sym_instrument_map = ChainMap(self._id_map, self._sym_map)

    # ---------- 装载 ----------
    def _load_all(self):
        instruments, dfs = [], {}
        for fn in sorted(os.listdir(self._data_dir)):
            if not fn.endswith(".csv"):
                continue
            code = fn[:-4]                       # 600519
            oid = f"{code}.{'XSHG' if code.startswith('6') else 'XSHE'}"
            df = pd.read_csv(os.path.join(self._data_dir, fn))
            dfs[oid] = df
            # qfq 价近似涨跌停（主板 10%，创业板/科创板 20%）
            pct = 0.20 if (code.startswith("3") or code.startswith("68")) else 0.10
            instruments.append(self._make_instrument(oid, code, pct))
        self._instruments = instruments
        dates = sorted(set().union(*[set(d["date"]) for d in dfs.values()]))
        self._trading_dates = pd.DatetimeIndex(pd.to_datetime(dates))
        self._calendar_stores[TRADING_CALENDAR_TYPE.CN_STOCK] = self._trading_dates
        store = self._build_day_bar_store(dfs)
        self._day_bar_stores[(INSTRUMENT_TYPE.CS, MARKET.CN)] = store

    def _make_instrument(self, oid, code, pct):
        # qfq 涨跌停价 = round(prev_close * (1 ± pct), 2)
        return Instrument(dict(
            order_book_id=oid, symbol=code, type="CS",
            listed_date=self._trading_dates[0], de_listed_date=self._trading_dates[-1],
            round_lot=100, market_tplus=1,
            exchange=oid.split(".")[1],
            board_type="MainBoard" if pct == 0.10 else "ChiNext",
            price_tick=0.01,  # 交易单位
        ))

    def _build_day_bar_store(self, dfs):
        bar_dicts = {}
        for oid, df in dfs.items():
            df = df.sort_values("date")
            prev_close = None
            recs = []
            for r in df.itertuples():
                close = float(r.close)
                limit_up = round(prev_close * 1.10, 2) if prev_close else float(r.open)
                limit_dn = round(prev_close * 0.90, 2) if prev_close else float(r.open)
                # ★★ 致命坑：datetime 必须 12 位 YYYYMMDD000000！
                recs.append((
                    convert_date_to_int(pd.Timestamp(r.date)),   # → 20230103000000
                    float(r.open), float(r.close), float(r.high), float(r.low),
                    float(r.volume), float(r.volume) * 0.0,      # total_turnover 占位
                    limit_up, limit_dn,
                ))
                prev_close = close
            arr = np.array(recs, dtype=[
                ("datetime", "i8"), ("open", "f8"), ("close", "f8"),
                ("high", "f8"), ("low", "f8"), ("volume", "f8"),
                ("total_turnover", "f8"), ("limit_up", "f8"), ("limit_down", "f8"),
            ])
            bar_dicts[oid] = arr
        return bar_dicts

    # ---------- 基类抽象方法 ----------
    def get_trading_calendar(self, *args, **kwargs):
        return self._calendar_stores[TRADING_CALENDAR_TYPE.CN_STOCK]

    def get_bar(self, instrument, dt, frequency):
        arr = self._day_bar_stores[(INSTRUMENT_TYPE.CS, MARKET.CN)][instrument.order_book_id]
        dt_int = convert_date_to_int(dt)
        i = arr["datetime"].searchsorted(dt_int, side="right") - 1
        if i < 0:
            return None
        row = arr[i]
        return (instrument.order_book_id, row["datetime"], row["open"], row["close"],
                row["high"], row["low"], row["volume"], row["total_turnover"],
                row["limit_up"], row["limit_down"])

    def history_bars(self, instrument, bar_count, frequency, field=None,
                     skip_suspended=True, include_now=False, adjust_type="pre"):
        arr = self._day_bar_stores[(INSTRUMENT_TYPE.CS, MARKET.CN)][instrument.order_book_id]
        if field == "datetime":
            return arr["datetime"][-bar_count:]
        if field is None:
            return arr[-bar_count:]
        return arr[field][-bar_count:]

    def current_snapshot(self, instrument, frequency, dt):
        return None

    def available_data_range(self, frequency):
        return self._trading_dates[0], self._trading_dates[-1]

    def get_instrument(self, id_or_sym):
        return self._id_or_sym_instrument_map.get(id_or_sym)

    def get_dividend(self, *a, **kw): return None
    def get_split(self, *a, **kw): return None
    def get_ex_cum_factor(self, *a, **kw): return None
    def adjust_bars(self, *a, **kw): return None
```

> `bar` 数据结构说明：`(order_book_id, datetime, open, close, high, low, volume, total_turnover, limit_up, limit_down)` 是 rqalpha 内部 bar 的元组约定；`get_bars`/`history_bars` 返回 numpy structured array。完整可运行版见 `scripts/`（或仓库根 `rqalpha_mod_csvds/` 参考目录）。

## 7.4 策略与 runner

### 策略（函数式）

```python
# ma_ev.py —— MA20/50 金叉满仓 / 死叉清仓
def init(context):
    context.oid = "600519.XSHG"
    context.fast, context.slow = 20, 50
    scheduler.run_daily(trade)          # 每个交易日收盘前调度


def trade(context, bar_dict):
    closes = history_bars(context.oid, context.slow + 5, "1d", "close")
    ma_fast = closes[-context.fast:].mean()
    ma_slow = closes[-context.slow:].mean()
    prev_fast = closes[-context.fast - 1:-1].mean()
    prev_slow = closes[-context.slow - 1:-1].mean()
    if prev_fast <= prev_slow and ma_fast > ma_slow:      # 金叉
        order_target_value(context.oid, context.portfolio.total_value * 0.98)
        logger.info(f"[金叉] MA{context.fast}={ma_fast:.2f} > MA{context.slow}={ma_slow:.2f}")  # ★ f-string！
    elif prev_fast >= prev_slow and ma_fast < ma_slow:    # 死叉
        order_target_value(context.oid, 0.0)
        logger.info(f"[死叉] MA{context.fast}={ma_fast:.2f} < MA{context.slow}={ma_slow:.2f}")
```

### runner

```python
# run_ma_ev.py
import os, sys, pickle
os.environ["SSL_CERT_FILE"] = "/etc/ssl/certs/cacert.pem"
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # 让 import_module 找到 mod

from rqalpha import main
from rqalpha.utils.config import parse_config

config = {
    "base": {
        "start": "2023-01-03", "end": "2026-09-01",
        "accounts": {"stock": 1000000},
        "frequency": "1d", "benchmark": None,
    },
    "mod": {
        "sys_analyser": {"enabled": True, "output_file": "result.pkl"},
        "csvds": {"enabled": True, "data_dir": "data"},   # ★ 自定义 mod 名
        "sys_transaction_cost": {"enabled": True},
    },
}
cfg = parse_config(config)
main.run(cfg)
```

> `parse_config` 是**嵌套 dict** 模式（非 click 模式），内部 deep_update，可直接喂 dict。

## 7.5 读结果

`sys_analyser` 的 `output_file` 是**原生 pickle**（不是 jsonpickle！）：

```python
import pickle
with open("result.pkl", "rb") as f:
    r = pickle.load(f)
print(r["summary"])       # 总收益/年化/最大回撤/交易次数...
print(r["trades"])        # 每笔成交 DataFrame
nav = r["portfolio"]["unit_net_value"]   # 日净值序列（DataFrame）
```

## 7.6 致命坑（按排查成本排序）

1. **bar 的 datetime 必须用 `convert_date_to_int` 的 12 位编码（YYYYMMDD000000）**。
   只存 8 位 YYYYMMDD → `bars["datetime"].searchsorted(dt_int, side="right")` 恒定位到数组尾部 → `history_bars` 永远返回最后 N 根 → **MA 恒定、策略永不交易、零报错**（最隐蔽的坑，先查它）。
2. **user_log / logger 不支持 `%s` 占位**（输出原样、不报错）→ 排查信号问题必须用 f-string。
3. **analyser output_file 是原生 pickle**（不是 jsonpickle）→ 用 `pickle.load` 读。
4. **无 benchmark 时** risk-free 缺失 → summary 的 sharpe / alpha / volatility = NaN（不影响撮合），展示用日净值重算：`nav.pct_change()` 年化。
5. 数据源 15 只全注册但回测 2 秒完成、positions 全 0 → 极可能是坑 1，先查 MA 是否随时间变化。

## 7.7 真实结果（600519，2023-01 ~ 2026-09，事件驱动）

| 框架 | 结果 | 差异原因 |
|---|---|---|
| rqalpha（本机撮合，默认费率：佣金万 8 + 卖出印花千 1） | **−23.78%**（100 万 → ¥762,207，21 笔交易） | 当日收盘撮合 + 更贵的费率 |
| backtrader 同策略（佣金万 8） | −11.99% | 撮合时点与费率模型不同 |
| 买入持有 | −16.19% | — |

> 同一策略三个数字 = 教学金矿：撮合时机与费率差异对结果影响巨大。**事件驱动框架（rqalpha/backtrader）各报各的数，别指望完全一致，关键是理解差异来源。**

---

**下一章**：[08 · pyqlib 因子学习](08-pyqlib因子学习.md) —— 微软 Qlib 源码树装配 + Alpha158 + LightGBM。
