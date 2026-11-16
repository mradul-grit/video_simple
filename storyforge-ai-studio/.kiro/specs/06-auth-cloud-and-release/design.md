# Spec 06 — Design

- Implement auth provider interface and one concrete provider for beta; no dual identity system.
- Implement S3 adapter using role-based credentials in cloud and development-only local env vars.
- Implement SQS adapter with DLQ/visibility-timeout strategy and idempotent worker jobs.
- Keep Supabase Postgres as one early-beta option; production database selection requires backup/availability/cost analysis.
- Add infra-as-code only after written review of regions, services, resource sizes, budget and teardown.
- Add CI secret/dependency scanning, tests and build artifacts; no deployment job without manual approval.
