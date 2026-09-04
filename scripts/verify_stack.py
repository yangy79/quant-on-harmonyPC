#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Quant-on-HarmonyOS 分层冒烟验证脚本
用法: python3 verify_stack.py
预期: 全部分层打印 OK / PASS
"""
import os
os.environ.setdefault("SSL_CERT_FILE", "/etc/ssl/certs/cacert.pem")
ok = True


def check(name, fn):
    global ok
    try:
        fn()
        print(f"[PASS] {name}")
    except Exception as e:
        ok = False
        print(f"[FAIL] {name}: {type(e).__name__}: {e}")


# ---------- 第 1 层: 科学计算栈 ----------
def l1():
    import numpy, pandas, scipy, matplotlib, PIL, h5py
    assert numpy.__version__ == "2.2.6", numpy.__version__
    assert pandas.__version__ == "2.2.3", pandas.__version__
    print(f"  numpy {numpy.__version__} / pandas {pandas.__version__} / "
          f"scipy {scipy.__version__} / matplotlib {matplotlib.__version__} / "
          f"Pillow {PIL.__version__} / h5py {h5py.__version__}")

    # scipy 全功能
    import numpy as np
    from scipy.linalg import eig, solve
    from scipy.optimize import minimize, root
    from scipy.integrate import quad
    from scipy.sparse.linalg import svds
    import scipy.sparse as sp
    from scipy import stats, fft
    w, _ = eig(np.diag([3., -1., 5.]))
    assert abs(w.max()) == 5.0
    solve([[3, 2], [1, 4]], [1, 2])
    minimize(lambda v: (v[0]-3)**2 + (v[1]+2)**2, [0, 0])
    root(lambda x: [x[0]+x[1]-2, x[0]-x[1]-8], [0, 0])
    quad(lambda t: np.exp(-t**2), 0, 1)
    svds(sp.random(40, 30, density=0.3, random_state=0), k=3)   # propack 路径
    stats.norm.cdf(0)
    fft.fft(np.arange(1, 11))
    # matplotlib + Pillow 出图回读
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(); ax.plot([1, 2, 3], [1, 4, 2])
    fig.savefig(os.path.expanduser("~/.cache/_v.png"), dpi=80)
    PIL.Image.open(os.path.expanduser("~/.cache/_v.png"))


# ---------- 第 2 层: ML / DL ----------
def l2():
    import lightgbm, sklearn, numba, llvmlite
    print(f"  lightgbm {lightgbm.__version__} / sklearn {sklearn.__version__} / "
          f"numba {numba.__version__} / llvmlite {llvmlite.__version__}")
    from numba import njit
    @njit
    def f(x): return x * 2 + 1
    assert f(21) == 43

    import torch
    print(f"  torch {torch.__version__} (threads={torch.get_num_threads()})")
    a = torch.randn(64, 64); b = torch.randn(64, 64)
    assert (a @ b).shape == (64, 64)
    m = torch.nn.Linear(4, 1)
    opt = torch.optim.SGD(m.parameters(), lr=0.01)
    loss = torch.nn.functional.mse_loss(m(torch.randn(8, 4)), torch.randn(8, 1))
    loss.backward(); opt.step()
    import numpy as np
    assert torch.from_numpy(np.arange(6).reshape(2, 3)).shape == (2, 3)


# ---------- 第 3 层: 数据 / 回测 / 因子 ----------
def l3():
    import akshare as ak
    print(f"  akshare {ak.__version__}")
    import backtrader
    print(f"  backtrader {backtrader.__version__}")
    import vectorbt
    print(f"  vectorbt {vectorbt.__version__}")
    import rqalpha
    print(f"  rqalpha {rqalpha.__version__}")
    import lightgbm  # noqa  (pyqlib 需源码树装配, 见 docs/08)


check("科学计算栈 (numpy/pandas/scipy/matplotlib/PIL/h5py + scipy 全功能)", l1)
check("ML/DL (lightgbm/sklearn/numba-JIT/torch-CPU)", l2)
check("数据/回测 (akshare/backtrader/vectorbt/rqalpha)", l3)

print()
print("=== 验证完成:", "全部 PASS ✅" if ok else "存在 FAIL ❌, 对照 docs/11 排查 ===")
raise SystemExit(0 if ok else 1)
