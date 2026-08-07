#!/usr/bin/env python3
"""Build deterministic, non-sendable M1 approval request packets."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.verify_personal_holdings_risk_card_entry import (  # noqa: E402
    APPROVAL_AUTHORITY_TYPES,
    APPROVAL_METHODS,
    REQUIRED_APPROVALS,
    approval_scope,
    digest,
    load_json,
    scope_hash,
    verify_contract,
)


REQUEST_DETAILS: dict[str, dict[str, Any]] = {
    "market_data_rights": {
        "title": "市场数据目标使用权批准请求",
        "target": "数据提供方或覆盖全部 source key 的合同包权利人",
        "questions": [
            "是否明确批准 scope hash 所列字段用于最多 20 名中国大陆受邀会员的一对一付费私域风险卡？",
            "是否允许生成并展示 scope 中列明的衍生 risk/style/posture/leadership 输出？",
            "是否允许外部展示、30 天缓存、JSON/CSV 用户导出，以及人工复核人员的最小必要访问？",
            "是否禁止原始行情再分发或下载；若允许范围更窄，请逐项写明限制、署名、交易所审批和额外费用？",
            "批准覆盖哪些 source key、何时生效、何时到期，以及 scope 变化后是否必须重新批准？",
        ],
    },
    "securities_service_boundary": {
        "title": "证券服务边界专项批准请求",
        "target": "中国大陆专项法律顾问或持牌证券合作方",
        "questions": [
            "在 scope hash 所列收费、私域、个性化持仓映射和输出边界下，产品是否可以按当前设计开展？",
            "哪些输出可能构成证券投资咨询、投资顾问、荐股软件或其他持牌活动？",
            "现有永久禁区与人工复核是否充分；还必须增加哪些产品、文案、人员资质或合作安排？",
            "免费 concierge、付费 beta 和未来公开版本的法律结论是否不同？本批准只覆盖哪一档？",
            "意见适用的司法辖区、前提、失效条件、生效日和到期日是什么？",
        ],
    },
    "personal_information_processing": {
        "title": "个人持仓信息处理批准请求",
        "target": "隐私专项法律顾问或数据保护负责人",
        "questions": [
            "scope 中 ticker、组合权重、持有周期和用户风险规则的处理目的、最小必要性和法律基础是否成立？",
            "显式可撤回同意、人工最小访问、30 天保存、24 小时导出/删除是否足够？",
            "发送目的地、身份匹配、错误收件人、未授权披露和总停止开关还需哪些控制？",
            "可以保留哪些不含持仓正文的审计 receipt；删除、备份和事故通知如何执行？",
            "批准的司法辖区、用户范围、处理者/受托人、跨境边界、生效日和到期日是什么？",
        ],
    },
    "notification_channel": {
        "title": "私密通知渠道批准请求",
        "target": "所选发送渠道的业务管理员或合规管理员",
        "questions": [
            "是否批准最多 20 名受邀用户的一对一风险卡发送，并明确禁止群发、公开链接和未同意触达？",
            "渠道允许的内容、频率、发送身份、退订方式、审计字段和保存期限是什么？",
            "能否在第一张外发卡之前验证单用户停止和全局停止开关？",
            "错误收件人或未授权披露时，如何立即停止、通知 owner、纠正并留下最小 receipt？",
            "批准覆盖的具体 channel identity、生效日、到期日和失效条件是什么？",
        ],
    },
    "park_owner_approval": {
        "title": "Park 产品 owner 最终准入批准请求",
        "target": "Park 本人",
        "questions": [
            "是否批准 scope hash 所列 provider、字段、衍生输出、20 人、30 天、一对一私信和 paid 范围？",
            "是否确认已亲自查看另外四份批准摘要及其外部原件 hash/locator，而不是只批准路线图？",
            "是否接受每张卡人工复核、无具体买卖/仓位/目标价、无券商连接和无自动交易的永久边界？",
            "是否授权先执行 3–5 人 × 3 个交易日 smoke，只有独立验收后才扩至 20 人 × 10 个交易日？",
            "批准通过 GitHub 明确评论或签字文件给出，并写明生效日、到期日和失效条件吗？",
        ],
    },
}

RETURN_FIELDS = [
    "approval_id",
    "approval_key",
    "decision",
    "authority_identity",
    "verification_method",
    "scope_hash",
    "underlying_evidence_sha256",
    "safe_evidence_locator",
    "dual_control_hmac_sha256",
    "verified_by",
    "verified_at",
    "issued_at",
    "expires_at",
    "test_only=false",
    "receipt_hash",
]

RECORDING_RULES = [
    "必须明确返回 approved 或 rejected；沉默、口头意见、免责声明和测试通过都不是批准。",
    "原合同、法律意见、邮件正文、个人信息、账号、密钥和凭证不得提交到仓库。",
    "原件保存在受控系统；本地计算其 SHA-256，仓库只保存安全 locator、hash 和结构化摘要。",
    "authority 与 verifier identity 必须先用独立身份原件 hash/locator 登记到 ready trust policy；自称身份无效。",
    "每个 approval key 的 authority 与 verifier 必须是不同 safe identity；trust policy 要有 epoch、有效期、撤销边界和 Park-pinned current receipt。",
    "production 摘要必须由已登记 trust root 的外部 dual-control secret 对全部摘要字段生成 HMAC；operator 自算 receipt hash 无效。",
    "摘要必须使用 personal-holdings-risk-card-approval-v1，并由独立复核人核对原件后签发。",
    "任何更窄、不同或过期 scope 都保持 blocked；scope 变化必须重发请求并取得新批准。",
]


def _json_text(value: Mapping[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def build_request(payload: Mapping[str, Any], approval_key: str) -> dict[str, Any]:
    frozen_scope = approval_scope(payload)
    expected_scope_hash = scope_hash(payload)
    details = REQUEST_DETAILS[approval_key]
    request: dict[str, Any] = {
        "schema_version": "personal-holdings-risk-card-approval-request-v1",
        "request_id": f"m1-g1:{approval_key}:{expected_scope_hash[:12]}",
        "approval_key": approval_key,
        "request_status": "draft_not_sent",
        "outbound_action_authorized": False,
        "generated_at": payload["generated_at"],
        "source_contract_id": payload["contract_id"],
        "source_receipt_hash": payload["receipt_hash"],
        "scope_hash": expected_scope_hash,
        "title": details["title"],
        "target": details["target"],
        "acceptable_authority_types": sorted(APPROVAL_AUTHORITY_TYPES[approval_key]),
        "acceptable_verification_methods": sorted(APPROVAL_METHODS[approval_key]),
        "approval_scope": frozen_scope,
        "decision_questions": details["questions"],
        "required_return_fields": RETURN_FIELDS,
        "recording_rules": RECORDING_RULES,
    }
    request["packet_hash"] = digest(request)
    return request


def render_markdown(request: Mapping[str, Any]) -> str:
    question_lines = "\n".join(
        f"{index}. {question}"
        for index, question in enumerate(request["decision_questions"], start=1)
    )
    method_lines = "\n".join(
        f"- `{method}`" for method in request["acceptable_verification_methods"]
    )
    authority_lines = "\n".join(
        f"- `{authority}`" for authority in request["acceptable_authority_types"]
    )
    field_lines = "\n".join(f"- `{field}`" for field in request["required_return_fields"])
    rule_lines = "\n".join(f"- {rule}" for rule in request["recording_rules"])
    frozen_scope = json.dumps(
        request["approval_scope"], ensure_ascii=False, sort_keys=True, indent=2
    )
    return f"""# {request['title']}

Status: **DRAFT / NOT SENT**

这是一份可转发的决定请求，不是批准本身。`outbound_action_authorized=false`；发送、签约、购买或接受条款仍需 owner 明确授权。

- Request: `{request['request_id']}`
- Target: {request['target']}
- Scope hash: `{request['scope_hash']}`
- Source receipt: `{request['source_receipt_hash']}`
- Packet hash: `{request['packet_hash']}`

## 需要明确回答的问题

{question_lines}

## 可接受的批准机构类型

{authority_lines}

## 可接受的核验方法

{method_lines}

## 冻结 scope

以下 JSON 的 canonical SHA-256 必须等于上方 scope hash；任何字段变化都会使旧批准失效。

```json
{frozen_scope}
```

## 安全摘要必须返回

{field_lines}

## 记录边界

{rule_lines}
"""


def build_outputs(payload: Mapping[str, Any]) -> dict[Path, str]:
    outputs: dict[Path, str] = {}
    for approval_key in REQUIRED_APPROVALS:
        request = build_request(payload, approval_key)
        outputs[
            Path("evidence/market-regime-m1/approval-requests")
            / f"{approval_key}.request.json"
        ] = _json_text(request)
        outputs[
            Path("docs/market-regime/approval-requests")
            / f"{approval_key}.request.md"
        ] = render_markdown(request)
    return outputs


def apply_outputs(root: Path, outputs: Mapping[Path, str], *, check: bool) -> list[str]:
    mismatches: list[str] = []
    for relative, content in sorted(outputs.items(), key=lambda item: item[0].as_posix()):
        destination = root / relative
        if check:
            if not destination.is_file():
                mismatches.append(f"missing:{relative.as_posix()}")
            elif destination.read_text(encoding="utf-8") != content:
                mismatches.append(f"stale:{relative.as_posix()}")
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8")
    return mismatches


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument(
        "--contract",
        type=Path,
        default=Path("evidence/market-regime-m1/entry-readiness.json"),
    )
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    root = args.root.resolve()
    contract = args.contract if args.contract.is_absolute() else root / args.contract
    entry_schema = root / "product/schemas/personal-holdings-risk-card-entry-v1.schema.json"
    approval_schema = (
        root / "product/schemas/personal-holdings-risk-card-approval-v1.schema.json"
    )
    verify_contract(
        contract,
        entry_schema,
        repo_root=root,
        approval_schema_path=approval_schema,
    )
    payload = load_json(contract)
    if payload.get("test_only"):
        raise SystemExit("test_only contract cannot produce operator approval packets")
    outputs = build_outputs(payload)
    mismatches = apply_outputs(root, outputs, check=args.check)
    if mismatches:
        print(json.dumps({"approval_packets_current": False, "mismatches": mismatches}))
        return 1
    print(
        json.dumps(
            {
                "approval_packets_current": True,
                "count": len(REQUIRED_APPROVALS),
                "mode": "check" if args.check else "write",
                "scope_hash": scope_hash(payload),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
