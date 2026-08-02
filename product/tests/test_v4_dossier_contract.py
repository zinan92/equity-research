from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "product"))

from v4_dossier_contract import (  # noqa: E402
    V4_HEADINGS,
    assert_valid_v4_dossier,
    validate_v4_dossier,
    v4_contract_manifest,
)


def _sample() -> str:
    sections = []
    for index, heading in enumerate(V4_HEADINGS, 1):
        number = 9 if heading == "生产记录" else index
        if heading == "生产记录":
            body = "运行 ID：run-001。复跑策略：固定输入、更新 as_of 后重跑并保存 receipt；来源身份、正文哈希和输出哈希一并保留。模型与人工介入边界、来源数量和失败原因均写入生产记录。"
        elif heading == "一句话定位":
            body = "研究判断：这是一家被规模与现金回报同时约束的制造平台。已核验事实支持定位，并写明优势、代价和证伪条件。[F-01][S-01]。" * 2
        elif heading == "产业坐标":
            body = "产业链位置：上游材料 → 公司 → 下游客户；大白话逻辑链：需求发生、传导到这个环节、公司拿到钱以及断点如何证伪。[S-01]。" * 3
        elif heading == "创始人与团队":
            body = "事实：关键人物与公司治理安排已在年报披露。治理判断：继任与授权是持续观察项；角色和控制边界必须可回读。[S-01]。" * 3
        elif heading == "发展时间线":
            body = "2025 年：公司披露研发与产能节点。事件改变能力边界，仍需下一期验证；发展时间线只写真正改变公司的节点。[S-01]。" * 4
        elif heading == "技术、产品与商业模式":
            body = "业务：公司向客户交付产品并获得收入。客户、交付物和关键依赖均来自披露；收入驱动和经营约束不能只列产品名。[S-01]。" * 4
        elif heading == "财务与估值":
            body = "三年增长与盈利质量需要拆解；收入、最新期间的利润、现金和口径均有来源，并明确同期增长或下滑方向。估值只使用 point-in-time 证据。[S-01]。" * 4
        elif heading == "风险与点评":
            body = "核心风险：已知事实、触发条件和下一次核验必须同时写出；大白话点评给出可反驳结论，反题材不能写成免责声明。[S-01]。" * 5
        sections.append(f"## {number}. {heading}\n\n{body}\n")
    return "# 公司｜公司档案\n\n" + "\n".join(sections) + "\n## Sources\n\n| ID | URL |\n| --- | --- |\n| S-01 | https://example.com/a.pdf |\n"


class V4ContractTests(unittest.TestCase):
    def test_round7_order_and_markers_are_valid(self) -> None:
        self.assertEqual(validate_v4_dossier(_sample()), [])
        assert_valid_v4_dossier(_sample())

    def test_missing_section_and_http_are_rejected(self) -> None:
        text = _sample().replace("## 6. 护城河的证据链", "## 6. 错误章节")
        text = text.replace("https://example.com/a.pdf", "http://example.com/a.pdf")
        errors = validate_v4_dossier(text)
        self.assertTrue(any("section order" in error for error in errors))
        self.assertTrue(any("HTTPS" in error for error in errors))

    def test_fixture_is_allowed_only_as_explicit_preview(self) -> None:
        text = _sample() + "\n本文件来自 fixture 预览。\n"
        self.assertTrue(any("fixture" in error for error in validate_v4_dossier(text)))
        self.assertEqual([error for error in validate_v4_dossier(text, preview_only=True) if "fixture" in error], [])

    def test_manifest_is_reader_contract_not_legacy_c1(self) -> None:
        manifest = v4_contract_manifest()
        self.assertEqual(manifest["schema_version"], "park-v4-dossier-v1")
        self.assertEqual(manifest["section_order"], list(V4_HEADINGS))
        self.assertIn("legacy_boundary", manifest)

    def test_legacy_blind_set_is_not_a_publishable_reader_contract(self) -> None:
        for ticker in ("002371.SZ", "002594.SZ", "300308.SZ", "300502.SZ", "nvda"):
            path = ROOT / "docs" / "dossier-production" / "samples" / f"{ticker}-v1.md"
            self.assertTrue(path.exists(), ticker)
            self.assertTrue(validate_v4_dossier(path.read_text(encoding="utf-8")), ticker)


if __name__ == "__main__":
    unittest.main()
