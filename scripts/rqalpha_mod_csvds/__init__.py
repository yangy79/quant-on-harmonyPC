# -*- coding: utf-8 -*-
"""rqalpha_mod_csvds 包入口 (仿官方 rqalpha_mod_sys_* 结构)"""

__config__ = {
    # CSV 数据目录(绝对路径), 内含 <symbol>.csv: date,open,close,high,low,volume,turnover,amount
    "data_dir": None,
}


def load_mod():
    from .mod import CsvDataMod
    return CsvDataMod()
