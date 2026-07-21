# Park A 股长期投委会面板

这是仓库中的产品层：读取经过质量门的数据快照，输出组合投委会、公司研报、证据、版本差异、会员权限和发布包。完整产品定位、边界与架构见仓库根目录 [README](../README.md)。

## 本地启动

从仓库根目录执行：

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r product/requirements.txt
python3 product/server.py --host 127.0.0.1 --port 8877
```

打开 <http://127.0.0.1:8877>。运行数据库默认位于 `product/runtime/investment_dashboard_v2.db`，不会提交 Git。fresh clone 首次启动只建立 `DEMO` 结构和 8 股演示首页，不包含历史 verified 深研、DeepSeek 批准或发布包。

不要在真实库上使用 `--reset-demo`；该参数只用于重建演示数据库。

## 数据与研究工作流

### 验收 canonical 数据基座

    python3 scripts/verify_data_foundation.py
    python3 -m unittest product.tests.test_data_foundation -v

product/data_core/ 定义 data-foundation-v1：本地 SQLite adapter 用于 fresh-clone 和故障测试，PostgreSQL/Supabase migration 用于后续线上权威库。随仓库提供的 12 股 fixture 永远标记为 fixture，只证明 schema、quality gate、replay 和 restore，不代表实时行情。

### 更新真实快照

```bash
python3 product/refresh_engine.py --timeout 12
```

刷新前会归档当前研报。三类数据覆盖不完整时本次失败并保留上一合格快照；manifest 完全一致时标记 `reused`；新输入通过质量门后才激活新快照。

### 首批 8 股研究包

```bash
python3 product/batch_research.py --timeout 12
python3 product/batch_research.py --no-refresh
```

历史验收 runtime 中，宁德时代达到公司级 `verified / deep`，其余 7 股为明确披露的 `baseline / quantitative_baseline`；fresh clone 必须先重建真实快照与证据门才能恢复该状态。单股失败不会阻断其余股票，但只有 8/8 成功或复用时整批才是 `success`。

### 单独构建真实组合草稿

```bash
python3 product/real_pipeline.py --timeout 10
python3 product/real_pipeline.py --replay <snapshot-id>
```

采集范围是 8 只核心 A 股的腾讯行情、腾讯前复权日线和东方财富 F10 财务。覆盖不足 8/8 时不生成可批准草稿。

## DeepSeek 正文

前置条件是数据库已有通过质量门的 `verified` 报告与冻结证据集；DEMO 会按设计拒绝。满足前置条件后，密钥必须放在仓库外并通过环境变量传入：

```bash
export DEEPSEEK_API_KEY_FILE=/absolute/path/outside/repository/deepseek-key
export DEEPSEEK_MODEL=deepseek-v4-pro
python3 product/deepseek_writer.py 300750.SZ
python3 product/deepseek_writer.py 300750.SZ --status
```

DeepSeek 只收到冻结证据包。正文生成后必须经过 schema、指标来源、数字逐项和禁用表达校验，再由独立编辑使用 `--approve --reviewer ... --expected-narrative-hash ... --expected-evidence-manifest-hash ...` 批准。Key 不复制到项目、不写日志、不进入环境样例。

## 发布包

只有 `verified / deep`、证据集当前有效、正文已独立批准且仓位复核完成的研报才允许生成：

```bash
python3 -m pip install -r product/requirements.txt
cd product
npm ci
npx playwright install chromium
cd ..
python3 product/publication_pack.py 300750.SZ
python3 product/publication_pack.py --validate product/runtime/publication_packs/<pack-id>
```

成品包含独立 HTML、1200px 长图、A4 PDF、研报 JSON、渲染回执和 ZIP。Poppler（`pdfinfo` / `pdftotext`）是发布包 PDF 结构、页数、文字指纹校验的必需依赖。

渲染器可配置：

- `NODE_BINARY`：Node.js 可执行文件；默认从 PATH 查找。
- `NODE_MODULES`：Node modules 目录；默认 `product/node_modules`。
- `PLAYWRIGHT_PATH`：Playwright 模块路径；默认 npm 解析 `playwright`。
- `CHROME_PATH`：可选 Chromium/Chrome 路径；未设置时使用 Playwright 自带 Chromium。
- `PDFINFO_BINARY` / `PDFTOTEXT_BINARY`：Poppler 工具路径；默认从 PATH 查找。

## 私域会员

本地开发默认不开身份门。创建 owner 和邀请码：

```bash
python3 product/member_admin.py create-owner --email <owner-email> --name Park
python3 product/member_admin.py create-invite --owner-email <owner-email> --tier paid --max-uses 1 --valid-days 7
PARK_AUTH_REQUIRED=1 PARK_COOKIE_SECURE=0 python3 product/server.py --host 127.0.0.1 --port 8877
```

`preview` 只看首页，`member` 可看公司级研报，`paid` 可下载发布包，`owner` 才能刷新、批准、发布和管理会员。上述命令只用于本机 HTTP；公网必须使用 HTTPS，并改为 `PARK_COOKIE_SECURE=1`。

## API

只读：

- `GET /api/health`
- `GET /api/auth/me`
- `GET /api/dashboard`
- `GET /api/committee`
- `GET /api/stocks/{ticker}`
- `GET /api/reports/{ticker}`
- `GET /api/publications`
- `GET /api/refresh/status`
- `GET /api/report-versions/{ticker}`
- `GET /api/research/batches/latest`
- `GET /api/research/evidence/{ticker}`
- `GET /api/research/editorial-queue`
- `GET /api/research/editorial-status/{ticker}`
- `GET /api/publication-packs/latest`

写入：

- `POST /api/auth/login`
- `POST /api/auth/signup`
- `POST /api/auth/logout`
- `POST /api/refresh`
- `POST /api/publications/{id}/approve`
- `POST /api/publications/{id}/publish`

批准会锁定组合内容哈希；内容变化后原批准自动失效，发布请求会被拒绝。

## 自动化模板

`product/automation/*.plist` 是 LaunchAgent 模板，不是可直接安装的机器配置。使用前先按“本地启动”创建 `.venv`，并执行 `mkdir -p product/runtime`。然后把 `/ABSOLUTE/PATH/TO/equity-research` 替换为本机仓库绝对路径；发布模板还必须用 `command -v node`、`command -v pdfinfo`、`command -v pdftotext` 替换对应占位符。完成后再复制到 `~/Library/LaunchAgents/`。自动刷新不会调用或自动批准 DeepSeek。

## 验收

```bash
python3 -m unittest discover -s product/tests -q
python3 scripts/verify_baseline.py
python3 -m py_compile product/*.py
node --check product/render_publication.mjs
```

当前产品测试共 127 项，覆盖数据完整性、canonical schema、PIT 财务修订/公司行动、混合时区、复权/公司行动版本、增量 ingestion、source manifest/run 绑定、fixture→REAL 防升级、质量门到冻结的 TOCTOU、全 lineage provenance、可重放/恢复、版本身份、标准研报结构、跨市场币种与披露语义、缺失/不适用边界、前端消费字段类型、最终 API 再校验、无效 AI 降级、伪造引用、危险来源链接、故障隔离、研究质量门、审批失效、发布包篡改、权限提升、CSRF、session 撤销和 HTTP 安全头。

标准化报告接口遵循 [`research-report-v1`](../docs/product/research-report-v1.md)。`report_contract.module_manifest` 是 Web、移动和发布包的唯一章节顺序来源；客户端遇到未知或乱序版本必须 fail closed。

## 当前限制

本地 SQLite 和会员层适合自己与少数朋友私域内测。PostgreSQL/Supabase schema 已定义但尚未线上部署；正式公网商业化仍需执行 migration、配置 RLS/Storage/备份，并补齐邮件找回/二次验证、支付订阅、全市场候选池、正式公司行动数据和长期影子回测。
