#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修复 cnb.cool scipy 1.16.3 的 _propack 打包瑕疵 + libopenblas 硬编码路径

背景见 docs/03 §3.3。三件事:
  (a) 补 scipy/sparse/linalg/_propack/__init__.py（回导出子模块）
  (b) 删顶层抢名的残次 _propack.cpython-312-aarch64-linux-ohos.so
  (c) 复制 scipy.libs/libscipy_openblas-*.so 到 ~/.local/lib/libopenblas.so
      （_propack.so 硬编码 NEEDED 该绝对路径）

用法: python3 fix_scipy_propack.py
"""
import os
import glob
import shutil
import site

SP = os.environ.get("SP") or site.getusersitepackages()


def main():
    propack_dir = os.path.join(SP, "scipy", "sparse", "linalg", "_propack")

    # (a) __init__.py
    os.makedirs(propack_dir, exist_ok=True)
    init = os.path.join(propack_dir, "__init__.py")
    if not os.path.exists(init):
        with open(init, "w") as f:
            f.write("from . import _spropack\n"
                    "from . import _dpropack\n"
                    "from . import _cpropack\n"
                    "from . import _zpropack\n")
        print("[a] wrote", init)
    else:
        print("[a] already ok:", init)

    # (b) 顶层残次 .so
    bad = os.path.join(os.path.dirname(propack_dir),
                       "_propack.cpython-312-aarch64-linux-ohos.so")
    if os.path.exists(bad):
        os.remove(bad)
        print("[b] removed", bad)
    else:
        print("[b] nothing to remove")

    # (c) libopenblas.so
    src = glob.glob(os.path.join(SP, "scipy.libs", "libscipy_openblas-*.so"))
    if src:
        dst = os.path.expanduser("~/.local/lib/libopenblas.so")
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if not os.path.exists(dst):
            shutil.copy(src[0], dst)
            print("[c] copied ->", dst)
        else:
            print("[c] already exists:", dst)
    else:
        print("[c] WARN: 未找到 scipy.libs/libscipy_openblas-*.so")

    # 验证
    try:
        from scipy.sparse.linalg import svds
        import scipy.sparse as sp
        svds(sp.random(40, 30, density=0.3, random_state=0), k=3)
        print("验证: sparse.linalg.svds OK ✅")
    except Exception as e:
        print("验证失败:", type(e).__name__, e)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
