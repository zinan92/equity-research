-- Development-only seed: capability metadata, not sample market facts.
insert into control.source_manifests (
  manifest_hash, source_key, domain_scope, authority_tier,
  provider_version, provider_schema_version, license_status,
  source_url, quality_flags, active
) values (
  repeat('0', 64),
  'development_seed_v1',
  array['market','fundamental','document','estimate','event'],
  'supplementary_only',
  'development-only',
  'development-only',
  'test_fixture',
  'fixture://canonical-authority-v1',
  array['fixture_only','never_publish'],
  false
)
on conflict (manifest_hash) do nothing;
