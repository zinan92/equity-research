from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch


PRODUCT = Path(__file__).resolve().parents[1]
import sys

sys.path.insert(0, str(PRODUCT))

from data_core.market_regime_kline_world_context import (  # noqa: E402
    KlineWorldContextStore,
    build_kline_world_context,
)
from data_core.market_regime_kline_world_model import (  # noqa: E402
    DeepSeekWorldModelProvider,
    KlineWorldModelError,
    KlineWorldModelStore,
    SYSTEM_PROMPT,
    build_world_model_request,
    validate_model_output,
)
from product.tests.test_market_regime_kline_world_context import inputs  # noqa: E402


def fixture_context() -> dict:
    daily, macro, pack, bitcoin = inputs()
    return build_kline_world_context(
        daily=daily,
        macro=macro,
        pack=pack,
        bitcoin=bitcoin,
        allow_fixture=True,
    )


def series_by_key(context: dict) -> dict[str, dict]:
    return {item["key"]: item for item in context["series"]}


def observed_direction(item: dict) -> str:
    features = item["features"]
    value = (
        features["change_20d_bp"]
        if item["series_type"] == "rate_level"
        else features["return_20d_pct"]
    )
    return "rising" if value > 0.25 else "falling" if value < -0.25 else "flat"


def usable_pairs(context: dict) -> list[dict]:
    return [
        item
        for item in context["relationships"]
        if item["features"]["leader_20d"] in {item["lhs"], item["rhs"]}
    ]


def valid_output(context: dict) -> dict:
    by_key = series_by_key(context)
    pairs = usable_pairs(context)[:2]
    assert len(pairs) == 2

    def pair_refs(pair: dict) -> list[str]:
        return [
            pair["relationship_id"],
            by_key[pair["lhs"]]["series_id"],
            by_key[pair["rhs"]]["series_id"],
        ]

    first, second = pairs
    first_to = first["features"]["leader_20d"]
    first_from = first["rhs"] if first_to == first["lhs"] else first["lhs"]
    second_to = second["features"]["leader_20d"]
    second_from = second["rhs"] if second_to == second["lhs"] else second["lhs"]
    world_refs = [
        first["relationship_id"],
        by_key[first["lhs"]]["series_id"],
        by_key[first["rhs"]]["series_id"],
        second["relationship_id"],
    ]
    first_series = by_key[first_to]
    second_series = by_key[second_to]
    return {
        "world_model": {
            "headline": "跨资产领导权正在重新排序",
            "synthesis": "相对价格暗示资金可能偏离旧主线，转向趋势更完整且波动约束更小的资产。",
            "evidence_ids": world_refs,
        },
        "regime": {
            "posture": "wait",
            "risk": "mixed",
            "style": "mixed",
            "leadership": first_to,
            "explanation": "风险偏好与风格信号可能并不同步，因此更像有选择的轮动，而不是全面进攻。",
            "evidence_ids": world_refs,
        },
        "flow_map": [
            {
                "from_key": first_from,
                "to_key": first_to,
                "confidence": "high",
                "rationale": "相对强弱暗示资金可能从弱端转向领导端。",
                "evidence_ids": pair_refs(first),
            },
            {
                "from_key": second_from,
                "to_key": second_to,
                "confidence": "medium",
                "rationale": "持续的相对表现可能意味着第二条轮动线正在形成。",
                "evidence_ids": pair_refs(second),
            },
        ],
        "transmission_chain": [
            {
                "claim_class": "observed",
                "subject_id": first_series["series_id"],
                "direction": observed_direction(first_series),
                "statement": "第一领导资产维持当前趋势。",
                "evidence_ids": [first_series["series_id"]],
            },
            {
                "claim_class": "observed",
                "subject_id": second_series["series_id"],
                "direction": observed_direction(second_series),
                "statement": "第二领导资产也维持当前趋势。",
                "evidence_ids": [second_series["series_id"]],
            },
            {
                "claim_class": "inferred",
                "subject_id": first["relationship_id"],
                "direction": "not_applicable",
                "statement": "两端分化可能在塑造新的跨资产传导顺序。",
                "evidence_ids": pair_refs(first),
            },
        ],
        "contradictions": [
            {
                "statement": "第二组关系没有完全确认第一组主线，仍需保留反转可能。",
                "evidence_ids": [second["relationship_id"], first["relationship_id"]],
            }
        ],
        "trade_plan": [
            {
                "action": "rotate",
                "target": first_to,
                "horizon": "weeks",
                "condition": "只有相对领导保持时才执行轮动。",
                "rationale": "当前证据支持优先跟随更强的一端，同时保留证伪出口。",
                "evidence_ids": pair_refs(first),
                "falsifier_index": 0,
            }
        ],
        "falsifiers": [
            {
                "subject_id": first["relationship_id"],
                "trigger": "relative_leadership_reversal",
                "condition": "若相对领导关系反转，第一条资金迁移推断失效。",
                "evidence_ids": pair_refs(first),
            },
            {
                "subject_id": second_series["series_id"],
                "trigger": "trend_reversal",
                "condition": "若第二领导资产趋势反转，当前世界模型需要重建。",
                "evidence_ids": [second_series["series_id"]],
            },
        ],
    }


class FakeProvider:
    provider_name = "DeepSeek"
    model = "fixture-model"

    def __init__(self, output: dict, *, failure: BaseException | None = None) -> None:
        self.output = output
        self.failure = failure
        self.request = None

    def generate(self, request: dict) -> tuple[dict, dict]:
        self.request = request
        if self.failure:
            raise self.failure
        return deepcopy(self.output), {
            "request_id": "request-safe",
            "model": self.model,
            "finish_reason": "stop",
            "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        }


class PublishingProvider(FakeProvider):
    def __init__(self, output: dict, store: KlineWorldContextStore, replacement: dict) -> None:
        super().__init__(output)
        self.store = store
        self.replacement = replacement

    def generate(self, request: dict) -> tuple[dict, dict]:
        result = super().generate(request)
        self.store.publish(self.replacement)
        return result


class RetryProvider(FakeProvider):
    def __init__(self, first: dict, second: dict) -> None:
        super().__init__(second)
        self.first = first
        self.requests = []

    def generate(self, request: dict) -> tuple[dict, dict]:
        self.requests.append(deepcopy(request))
        output = self.first if len(self.requests) == 1 else self.output
        return deepcopy(output), {
            "request_id": f"request-{len(self.requests)}",
            "model": self.model,
            "finish_reason": "stop",
            "usage": {},
        }


class SequenceProvider:
    provider_name = "DeepSeek"
    model = "fixture-model"

    def __init__(self, steps: list[dict | BaseException]) -> None:
        self.steps = steps
        self.requests: list[dict] = []

    def generate(self, request: dict) -> tuple[dict, dict]:
        self.requests.append(deepcopy(request))
        step = self.steps[min(len(self.requests) - 1, len(self.steps) - 1)]
        if isinstance(step, BaseException):
            raise step
        return deepcopy(step), {
            "request_id": f"sequence-{len(self.requests)}",
            "model": self.model,
            "finish_reason": "stop",
            "usage": {},
        }


class KlineWorldModelTests(unittest.TestCase):
    def test_normal_provider_uses_bounded_non_thinking_structured_call(self) -> None:
        captured: dict = {}

        def fake_call(**kwargs):
            captured.update(kwargs)
            return {}, {"finish_reason": "stop"}

        provider = DeepSeekWorldModelProvider(Path("/tmp/test-deepseek-key"))
        with patch("deepseek_writer.call_structured_deepseek", side_effect=fake_call):
            result = provider.generate({"frozen": True})

        self.assertEqual(result, ({}, {"finish_reason": "stop"}))
        self.assertEqual(captured["max_tokens"], 10000)
        self.assertEqual(captured["reasoning_effort"], "low")
        self.assertEqual(captured["thinking_type"], "disabled")

    def test_prompt_names_exact_leadership_and_trade_falsifier_links(self) -> None:
        self.assertIn("不能使用 precious_metals、growth、defensive", SYSTEM_PROMPT)
        self.assertIn("每条 trade_plan.evidence_ids 必须与它所指向的 falsifier", SYSTEM_PROMPT)
        self.assertIn("恰好输出两个 falsifiers", SYSTEM_PROMPT)

    def test_request_contains_full_context_and_success_accepts_authored_advice(self) -> None:
        context = fixture_context()
        request = build_world_model_request(context)
        self.assertEqual(len(request["context"]["series"]), 17)
        self.assertEqual(len(request["context"]["series"][0]["points"]), 120)
        self.assertEqual(len(request["context"]["relationships"]), 12)
        self.assertEqual(
            request["context"]["series"][0]["point_columns"],
            ["date", "open", "high", "low", "close", "volume"],
        )
        self.assertIsInstance(request["context"]["series"][0]["points"][0], list)
        self.assertIsInstance(context["llm_projection"]["series"][0]["points"][0], dict)
        self.assertIn("No OHLC", request["point_encoding"])
        for original, encoded in zip(
            context["llm_projection"]["series"],
            request["context"]["series"],
            strict=True,
        ):
            self.assertEqual(
                [dict(zip(encoded["point_columns"], point, strict=True)) for point in encoded["points"]],
                original["points"],
            )
        for original, encoded in zip(
            context["llm_projection"]["relationships"],
            request["context"]["relationships"],
            strict=True,
        ):
            self.assertEqual(
                [dict(zip(encoded["point_columns"], point, strict=True)) for point in encoded["points"]],
                original["points"],
            )
        self.assertIn("must literally contain", request["validator_rules"]["synthesis_inference_language"])
        self.assertIn("exact leadership series_id", request["validator_rules"]["regime_leadership_citation"])
        catalog = request["validation_catalog"]
        by_key = series_by_key(context)
        self.assertEqual(
            catalog["falsifier_subject_ids"]["volatility_breakout"],
            [by_key["vix"]["series_id"]],
        )
        self.assertEqual(
            set(catalog["trade_target_series_ids"]["precious_metals"]),
            {by_key["gold"]["series_id"], by_key["silver"]["series_id"]},
        )
        self.assertEqual(catalog["trade_target_series_ids"]["cash"], [])
        self.assertTrue(catalog["rotation_leaders"])
        self.assertTrue(
            all(
                row["to_series_id"] == by_key[row["to_key"]]["series_id"]
                for row in catalog["rotation_leaders"]
            )
        )
        output = validate_model_output(valid_output(context), context)
        self.assertEqual(output["trade_plan"][0]["action"], "rotate")
        self.assertIn("可能", output["world_model"]["synthesis"])

    def test_flow_requires_exact_pair_endpoints_and_observed_leader(self) -> None:
        context = fixture_context()
        output = valid_output(context)
        output["flow_map"][0]["from_key"], output["flow_map"][0]["to_key"] = (
            output["flow_map"][0]["to_key"],
            output["flow_map"][0]["from_key"],
        )
        with self.assertRaisesRegex(KlineWorldModelError, "flow_direction"):
            validate_model_output(output, context)

        output = valid_output(context)
        output["flow_map"][0]["evidence_ids"] = output["flow_map"][1]["evidence_ids"]
        with self.assertRaisesRegex(KlineWorldModelError, "flow_direction"):
            validate_model_output(output, context)

    def test_unknown_citation_and_invented_number_fail_closed(self) -> None:
        context = fixture_context()
        output = valid_output(context)
        output["world_model"]["evidence_ids"][0] = "invented:id"
        with self.assertRaisesRegex(KlineWorldModelError, "citation"):
            validate_model_output(output, context)

        output = valid_output(context)
        output["trade_plan"][0]["rationale"] = "建议依据不存在的 +999999% 信号。"
        with self.assertRaisesRegex(KlineWorldModelError, "numeric"):
            validate_model_output(output, context)
        for invented in ("可能上涨 five percent。", "可能上涨半成。", "可能上涨½%。"):
            output = valid_output(context)
            output["trade_plan"][0]["rationale"] = invented
            with self.assertRaisesRegex(KlineWorldModelError, "numeric"):
                validate_model_output(output, context)

    def test_observed_direction_and_inference_language_are_bound(self) -> None:
        context = fixture_context()
        output = valid_output(context)
        output["transmission_chain"][0]["direction"] = "falling"
        with self.assertRaisesRegex(KlineWorldModelError, "chain_direction"):
            validate_model_output(output, context)

        output = valid_output(context)
        output["flow_map"][0]["rationale"] = "资金已经流入领导资产。"
        with self.assertRaisesRegex(KlineWorldModelError, "semantic"):
            validate_model_output(output, context)

    def test_series_key_alias_and_declared_window_labels_normalize_safely(self) -> None:
        context = fixture_context()
        output = valid_output(context)
        first_subject = output["transmission_chain"][0]["subject_id"]
        item = next(row for row in context["series"] if row["series_id"] == first_subject)
        output["transmission_chain"][0]["subject_id"] = item["key"]
        output["transmission_chain"][0]["statement"] = "该资产20日趋势维持当前方向。"
        normalized = validate_model_output(output, context)
        self.assertEqual(normalized["transmission_chain"][0]["subject_id"], first_subject)

    def test_advice_is_allowed_but_auto_execution_guarantees_and_sizing_are_not(self) -> None:
        context = fixture_context()
        output = valid_output(context)
        output["trade_plan"][0]["action"] = "buy"
        validate_model_output(output, context)

        for unsafe in (
            "系统会自动下单完成轮动。",
            "这一交易保证收益。",
            "建议使用 80% 仓位。",
        ):
            output = valid_output(context)
            output["trade_plan"][0]["rationale"] = unsafe
            with self.assertRaisesRegex(KlineWorldModelError, "semantic"):
                validate_model_output(output, context)

    def test_success_store_replays_identity_and_code_owned_confidence(self) -> None:
        context = fixture_context()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            context_store = KlineWorldContextStore(root / "context", allow_fixture=True)
            context_store.publish(context)
            store = KlineWorldModelStore(context_store, root / "model")
            provider = FakeProvider(valid_output(context))
            artifact = store.compile_latest(provider)
            replay = store.latest(expected_context_id=context["context_id"])
            self.assertEqual(replay["world_model_id"], artifact["world_model_id"])
            self.assertEqual(replay["generation_status"], "model_generated_unreviewed")
            self.assertTrue(replay["truth_boundary"]["contains_investment_advice"])
            self.assertFalse(replay["truth_boundary"]["automatic_execution_eligible"])
            self.assertEqual(replay["code_owned_confidence"]["directional_clarity"]["score"], 0.84)
            self.assertEqual(provider.request["context"]["context_id"], context["context_id"])

    def test_one_bounded_semantic_retry_uses_fixed_feedback_and_can_recover(self) -> None:
        context = fixture_context()
        invalid = valid_output(context)
        invalid["world_model"]["headline"] = "English output is not accepted"
        provider = RetryProvider(invalid, valid_output(context))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            context_store = KlineWorldContextStore(root / "context", allow_fixture=True)
            context_store.publish(context)
            store = KlineWorldModelStore(context_store, root / "model")
            artifact = store.compile_latest(provider)
            self.assertEqual(artifact["generation_status"], "model_generated_unreviewed")
            self.assertEqual(len(provider.requests), 2)
            self.assertNotIn("validation_feedback", provider.requests[0])
            self.assertEqual(
                provider.requests[1]["validation_feedback"]["failed_codes"],
                ["output_semantic_invalid:world_model.headline"],
            )
            state = json.loads((root / "model/state.json").read_text(encoding="utf-8"))
            receipt_path = root / "model" / state["pointer"]["receipt"]["path"]
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            self.assertEqual(receipt["attempt_count"], 2)
            self.assertEqual(
                receipt["validation_feedback"],
                ["output_semantic_invalid:world_model.headline"],
            )
            self.assertEqual(
                receipt["attempt_outcomes"],
                ["output_semantic_invalid:world_model.headline", "accepted"],
            )

    def test_truncation_retries_same_frozen_request_and_can_recover(self) -> None:
        context = fixture_context()
        provider = SequenceProvider(
            [
                RuntimeError("DeepSeek structured response did not finish cleanly: length"),
                valid_output(context),
            ]
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            context_store = KlineWorldContextStore(root / "context", allow_fixture=True)
            context_store.publish(context)
            store = KlineWorldModelStore(context_store, root / "model")
            artifact = store.compile_latest(provider)
            self.assertEqual(artifact["generation_status"], "model_generated_unreviewed")
            self.assertEqual(len(provider.requests), 2)
            self.assertEqual(provider.requests[0], provider.requests[1])
            state = json.loads((root / "model/state.json").read_text(encoding="utf-8"))
            receipt = json.loads(
                (root / "model" / state["pointer"]["receipt"]["path"]).read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(receipt["attempt_outcomes"], ["provider_truncated", "accepted"])
            self.assertEqual(receipt["validation_feedback"], [])

    def test_two_path_scoped_corrections_recover_with_code_owned_hints(self) -> None:
        context = fixture_context()
        leadership_invalid = valid_output(context)
        leadership_key = leadership_invalid["regime"]["leadership"]
        leadership_invalid["regime"]["evidence_ids"] = [
            reference
            for reference in leadership_invalid["regime"]["evidence_ids"]
            if series_by_key(context)[leadership_key]["series_id"] != reference
        ]
        synthesis_invalid = valid_output(context)
        synthesis_invalid["world_model"]["synthesis"] = "跨资产资金轮动正在形成。"
        provider = SequenceProvider(
            [leadership_invalid, synthesis_invalid, valid_output(context)]
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            context_store = KlineWorldContextStore(root / "context", allow_fixture=True)
            context_store.publish(context)
            store = KlineWorldModelStore(context_store, root / "model")
            artifact = store.compile_latest(provider)
            self.assertEqual(artifact["generation_status"], "model_generated_unreviewed")
            self.assertEqual(len(provider.requests), 3)
            final_feedback = provider.requests[2]["validation_feedback"]
            self.assertEqual(
                final_feedback["failed_codes"],
                [
                    "output_citation_invalid:regime_leadership",
                    "output_semantic_invalid:world_model.synthesis",
                ],
            )
            self.assertEqual(len(final_feedback["field_hints"]), 2)
            state = json.loads((root / "model/state.json").read_text(encoding="utf-8"))
            receipt = json.loads(
                (root / "model" / state["pointer"]["receipt"]["path"]).read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(
                receipt["attempt_outcomes"],
                [
                    "output_citation_invalid:regime_leadership",
                    "output_semantic_invalid:world_model.synthesis",
                    "accepted",
                ],
            )

    def test_real_failure_paths_receive_exact_catalog_feedback(self) -> None:
        context = fixture_context()
        falsifier_invalid = valid_output(context)
        falsifier_invalid["falsifiers"][0]["trigger"] = "yield_breakout"
        numeric_invalid = valid_output(context)
        numeric_invalid["contradictions"][0]["statement"] = (
            "当前矛盾包含不存在的 +999999% 数值。"
        )
        provider = SequenceProvider(
            [falsifier_invalid, numeric_invalid, valid_output(context)]
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            context_store = KlineWorldContextStore(
                root / "context", allow_fixture=True
            )
            context_store.publish(context)
            artifact = KlineWorldModelStore(
                context_store, root / "model"
            ).compile_latest(provider)
            self.assertEqual(artifact["generation_status"], "model_generated_unreviewed")
            self.assertIn(
                "falsifier_subject_ids",
                " ".join(
                    provider.requests[1]["validation_feedback"]["field_hints"]
                ),
            )
            final_hints = " ".join(
                provider.requests[2]["validation_feedback"]["field_hints"]
            )
            self.assertIn("numeric literal", final_hints)

        trade_invalid = valid_output(context)
        trade_invalid["trade_plan"][0]["action"] = "buy"
        trade_invalid["trade_plan"][0]["target"] = "vix"
        provider = SequenceProvider([trade_invalid, valid_output(context)])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            context_store = KlineWorldContextStore(
                root / "context", allow_fixture=True
            )
            context_store.publish(context)
            artifact = KlineWorldModelStore(
                context_store, root / "model"
            ).compile_latest(provider)
            self.assertEqual(artifact["generation_status"], "model_generated_unreviewed")
            hints = " ".join(
                provider.requests[1]["validation_feedback"]["field_hints"]
            )
            self.assertIn("trade_target_series_ids", hints)

    def test_timeout_exhaustion_records_three_attempts_without_feedback(self) -> None:
        context = fixture_context()
        provider = SequenceProvider([TimeoutError("secret transport detail")])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            context_store = KlineWorldContextStore(root / "context", allow_fixture=True)
            context_store.publish(context)
            store = KlineWorldModelStore(context_store, root / "model")
            artifact = store.compile_latest(provider)
            self.assertEqual(artifact["failure_code"], "provider_timeout")
            self.assertEqual(len(provider.requests), 3)
            state = json.loads((root / "model/state.json").read_text(encoding="utf-8"))
            receipt = json.loads(
                (root / "model" / state["pointer"]["receipt"]["path"]).read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(receipt["attempt_outcomes"], ["provider_timeout"] * 3)
            self.assertEqual(receipt["validation_feedback"], [])
            self.assertNotIn("secret transport detail", json.dumps(receipt))

    def test_coherently_rehashed_attempt_ledger_tamper_fails_replay(self) -> None:
        context = fixture_context()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            context_store = KlineWorldContextStore(root / "context", allow_fixture=True)
            context_store.publish(context)
            store = KlineWorldModelStore(context_store, root / "model")
            store.compile_latest(FakeProvider(valid_output(context)))
            state_path = root / "model/state.json"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            receipt_path = root / "model" / state["pointer"]["receipt"]["path"]
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            receipt["attempt_outcomes"] = ["provider_error"]
            encoded = (
                json.dumps(receipt, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                + "\n"
            ).encode("utf-8")
            receipt_path.write_bytes(encoded)
            state["pointer"]["receipt"]["sha256"] = sha256(encoded).hexdigest()
            state_path.write_text(json.dumps(state), encoding="utf-8")
            with self.assertRaisesRegex(KlineWorldModelError, "attempt_receipt_invalid"):
                store.latest()

    def test_no_provider_and_timeout_publish_same_context_unavailable_without_advice(self) -> None:
        context = fixture_context()
        for provider, reason in (
            (None, "provider_missing"),
            (FakeProvider(valid_output(context), failure=TimeoutError("secret detail")), "provider_timeout"),
            (
                FakeProvider(
                    valid_output(context),
                    failure=RuntimeError("structured response did not finish cleanly: length"),
                ),
                "provider_truncated",
            ),
        ):
            with self.subTest(reason=reason), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                context_store = KlineWorldContextStore(root / "context", allow_fixture=True)
                context_store.publish(context)
                store = KlineWorldModelStore(context_store, root / "model")
                artifact = store.compile_latest(provider)
                self.assertEqual(artifact["context_id"], context["context_id"])
                self.assertEqual(artifact["failure_code"], reason)
                self.assertEqual(artifact["output"]["trade_plan"], [])
                self.assertEqual(artifact["output"]["flow_map"], [])
                self.assertFalse(artifact["truth_boundary"]["contains_investment_advice"])
                self.assertNotIn("secret detail", json.dumps(artifact, ensure_ascii=False))

    def test_secret_shaped_provider_metadata_never_persists(self) -> None:
        context = fixture_context()

        class UnsafeProvider(FakeProvider):
            provider_name = "AKIAIOSFODNN7EXAMPLE"
            model = "sk-live-AbCdEf123456"

            def generate(self, request: dict) -> tuple[dict, dict]:
                output, receipt = super().generate(request)
                receipt["request_id"] = "ghp_AbCdEf1234567890"
                return output, receipt

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            context_store = KlineWorldContextStore(root / "context", allow_fixture=True)
            context_store.publish(context)
            store = KlineWorldModelStore(context_store, root / "model")
            artifact = store.compile_latest(UnsafeProvider(valid_output(context)))
            self.assertEqual(artifact["generation_status"], "interpretation_unavailable")
            payload = (root / "model").read_text() if (root / "model").is_file() else "".join(
                path.read_text(encoding="utf-8") for path in (root / "model").rglob("*.json")
            )
            self.assertNotIn("AKIAIOSFODNN7EXAMPLE", payload)
            self.assertNotIn("sk-live", payload)
            self.assertNotIn("ghp_", payload)

    def test_tampered_artifact_or_context_provenance_fails_replay(self) -> None:
        context = fixture_context()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            context_store = KlineWorldContextStore(root / "context", allow_fixture=True)
            context_store.publish(context)
            store = KlineWorldModelStore(context_store, root / "model")
            store.compile_latest(FakeProvider(valid_output(context)))
            state = json.loads((root / "model/state.json").read_text(encoding="utf-8"))
            artifact_path = root / "model" / state["pointer"]["artifact"]["path"]
            artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
            artifact["output"]["world_model"]["headline"] = "tampered"
            artifact_path.write_text(json.dumps(artifact), encoding="utf-8")
            with self.assertRaisesRegex(KlineWorldModelError, "hash"):
                store.latest()

    def test_context_advance_during_provider_call_does_not_publish_stale_advice(self) -> None:
        context = fixture_context()
        daily, macro, pack, bitcoin = inputs()
        daily["instruments"][0]["bars"][-1]["close"] += 1
        daily["instruments"][0]["bars"][-1]["high"] += 1
        replacement = build_kline_world_context(
            daily=daily,
            macro=macro,
            pack=pack,
            bitcoin=bitcoin,
            allow_fixture=True,
        )
        self.assertNotEqual(context["context_id"], replacement["context_id"])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            context_store = KlineWorldContextStore(root / "context", allow_fixture=True)
            context_store.publish(context)
            store = KlineWorldModelStore(context_store, root / "model")
            provider = PublishingProvider(valid_output(context), context_store, replacement)
            with self.assertRaisesRegex(KlineWorldModelError, "context_advanced"):
                store.compile_latest(provider)
            self.assertFalse((root / "model/state.json").exists())


if __name__ == "__main__":
    unittest.main()
