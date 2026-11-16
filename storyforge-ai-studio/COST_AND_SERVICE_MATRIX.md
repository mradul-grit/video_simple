# Cost-first service matrix

## Principle
Free-first does not mean quality-blind. Start locally with open-source software, then spend only where measured quality, speed or reliability requires it. All cloud services are optional adapters. Prices and free quotas change; verify the provider's pricing page immediately before enabling a paid or billable service.

| Capability | Default for development | Optional cloud/paid path | Cost / quality notes |
|---|---|---|---|
| Mobile client | Flutter SDK | App Store / Play Store accounts when distributing | Framework is free; publishing accounts and testing devices may cost. |
| API | FastAPI locally in Docker | AWS ECS/App Runner/Lambda control plane | Local is free; hosted compute is billable. Do not run always-on services without a budget. |
| Database | Postgres in Docker | Supabase Free Postgres; later managed Postgres | Supabase free currently lists 500 MB DB, 50,000 MAU, 5 GB egress, 1 GB storage and pauses after one week inactive. Not suitable as sole durable production database without backup/uptime plan. |
| Authentication | Local dev-only auth/test identity | Supabase Auth or Cognito | Choose one provider for beta. No production mock auth. |
| Media storage | Local filesystem | AWS S3 or Cloudflare R2 | S3 fits AWS queue/workers and credits; R2 currently lists 10 GB-month, 1M Class A, 10M Class B and free egress for standard storage. Cross-provider transfer should be measured. |
| Queue | Redis + Celery locally | AWS SQS | SQS is durable and decouples workers. Queue messages contain IDs/keys, never raw video bytes or secrets. |
| Speech-to-text | Faster-Whisper local, CPU int8 | GPU worker; managed speech API as optional adapter | Local is free except compute/electricity. Large models can require substantial RAM/VRAM. Benchmark actual Hinglish samples. |
| VAD | Silero VAD or equivalent maintained open-source implementation | Managed speech services if justified | Helps locate speech and pauses; never treat VAD alone as editorial intent. |
| Story analysis | Ollama local instruct model | Bedrock or other API provider behind adapter | Local cost depends on hardware; use structured output + source grounding. Model quality varies. |
| Image search | Openverse API with license filtering | Pixabay/Pexels/licensed stock | Always retain source URL, creator, license, attribution text, retrieval date and terms. Never assume all search results permit commercial use. |
| Image generation | Optional local ComfyUI if capable GPU is available | Bedrock or another approved provider | Local generation is not “free” if hardware/time is counted. Paid generation needs quotas and per-project estimates. |
| Audio cleanup | FFmpeg filters + optional open-source denoiser | Dedicated paid enhancement API | Offer subtle presets and A/B preview; avoid over-processing. |
| Video rendering | FFmpeg in local worker Docker | ECS/EC2 Spot/Fargate workers | CPU-heavy. Use background jobs, autoscaling and usage quotas. |
| Monitoring | Structured logs + OpenTelemetry local | CloudWatch / Sentry free tier | Do not send raw audio/video, transcripts or secrets to telemetry by default. |
| Source control | Git + private GitHub repo | GitHub Actions | CI free quotas can change; do not store secrets in repository. |

## Recommended service selection

### Stage A — build for ₹0 service spend
- Local Flutter client.
- Local FastAPI + Postgres + Redis using Docker Compose.
- Local filesystem media storage.
- FFmpeg local worker.
- Faster-Whisper when local machine can run it; mock provider only for automated tests.
- Ollama only if local RAM/CPU/GPU can support an appropriate model; otherwise use grounded deterministic output in tests and evaluate a small API budget only after user approval.
- Openverse for discoverable open-licensed assets.

### Stage B — small private beta
- Supabase Free for auth/Postgres only if its pause, egress, DB and backup limitations are acceptable.
- Store large media in a private S3 or R2 bucket, not the relational database.
- Worker can run on a controlled machine or an explicitly approved AWS compute option.
- Introduce per-user duration/storage quotas, daily spend limit, cleanup policy and alerts before inviting testers.

### Stage C — production path
- AWS S3 + SQS + ECS workers + CloudWatch; optionally Cognito and managed database after cost review.
- Run workers only when jobs exist; use Spot capacity only with safe retries and checkpointing.
- Separate API/control plane from heavy GPU/render workers.
- Apply object lifecycle deletion to temporary originals/proxies/failed outputs according to the product's retention policy.

## AWS credits
The user has previously mentioned AWS promotional credits. Treat any credits as **unverified until checked in the AWS Billing console**. Credits are not the same as a permanently free service, can have eligible-service/region/expiry rules, and do not guarantee that every service is covered. Never deploy or create resources automatically. Before use: confirm remaining amount, expiry, eligible products, region and account plan; create budget alerts and hard usage limits where available.

## Required cost controls
- Maximum upload size and duration configurable server-side.
- Free account daily/monthly minutes and storage quota.
- Max concurrent jobs per user and global queue backpressure.
- Image generation disabled by default; explicit opt-in and credit estimate.
- Cache visual search with provider-required TTL (Pixabay requires 24-hour caching).
- Keep original files only for a user-visible retention period; provide immediate delete action.
- Track usage by provider, model, input seconds, output seconds, image count, bytes and render time.
- Show an estimated cost before paid provider calls when pricing is available.
- Circuit breaker on budget threshold and provider outage.
- No surprise upgrade, no hidden paid API, no uncontrolled loops/retries.

## Quality rule
Do not silently substitute a low-quality model to preserve a free tier. Label quality modes (Local Draft / High Quality) and explain expected speed/cost. Evaluate on a fixed set of real, consented Hindi, Indian English and Hinglish clips before choosing defaults.
