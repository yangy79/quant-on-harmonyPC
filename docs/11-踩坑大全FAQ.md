# 11 · 踩坑大全 FAQ（按症状索引）

> 全部为真机实测踩过的坑。按"你看到什么 → 原因 → 解法"组织，遇到问题先查这里。

---

## A. 安装 / 环境类

### A1. pip install 报证书错 / 网络断流
- **原因**：鸿蒙无系统 CA 证书库，https 校验失败
- **解法**：`export SSL_CERT_FILE=/etc/ssl/certs/cacert.pem`（建议写进 shell 配置）

### A2. "Could not find a version that satisfies the requirement"（装编译型包）
- **原因**：默认 PyPI 的 manylinux/musllinux wheel 平台标签不匹配 ohos_aarch64
- **解法**：改用 OH 镜像 `--index-url "$OH_SRC" --only-binary=:all:`；若镜像也没有，按 docs/01 §1.4 判定铁律走纯 PyPI 或源码树

### A3. `python3 -m venv` 失败
- **原因**：鸿蒙禁止符号链接，venv 依赖 symlink
- **解法**：不用 venv，`pip install --user`；要隔离用 `--target` + `PYTHONPATH`

### A4. import 报 `signature verification failed`
- **原因**：`.so` 未签名（或签名被覆盖）
- **解法**：重跑签名循环（docs/02 §2.4），签名幂等无害

### A5. 装完编译型包后某功能还是崩
- **原因**：可能装到了 noexec 分区（工作区），或漏签
- **解法**：确保装到 `~/.local`（HOME），重签；工作区里的包删掉重装

### A6. `rm` / `ln` 报 bad interpreter / 权限错
- **原因**：这些命令的 shim 解释器在部分环境坏掉
- **解法**：用 Python 做文件操作：`os.remove()` / `os.symlink()` / `shutil`，别用 rm/ln

### A7. 某纯 Python 包在 OH 镜像装不上
- **原因**：OH 镜像只收录有 ohos wheel 的包，纯 Python 包很多没收录
- **解法**：从官方 PyPI 直装（`pip install --user <pkg>`）

---

## B. scipy / 科学计算类

### B1. scipy import 成功，但一调用就 segfault
- **原因**：装了 volces 的 scipy 1.17.1——捆绑的 libgfortran 在本机 dlopen 即段错误
- **解法**：卸载，改装 cnb.cool 的 `scipy==1.16.3`（NOFORTRAN 构建，docs/03 §3.3）

### B2. `ImportError: cannot import name '_spropack' from 'scipy.sparse.linalg._propack'`
- **原因**：cnb scipy 1.16.3 的打包瑕疵（_propack 目录缺 `__init__.py` + 顶层残次 .so 抢名）
- **解法**：docs/03 §3.3 修复步 (a)(b)：补 `__init__.py` 回导出 + 删顶层残次 .so

### B3. `Error loading shared library .../libopenblas.so`
- **原因**：cnb 的 `_propack.so` 硬编码 NEEDED 绝对路径 `~/.local/lib/libopenblas.so`，该文件不存在
- **解法**：从 `scipy.libs/libscipy_openblas-*.so` 复制过去并重签（docs/03 §3.3）

### B4. matplotlib 中文乱码（方块）
- **原因**：matplotlib 默认不扫 /system/fonts，且字体内部名 ≠ 文件名
- **解法**：显式注册并取内部名：
```python
from matplotlib import font_manager
font_manager.fontManager.addfont("/system/fonts/FZHeiT-SC-Regular.ttf")
plt.rcParams["font.family"] = font_manager.FontProperties(
    fname="/system/fonts/FZHeiT-SC-Regular.ttf").get_name()
# 内部名是 FZHeiT-SC（不是 FZHeiT-SC-Regular！）
```

### B5. matplotlib 报无显示设备
- **解法**：脚本开头 `matplotlib.use("Agg")`，出图存文件

---

## C. 数据获取类

### C1. akshare 东财接口报 Connection aborted / RemoteDisconnected
- **原因**：东财对本机出口 IP 直接拒连
- **解法**：换腾讯源 `ak.stock_zh_a_hist_tx`（docs/05）；无解，别重试

### C2. akshare 新浪接口报 py_mini_racer 相关错
- **原因**：`stock_zh_a_daily` 依赖 JS 引擎 py_mini_racer（无 ohos wheel）
- **解法**：不用新浪源；py_mini_racer 缺失不影响腾讯源

### C3. 腾讯源 amount/volume 算出的 vwap 超出当日高低点
- **原因**：qfq 价与 amount 不是同一复权口径
- **解法**：用典型价 `vwap=(high+low+close)/3` 代理

### C4. qlib dump 时 CSV 文件名不对
- **解法**：文件名必须 `sh600519.csv` / `sz000858.csv`（6→sh，0/3→sz）

---

## D. rqalpha 类

### D1. 回测秒完成、零交易、无任何报错（最隐蔽！）
- **原因**：bar 的 datetime 只存了 8 位 YYYYMMDD，rqalpha 内部 `searchsorted` 定位恒落数组尾部 → history_bars 永远返回最后 N 根 → MA 恒定 → 信号永不触发
- **解法**：datetime 用 `convert_date_to_int` 的 **12 位编码**（YYYYMMDD000000），docs/07 §7.3.3

### D2. logger 输出的 %s 原样显示
- **原因**：rqalpha user_log 不支持 `%s` 占位
- **解法**：用 f-string

### D3. pickle.load 读 analyser 输出报错/乱码
- **原因**：output_file 是原生 pickle（不是 jsonpickle）
- **解法**：`pickle.load` 直接读

### D4. summary 的 sharpe/alpha 是 NaN
- **原因**：无 benchmark 时 risk-free 缺失
- **解法**：不影响撮合；展示用日净值 `nav.pct_change()` 重算年化

### D5. rqalpha 默认数据源报 h5 bundle 路径错误
- **原因**：没注入自定义 mod，main.run 构造了默认 BaseDataSource
- **解法**：自定义 mod 在 start_up 里 `env.set_data_source()`（docs/07 §7.3）

---

## E. pyqlib 类

### E1. `pip install qlib` 后 import 报缺模块
- **原因**：装到空壳假包了（qlib 0.0.2.dev20，真包叫 pyqlib）
- **解法**：卸载假包，走源码树装配（docs/08）

### E2. import qlib 报缺编译模块（rolling/expanding 相关）
- **原因**：qlib 的 2 个 Cython 扩展没编译
- **解法**：`_libs/` 下新建同名 `.py` 纯 numpy 替换（docs/08 §8.3-A）

### E3. `qlib.init()` 报 mlflow 相关错
- **原因**：config.register() 硬 import qlib.workflow → mlflow
- **解法**：patch register() 的 recorder 段 try/except（docs/08 §8.3-B）

### E4. 装 pydantic-settings 时 pip 尝试编译 pydantic-core 失败
- **原因**：pydantic-settings 依赖 Rust 扩展 pydantic-core
- **解法**：先从 OH 镜像装 `pydantic-core==2.46.5`，再 `--no-deps` 装 pydantic 2.13.5 + settings 2.15.0（版本强绑定）

### E5. dump_bin.py 跑 CSV dump 报 pickle 绑定方法错
- **原因**：原脚本用 ProcessPoolExecutor 提交绑定方法，spawn 模式无法 pickle
- **解法**：换成 ThreadPoolExecutor（docs/08 §8.3-C）

### E6. qlib 脚本用 heredoc 跑报 FileNotFoundError: <stdin>
- **原因**：qlib 数据层内部多进程 spawn，从 stdin 无法重新导入主模块
- **解法**：所有 qlib 脚本写成 `.py` 文件 + `if __name__ == "__main__":` 守卫

### E7. `qlib.init(..., default_conf="local")` 报错
- **原因**：0.9.7 的 MODE_CONF 没有 "local" key
- **解法**：不传 default_conf，默认 client 即本地读

---

## F. 通用类

### F1. 下载 GitHub/文件慢或失败
- **解法**：`curl -sL --cacert /etc/ssl/certs/cacert.pem` 或 python urllib；可让有网机器代下后拷入

### F2. getcwd 报 "Invalid argument" 类错误（shell 提示）
- **原因**：部分目录切换后 shell 的 cwd 失效（鸿蒙 shell 特性）
- **解法**：无害；命令里用绝对路径，必要时 `cd` 到 HOME 再跑

### F3. 新复制的 .so 报无法加载
- **解法**：对复制出的新文件重新签名一次

---

## 兜底检查顺序（什么都失败时）

```
1. export SSL_CERT_FILE=/etc/ssl/certs/cacert.pem  （网络错先查这个）
2. 包在不在 ~/.local？→ pip list --user
3. .so 签没签？→ 重跑签名循环
4. 版本对不对？→ 对照各章"版本锁"表格
5. 是不是装到 noexec 分区了？→ 卸载重装到 --user
6. 是不是该走源码树/纯 Python 路线？→ docs/01 §1.4 判定铁律
```

---

*至此 11 章完结。配合 [scripts/](../scripts/) 一键脚本使用。*
