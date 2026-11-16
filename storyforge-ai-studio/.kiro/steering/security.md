---
inclusion: always
---
# Security and privacy steering

- Never commit secrets or include provider keys in client code. Use server-side environment/secret store.
- Authorize every object/project/media/job/export by verified user identity and ownership.
- Private storage only; use short-lived signed URLs.
- Treat uploaded media and transcripts as untrusted input.
- Validate file signature, MIME, size, duration, codecs, frame dimensions and paths before processing.
- Invoke FFmpeg safely with argv arrays, restricted protocols and timeouts; never use shell interpolation with user input.
- Do not log media, transcript, tokens or signed URLs.
- Enforce quotas, rate limits, concurrency controls and retention/deletion.
- Do not train on user data or send it to a third-party AI provider without explicit disclosure/consent.
- Keep asset licensing and attribution metadata through render/export.
