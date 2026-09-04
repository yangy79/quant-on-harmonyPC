#!/bin/bash
# ============================================================
# Quant-on-HarmonyOS 一键安装脚本（分段可手动执行）
# 实测环境: HarmonyOS PC (ohos-aarch64, Python 3.12.9, musl)
# 用法: bash install_stack.sh [scipy|ml|torch|all]  默认 all
# ============================================================
set -u

export SSL_CERT_FILE=/etc/ssl/certs/cacert.pem
PY=${PY:-/data/storage/el1/bundle/libs/arm64/python/bin/python3}
SP=$HOME/.local/lib/python3.12/site-packages
# 签名工具路径按设备实际调整: find /data/service/hnp -name binary-sign-tool
SIG=${SIG:-/data/service/hnp/ohos-sdk.org/ohos-sdk_26.0.0.18/ohos/toolchains/lib/binary-sign-tool}
OH_SRC="https://pypi.repo.openharmony.cn/artifactory/api/pypi/openharmony-pypi-local/simple/"
CNB="https://pypi.cnb.cool/OpenHarmonyPCDeveloper/pypi/-/packages/simple"

[ -x "$SIG" ] || { echo "[ERR] binary-sign-tool 不存在, 请设置 SIG 环境变量"; exit 1; }

sign_all() {
  echo "== 签名所有 .so =="
  find "$SP" \( -name '*.so' -o -name '*.so.*' \) | while read -r s; do
    "$SIG" sign -inFile "$s" -outFile "$s" -selfSign 1 >/dev/null 2>&1 || echo "SIGN-FAIL $s"
  done
  echo "签名完成"
}

step_sci() {
  # --- 科学计算栈（matplotlib/pillow/h5py 走 OH 镜像）---
  echo "== [1/3] numpy/pandas 系统预置, 补 matplotlib/pillow/h5py =="
  $PY -m pip install --user --only-binary=:all: --index-url "$OH_SRC" \
      matplotlib==3.10.0 pillow h5py
  $PY -m pip install --user --no-deps cycler fonttools pyparsing packaging 2>/dev/null
  sign_all

  # --- scipy 必须 cnb NOFORTRAN ---
  echo "== [2/3] scipy 1.16.3 (cnb NOFORTRAN, 勿装 volces 1.17.1) =="
  $PY -m pip install --no-deps --index-url "$CNB" scipy==1.16.3
  sign_all

  # --- 修 _propack 包 bug + libopenblas 硬编码路径 ---
  echo "== [3/3] 修复 cnb scipy _propack =="
  python3 - "$SP" <<'PY'
import os, sys, glob, shutil
sp = sys.argv[1]
propack = os.path.join(sp, "scipy", "sparse", "linalg", "_propack")
# (a) 补 __init__.py
os.makedirs(propack, exist_ok=True)
init = os.path.join(propack, "__init__.py")
if not os.path.exists(init):
    with open(init, "w") as f:
        f.write("from . import _spropack\nfrom . import _dpropack\n"
                "from . import _cpropack\nfrom . import _zpropack\n")
    print("wrote", init)
# (b) 删顶层残次 .so
bad = os.path.join(os.path.dirname(propack),
                   "_propack.cpython-312-aarch64-linux-ohos.so")
if os.path.exists(bad):
    os.remove(bad); print("removed", bad)
# (c) libopenblas.so 硬编码路径
src = glob.glob(os.path.expanduser("~/.local/lib/python3.12/site-packages/scipy.libs/libscipy_openblas-*.so"))
if src:
    dst = os.path.expanduser("~/.local/lib/libopenblas.so")
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if not os.path.exists(dst):
        shutil.copy(src[0], dst); print("copied ->", dst)
PY
}

step_ml() {
  # --- 机器学习（镜像直装）---
  echo "== lightgbm / scikit-learn / numba / llvmlite =="
  $PY -m pip install --user --only-binary=:all: --index-url "$OH_SRC" \
      lightgbm==4.6.0 scikit-learn==1.8.0 numba==0.67.0 llvmlite==0.49.0
  sign_all
}

step_torch() {
  # --- torch CPU（本体镜像 + 纯依赖 PyPI 混装）---
  echo "== torch 2.11.0 CPU =="
  $PY -m pip install --user --no-deps --index-url "$OH_SRC" torch==2.11.0
  $PY -m pip install --user filelock typing-extensions sympy networkx jinja2 fsspec
  sign_all
}

step_data() {
  # --- 数据（akshare, lxml 走镜像）---
  echo "== akshare（lxml 镜像 + 本体 PyPI）=="
  $PY -m pip install --user --only-binary=:all: --index-url "$OH_SRC" lxml
  $PY -m pip install --user akshare
  sign_all
}

step_bt() {
  # --- 回测引擎 ---
  echo "== backtrader / vectorbt =="
  $PY -m pip install --user backtrader
  $PY -m pip install --user --no-deps vectorbt==0.28.5
  sign_all
}

step_rqalpha() {
  # --- rqalpha 6.3（混合源）---
  echo "== rqalpha 6.3.0 =="
  $PY -m pip install --user --only-binary=:all: --index-url "$OH_SRC" logbook simplejson wrapt
  $PY -m pip install --user six jsonpickle tabulate more-itertools methodtools rqrisk typing-extensions
  $PY -m pip install --user --no-deps rqalpha==6.3.0
  sign_all
}

step_pyqlib_deps() {
  # --- pyqlib 依赖（源码树本身见 docs/08）---
  echo "== pyqlib 依赖（pydantic 全家桶等）=="
  $PY -m pip install --user --only-binary=:all: --index-url "$OH_SRC" pydantic-core==2.46.5
  $PY -m pip install --user redis ruamel.yaml packaging loguru tqdm joblib dill filelock fire pyyaml python-redis-lock
  $PY -m pip install --user --no-deps pydantic==2.13.5 annotated-types typing-inspection python-dotenv pydantic-settings==2.15.0
  sign_all
}

case "${1:-all}" in
  sci)     step_sci ;;
  ml)      step_ml ;;
  torch)   step_torch ;;
  data)    step_data ;;
  bt)      step_bt ;;
  rqalpha) step_rqalpha ;;
  pyqlib)  step_pyqlib_deps ;;
  all)
    step_sci
    step_ml
    step_torch
    step_data
    step_bt
    step_rqalpha
    step_pyqlib_deps
    echo "== 全部完成，运行验证: python3 verify_stack.py =="
    ;;
  *) echo "用法: bash $0 [sci|ml|torch|data|bt|rqalpha|pyqlib|all]"; exit 1 ;;
esac
