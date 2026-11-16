# Spec 05 — Design

- Implement `RenderEngine` interface and FFmpeg implementation in worker.
- Use ffprobe for input/output inspection.
- Build filter graphs from typed validated components; escape filter values correctly and never interpolate untrusted shell commands.
- Use job-specific temp directories, CPU/memory/time limits, cleanup and progress parser.
- Write output to a temporary object key; validate then atomically mark export complete.
- Preserve renderer version/config for diagnostics; do not log personal paths or content.
