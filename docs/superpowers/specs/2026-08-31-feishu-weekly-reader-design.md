# Feishu Weekly K-line reader design

## Goal

让 K 线周报在飞书里成为可直接阅读的图文 newsletter。读者不需要打开本地
HTML，也不需要看到 Markdown 图片语法或本地 snapshot 路径。

## Chosen approach

使用本机已认证的官方 `lark-cli` bot identity 上传每张真实 PNG，取得
`image_key`；使用 K 线周报专属 webhook 发送静态 `post` 富文本消息。Webhook
仍然是频道入口，CLI 只负责图片资源上传，不读取 Finance Daily。

不使用 interactive card 作为主体：44 张图和逐周期解释会超过卡片的舒适密度，且
卡片 Markdown 支持不完整。也不发送 `latest.html`，因为 webhook 消息不会执行
本地 HTML。

## Reader structure

1. 一条封面消息：报告周期、图表覆盖、数据边界。
2. 五条按资产分组的图文消息：钱的价格、风险资产、加密资产、亚洲与 A 股、实物资产。
3. 每个资产按 `资产身份 → 周线图/解释 → 日线图/解释 → 4 小时图/解释 →
   综合结论与市场含义` 排列。
4. 图表缺失时保留该周期的明确缺失说明，不换旧图，不伪造图片。

## Delivery and truth boundary

- CLI 凭据留在操作系统 keychain；仓库和日志不保存 token 或 secret。
- 只上传当前报告引用的 PNG，上传失败或 webhook 失败即生成 failed receipt，
  不静默退回链接文本。
- receipt 记录 report ID、内容 hash、消息数、上传图片数和状态。
- 这是研究阅读输出，不连接券商、不自动执行交易。

## Acceptance

- 飞书消息正文不出现 `![...]` 或 `snapshots/...` 本地路径。
- 真实 PNG 以内嵌图片显示，图片顺序与报告周期顺序一致。
- 发送结果可由 receipt 和 CLI/API 返回共同核验。
