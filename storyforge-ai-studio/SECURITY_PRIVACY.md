# Security, privacy and media rights requirements

## User media
- Explain what is uploaded and why; obtain user action/consent before cloud upload or external AI processing.
- Default projects and objects to private. Never expose public bucket ACLs.
- Original source remains unchanged. Store edits separately.
- Use short-lived signed upload/download URLs and validate owner/project/object relationship on every request.
- Provide project deletion and media deletion. Deletion must cover originals, proxies, transcripts, suggestions, exports and queued/running jobs; document backup/lifecycle limits honestly.
- Retention defaults must be explicit and configurable. Avoid retaining source video indefinitely.
- Do not use user media/transcripts to train models or for unrelated analytics.
- Avoid logging raw transcript, image contents, signed URLs, tokens, file names that contain personal data or secrets.

## API and infrastructure
- Server-side secrets only; `.env` ignored; `.env.example` placeholders only.
- JWT validation: signature, issuer, audience, expiry and subject. Never trust user ID in request body.
- Authorization checks at every project, media, job and export access.
- Rate limiting and quotas for upload, analysis, visual search, image generation and render jobs.
- Validate MIME, file signature, codec, dimensions, duration, file size and audio/video streams.
- Restrict FFmpeg protocols and input paths; no arbitrary remote URLs or shell command interpolation.
- Use subprocess argument arrays; safe temp directories; path canonicalization; cleanup; timeouts and worker resource limits.
- CORS allowlist; TLS in cloud; database least-privilege credentials; encryption at rest where provider supports it.
- Protect against IDOR, SSRF, path traversal, zip bombs, decompression bombs, malformed media, replayed upload grants and job flooding.
- Use request IDs and security-safe audit events.

## AI quality and safety
- Treat transcript/media as untrusted user content, not tool instructions.
- LLM output must validate against a strict schema. Reject malformed/extra fields.
- Every editorial caption must cite source transcript segment IDs and/or timestamps. If it cannot, reject it or mark it as a suggestion needing correction.
- Do not infer sensitive characteristics about speakers from video/audio.
- No face identity recognition. No cloning a person's voice. No impersonation feature.
- Make synthetic/generated visuals visually distinguishable in the review UI when relevant; preserve creator and license metadata for stock media.
- Show low confidence and request human review. Do not invent what the video depicts.

## Media licensing
- Search results are not automatically licensed for every use. Store exact license identifier, creator, provider, source page, attribution text, retrieval date and modification state.
- For MVP, default to public-domain/CC0 and CC BY-compatible images where license data is present. Exclude non-commercial and no-derivatives licenses from default commercial workflow. Do not assume every asset can be modified, cropped or used in an advertisement.
- Display attribution where required, and include a generated credits screen/file for final exports when required by license/terms.
- Follow each provider's API terms, cache, rate limits, attribution and download rules.
- Do not bundle copyrighted music, paid stock, fonts, model weights or third-party binaries without checking redistribution rights.
- Maintain `THIRD_PARTY_NOTICES.md` as dependencies/providers are added.

## Operational controls
- User-visible data export/delete path.
- Secret rotation procedure.
- Dependency and container vulnerability scanning in CI.
- Backup/restore plan before production.
- Incident response contact/process before public release.
