# Park A 股长期投委会面板

当前为本地内测版：真实行情、前复权日线和财务数据已形成不可回写快照，规则引擎会输出股票名称、目标仓位、理由、风险与证据；DeepSeek 只负责基于证据包撰写中文深度正文；Park 批准后才允许发布。

## 启动

```bash
cd /Users/wendy/Documents/投研面板/product
python3 server.py
```

打开 <http://127.0.0.1:8877>。

不要在真实库上使用 `--reset-demo`；该参数只用于重建演示数据库。

## 一键更新真实研报

推荐使用统一更新入口；它会先存档当前研报，再采集、执行质量门、生成不可变快照、重算确定性研报并输出新旧差异：

```bash
cd /Users/wendy/Documents/投研面板
python3 product/refresh_engine.py --timeout 12
```

页面右上角刷新按钮调用同一条安全链路，不再只是重新加载页面。

## 一键生成首批 8 股研究包

批量入口只刷新一次 8 股共享的数据快照，然后逐股生成、校验和归档；某一只报告失败不会阻断其余 7 只：

```bash
cd /Users/wendy/Documents/投研面板
python3 product/batch_research.py --timeout 12
```

若只想从当前已经通过质量门的不可变快照重新生成研究包（不访问外部数据源）：

```bash
python3 product/batch_research.py --no-refresh
```

每次运行都会写入 `product/runtime/research_batches/<batch-id>/index.json`，并为每只股票生成独立 JSON 研报；`latest.json` 指向最近一次批量回执。完整批次必须满足 8/8 报告均通过各自研究深度的质量门：宁德时代为公司级 `verified/deep`，其余 7 股当前为如实披露的 `baseline/quantitative_baseline`；单股阻断或失败会令批次变为 `partial` 或 `failed`。

- 三类数据覆盖不完整：本次失败，继续显示上一快照。
- 输入 manifest 完全一致：标记 `reused`，不重复写快照和报告。
- 新输入通过质量门：生成新快照、报告版本和更新差异。
- DeepSeek：新证据会让旧稿失效；未经重新生成和独立编辑批准，不进入页面。

本机已安装工作日收盘后自动更新：周一至周五 `17:30`，LaunchAgent 为 `com.park.a-share-research-refresh`。运行凭证保存在数据库 `refresh_runs`，日志位于 `product/runtime/refresh-automation*.log`。

## 仅生成新一期真实组合草稿

```bash
cd /Users/wendy/Documents/投研面板/product
python3 real_pipeline.py --timeout 10
```

当前采集范围为 8 只核心 A 股：腾讯实时行情、腾讯前复权日线、东方财富 F10 主要财务指标。任一类覆盖不足 8/8 时整期失败，不会生成可批准草稿。

## 离线重放

```bash
cd /Users/wendy/Documents/投研面板/product
python3 real_pipeline.py --replay snap_real_e1347cc6b85b
```

重放只读取快照内存储的行情、日线和财务，不访问网络；评分、仓位、现金和市场状态必须与原版本一致。

## API

- `GET /api/health`
- `GET /api/auth/me`
- `GET /api/dashboard`
- `GET /api/committee`
- `GET /api/stocks/600519.SH`
- `GET /api/reports/300750.SZ`
- `GET /api/publications`
- `GET /api/refresh/status`
- `GET /api/report-versions/300750.SZ`
- `GET /api/research/batches/latest`
- `GET /api/research/evidence/300750.SZ`
- `GET /api/research/editorial-queue`
- `GET /api/research/editorial-status/300750.SZ`
- `GET /api/publication-packs/latest`
- `POST /api/auth/login`
- `POST /api/auth/signup`
- `POST /api/auth/logout`
- `POST /api/refresh`
- `POST /api/publications/{id}/approve`
- `POST /api/publications/{id}/publish`

批准会锁定组合内容哈希。批准后若组合内容发生变化，发布会被拒绝并将版本标记为 `invalidated`。

## 私域会员内测

本地开发默认不开身份门。准备给少数朋友使用时，先创建唯一 owner，再生成一次性或限次邀请码：

```bash
cd /Users/wendy/Documents/投研面板
python3 product/member_admin.py create-owner --email <owner-email> --name Park
python3 product/member_admin.py create-invite --owner-email <owner-email> --tier paid --max-uses 1 --valid-days 7
PARK_AUTH_REQUIRED=1 PARK_COOKIE_SECURE=1 python3 product/server.py --host 127.0.0.1 --port 8877
```

密码只通过隐藏输入读取；邀请码明文只在创建时显示一次。`preview` 只看首页，`member` 可看公司级研报，`paid` 还可下载发布包，`owner` 才能刷新、批准和发布。公网必须由 HTTPS 反向代理承接，并保持 `PARK_COOKIE_SECURE=1`。

成员停用会立即撤销现有会话：

```bash
python3 product/member_admin.py list-members --owner-email <owner-email>
python3 product/member_admin.py set-status --owner-email <owner-email> --member-email <member-email> --status suspended
python3 product/member_admin.py revoke-invite --owner-email <owner-email> --invite-id <invite-id>
```

## 生成私域发布包

只有 `verified/deep`、证据集当前有效、DeepSeek 正文通过独立编辑双哈希批准、且存在建议复核仓位的单股研报才允许生成：

```bash
python3 product/publication_pack.py 300750.SZ
python3 product/publication_pack.py --validate product/runtime/publication_packs/<pack-id>
```

成品包含独立 HTML、1200px 长图、A4 PDF、研报 JSON、渲染回执和 ZIP。构建使用跨进程锁和临时目录；相同研究身份复用既有成品，不会覆盖。PDF/PNG/HTML/回执均执行结构与身份校验；任何报告、证据、批准或渲染逻辑变化会使旧 `latest` 失效。工作日 `18:30` 的 LaunchAgent 为 `com.park.a-share-publication-pack`。

## 生成 DeepSeek 深度正文

Key 只保存在项目外部、权限为 `600` 的本地文件中：

```bash
cd /Users/wendy/Documents/投研面板
DEEPSEEK_API_KEY_FILE=/absolute/path/to/deepseek-key \
python3 product/deepseek_writer.py 300750.SZ --model deepseek-v4-pro
```

生成器只接受已经通过真实数据门和公司证据门的研报。公司证据门至少需要两份有日期的公司原始资料、一份独立交叉来源，并拒绝未来资料、过期资料和 UZI 聚合维度。生成器继续校验来源 ID、模型数字、段落完整性和快照一致性。生成稿绑定 `snapshot_id + profile_hash + research_logic_hash + evidence_set_id + evidence_manifest_hash`；任一项变化，旧稿自动失效且不会进入页面。

UZI 输出只导入为研究线索，不会自动升级为事实：

```bash
python3 product/research_evidence.py import-uzi /path/to/raw_data.json
python3 product/research_evidence.py sync-profile 300750.SZ --capture
python3 product/research_evidence.py build-set 300750.SZ <snapshot-id> --knowledge-cutoff <ISO-time>
```

`--capture` 会保存不可修改的原始 PDF/HTML，并把原文 SHA256、抓取时间、MIME、HTTP 状态和规范 URL 写入证据 manifest。只有可信公司/交易所/监管域名可成为 primary/company release，独立来源使用受控域名白名单；聚合器和没有原文快照的 URL 只能保留为 lead。

生成后先查看待审哈希：

```bash
python3 product/deepseek_writer.py 300750.SZ --status
```

独立编辑确认正文与证据清单后，必须提交自己实际看过的两个哈希；哈希不一致即拒绝批准：

```bash
python3 product/deepseek_writer.py 300750.SZ --approve \
  --reviewer "editor name" \
  --expected-narrative-hash <narrative-hash> \
  --expected-evidence-manifest-hash <evidence-manifest-hash>
```

## 验证

```bash
cd /Users/wendy/Documents/投研面板/product
python3 -W error::ResourceWarning -m unittest discover -s tests -v
node --check static/app.js
python3 -m py_compile data_store.py deepseek_writer.py research_artifact_store.py research_reports.py report_versions.py refresh_engine.py ingest_quotes.py real_pipeline.py server.py auth_store.py publication_pack.py member_admin.py
```

运行数据库位于 `product/runtime/investment_dashboard_v2.db`，不提交 Git。当前会员层适合少数朋友私域内测；正式公网商业化仍应迁移 Supabase/PostgreSQL + RLS，补齐邮件找回/二次验证、支付订阅、全市场候选池、正式公司行动数据和长期影子回测。
