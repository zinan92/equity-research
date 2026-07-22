# Official Filing Ingest v1

## User outcome

公司官方披露可以增量发现、下载为不可变 raw PDF，并以稳定 document identity 进入 canonical ingestion；新闻聚合页不能冒充官方 primary evidence。

## Reuse

B1 复用 A3 `IngestionRuntime`、A2 content-addressed raw storage contract 和 A4 ticker normalization，只新增官方披露 adapters 与少量 orchestration glue：

```text
CNINFO official index
  -> security identity check
  -> incremental known_document_ids filter
  -> CNINFO / SSE / SZSE / BSE official PDF adapter
  -> raw bytes + SHA-256 + MIME + HTTP/redirect metadata
  -> canonical document record
```

## Contract

1. CNINFO index 每条结果必须与请求证券代码一致；任一跨证券 row 使整批 fail closed。
2. 已知 `document_id` 不重复下载；新披露形成独立 ingestion run/raw capture。
3. PDF adapter 只接受注册的官方 HTTPS host，且 redirect chain 不能离开同一 allowlist。
4. raw body 必须是 PDF；`content_hash == raw_hash` 且 `storage_uri == raw storage URI`。
5. document payload 保存 status、MIME、initial/final URL、redirect chain、ETag/Last-Modified/Content-Length 等可用 HTTP metadata。
6. 标题分类区分 annual report、annual summary、quarterly report、semiannual report、major announcement 与 other announcement。
7. source role 由固定 source key + official manifest + host 三者共同决定；aggregator 即使自称 official 也不能成为 primary。

## Verification

- Issue test: `python3 -m pytest product/tests/test_official_filing_ingest.py -q`
- Upstream smoke: `python3 -m pytest product/tests/test_official_filing_ingest.py product/tests/test_ingestion_core.py product/tests/test_data_contract.py -q`
- Live probe: CATL CNINFO index + five PDFs all passed; CATL 2026 Q1 report captured as `quarterly_report`; one SZSE official PDF captured successfully.

## Truth boundary

- Live probes prove current sample connectivity, not provider SLA or all-market coverage.
- B1 stores PDFs and metadata but does not OCR or extract financial tables.
- Seller research and aggregators remain supplementary leads, never official primary evidence.
- Real Supabase project wiring/backup remains a separate deployment milestone.

## Gotchas

- CNINFO search JSON is an index capture, not the PDF itself; index raw hash cannot be reused as document content hash.
- “年度报告摘要”不能冒充完整年报，“半年度报告”必须在“年度报告”之前分类。
- 非财报公告不一定都是重大公告；只有明确重大/重组/担保/诉讼/回购/业绩预告等关键词进入 major classification。
