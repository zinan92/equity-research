# Generalized Ingestion Core v1

状态：A3 implementation
合同版本：`generalized-ingestion-core-v1`

## User outcome

任意 market、fundamental、document、estimate、event provider 都能通过同一条可测试、可降级、可审计的 ingestion path 进入 canonical authority。用户侧未来看到的 summary 和深度研报不会直接依赖某个外部 repo 的临时 schema、缓存或实时接口。

## Scope

A3 交付的是 ingestion runtime，不是 provider 覆盖：

- one primary + explicit fallbacks；
- five-domain adapter contract harness；
- raw capture before parse，保证 parse failure 仍保留原始证据；
- quality gate，阻止 fixture/cached/stale data 被发布；
- local SQLite replay cache，永远不是 authority；
- Supabase authority sink adapter，使用 DB-API connection factory + Storage object adapter，不新增运行时依赖。

## Runtime flow

```text
FetchRequest
  -> SourceChoice(primary)
  -> adapter.fetch()
  -> build RawCapture from bytes
  -> adapter.parse()
  -> validate RecordEnvelope contract
  -> quality gate
  -> persist live attempt to authority
  -> promote only when real + quality passed
  -> otherwise try explicit fallback
  -> if all live sources fail, try SQLite cache as degraded read-only fallback
```

`fixture` 和 `cached` records 可以用于本地调试、演示或降级查看，但不能成为 publishable output。runtime cache 的 `authority` 固定为 `False`；若注入的 cache 声称自己是 authority，runtime 初始化直接拒绝。

## Authority sink

`SupabaseAuthoritySink` 不直接绑定 Supabase SDK。它要求调用方提供：

- DB-API compatible `connection_factory`
- object storage adapter with `put_if_absent(bucket, path, body, content_type)`

一次 live attempt 持久化顺序：

1. 上传 content-addressed raw bytes 到 private `canonical-raw` bucket。
2. 插入 source manifest。
3. 插入 ingestion run。
4. 插入或校验 raw object metadata。
5. 插入 raw capture。
6. 插入 accepted/rejected record receipts。
7. 仅当 attempt `promote=True` 时插入 domain rows。

cached 和 fixture attempt 不会由 runtime 写入 authority，sink 也会拒绝二者作为防线。fixture primary 不会中断 fallback；runtime 会继续尝试后续 real fallback。degraded live attempt 仍保留 run/raw/capture；若 records 是 accepted 但未通过 quality/promotion gate，不写入 `control.record_receipts`，避免后续 snapshot builder 把 stale accepted receipt 误当 canonical fact。rejected records 仍可作为失败审计 receipt 保存。

Document accepted payload 必须绑定同一份 raw capture：`content_hash == raw.raw_hash` 且 `storage_uri == raw.storage_uri`。若一个索引页引用另一份 PDF blob，后续 provider 必须建模成两次 capture，而不是用单条 receipt 指向两份 raw。

## Reuse boundary

A3 复用 datafeed 的核心思想：explicit manifest、port/adapter boundary、provenance first、quality gate、fallback。没有整仓复制 datafeed，也没有把它的 SQLite/cache 当作 production authority。

UZI-Skill 仍只作为 report/rendering/reference，不参与 A3 ingestion authority path。

## Verification

Focused command：

```bash
python3 -m pytest product/tests/test_ingestion_core.py -q
```

覆盖点：

- five-domain adapter harness；
- content-addressed raw path；
- wrong-domain and invalid adapter output fail closed；
- primary failure/timeout style fallback；
- quality-block fallback；
- SQLite cache degraded fallback and non-authority boundary；
- duplicate adapter rejection；
- Supabase sink raw upload and SQL emission；
- degraded accepted attempts do not insert receipts or domain rows；
- cached attempts are rejected by authority sink；
- fixture attempts are rejected by authority sink；
- fixture primary does not abort real fallback；
- document record content identity must match raw capture identity；
- parse failure still persists raw capture；
- live adapter responses mislabeled as cached are failed but still keep raw audit；
- fixture data never promotes.

## Gotchas

- raw capture must be built before parse. If parse throws and raw is lost, the system cannot audit provider bytes that broke the parser.
- local cache must not be persisted as authority, even when it parses cleanly. It is only a degraded last-known view.
- fixture attempts need two defenses: runtime skips authority persistence so fallback can continue, and sink rejects fixture if called directly.
- non-publishable accepted records must not enter `control.record_receipts`; otherwise later snapshot code could accidentally treat them as accepted canonical facts.
- document record payloads cannot point to a different raw object than the capture proving the record.
- storing raw object before DB transaction can leave a content-addressed orphan blob if DB commit fails. This is acceptable because the path is deterministic and retryable.
- same bytes may feed multiple domains or runs. Dedup belongs to raw object identity, not to capture identity.
- provider adapters are not allowed to emit `cached`; only the runtime-owned local cache may mark a payload that way.
