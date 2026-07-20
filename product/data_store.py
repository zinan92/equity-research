from __future__ import annotations

import json
import hashlib
import hmac
import os
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
RUNTIME_DIR = ROOT / "runtime"
DB_PATH = Path(os.environ.get("PARK_DASHBOARD_DB", RUNTIME_DIR / "investment_dashboard_v2.db"))


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS dataset_snapshots (
    id TEXT PRIMARY KEY,
    data_mode TEXT NOT NULL CHECK (data_mode IN ('DEMO', 'CACHED', 'REAL')),
    as_of TEXT NOT NULL,
    known_at TEXT NOT NULL,
    quality_status TEXT NOT NULL CHECK (quality_status IN ('passed', 'degraded', 'blocked')),
    source_summary TEXT NOT NULL,
    manifest_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS publications (
    id TEXT PRIMARY KEY,
    snapshot_id TEXT NOT NULL REFERENCES dataset_snapshots(id),
    status TEXT NOT NULL CHECK (status IN ('draft', 'quality_passed', 'approved', 'published', 'blocked', 'invalidated')),
    title TEXT NOT NULL,
    market_regime TEXT NOT NULL,
    regime_note TEXT NOT NULL,
    equity_weight REAL NOT NULL,
    cash_weight REAL NOT NULL,
    model_version TEXT NOT NULL,
    published_at TEXT,
    approved_at TEXT,
    approval_hash TEXT,
    blocked_reason TEXT,
    CHECK (ABS(equity_weight + cash_weight - 100.0) < 0.001)
);

CREATE TABLE IF NOT EXISTS portfolio_items (
    publication_id TEXT NOT NULL REFERENCES publications(id),
    ticker TEXT NOT NULL,
    name TEXT NOT NULL,
    exchange TEXT NOT NULL,
    industry TEXT NOT NULL,
    target_weight REAL NOT NULL CHECK (target_weight >= 5 AND target_weight <= 15),
    previous_weight REAL NOT NULL,
    action TEXT NOT NULL CHECK (action IN ('新建', '加仓', '持有', '减仓', '退出')),
    reference_price REAL,
    execution_range TEXT NOT NULL,
    confidence INTEGER NOT NULL CHECK (confidence BETWEEN 0 AND 100),
    quality_status TEXT NOT NULL,
    data_as_of TEXT NOT NULL,
    thesis TEXT NOT NULL,
    primary_risk TEXT NOT NULL,
    valuation TEXT NOT NULL,
    bull_case TEXT NOT NULL,
    base_case TEXT NOT NULL,
    bear_case TEXT NOT NULL,
    PRIMARY KEY (publication_id, ticker)
);

CREATE TABLE IF NOT EXISTS evidence (
    publication_id TEXT NOT NULL,
    ticker TEXT NOT NULL,
    evidence_type TEXT NOT NULL CHECK (evidence_type IN ('fact', 'inference', 'risk')),
    label TEXT NOT NULL,
    value TEXT NOT NULL,
    source TEXT NOT NULL,
    known_at TEXT NOT NULL,
    quality_status TEXT NOT NULL,
    FOREIGN KEY (publication_id, ticker) REFERENCES portfolio_items(publication_id, ticker)
);

CREATE TABLE IF NOT EXISTS portfolio_risks (
    publication_id TEXT NOT NULL REFERENCES publications(id),
    rank INTEGER NOT NULL,
    title TEXT NOT NULL,
    detail TEXT NOT NULL,
    severity TEXT NOT NULL CHECK (severity IN ('high', 'medium', 'low')),
    PRIMARY KEY (publication_id, rank)
);

CREATE TABLE IF NOT EXISTS performance_points (
    publication_id TEXT NOT NULL REFERENCES publications(id),
    date TEXT NOT NULL,
    portfolio REAL NOT NULL,
    benchmark REAL NOT NULL,
    PRIMARY KEY (publication_id, date)
);

CREATE TABLE IF NOT EXISTS market_quotes (
    snapshot_id TEXT NOT NULL REFERENCES dataset_snapshots(id),
    ticker TEXT NOT NULL,
    name TEXT NOT NULL,
    price REAL NOT NULL CHECK (price > 0),
    change_pct REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    pe_ttm REAL,
    pb REAL,
    market_cap_yi REAL,
    circulating_cap_yi REAL,
    quote_time TEXT NOT NULL,
    source_key TEXT NOT NULL,
    source_url TEXT NOT NULL,
    raw_hash TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    quality_status TEXT NOT NULL,
    PRIMARY KEY (snapshot_id, ticker)
);

CREATE TABLE IF NOT EXISTS daily_bars (
    snapshot_id TEXT NOT NULL REFERENCES dataset_snapshots(id),
    ticker TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    open REAL NOT NULL,
    close REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    volume_lots REAL NOT NULL,
    source_key TEXT NOT NULL,
    raw_hash TEXT NOT NULL,
    quality_status TEXT NOT NULL,
    PRIMARY KEY (snapshot_id, ticker, trade_date)
);

CREATE TABLE IF NOT EXISTS financial_metrics (
    snapshot_id TEXT NOT NULL REFERENCES dataset_snapshots(id),
    ticker TEXT NOT NULL,
    report_date TEXT NOT NULL,
    notice_date TEXT NOT NULL,
    report_type TEXT NOT NULL,
    revenue REAL,
    net_profit REAL,
    revenue_yoy REAL,
    net_profit_yoy REAL,
    roe REAL,
    gross_margin REAL,
    net_margin REAL,
    debt_ratio REAL,
    operating_cash_per_share REAL,
    source_key TEXT NOT NULL,
    raw_hash TEXT NOT NULL,
    quality_status TEXT NOT NULL,
    PRIMARY KEY (snapshot_id, ticker, report_date)
);

CREATE TABLE IF NOT EXISTS stock_features (
    snapshot_id TEXT NOT NULL REFERENCES dataset_snapshots(id),
    ticker TEXT NOT NULL,
    return_20d REAL,
    return_60d REAL,
    return_250d REAL,
    volatility_60d REAL,
    max_drawdown_250d REAL,
    ma20 REAL,
    ma60 REAL,
    ma200 REAL,
    adv20_yi REAL,
    value_score REAL NOT NULL,
    quality_score REAL NOT NULL,
    trend_score REAL NOT NULL,
    resilience_score REAL NOT NULL,
    composite_score REAL NOT NULL,
    data_completeness REAL NOT NULL,
    feature_version TEXT NOT NULL,
    PRIMARY KEY (snapshot_id, ticker)
);

CREATE TABLE IF NOT EXISTS source_runs (
    id TEXT PRIMARY KEY,
    snapshot_id TEXT NOT NULL REFERENCES dataset_snapshots(id),
    source_key TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('success', 'degraded', 'failed')),
    fetched_count INTEGER NOT NULL,
    accepted_count INTEGER NOT NULL,
    error_summary TEXT
);

CREATE TABLE IF NOT EXISTS publication_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    publication_id TEXT NOT NULL REFERENCES publications(id),
    event_type TEXT NOT NULL,
    from_status TEXT,
    to_status TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    actor TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS refresh_runs (
    id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL CHECK (status IN ('running', 'success', 'reused', 'failed')),
    previous_snapshot_id TEXT,
    result_snapshot_id TEXT,
    publication_id TEXT,
    manifest_hash TEXT,
    error_summary TEXT
);

CREATE TABLE IF NOT EXISTS research_report_versions (
    snapshot_id TEXT NOT NULL REFERENCES dataset_snapshots(id),
    ticker TEXT NOT NULL,
    report_hash TEXT NOT NULL,
    report_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (ticker, report_hash)
);

CREATE TABLE IF NOT EXISTS research_documents (
    id TEXT PRIMARY KEY,
    ticker TEXT NOT NULL,
    source_adapter TEXT NOT NULL,
    source_key TEXT NOT NULL,
    source_url TEXT,
    title TEXT NOT NULL,
    document_kind TEXT NOT NULL,
    evidence_strength TEXT NOT NULL CHECK (evidence_strength IN ('strong', 'medium', 'weak', 'lead')),
    published_at TEXT,
    observed_at TEXT NOT NULL,
    quality_status TEXT NOT NULL CHECK (quality_status IN ('accepted', 'degraded', 'rejected')),
    content_hash TEXT NOT NULL,
    canonical_url TEXT,
    raw_sha256 TEXT,
    raw_mime_type TEXT,
    http_status INTEGER,
    fetched_at TEXT,
    payload_json TEXT NOT NULL,
    raw_path TEXT,
    created_at TEXT NOT NULL,
    UNIQUE (ticker, content_hash)
);

CREATE TABLE IF NOT EXISTS research_evidence_sets (
    id TEXT PRIMARY KEY,
    ticker TEXT NOT NULL,
    snapshot_id TEXT NOT NULL REFERENCES dataset_snapshots(id),
    knowledge_cutoff TEXT NOT NULL,
    policy_version TEXT NOT NULL,
    manifest_hash TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('passed', 'insufficient', 'blocked')),
    gate_json TEXT NOT NULL,
    gate_hash TEXT,
    created_at TEXT NOT NULL,
    UNIQUE (ticker, snapshot_id, manifest_hash)
);

CREATE TABLE IF NOT EXISTS research_evidence_set_items (
    evidence_set_id TEXT NOT NULL REFERENCES research_evidence_sets(id),
    document_id TEXT NOT NULL REFERENCES research_documents(id),
    role TEXT NOT NULL CHECK (role IN ('primary', 'independent', 'supporting', 'lead')),
    PRIMARY KEY (evidence_set_id, document_id)
);

CREATE TABLE IF NOT EXISTS research_document_identities (
    document_id TEXT NOT NULL REFERENCES research_documents(id),
    ticker TEXT NOT NULL,
    company_name TEXT NOT NULL,
    matched_by TEXT NOT NULL,
    excerpt_hash TEXT NOT NULL,
    extractor_version TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (document_id, ticker)
);

CREATE TABLE IF NOT EXISTS research_document_identity_assertions (
    document_id TEXT NOT NULL REFERENCES research_documents(id),
    ticker TEXT NOT NULL,
    company_name TEXT NOT NULL,
    matched_by TEXT NOT NULL,
    excerpt_hash TEXT NOT NULL,
    extractor_version TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (document_id, ticker, extractor_version)
);
"""


RESEARCH_IMMUTABILITY_SQL = """
CREATE TRIGGER IF NOT EXISTS research_documents_no_update
BEFORE UPDATE ON research_documents BEGIN SELECT RAISE(ABORT, 'research_documents are append-only'); END;
CREATE TRIGGER IF NOT EXISTS research_documents_no_delete
BEFORE DELETE ON research_documents BEGIN SELECT RAISE(ABORT, 'research_documents are append-only'); END;
CREATE TRIGGER IF NOT EXISTS research_evidence_sets_no_update
BEFORE UPDATE ON research_evidence_sets BEGIN SELECT RAISE(ABORT, 'research_evidence_sets are append-only'); END;
CREATE TRIGGER IF NOT EXISTS research_evidence_sets_no_delete
BEFORE DELETE ON research_evidence_sets BEGIN SELECT RAISE(ABORT, 'research_evidence_sets are append-only'); END;
CREATE TRIGGER IF NOT EXISTS research_evidence_set_items_no_update
BEFORE UPDATE ON research_evidence_set_items BEGIN SELECT RAISE(ABORT, 'research_evidence_set_items are append-only'); END;
CREATE TRIGGER IF NOT EXISTS research_evidence_set_items_no_delete
BEFORE DELETE ON research_evidence_set_items BEGIN SELECT RAISE(ABORT, 'research_evidence_set_items are append-only'); END;
CREATE TRIGGER IF NOT EXISTS research_document_identities_no_update
BEFORE UPDATE ON research_document_identities BEGIN SELECT RAISE(ABORT, 'research_document_identities are append-only'); END;
CREATE TRIGGER IF NOT EXISTS research_document_identities_no_delete
BEFORE DELETE ON research_document_identities BEGIN SELECT RAISE(ABORT, 'research_document_identities are append-only'); END;
CREATE TRIGGER IF NOT EXISTS research_document_identity_assertions_no_update
BEFORE UPDATE ON research_document_identity_assertions BEGIN SELECT RAISE(ABORT, 'research_document_identity_assertions are append-only'); END;
CREATE TRIGGER IF NOT EXISTS research_document_identity_assertions_no_delete
BEFORE DELETE ON research_document_identity_assertions BEGIN SELECT RAISE(ABORT, 'research_document_identity_assertions are append-only'); END;
"""

RESEARCH_IMMUTABILITY_TRIGGERS = (
    "research_documents_no_update", "research_documents_no_delete",
    "research_evidence_sets_no_update", "research_evidence_sets_no_delete",
    "research_evidence_set_items_no_update", "research_evidence_set_items_no_delete",
    "research_document_identities_no_update", "research_document_identities_no_delete",
    "research_document_identity_assertions_no_update", "research_document_identity_assertions_no_delete",
)


DEMO_POSITIONS = [
    {
        "ticker": "600519.SH", "name": "贵州茅台", "exchange": "上交所", "industry": "食品饮料",
        "target_weight": 12, "previous_weight": 12, "action": "持有", "reference_price": 1488.00,
        "execution_range": "仅作界面示意", "confidence": 78, "quality_status": "demo",
        "thesis": "品牌心智、渠道掌控与高现金回报构成长期质量锚，组合中承担消费核心资产角色。",
        "primary_risk": "需求恢复弱于预期，批价与渠道库存同时承压。", "valuation": "估值处于可跟踪区间；真实分位待接入",
        "bull_case": "需求修复与分红提升同时发生，盈利质量继续获得溢价。",
        "base_case": "收入与利润温和增长，估值围绕长期中枢波动。",
        "bear_case": "批价持续下行、渠道去库存时间显著延长。",
    },
    {
        "ticker": "600036.SH", "name": "招商银行", "exchange": "上交所", "industry": "银行",
        "target_weight": 12, "previous_weight": 10, "action": "加仓", "reference_price": 42.16,
        "execution_range": "仅作界面示意", "confidence": 75, "quality_status": "demo",
        "thesis": "零售负债基础与财富管理能力仍是同业差异，低估值为资产质量波动提供缓冲。",
        "primary_risk": "息差继续收窄或零售资产质量超预期恶化。", "valuation": "PB 框架待真实历史分位校验",
        "bull_case": "息差企稳、财富管理修复，估值回归优质银行区间。",
        "base_case": "利润低个位数增长，股息承担主要回报。",
        "bear_case": "资产质量与息差同时恶化，低估值陷阱延续。",
    },
    {
        "ticker": "600900.SH", "name": "长江电力", "exchange": "上交所", "industry": "公用事业",
        "target_weight": 11, "previous_weight": 11, "action": "持有", "reference_price": 29.38,
        "execution_range": "仅作界面示意", "confidence": 82, "quality_status": "demo",
        "thesis": "稀缺水电资产与可预期现金流为组合提供防守底仓，并降低高波动行业暴露。",
        "primary_risk": "来水不及预期或高估值压缩未来回报。", "valuation": "股息率与利率敏感度待真实计算",
        "bull_case": "来水改善、现金流增长与利率下行共同推升价值。",
        "base_case": "稳定发电与分红贡献中低个位数复合回报。",
        "bear_case": "来水偏弱且无风险利率上行，估值承压。",
    },
    {
        "ticker": "000333.SZ", "name": "美的集团", "exchange": "深交所", "industry": "家用电器",
        "target_weight": 11, "previous_weight": 9, "action": "加仓", "reference_price": 73.20,
        "execution_range": "仅作界面示意", "confidence": 77, "quality_status": "demo",
        "thesis": "多品类运营、全球渠道和制造效率带来稳健自由现金流，是消费与制造交叉的质量资产。",
        "primary_risk": "海外需求、汇率或原材料成本导致利润率波动。", "valuation": "PE 与自由现金流收益率待真实快照",
        "bull_case": "海外业务与高端化共振，利润增速持续高于收入。",
        "base_case": "内需平稳、海外增长，现金流支持回购与分红。",
        "bear_case": "全球需求转弱且价格竞争加剧，利润率回落。",
    },
    {
        "ticker": "600941.SH", "name": "中国移动", "exchange": "上交所", "industry": "通信服务",
        "target_weight": 10, "previous_weight": 10, "action": "持有", "reference_price": 112.60,
        "execution_range": "仅作界面示意", "confidence": 80, "quality_status": "demo",
        "thesis": "成熟通信现金流、高分红与云业务可选性共同提供防守收益和数字基础设施敞口。",
        "primary_risk": "资本开支回升或新业务变现低于预期。", "valuation": "股息与增长拆分待真实建模",
        "bull_case": "云与算力业务重估，同时维持高分红。",
        "base_case": "传统业务稳定，新业务贡献温和增量。",
        "bear_case": "资本开支扩张侵蚀自由现金流，估值回落。",
    },
    {
        "ticker": "300750.SZ", "name": "宁德时代", "exchange": "深交所", "industry": "电力设备",
        "target_weight": 10, "previous_weight": 12, "action": "减仓", "reference_price": 285.40,
        "execution_range": "仅作界面示意", "confidence": 68, "quality_status": "demo",
        "thesis": "规模、研发和客户结构仍构成电池龙头壁垒，但行业价格与技术迭代要求更高安全边际。",
        "primary_risk": "价格竞争、产能利用率或技术路线变化压缩盈利。", "valuation": "成长情景敏感；真实盈利预测待接入",
        "bull_case": "储能与海外增长抵消动力电池降价，份额继续提升。",
        "base_case": "销量增长但单位盈利回落，利润保持中速增长。",
        "bear_case": "供给过剩与技术替代造成盈利和估值双杀。",
    },
    {
        "ticker": "601088.SH", "name": "中国神华", "exchange": "上交所", "industry": "煤炭",
        "target_weight": 9, "previous_weight": 8, "action": "加仓", "reference_price": 41.12,
        "execution_range": "仅作界面示意", "confidence": 73, "quality_status": "demo",
        "thesis": "一体化经营与资本纪律使周期现金流更可控，高分红为组合提供实际回报缓冲。",
        "primary_risk": "煤价中枢快速下行或资本开支纪律变化。", "valuation": "周期中枢与股息覆盖待真实校验",
        "bull_case": "煤价韧性与高分红持续，现金回报超预期。",
        "base_case": "煤价回落但一体化与成本优势维持盈利。",
        "bear_case": "需求转弱推动煤价大幅下行，分红同步下降。",
    },
    {
        "ticker": "688036.SH", "name": "传音控股", "exchange": "上交所", "industry": "消费电子",
        "target_weight": 7, "previous_weight": 10, "action": "减仓", "reference_price": 92.80,
        "execution_range": "仅作界面示意", "confidence": 64, "quality_status": "demo",
        "thesis": "新兴市场渠道与本地化产品能力具有差异化，但竞争加剧和区域风险提升了持仓折价要求。",
        "primary_risk": "区域竞争、汇率和渠道库存造成盈利大幅波动。", "valuation": "增长质量与区域风险待真实数据重估",
        "bull_case": "非洲基本盘稳固，新市场和新品类放量。",
        "base_case": "收入增长放缓但渠道优势维持合理利润。",
        "bear_case": "竞争升级与需求波动同时打击份额和利润率。",
    },
]


def connect(db_path: Path = DB_PATH) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize(db_path: Path = DB_PATH, *, force_seed: bool = False) -> None:
    with closing(connect(db_path)) as conn:
        conn.executescript(SCHEMA)
        document_columns = {row["name"] for row in conn.execute("PRAGMA table_info(research_documents)").fetchall()}
        for name, column_type in (
            ("canonical_url", "TEXT"), ("raw_sha256", "TEXT"), ("raw_mime_type", "TEXT"),
            ("http_status", "INTEGER"), ("fetched_at", "TEXT"),
        ):
            if name not in document_columns:
                conn.execute(f"ALTER TABLE research_documents ADD COLUMN {name} {column_type}")
        set_columns = {row["name"] for row in conn.execute("PRAGMA table_info(research_evidence_sets)").fetchall()}
        if "gate_hash" not in set_columns:
            conn.execute("ALTER TABLE research_evidence_sets ADD COLUMN gate_hash TEXT")
        version_pk = [
            row["name"] for row in sorted(
                conn.execute("PRAGMA table_info(research_report_versions)").fetchall(),
                key=lambda row: row["pk"],
            ) if row["pk"]
        ]
        if version_pk == ["snapshot_id", "ticker"]:
            conn.execute("ALTER TABLE research_report_versions RENAME TO research_report_versions_legacy")
            conn.execute(
                """CREATE TABLE research_report_versions (
                    snapshot_id TEXT NOT NULL REFERENCES dataset_snapshots(id),
                    ticker TEXT NOT NULL,
                    report_hash TEXT NOT NULL,
                    report_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (ticker, report_hash)
                )"""
            )
            conn.execute(
                """INSERT OR IGNORE INTO research_report_versions
                   SELECT snapshot_id, ticker, report_hash, report_json, created_at
                   FROM research_report_versions_legacy"""
            )
            conn.execute("DROP TABLE research_report_versions_legacy")
        # Backfill early refresh receipts that stored only the snapshot-id suffix.
        conn.execute(
            """UPDATE refresh_runs
               SET manifest_hash=(
                   SELECT s.manifest_hash FROM dataset_snapshots s
                   WHERE s.id=refresh_runs.result_snapshot_id
               )
               WHERE result_snapshot_id IS NOT NULL
                 AND EXISTS (
                   SELECT 1 FROM dataset_snapshots s
                   WHERE s.id=refresh_runs.result_snapshot_id
                     AND (refresh_runs.manifest_hash IS NULL OR refresh_runs.manifest_hash != s.manifest_hash)
                 )"""
        )
        conn.commit()
        exists = conn.execute("SELECT 1 FROM publications LIMIT 1").fetchone()
        if exists and not force_seed:
            conn.executescript(RESEARCH_IMMUTABILITY_SQL)
            return
        if force_seed:
            for trigger in RESEARCH_IMMUTABILITY_TRIGGERS:
                conn.execute(f"DROP TRIGGER IF EXISTS {trigger}")
        for table in ("research_evidence_set_items", "research_evidence_sets", "research_document_identity_assertions", "research_document_identities", "research_documents", "research_report_versions", "refresh_runs", "publication_events", "source_runs", "stock_features", "financial_metrics", "daily_bars", "market_quotes", "performance_points", "portfolio_risks", "evidence", "portfolio_items", "publications", "dataset_snapshots"):
            conn.execute(f"DELETE FROM {table}")
        _seed_demo(conn)
        conn.executescript(RESEARCH_IMMUTABILITY_SQL)
        conn.commit()


def _seed_demo(conn: sqlite3.Connection) -> None:
    snapshot_id = "snap_demo_20260717_v1"
    publication_id = "pub_demo_2026w29"
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO dataset_snapshots VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (snapshot_id, "DEMO", "2026-07-16", "2026-07-17T05:30:00+08:00", "degraded",
         "UZI mock structure + product assumptions; not live market data", "demo-manifest-9b47e6c8", now),
    )
    conn.execute(
        """INSERT INTO publications (
            id, snapshot_id, status, title, market_regime, regime_note,
            equity_weight, cash_weight, model_version, published_at,
            approved_at, approval_hash, blocked_reason
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (publication_id, snapshot_id, "draft", "2026 W29 长期模型组合", "均衡偏防守", "优先现金流与资产质量，成长仓位保留但不追价。",
         82, 18, "portfolio-rules-v0.1-demo", None, None, None, None),
    )
    for item in DEMO_POSITIONS:
        conn.execute(
            """INSERT INTO portfolio_items VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )""",
            (publication_id, item["ticker"], item["name"], item["exchange"], item["industry"],
             item["target_weight"], item["previous_weight"], item["action"], item["reference_price"],
             item["execution_range"], item["confidence"], item["quality_status"], "2026-07-16",
             item["thesis"], item["primary_risk"], item["valuation"], item["bull_case"],
             item["base_case"], item["bear_case"],),
        )
        for evidence_type, label, value, source, quality in (
            ("fact", "组合目标仓位", f'{item["target_weight"]:.0f}%', "portfolio-rules-v0.1-demo", "verified-demo"),
            ("inference", "投委会摘要", item["thesis"], "Codex product seed", "demo"),
            ("risk", "首要风险", item["primary_risk"], "Codex product seed", "demo"),
        ):
            conn.execute(
                "INSERT INTO evidence VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (publication_id, item["ticker"], evidence_type, label, value, source,
                 "2026-07-17T05:30:00+08:00", quality),
            )

    risks = [
        (1, "估值与利率", "高股息与稳定资产对无风险利率变化敏感，利率上行会压缩估值。", "high"),
        (2, "需求修复不均", "消费与制造需求可能继续分化，不能用单一宏观叙事覆盖所有公司。", "medium"),
        (3, "演示结论限制", "当前组合动作、估值和文字判断仅用于验证产品结构，不能据此交易。", "high"),
    ]
    conn.executemany("INSERT INTO portfolio_risks VALUES (?, ?, ?, ?, ?)", [(publication_id, *r) for r in risks])

    performance = [
        ("2026-02", 100.0, 100.0), ("2026-03", 101.8, 100.9), ("2026-04", 100.7, 99.6),
        ("2026-05", 103.4, 101.2), ("2026-06", 105.1, 102.6), ("2026-07", 104.6, 102.1),
    ]
    conn.executemany("INSERT INTO performance_points VALUES (?, ?, ?, ?)", [(publication_id, *p) for p in performance])


def _rows(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]


def dashboard_payload(db_path: Path = DB_PATH) -> dict[str, Any]:
    initialize(db_path)
    with closing(connect(db_path)) as conn:
        publication = conn.execute(
            """SELECT p.*, s.data_mode, s.as_of, s.known_at, s.quality_status AS snapshot_quality,
                      s.source_summary, s.manifest_hash
               FROM publications p JOIN dataset_snapshots s ON s.id = p.snapshot_id
               WHERE (
                    (p.status IN ('quality_passed', 'approved', 'published') AND s.quality_status = 'passed')
                    OR (p.status='draft' AND s.data_mode IN ('DEMO', 'CACHED') AND s.quality_status != 'blocked')
               )
               ORDER BY COALESCE(p.published_at, s.created_at) DESC LIMIT 1"""
        ).fetchone()
        if not publication:
            raise RuntimeError("No portfolio publication available")
        pub = dict(publication)
        positions = _rows(conn.execute(
            """SELECT i.*, f.return_20d, f.return_60d, f.return_250d,
                      f.volatility_60d, f.max_drawdown_250d, f.ma20, f.ma60, f.ma200,
                      f.adv20_yi, f.value_score, f.quality_score, f.trend_score,
                      f.resilience_score, f.composite_score, f.data_completeness
               FROM portfolio_items i
               LEFT JOIN stock_features f ON f.snapshot_id = ? AND f.ticker = i.ticker
               WHERE i.publication_id = ? ORDER BY i.target_weight DESC, i.ticker""",
            (pub["snapshot_id"], pub["id"]),
        ).fetchall())
        risks = _rows(conn.execute(
            "SELECT * FROM portfolio_risks WHERE publication_id = ? ORDER BY rank", (pub["id"],)
        ).fetchall())
        performance = _rows(conn.execute(
            "SELECT date, portfolio, benchmark FROM performance_points WHERE publication_id = ? ORDER BY date",
            (pub["id"],),
        ).fetchall())
        quote_count = conn.execute(
            "SELECT COUNT(*) FROM market_quotes WHERE snapshot_id = ? AND quality_status = 'accepted'",
            (pub["snapshot_id"],),
        ).fetchone()[0]
        bar_count = conn.execute(
            "SELECT COUNT(*) FROM daily_bars WHERE snapshot_id = ? AND quality_status = 'accepted'",
            (pub["snapshot_id"],),
        ).fetchone()[0]
        financial_count = conn.execute(
            "SELECT COUNT(*) FROM financial_metrics WHERE snapshot_id = ? AND quality_status = 'accepted'",
            (pub["snapshot_id"],),
        ).fetchone()[0]
        source_runs = _rows(conn.execute(
            """SELECT source_key, status, fetched_count, accepted_count, finished_at, error_summary
               FROM source_runs WHERE snapshot_id = ? ORDER BY source_key""",
            (pub["snapshot_id"],),
        ).fetchall())
        events = _rows(conn.execute(
            """SELECT event_type, from_status, to_status, content_hash, actor, created_at
               FROM publication_events WHERE publication_id = ? ORDER BY id""",
            (pub["id"],),
        ).fetchall())

    stock_weight = round(sum(float(p["target_weight"]) for p in positions), 4)
    industries: dict[str, float] = {}
    for position in positions:
        industries[position["industry"]] = industries.get(position["industry"], 0) + float(position["target_weight"])

    return {
        "publication": {
            "id": pub["id"], "title": pub["title"], "status": pub["status"],
            "market_regime": pub["market_regime"], "regime_note": pub["regime_note"],
            "model_version": pub["model_version"], "published_at": pub["published_at"],
        },
        "snapshot": {
            "id": pub["snapshot_id"], "data_mode": pub["data_mode"], "as_of": pub["as_of"],
            "known_at": pub["known_at"], "quality_status": pub["snapshot_quality"],
            "source_summary": pub["source_summary"], "manifest_hash": pub["manifest_hash"],
            "real_quote_coverage": {"accepted": quote_count, "required": len(positions)},
            "daily_bar_coverage": {"accepted": bar_count, "required_minimum": len(positions) * 250},
            "financial_coverage": {"accepted": financial_count, "required_minimum": len(positions)},
        },
        "allocation": {"equity": stock_weight, "cash": float(pub["cash_weight"]), "total": stock_weight + float(pub["cash_weight"])},
        "positions": positions,
        "industry_exposure": [{"industry": key, "weight": value} for key, value in sorted(industries.items(), key=lambda item: -item[1])],
        "risks": risks,
        "performance": performance,
        "source_status": source_runs,
        "review": {
            "can_approve": pub["status"] == "quality_passed",
            "can_publish": pub["status"] == "approved",
            "approved_at": pub.get("approved_at"),
            "approval_hash": pub.get("approval_hash"),
            "events": events,
        },
    }


def stock_payload(ticker: str, db_path: Path = DB_PATH, *, snapshot_id: str | None = None) -> dict[str, Any] | None:
    initialize(db_path)
    with closing(connect(db_path)) as conn:
        row = conn.execute(
            f"""SELECT i.*, p.snapshot_id, p.model_version, p.status AS publication_status,
                      p.market_regime, p.cash_weight,
                      s.data_mode, s.source_summary,
                      s.quality_status AS snapshot_quality,
                      s.as_of AS snapshot_as_of, s.known_at AS snapshot_known_at
               FROM portfolio_items i
               JOIN publications p ON p.id = i.publication_id
               JOIN dataset_snapshots s ON s.id = p.snapshot_id
               WHERE i.ticker = ?
                 AND (
                    (p.status IN ('quality_passed', 'approved', 'published') AND s.quality_status = 'passed')
                    OR (p.status='draft' AND s.data_mode IN ('DEMO', 'CACHED') AND s.quality_status != 'blocked')
                 )
                 {"AND p.snapshot_id = ?" if snapshot_id else ""}
               ORDER BY COALESCE(p.published_at, s.created_at) DESC LIMIT 1""",
            (ticker.upper(), snapshot_id) if snapshot_id else (ticker.upper(),),
        ).fetchone()
        if not row:
            return None
        evidence_rows = conn.execute(
            """SELECT evidence_type, label, value, source, known_at, quality_status
               FROM evidence WHERE publication_id = ? AND ticker = ?
                 AND (? != 'REAL' OR (quality_status='accepted' AND substr(known_at, 1, 10) <= ?))""",
            (row["publication_id"], row["ticker"], row["data_mode"], str(row["snapshot_known_at"] or "")[:10]),
        ).fetchall()
        quote = conn.execute(
            """SELECT price, change_pct, high, low, pe_ttm, pb, market_cap_yi,
                      circulating_cap_yi, quote_time, source_key, source_url,
                      raw_hash, fetched_at, quality_status
               FROM market_quotes WHERE snapshot_id = ? AND ticker = ?""",
            (row["snapshot_id"], row["ticker"]),
        ).fetchone()
        features = conn.execute(
            "SELECT * FROM stock_features WHERE snapshot_id = ? AND ticker = ?",
            (row["snapshot_id"], row["ticker"]),
        ).fetchone()
        financials = conn.execute(
            """SELECT report_date, notice_date, report_type, revenue, net_profit,
                      revenue_yoy, net_profit_yoy, roe, gross_margin, net_margin,
                      debt_ratio, operating_cash_per_share, source_key, raw_hash, quality_status
               FROM financial_metrics WHERE snapshot_id = ? AND ticker = ?
               ORDER BY report_date DESC LIMIT 8""",
            (row["snapshot_id"], row["ticker"]),
        ).fetchall()
        position_count = conn.execute(
            "SELECT COUNT(*) FROM portfolio_items WHERE publication_id = ?", (row["publication_id"],)
        ).fetchone()[0]
        portfolio_weights = {
            item["ticker"]: float(item["target_weight"])
            for item in conn.execute(
                "SELECT ticker, target_weight FROM portfolio_items WHERE publication_id=? ORDER BY ticker",
                (row["publication_id"],),
            ).fetchall()
        }
        accepted_quote_count = conn.execute(
            "SELECT COUNT(*) FROM market_quotes WHERE snapshot_id = ? AND quality_status = 'accepted'", (row["snapshot_id"],)
        ).fetchone()[0]
        accepted_bar_count = conn.execute(
            "SELECT COUNT(*) FROM daily_bars WHERE snapshot_id = ? AND quality_status = 'accepted'", (row["snapshot_id"],)
        ).fetchone()[0]
        ticker_bar_count = conn.execute(
            "SELECT COUNT(*) FROM daily_bars WHERE snapshot_id = ? AND ticker = ? AND quality_status = 'accepted'",
            (row["snapshot_id"], row["ticker"]),
        ).fetchone()[0]
        accepted_financial_count = conn.execute(
            "SELECT COUNT(*) FROM financial_metrics WHERE snapshot_id = ? AND quality_status = 'accepted'", (row["snapshot_id"],)
        ).fetchone()[0]
        source_runs = _rows(conn.execute(
            "SELECT source_key, status, fetched_count, accepted_count, finished_at FROM source_runs WHERE snapshot_id = ? ORDER BY source_key",
            (row["snapshot_id"],),
        ).fetchall())
        portfolio_coverage = _rows(conn.execute(
            """SELECT i.ticker,
                      (SELECT COUNT(*) FROM market_quotes q WHERE q.snapshot_id = p.snapshot_id AND q.ticker = i.ticker AND q.quality_status = 'accepted') AS quote_count,
                      (SELECT MAX(q.quote_time) FROM market_quotes q WHERE q.snapshot_id = p.snapshot_id AND q.ticker = i.ticker AND q.quality_status = 'accepted') AS quote_time,
                      (SELECT COUNT(*) FROM daily_bars b WHERE b.snapshot_id = p.snapshot_id AND b.ticker = i.ticker AND b.quality_status = 'accepted') AS bar_count,
                      (SELECT MAX(b.trade_date) FROM daily_bars b WHERE b.snapshot_id = p.snapshot_id AND b.ticker = i.ticker AND b.quality_status = 'accepted') AS max_trade_date,
                      (SELECT COUNT(*) FROM financial_metrics f WHERE f.snapshot_id = p.snapshot_id AND f.ticker = i.ticker AND f.quality_status = 'accepted') AS financial_count,
                      (SELECT MAX(f.notice_date) FROM financial_metrics f WHERE f.snapshot_id = p.snapshot_id AND f.ticker = i.ticker AND f.quality_status = 'accepted') AS max_notice_date
               FROM portfolio_items i
               JOIN publications p ON p.id = i.publication_id
               WHERE i.publication_id = ? ORDER BY i.ticker""",
            (row["publication_id"],),
        ).fetchall())
    payload = dict(row)
    payload["evidence"] = _rows(evidence_rows)
    payload["market_quote"] = dict(quote) if quote else None
    payload["features"] = dict(features) if features else None
    payload["financials"] = _rows(financials)
    payload["portfolio_weights"] = portfolio_weights
    payload["data_gate"] = {
        "position_count": position_count,
        "accepted_quote_count": accepted_quote_count,
        "accepted_bar_count": accepted_bar_count,
        "required_bar_count": position_count * 250,
        "ticker_bar_count": ticker_bar_count,
        "accepted_financial_count": accepted_financial_count,
        "required_financial_count": position_count,
        "source_runs": source_runs,
        "portfolio_coverage": portfolio_coverage,
        "snapshot_as_of": payload.get("snapshot_as_of"),
        "snapshot_known_at": payload.get("snapshot_known_at"),
    }
    return payload


def save_market_quotes(quotes: list[dict[str, Any]], db_path: Path = DB_PATH) -> int:
    initialize(db_path)
    with closing(connect(db_path)) as conn:
        publication = conn.execute(
            "SELECT id, snapshot_id FROM publications ORDER BY rowid DESC LIMIT 1"
        ).fetchone()
        if not publication:
            raise RuntimeError("No publication available for quote ingestion")
        accepted = 0
        for quote in quotes:
            ticker = str(quote["ticker"]).upper()
            item = conn.execute(
                "SELECT name FROM portfolio_items WHERE publication_id = ? AND ticker = ?",
                (publication["id"], ticker),
            ).fetchone()
            canonical_name = item["name"].removeprefix("XD") if item else ""
            provider_name = str(quote["name"]).removeprefix("XD")
            if not item or canonical_name[:3] != provider_name[:3]:
                continue
            conn.execute(
                """INSERT INTO market_quotes (
                   snapshot_id, ticker, name, price, change_pct, high, low,
                   pe_ttm, pb, market_cap_yi, circulating_cap_yi,
                   quote_time, source_key, source_url, raw_hash, fetched_at, quality_status
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(snapshot_id, ticker) DO UPDATE SET
                   name=excluded.name, price=excluded.price, change_pct=excluded.change_pct,
                   high=excluded.high, low=excluded.low, quote_time=excluded.quote_time,
                   pe_ttm=excluded.pe_ttm, pb=excluded.pb, market_cap_yi=excluded.market_cap_yi,
                   circulating_cap_yi=excluded.circulating_cap_yi,
                   source_key=excluded.source_key, source_url=excluded.source_url,
                   raw_hash=excluded.raw_hash, fetched_at=excluded.fetched_at,
                   quality_status=excluded.quality_status""",
                (publication["snapshot_id"], ticker, quote["name"], quote["price"], quote["change_pct"],
                 quote["high"], quote["low"], quote.get("pe_ttm"), quote.get("pb"),
                 quote.get("market_cap_yi"), quote.get("circulating_cap_yi"),
                 quote["quote_time"], quote["source_key"],
                 quote["source_url"], quote["raw_hash"], quote["fetched_at"], "accepted"),
            )
            conn.execute(
                "UPDATE portfolio_items SET reference_price = ?, data_as_of = ? WHERE publication_id = ? AND ticker = ?",
                (quote["price"], quote["quote_time"].split("T", 1)[0], publication["id"], ticker),
            )
            conn.execute(
                "DELETE FROM evidence WHERE publication_id = ? AND ticker = ? AND label = '最新行情参考价'",
                (publication["id"], ticker),
            )
            conn.execute(
                "INSERT INTO evidence VALUES (?, ?, 'fact', '最新行情参考价', ?, ?, ?, 'accepted')",
                (publication["id"], ticker, f'¥{quote["price"]:.2f}（{quote["change_pct"]:+.2f}%）',
                 quote["source_key"], quote["quote_time"]),
            )
            accepted += 1
        if accepted:
            conn.execute(
                """UPDATE dataset_snapshots
                   SET source_summary = ?, known_at = ?
                   WHERE id = ?""",
                (f"{accepted} 只股票已接腾讯行情快照；组合动作、估值和文字判断仍为 DEMO",
                 max(q["quote_time"] for q in quotes), publication["snapshot_id"]),
            )
        conn.commit()
        return accepted


def validate_invariants(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    allocation = payload["allocation"]
    if abs(float(allocation["total"]) - 100) > 0.001:
        errors.append("股票与现金仓位合计不等于 100%")
    positions = payload["positions"]
    if not 6 <= len(positions) <= 12:
        errors.append("组合股票数量不在 6–12 只范围")
    for position in positions:
        if not 5 <= float(position["target_weight"]) <= 15:
            errors.append(f'{position["ticker"]} 单股仓位越界')
    for exposure in payload["industry_exposure"]:
        if float(exposure["weight"]) > 30:
            errors.append(f'{exposure["industry"]} 行业仓位超过 30%')
    if not 10 <= float(allocation["cash"]) <= 40:
        errors.append("现金仓位不在 10%–40% 范围")
    if payload["snapshot"]["data_mode"] not in {"DEMO", "CACHED", "REAL"}:
        errors.append("数据模式标签无效")
    return errors


def publication_content_hash(conn: sqlite3.Connection, publication_id: str) -> str:
    row = conn.execute("SELECT * FROM publications WHERE id = ?", (publication_id,)).fetchone()
    if not row:
        raise KeyError(publication_id)
    publication = dict(row)
    items = _rows(conn.execute(
        "SELECT * FROM portfolio_items WHERE publication_id = ? ORDER BY ticker", (publication_id,)
    ).fetchall())
    excluded = {"status", "published_at", "approved_at", "approval_hash", "blocked_reason"}
    from research_reports import active_research_artifact_hash, research_logic_hash, research_profile_hash, research_profile_tickers
    from research_evidence import load_evidence_set

    snapshot_id = publication["snapshot_id"]
    database_file = Path(conn.execute("PRAGMA database_list").fetchone()["file"])
    covered_tickers = tuple(ticker for ticker in research_profile_tickers() if any(item["ticker"] == ticker for item in items))
    research_inputs: dict[str, Any] = {}
    if covered_tickers:
        placeholders = ",".join("?" for _ in covered_tickers)
        params = (snapshot_id, *covered_tickers)
        research_inputs = {
            "market_quotes": _rows(conn.execute(
                f"SELECT * FROM market_quotes WHERE snapshot_id = ? AND ticker IN ({placeholders}) ORDER BY ticker", params
            ).fetchall()),
            "stock_features": _rows(conn.execute(
                f"SELECT * FROM stock_features WHERE snapshot_id = ? AND ticker IN ({placeholders}) ORDER BY ticker", params
            ).fetchall()),
            "financial_metrics": _rows(conn.execute(
                f"SELECT * FROM financial_metrics WHERE snapshot_id = ? AND ticker IN ({placeholders}) ORDER BY ticker, report_date", params
            ).fetchall()),
        }

    payload = {
        "publication": {key: value for key, value in publication.items() if key not in excluded},
        "items": items,
        "research_profile_hash": research_profile_hash("*"),
        "research_logic_hash": research_logic_hash(),
        "research_artifact_hashes": {
            ticker: active_research_artifact_hash(database_file, ticker, snapshot_id) for ticker in covered_tickers
        },
        "research_evidence_sets": {
            ticker: (
                {
                    "evidence_set_id": evidence_set["evidence_set_id"],
                    "manifest_hash": evidence_set["manifest_hash"],
                    "gate_hash": evidence_set["gate_hash"],
                }
                if (evidence_set := load_evidence_set(ticker, snapshot_id, database_file)) else None
            )
            for ticker in covered_tickers if ticker == "300750.SZ"
        },
        "research_inputs": research_inputs,
    }
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()


def publication_approval_state(publication_id: str, db_path: Path = DB_PATH) -> dict[str, Any]:
    """Return the effective approval state without trusting the stored status alone."""
    initialize(db_path)
    with closing(connect(db_path)) as conn:
        row = conn.execute(
            "SELECT status, approval_hash FROM publications WHERE id = ?", (publication_id,)
        ).fetchone()
        if not row:
            raise KeyError(publication_id)
        current_hash = publication_content_hash(conn, publication_id)
    approved_status = row["status"] in {"approved", "published"}
    matches = bool(row["approval_hash"]) and hmac.compare_digest(str(row["approval_hash"]), current_hash)
    return {
        "stored_status": row["status"],
        "effective_status": row["status"] if not approved_status or matches else "invalidated",
        "is_current": approved_status and matches,
        "approval_hash_matches": matches,
        "current_content_hash": current_hash,
    }


def publication_data_gate_errors(conn: sqlite3.Connection, publication_id: str) -> list[str]:
    snapshot = conn.execute(
        """SELECT p.snapshot_id, s.data_mode, s.quality_status, s.manifest_hash,
                  s.as_of, s.known_at
           FROM publications p JOIN dataset_snapshots s ON s.id = p.snapshot_id WHERE p.id = ?""",
        (publication_id,),
    ).fetchone()
    if not snapshot:
        return ["publication or snapshot missing"]
    errors: list[str] = []
    if snapshot["data_mode"] != "REAL" or snapshot["quality_status"] != "passed" or not snapshot["manifest_hash"]:
        errors.append("snapshot must be REAL, passed, and manifested")
    coverage = _rows(conn.execute(
        """SELECT i.ticker,
                  (SELECT COUNT(*) FROM market_quotes q WHERE q.snapshot_id = p.snapshot_id AND q.ticker = i.ticker AND q.quality_status = 'accepted') AS quote_count,
                  (SELECT MAX(q.quote_time) FROM market_quotes q WHERE q.snapshot_id = p.snapshot_id AND q.ticker = i.ticker AND q.quality_status = 'accepted') AS quote_time,
                  (SELECT COUNT(*) FROM daily_bars b WHERE b.snapshot_id = p.snapshot_id AND b.ticker = i.ticker AND b.quality_status = 'accepted') AS bar_count,
                  (SELECT MAX(b.trade_date) FROM daily_bars b WHERE b.snapshot_id = p.snapshot_id AND b.ticker = i.ticker AND b.quality_status = 'accepted') AS max_trade_date,
                  (SELECT COUNT(*) FROM financial_metrics f WHERE f.snapshot_id = p.snapshot_id AND f.ticker = i.ticker AND f.quality_status = 'accepted') AS financial_count,
                  (SELECT MAX(f.notice_date) FROM financial_metrics f WHERE f.snapshot_id = p.snapshot_id AND f.ticker = i.ticker AND f.quality_status = 'accepted') AS max_notice_date
           FROM portfolio_items i JOIN publications p ON p.id = i.publication_id
           WHERE i.publication_id = ? ORDER BY i.ticker""",
        (publication_id,),
    ).fetchall())
    if not coverage or any(row["quote_count"] != 1 or row["bar_count"] < 250 or row["financial_count"] < 1 for row in coverage):
        errors.append("every portfolio ticker requires one quote, 250 bars, and one financial record")
    snapshot_as_of = str(snapshot["as_of"] or "")[:10]
    snapshot_known_date = str(snapshot["known_at"] or "")[:10]
    if not snapshot_as_of or not snapshot_known_date or any(
        str(row.get("max_trade_date") or "")[:10] != snapshot_as_of
        or str(row.get("quote_time") or "")[:10] != snapshot_known_date
        or str(row.get("quote_time") or "")[:10] < snapshot_as_of
        or str(row.get("max_notice_date") or "")[:10] > snapshot_known_date
        for row in coverage
    ):
        errors.append("portfolio freshness or point-in-time alignment failed")
    if any(row["ticker"] == "300750.SZ" for row in coverage):
        from research_evidence import load_evidence_set
        from research_reports import CATL_PROFILE
        if any(str(source.get("known_at") or "")[:10] > snapshot_known_date for source in CATL_PROFILE["sources"]):
            errors.append("research source is newer than the snapshot knowledge boundary")
        database_file = Path(conn.execute("PRAGMA database_list").fetchone()["file"])
        if not load_evidence_set("300750.SZ", snapshot["snapshot_id"], database_file):
            errors.append("CATL deep research requires a current integrity-passed evidence set")
    invalid_evidence = conn.execute(
        """SELECT COUNT(*) FROM evidence
           WHERE publication_id=?
             AND (quality_status!='accepted' OR substr(known_at, 1, 10) > ?)""",
        (publication_id, snapshot_known_date),
    ).fetchone()[0]
    if invalid_evidence:
        errors.append("evidence ledger contains rejected or future-dated entries")
    required = {
        "tencent_quote": len(coverage),
        "tencent_qfq_daily": len(coverage) * 250,
        "eastmoney_f10_main": len(coverage),
    }
    runs = {row["source_key"]: dict(row) for row in conn.execute(
        "SELECT source_key, status, accepted_count, finished_at FROM source_runs WHERE snapshot_id = ?",
        (snapshot["snapshot_id"],),
    ).fetchall()}
    for source_key, minimum in required.items():
        run = runs.get(source_key) or {}
        if run.get("status") != "success" or int(run.get("accepted_count") or 0) < minimum or not run.get("finished_at"):
            errors.append(f"source run is not publishable: {source_key}")
    return errors


def transition_publication(publication_id: str, action: str, db_path: Path = DB_PATH) -> dict[str, Any]:
    initialize(db_path)
    now = datetime.now(timezone.utc).isoformat()
    with closing(connect(db_path)) as conn:
        publication = conn.execute("SELECT * FROM publications WHERE id = ?", (publication_id,)).fetchone()
        if not publication:
            raise KeyError(publication_id)
        current = publication["status"]
        if action in {"approve", "publish"}:
            gate_errors = publication_data_gate_errors(conn, publication_id)
            if gate_errors:
                raise ValueError(f"release data gate failed: {'; '.join(gate_errors)}")
            from portfolio_committee import portfolio_release_errors

            research_gate_errors = portfolio_release_errors(publication_id, db_path)
            if research_gate_errors:
                raise ValueError(f"release research gate failed: {'; '.join(research_gate_errors)}")
        content_hash = publication_content_hash(conn, publication_id)
        if action == "approve":
            if current != "quality_passed":
                raise ValueError(f"only quality_passed publication can be approved; current={current}")
            conn.execute(
                "UPDATE publications SET status='approved', approved_at=?, approval_hash=? WHERE id=?",
                (now, content_hash, publication_id),
            )
            target, event_type = "approved", "park_approval"
        elif action == "publish":
            if current != "approved":
                raise ValueError(f"only approved publication can be published; current={current}")
            if publication["approval_hash"] != content_hash:
                conn.execute(
                    "UPDATE publications SET status='invalidated', blocked_reason='approval package changed after approval' WHERE id=?",
                    (publication_id,),
                )
                conn.execute(
                    """INSERT INTO publication_events
                       (publication_id, event_type, from_status, to_status, content_hash, actor, created_at)
                       VALUES (?, 'approval_invalidated', 'approved', 'invalidated', ?, 'system', ?)""",
                    (publication_id, content_hash, now),
                )
                conn.commit()
                raise ValueError("approval package changed after approval")
            conn.execute(
                "UPDATE publications SET status='published', published_at=? WHERE id=?",
                (now, publication_id),
            )
            target, event_type = "published", "park_publish"
        else:
            raise ValueError(f"unsupported publication action: {action}")
        conn.execute(
            """INSERT INTO publication_events
               (publication_id, event_type, from_status, to_status, content_hash, actor, created_at)
               VALUES (?, ?, ?, ?, ?, 'Park', ?)""",
            (publication_id, event_type, current, target, content_hash, now),
        )
        conn.commit()
        return {"publication_id": publication_id, "from_status": current, "status": target, "content_hash": content_hash, "at": now}


def publication_history(db_path: Path = DB_PATH) -> list[dict[str, Any]]:
    initialize(db_path)
    with closing(connect(db_path)) as conn:
        rows = conn.execute(
            """SELECT p.id, p.title, p.status, p.market_regime, p.equity_weight, p.cash_weight,
                      p.model_version, p.approved_at, p.published_at, p.blocked_reason,
                      s.id AS snapshot_id, s.data_mode, s.as_of, s.known_at, s.quality_status
               FROM publications p JOIN dataset_snapshots s ON s.id = p.snapshot_id
               ORDER BY s.created_at DESC"""
        ).fetchall()
    return _rows(rows)


def dump_json(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
