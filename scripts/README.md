# scripts/ —— 一键脚本

> 全部在本机（HarmonyOS PC, ohos-aarch64）实测通过。用法详见 `docs/` 对应章节。

| 文件 | 用途 | 说明 |
|---|---|---|
| `install_stack.sh` | 分层安装全部依赖 | `bash install_stack.sh` 全装；或分段 `[sci\|ml\|torch\|data\|bt\|rqalpha\|pyqlib]`。安装前请先按 docs/01 核对 `SIG` 签名工具路径 |
| `verify_stack.py` | 分层冒烟验证 | `python3 verify_stack.py`，三层全 PASS 即环境就绪（本机实测输出见 docs/10） |
| `fetch_tencent.py` | 腾讯源 A 股日线抓取 | **纯 urllib 零依赖**，不需要装 akshare。`python3 fetch_tencent.py`（内置 15 只篮子）或 `python3 fetch_tencent.py 600519 000858`。自动分段抓满全区间、CSV 缓存、3 次重试 |
| `fix_scipy_propack.py` | 修复 cnb scipy 的 _propack 打包瑕疵 | 装完 `scipy==1.16.3`（cnb NOFORTRAN）后必跑，否则 sparse 相关 import 链断 |
| `rqalpha_mod_csvds/` | rqalpha 自定义 mod 包 | 喂本地 CSV 绕开 rqdatac/h5 bundle。拷贝到回测工作目录，config 里 `"mod": {"csvds": {"enabled": True, "data_dir": "data"}}`（详见 docs/07） |
| `qlib_pure_py_libs/` | pyqlib Cython 扩展的纯 numpy 替代 | 复制 `rolling.py` / `expanding.py` 到 qlib 源码树 `qlib/data/_libs/`（与 .pyx 同名共存，.py 优先加载）。误差与 Cython 版 < 1e-12（详见 docs/08） |

## 快速验证环境是否就绪

```bash
# 1. 科学栈 & ML & 回测引擎
python3 verify_stack.py          # 预期: 三层全部 PASS

# 2. 数据（任选其一）
python3 fetch_tencent.py 600519  # 纯 urllib 直拉（推荐, 零依赖）
# 或
python3 -c "import akshare as ak; df = ak.stock_zh_a_hist_tx(symbol='600519', start_date='20230101', end_date='20260901', adjust='qfq'); print(df.tail(3))"
```
