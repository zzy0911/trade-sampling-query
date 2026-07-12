# “四下”贸易抽样调查数据查询

面向企业内部网络的轻量 B/S 数据查询系统。当前第一版已实现：

- 按“两区合计 / 江北新区 / 浦口区”和四个行业查询季度同比趋势；
- 查询指定年份、季度的行业汇总和样本单位明细；
- 管理员登录、Excel 导入、导入记录查看；
- 样本单位本季度、上年同期和增幅说明在线修改；
- SQLite 本地存储，无前端构建步骤，也不依赖外网图表服务。

## 1. 环境准备

建议使用 Python 3.11 或更高版本。

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

不安装 Python 的 Windows 用户可直接前往 GitHub 仓库的 Releases 页面，下载
`trade-query-v0.1.0-windows-x64.zip`。完整解压后双击 `TradeQuery.exe` 即可使用。
发行包不包含业务数据；数据始终保存在程序旁的 `data/` 目录中。

## 2. 导入现有测试数据

```powershell
python -m scripts.import_excel "D:\path\to\JBXQ2026年数据.xlsx" --district "江北新区"
python -m scripts.import_excel "D:\path\to\PKQ2026年数据.xlsx" --district "浦口区"
```

文件名含有四位年份时会自动识别；也可以通过 `--year 2026` 明确指定。

## 3. 启动服务

在当前电脑上可以直接双击项目根目录的 `启动系统.cmd`，它会启动服务并打开浏览器。

也可以从命令行启动：

```powershell
python run.py
```

本机访问：<http://127.0.0.1:8000>。同一局域网内其他电脑使用 `http://本机IP:8000` 访问。若 Windows 防火墙拦截端口，需要由运维人员为该服务配置入站规则。

首次启动的默认管理员账户：

- 账户：`admin`
- 密码：`admin123`

正式使用前可直接修改现有测试数据库的管理员密码：

```powershell
python -m scripts.set_admin_password
```

也可以在数据库首次初始化前通过环境变量设置账户和密码：

```powershell
$env:ADMIN_USERNAME = "trade-admin"
$env:ADMIN_PASSWORD = "请替换为高强度密码"
python run.py
```

管理员密码只在数据库首次初始化时写入，后续修改环境变量不会覆盖既有密码；修改既有库请使用上面的密码脚本。数据文件默认位于 `data/trade_query.db`，上传的原始 Excel 归档在 `data/uploads/`；整个 `data/` 目录已排除在 Git 之外。

## 4. 数据口径

- 行业代码 `51` / `52` / `61` / `62` 开头依次对应批发业、零售业、住宿业、餐饮业。
- 批发、零售使用“商品销售额”；住宿、餐饮使用“营业额”。
- 同比增速按 `(本季度 - 上年同期) / 上年同期 × 100%` 计算。
- 首页“全行业合计”会把四个行业各自的调查指标按源表单位直接汇总。
- 单位代码以文本存储；对 Excel 数值单元格按其 15 位有效数字显示值恢复，不会把 18 位编码当作 JavaScript 数字处理。
- 上年同期为 0 时，同比显示为空，不进行除零计算。
- 样例二季度“增幅超20%企业解释”中的 `#NAME?` 不导入，避免把源表公式错误带入数据库。

## 5. 测试

```powershell
python -m unittest discover -v
```

## 项目结构

```text
trade_query/       数据库、Excel 导入和 HTTP 服务
static/            三个浏览器页面及本地图表
scripts/           命令行导入工具
tests/             核心逻辑测试
run.py             服务启动入口
```

当前版本是可运行的 MVP。正式上线前建议补充 HTTPS 反向代理、单位统一身份认证、操作审计和数据库备份策略。
