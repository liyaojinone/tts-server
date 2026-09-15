# 便携 Python 运行时

完整运行包的 Python 布局由 `PortableRuntimeLayout` 统一定义：

- 唯一解释器：`runtime/python/cp311/python.exe`；
- 网关依赖：`runtime/gateway/.venv/Lib/site-packages`；
- 服务依赖：`services/<service>/.venv/Lib/site-packages`。

当前阶段保留已验证的 `.venv` 目录作为依赖文件位置，但不会执行其中的
`Scripts/python.exe`。Windows venv 启动器和 `pyvenv.cfg` 会记录创建该环境时的
绝对 Python 路径，不能作为可搬运发布包的解释器。

`runtime/portable_python_launcher.py` 会显式加入所需依赖和仓库内源码路径，并跳过
editable `.pth`；这样服务目录被复制或移动后，也不会读取原开发机的绝对路径。

网关已验证依赖 `pywin32`。它的 Windows DLL 目录通常由 `pywin32.pth` 补入；完整包
模式不读取该 `.pth`，而是显式加入同一包目录内的 `win32`、`win32/lib`、`pythonwin`
和 `pywin32_system32`。这四个路径都由当前服务根推导，不含开发机绝对路径。

## 发布与高级维护

发布组装时，在待压缩的 `BoboGenServer` 目录运行一次
`scripts/install-portable-python.ps1`，随后把生成的
`runtime/python/cp311` **连同整个服务目录一起压缩**。该目录的二进制被 Git 忽略，
但不是发布包可省略的内容；最终用户只需解压完整包，不运行这个脚本，也不安装系统
Python。

`install.ps1` 仍是运行中心的高级维护入口：它允许技术用户使用本机 Python 创建或
更新传统 `.venv`。完整包的默认启动路径不依赖这一入口，也不会执行这些 venv 中的
`Scripts/python.exe`。
