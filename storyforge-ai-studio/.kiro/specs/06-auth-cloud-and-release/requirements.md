# Spec 06 — Auth, cloud providers and release

- Production authentication uses exactly one configured identity provider (Supabase Auth or Cognito).
- Backend validates JWT and enforces ownership for every resource.
- Object storage supports private S3-compatible storage and short-lived signed URLs.
- Queue abstraction supports local Redis/Celery and AWS SQS.
- Cloud deployment is opt-in, documented and cost-estimated.
- Budget alerts, per-user quotas, retention, lifecycle cleanup and observability exist before public beta.
- No cloud resources are created without explicit account-owner approval.
