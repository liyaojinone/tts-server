# 便携 Python 运行时

完整运行包的 Python 布局由 `PortableRuntimeLayout` 统一定义：

- 唯一解释器：`runtime/python/cp311/python.exe`；
- 网关依赖：`runtime/gateway/.venv/Lib/site-packages`；
- 服务依赖：`services/<service>/.venv/Lib/site-packages`。

当前阶段保留已验证的 `.venv` 目录作为依赖文件位置，但不会执行其中的
`Scripts/python.exe`。Windows venv 启动器和 `pyvenv.cfg` 会记录创建该环境时的
绝对 Python 路径，不能作为可搬运发布包的解释器。

后续启动引导器将显式加入所需依赖和仓库内源码路径，并跳过 editable `.pth`；这样
服务目录被复制或移动后，也不会读取原开发机的绝对路径。
