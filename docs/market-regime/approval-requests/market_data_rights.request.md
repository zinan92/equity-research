# 市场数据目标使用权批准请求

Status: **DRAFT / NOT SENT**

这是一份可转发的决定请求，不是批准本身。`outbound_action_authorized=false`；发送、签约、购买或接受条款仍需 owner 明确授权。

- Request: `m1-g1:market_data_rights:fbd101f1933b`
- Target: 数据提供方或覆盖全部 source key 的合同包权利人
- Scope hash: `fbd101f1933bbc3603d4e35f4093d9bddede2520cd903a97b57d8aa6d71746bd`
- Source receipt: `70bd53f723319a65a94052dbe08d1c9092a35399338fb2c891b978ff8dea254a`
- Packet hash: `1668b1b5266821daff11aa73a19f063b99cf89005af99b45867c5e711a301c83`

## 需要明确回答的问题

1. 是否明确批准 scope hash 所列字段用于最多 20 名中国大陆受邀会员的一对一付费私域风险卡？
2. 是否允许生成并展示 scope 中列明的衍生 risk/style/posture/leadership 输出？
3. 是否允许外部展示、30 天缓存、JSON/CSV 用户导出，以及人工复核人员的最小必要访问？
4. 是否禁止原始行情再分发或下载；若允许范围更窄，请逐项写明限制、署名、交易所审批和额外费用？
5. 批准覆盖哪些 source key、何时生效、何时到期，以及 scope 变化后是否必须重新批准？

## 可接受的批准机构类型

- `data_provider`
- `data_rights_bundle`

## 可接受的核验方法

- `provider_agreement_bundle`
- `provider_executed_agreement`
- `provider_written_permission`

## 冻结 scope

以下 JSON 的 canonical SHA-256 必须等于上方 scope hash；任何字段变化都会使旧批准失效。

```json
{
  "communication_policy": {
    "permitted_capabilities": [
      "market_regime_explanation",
      "portfolio_exposure_mapping",
      "conditional_observation",
      "invalidation_condition",
      "historical_calibration",
      "user_defined_rule_echo"
    ],
    "prohibited_capabilities": [
      "specific_buy_instruction",
      "specific_sell_instruction",
      "market_timing_instruction",
      "target_price",
      "position_size_instruction",
      "broker_connection",
      "automatic_trading",
      "guaranteed_return"
    ],
    "required_disclosures": [
      "model_generated_unreviewed_until_human_review",
      "not_investment_advice",
      "data_freshness_and_quality",
      "invalidation_conditions",
      "source_identity"
    ]
  },
  "decision_window": {
    "a_share_session_policy": "prior_completed_session_only",
    "card_scheduled_at": "08:45:00",
    "knowledge_cutoff": "08:44:59",
    "quality_states": {
      "fresh": "eligible_for_supported_claims",
      "partial": "degrade_only_dependent_claims",
      "stale": "block_dependent_claims",
      "unknown": "block_dependent_claims"
    },
    "replay_policy": "reject_observations_after_knowledge_cutoff",
    "timezone": "Asia/Shanghai"
  },
  "human_review": {
    "checklist": [
      "data_freshness",
      "security_identity",
      "evidence_binding",
      "portfolio_owner_match",
      "no_prohibited_action_language",
      "invalidation_present",
      "privacy_destination_match"
    ],
    "correction_policy": "append_only_correction_never_rewrite_original_card",
    "correction_sla_hours": 4,
    "required_before_delivery": true
  },
  "incident_response": {
    "delivery_stop_control": "required_before_first_external_delivery",
    "owner_notification_sla_hours": 1,
    "unauthorized_disclosure": "stop_all_delivery_preserve_minimum_audit_escalate",
    "wrong_portfolio_identity": "stop_affected_delivery_notify_owner_correct_before_resume"
  },
  "personal_data_policy": {
    "consent_mode": "explicit_scope_bound_revocable",
    "deletion_sla_hours": 24,
    "export_sla_hours": 24,
    "human_access": "owner_authorized_audited_minimum_only",
    "minimum_inputs": [
      "ticker",
      "portfolio_weight",
      "holding_horizon",
      "user_risk_rule"
    ],
    "post_deletion_audit": "receipt_without_portfolio_content",
    "prohibited_inputs": [
      "broker_password",
      "broker_session",
      "account_balance",
      "cost_basis",
      "complete_trade_history"
    ]
  },
  "product_scope": {
    "audience": "invited_private_members",
    "commercial_mode": "paid",
    "delivery_channels": [
      "manual_private_message"
    ],
    "deployment_mode": "m1_concierge",
    "export_formats": [
      "json",
      "csv"
    ],
    "external_distribution": true,
    "max_cohort_size": 20,
    "portfolio_inputs": [
      "ticker",
      "portfolio_weight",
      "holding_horizon",
      "user_risk_rule"
    ],
    "product_name": "A 股开盘前个人持仓风险卡",
    "regions": [
      "CN"
    ],
    "retention_days": 30,
    "use_case": "08:45_a_share_preopen_personal_risk_card"
  },
  "requested_data_sources": [
    {
      "derived_outputs": [
        "risk_state",
        "posture_state",
        "style_state",
        "cross_asset_leadership"
      ],
      "fields": [
        "daily_ohlc",
        "market_timestamp",
        "session_metadata"
      ],
      "provider": "Yahoo Chart",
      "source_key": "yahoo_chart"
    },
    {
      "derived_outputs": [
        "a_share_risk_state",
        "a_share_style_state"
      ],
      "fields": [
        "a_share_index_daily_ohlc",
        "quote_timestamp"
      ],
      "provider": "Tencent K-line",
      "source_key": "tencent_kline"
    }
  ]
}
```

## 安全摘要必须返回

- `approval_id`
- `approval_key`
- `decision`
- `authority_identity`
- `verification_method`
- `scope_hash`
- `underlying_evidence_sha256`
- `safe_evidence_locator`
- `dual_control_hmac_sha256`
- `verified_by`
- `verified_at`
- `issued_at`
- `expires_at`
- `test_only=false`
- `receipt_hash`

## 记录边界

- 必须明确返回 approved 或 rejected；沉默、口头意见、免责声明和测试通过都不是批准。
- 原合同、法律意见、邮件正文、个人信息、账号、密钥和凭证不得提交到仓库。
- 原件保存在受控系统；本地计算其 SHA-256，仓库只保存安全 locator、hash 和结构化摘要。
- authority 与 verifier identity 必须先用独立身份原件 hash/locator 登记到 ready trust policy；自称身份无效。
- 每个 approval key 的 authority 与 verifier 必须是不同 safe identity；trust policy 要有 epoch、有效期、撤销边界和 Park-pinned current receipt。
- production 摘要必须由已登记 trust root 的外部 dual-control secret 对全部摘要字段生成 HMAC；operator 自算 receipt hash 无效。
- 摘要必须使用 personal-holdings-risk-card-approval-v1，并由独立复核人核对原件后签发。
- 任何更窄、不同或过期 scope 都保持 blocked；scope 变化必须重发请求并取得新批准。
