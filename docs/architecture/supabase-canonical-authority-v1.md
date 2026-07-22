# Supabase Canonical Authority v1

状态：A2 implementation
合同版本：`canonical-authority-v1`

## User outcome

所有正式 market、fundamental、document、estimate 和 event 数据，以及它们的 raw JSON/HTML/PDF，都拥有唯一、私有、可迁移和可备份的生产位置。客户端不能直接读写 authority；研究只会在后续读取通过质量门的 snapshot。

## Schema ownership

| Schema | Owns | Does not own |
|---|---|---|
| `market` | accepted market/fundamental records | ingestion state、文档、用户权限 |
| `research` | accepted documents、broker estimates、events | raw bytes、会员内容策略 |
| `control` | source manifests、runs、raw object metadata、accepted/rejected receipts、snapshot membership | 用户 Auth、研究正文 |
| Supabase Storage | private `canonical-raw` raw bytes | normalized/canonical facts |

所有 canonical row 都以 `record_hash` 回指 `control.record_receipts`；receipt 再绑定 contract version、run、source manifest、raw capture 与 raw hash。每次 capture 保留实际 `source_url`。相同 raw bytes 只保存一个 content-addressed object，但每次获取都保存独立 capture，因此后续 run 可以复用 blob 而不丢失 provenance。A2 不允许 provider 直接写 domain table 而跳过这条链，accepted payload 缺字段或与 domain row 不一致也会由数据库 trigger 拒绝。

## Storage contract

Bucket：`canonical-raw`，`public=false`，单对象上限 50 MB，只允许 JSON、HTML、PDF。

```text
raw/sha256/{sha256-prefix}/{sha256}
```

路径由 `raw_storage_key()` 生成，只由 bytes 的 SHA-256 决定，因此相同内容跨 source、domain、日期和 MIME 声明都只对应一个 object。source URL、MIME、fetched_at 与 known_at 保存在每次独立的 domain-neutral raw capture；record domain 保存在 receipt，同一 capture 可以产生多域 records。URL、原始文件名和 ticker 均不能改变 blob identity。`..`、绝对路径、未知 MIME 与非 SHA-256 hash fail closed。

产品 migration 不直接改 Supabase-managed `storage.*` schema、trigger、grant 或 policy。`supabase/storage/canonical-raw.bucket.json` 是 desired-state contract；F5 部署用 backend service role 通过 Storage API 创建/核对 bucket。A2 不创建任何 client storage policy。

## RLS and service-role boundary

- `anon` 与 `authenticated` 对 `market / research / control` 无 schema/table/sequence privilege。
- 所有应用表启用 RLS，A2 不创建浏览器读取 policy；无 policy 即默认拒绝。
- 只有服务端 `service_role` 获得 schema usage 与 table/sequence 权限。该密钥只能存在于后台 secret store，不能进入浏览器、Git、日志或发布包。
- F1 才会为 member/editor/owner 定义产品级 policy；raw evidence 不因会员访问报告而自动开放。

## Migration and replay

生产 migration：`supabase/migrations/202607220001_canonical_authority.sql`。

验收在本地 PostgreSQL 16 中建立两个独立空 application database，模拟 Supabase 的 storage schema 与平台 roles，分别应用同一 migration + dev seed，并比较 tables 与 RLS schema signature；bucket desired-state JSON 另做独立 contract validation。测试还证明：

1. `anon` 读取 authority 被拒绝；
2. `service_role` 可以读取；
3. source manifest 更新被 append-only trigger 阻断；
4. 同一 raw blob 可由两个 run 分别 capture，blob 不重复、provenance 不丢失；
5. rejected receipt 不能进入 accepted domain table，MIME/path 不一致会被拒绝；
6. 两个空库产生相同 schema signature；
7. dev seed 只有一个 inactive fixture manifest，没有任何 market/research fact。

运行：

```bash
python3 -m pytest product/tests/test_supabase_schema.py -q
```

Docker 或本地 Postgres 只用于 migration acceptance，不是产品运行依赖。真正 Supabase project、region、backup 和 restore drill 分别属于 F3/F5；A2 不声称已经部署 production。
