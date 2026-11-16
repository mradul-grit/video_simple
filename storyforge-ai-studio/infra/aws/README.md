# AWS production path (design only; not deployed)

Suggested later architecture:
- S3 private buckets: originals, proxies, generated visual assets, exports. Separate prefixes/buckets and lifecycle policies.
- SQS queues: analysis and render jobs; dead-letter queue; visibility timeout above realistic task duration with heartbeats/extension.
- ECS tasks: API service and worker tasks. Evaluate Fargate, Fargate Spot or EC2 Spot based on measured CPU/GPU requirements and restart tolerance.
- CloudWatch logs/metrics/alarms and cost budgets.
- Cognito only if choosing AWS-native auth; do not add it alongside Supabase Auth without a migration design.
- Optional CloudFront signed URLs for exports.

Before deploy: estimate cost by 100/1,000/10,000 rendered minutes; identify region, expected duration, concurrency, CPU/GPU, storage, data transfer, retention, logs, backups and free-credit eligibility. Ask the account owner to approve the estimate and resource list. Use infrastructure-as-code and destroy test stacks after verification.
