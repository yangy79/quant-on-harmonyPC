# -*- coding: utf-8 -*-
"""rqalpha_mod_csvds: 用本地 CSV(腾讯源 qfq 日线) 替代 rqdatac 的自定义 mod

main.run 装配顺序: mod_handler.start_up() → 若无 data_source 才构造默认 BaseDataSource。
本 mod 在 start_up 阶段抢先 env.set_data_source() → 回测全程走内存 CSV 数据。
"""
import os

from rqalpha.interface import AbstractMod


class CsvDataMod(AbstractMod):
    def __init__(self):
        self._ds = None

    def start_up(self, env, mod_config):
        from .datasource import build_data_source

        data_dir = getattr(mod_config, "data_dir", None)
        if not data_dir or not os.path.isdir(data_dir):
            raise ValueError(f"[csvds] data_dir not found: {data_dir!r}")
        start = getattr(env.config.base, "start_date", None)
        end = getattr(env.config.base, "end_date", None)
        self._ds = build_data_source(data_dir, start=str(start) if start else None,
                                     end=str(end) if end else None)
        env.set_data_source(self._ds)
        # 日志用 system logger 在 run 配置好之后才有, 直接 print 到 stderr
        n_ins = len(self._ds._grouped_instruments.get("CS", []))
        print(f"[csvds] 内存数据源就绪: {n_ins} 只股票, "
              f"日历 {self._ds._date_bounds[0]} ~ {self._ds._date_bounds[1]}", flush=True)

    def tear_down(self, code, exception=None):
        pass


def load_mod():
    return CsvDataMod()
