# -*- coding: utf-8 -*-
"""内存版数据源: 把本地腾讯源 CSV 日线喂给 rqalpha (绕开 rqdatac / h5 bundle)

用法: 见 mod.py, 通过自定义 mod 在 start_up 阶段 env.set_data_source() 注入,
main.run 检测到已有 data_source 后不再构造默认的 BaseDataSource(它绑定 h5 bundle)。
"""
import os
from collections import ChainMap

import numpy as np
import pandas as pd

from rqalpha.data.base_data_source import BaseDataSource
from rqalpha.const import INSTRUMENT_TYPE, MARKET, TRADING_CALENDAR_TYPE
from rqalpha.model.instrument import Instrument
from rqalpha.utils.datetime_func import convert_date_to_int as _rq_date_to_int

# rqalpha SecuritiesDayBarStore 的 bar dtype: datetime(int64, YYYYMMDD) + OHLCV + turnover
# + 股票额外 limit_up/limit_down (撮合/涨跌停判断用)
BAR_DTYPE = np.dtype([
    ("datetime", np.int64),
    ("open", np.float64),
    ("close", np.float64),
    ("high", np.float64),
    ("low", np.float64),
    ("volume", np.float64),
    ("total_turnover", np.float64),
    ("limit_up", np.float64),
    ("limit_down", np.float64),
])

# A股板块涨跌停幅度: 创业板(300)/科创板(688) 20%, 其余主板 10%
def _limit_pct(symbol: str) -> float:
    return 0.2 if symbol.startswith(("300", "688")) else 0.1


def _sym_to_oid(symbol: str) -> str:
    """6 开头 → 上交所 .XSHG; 0/3 开头 → 深交所 .XSHE"""
    return f"{symbol}.XSHG" if symbol.startswith("6") else f"{symbol}.XSHE"


def _exchange(symbol: str) -> str:
    return "XSHG" if symbol.startswith("6") else "XSHE"


def _d_to_int(d) -> int:
    """date/datetime/str -> rqalpha 编码 (YYYYMMDD000000 12位, 时间位为0)"""
    return int(_rq_date_to_int(pd.Timestamp(d)))


class MemDayBarStore:
    """get_bars(order_book_id) -> np structured array (与 h5 DayBarStore 同契约)"""

    def __init__(self, bars_by_oid: dict):
        self._b = bars_by_oid

    def get_bars(self, order_book_id: str):
        return self._b.get(order_book_id, np.empty(0, dtype=BAR_DTYPE))

    def get_date_range(self, order_book_id: str):
        b = self._b.get(order_book_id)
        if b is None or len(b) == 0:
            return 20050104, 20050104
        return int(b["datetime"][0]), int(b["datetime"][-1])


class MemCalendarStore:
    def __init__(self, trading_dates: pd.DatetimeIndex):
        self._di = trading_dates

    def get_trading_calendar(self):
        return self._di


class _Dummy:
    """空 store: 让基类方法安全返回 None/空, 不抛错"""

    def __getattr__(self, name):
        def _f(*a, **k):
            return None
        return _f


class CsvDataSource(BaseDataSource):
    """不调用 BaseDataSource.__init__ (其强制读 h5 bundle 文件),
    手动铺好基类方法消费的属性, 全部数据来自内存 DataFrame/ndarray。"""

    def __init__(self, data_dir: str, oids: list = None, start: str = None, end: str = None):
        self._future_info_store = _Dummy()
        self._yield_curve = _Dummy()
        self._share_transformation = _Dummy()
        self._suspend_days = []                 # is_suspended -> [False]*n
        self._st_stock_days = _Dummy()          # is_st_stock -> None -> [False]*n
        self._dividend_stores = {}
        self._split_stores = {}
        self._ex_factor_stores = {}

        # 读 CSV
        bars_by_oid, all_days, symbols = self._load_csv(data_dir)
        if oids is not None:
            keep = set(oids)
            bars_by_oid = {k: v for k, v in bars_by_oid.items() if k in keep}
            symbols = [s for s in symbols if _sym_to_oid(s) in bars_by_oid]
        if start is not None:
            s_int = _d_to_int(start)
            bars_by_oid = {k: v[v["datetime"] >= s_int] for k, v in bars_by_oid.items()}
        if end is not None:
            e_int = _d_to_int(end)
            bars_by_oid = {k: v[v["datetime"] <= e_int] for k, v in bars_by_oid.items()}
        all_days = sorted({int(x) for v in bars_by_oid.values() for x in v["datetime"]})

        # 交易日历 (bars datetime 为 12 位编码 → 取前 8 位转日期)
        _day_ints = sorted({int(x) for v in bars_by_oid.values() for x in v["datetime"]})
        calendar = pd.to_datetime([str(x)[:8] for x in _day_ints], format="%Y%m%d")
        calendar = pd.DatetimeIndex(calendar, name="date")
        self._calendar_stores = {TRADING_CALENDAR_TYPE.CN_STOCK: MemCalendarStore(calendar)}

        # day bar store
        self._day_bar_stores = {}
        cs_store = MemDayBarStore(bars_by_oid)
        for ins_type in (INSTRUMENT_TYPE.CS, INSTRUMENT_TYPE.INDX, INSTRUMENT_TYPE.ETF,
                         INSTRUMENT_TYPE.LOF):
            self._day_bar_stores[ins_type, MARKET.CN] = cs_store

        # instruments
        self._id_instrument_map = {}
        self._sym_instrument_map = {}
        self._id_or_sym_instrument_map = ChainMap(self._id_instrument_map, self._sym_instrument_map)
        self._grouped_instruments = {}
        for sym in symbols:
            ins = self._make_instrument(sym)
            self.register_instruments([ins])
        self._date_bounds = (calendar[0].date(), calendar[-1].date())

    # ---------- 数据加载 ----------
    def _load_csv(self, data_dir: str):
        bars_by_oid, symbols = {}, []
        all_days = []
        for fn in sorted(os.listdir(data_dir)):
            if not fn.endswith(".csv"):
                continue
            sym = fn[:-4]
            if not sym.isdigit():
                continue
            path = os.path.join(data_dir, fn)
            try:
                df = pd.read_csv(path, encoding="utf-8-sig", parse_dates=["date"])
            except Exception:
                continue
            if df is None or len(df) < 2:
                continue
            df = df.dropna(subset=["open", "close", "high", "low", "volume"])
            df = df.sort_values("date").reset_index(drop=True)
            # 清洗: open/high/low 至少非负, 极少数脏行剔除
            df = df[(df["open"] > 0) & (df["close"] > 0) & (df["high"] > 0) & (df["low"] > 0)]
            if len(df) < 2:
                continue
            pct = _limit_pct(sym)
            prev_close = df["close"].shift(1)
            # 首日无前收: 以 open 为基准估算涨跌停
            prev_close = prev_close.fillna(df["open"])
            df["limit_up"] = (prev_close * (1 + pct)).round(2)
            df["limit_down"] = (prev_close * (1 - pct)).round(2)
            arr = np.zeros(len(df), dtype=BAR_DTYPE)
            arr["datetime"] = df["date"].map(_d_to_int).values.astype(np.int64)
            arr["open"] = df["open"].values
            arr["close"] = df["close"].values
            arr["high"] = df["high"].values
            arr["low"] = df["low"].values
            arr["volume"] = df["volume"].fillna(0).values
            arr["total_turnover"] = df.get("amount", pd.Series(0.0, index=df.index)).fillna(0).values
            arr["limit_up"] = df["limit_up"].values
            arr["limit_down"] = df["limit_down"].values
            bars_by_oid[_sym_to_oid(sym)] = arr
            symbols.append(sym)
            all_days.extend(arr["datetime"].tolist())
        return bars_by_oid, set(all_days), symbols

    @staticmethod
    def _make_instrument(sym: str) -> Instrument:
        oid = _sym_to_oid(sym)
        exch = _exchange(sym)
        board = "ChiNext" if sym.startswith("300") else ("STAR" if sym.startswith("688") else exch)
        dic = {
            "order_book_id": oid,
            "symbol": sym,
            "type": "CS",
            "listed_date": "2000-01-01",
            "de_listed_date": "2999-12-31",
            "round_lot": 100,
            "market_tplus": 1,
            "exchange": exch,
            "board_type": board,
            "status": "Active",
            "special_type": "Normal",
            "sector_code_name": "",
            "industry_name": "",
            "contract_multiplier": 1,
        }
        return Instrument(dic)

    # ---------- 覆盖基类会出问题的点 ----------
    def available_data_range(self, frequency):
        return self._date_bounds[0], self._date_bounds[1]

    def current_snapshot(self, instrument, frequency, dt):
        bar = self.get_bar(instrument, dt, "1d")
        if bar is None:
            return None
        dt_str = str(int(bar["datetime"]))
        return {
            "datetime": pd.to_datetime(dt_str[:8], format="%Y%m%d"),
            "open": float(bar["open"]), "close": float(bar["close"]),
            "high": float(bar["high"]), "low": float(bar["low"]),
            "volume": float(bar["volume"]), "last": float(bar["close"]),
            "limit_up": float(bar["limit_up"]), "limit_down": float(bar["limit_down"]),
            "prev_close": float(bar["open"]),
        }


def build_data_source(data_dir: str, oids: list = None, start: str = None, end: str = None) -> CsvDataSource:
    return CsvDataSource(data_dir, oids=oids, start=start, end=end)
