# Shared K-line reader and audited LLM provider fallback

Status: accepted

Daily and Weekly use one user-facing reader contract: each asset renders its
identity, eligible period cards, position/structure/odds, and combined meaning;
the period set differs by the edition and the asset's real source capability.
Static chart snapshots are part of the reader content, while source and
provider details stay in a visible status area. Every DeepSeek-backed layer may
fall back to a read-only Codex CLI invocation after DeepSeek's final failure.
Both providers receive the same frozen evidence and pass the same validators.
If both fail, the report still publishes verified charts and deterministic
readings but explicitly says that both model explanations failed, with neither
old prose nor fabricated data reused.

This separates two failure classes that must not be conflated: data-source
failure remains an evidence state, while model-provider failure selects an
audited explanation provider or produces a clearly labelled degraded edition.
