# StoryForge AI Studio — Kiro Build Pack

> Working title. Rename after product and trademark checks.

StoryForge turns a creator's talking-head recording into a reviewed, story-aware, vertical social video. It analyses speech, proposes edits, creates concise editorial captions, finds relevant supporting visuals, and renders a polished export.

This repository is an implementation blueprint and starter backend scaffold. It is designed to be opened as a Git repository in Kiro. The mobile application is intentionally specified rather than pre-generated so Kiro can create a clean Flutter platform project in the environment where Android/iOS tooling is installed.

## Start here

1. Read `START_WITH_KIRO.md`.
2. Create a private GitHub repository named `storyforge-ai-studio` (or your preferred name).
3. Extract this ZIP into the repository root and commit the untouched blueprint as the first commit.
4. Open the repository folder in Kiro IDE.
5. Copy the single prompt in `START_WITH_KIRO.md` into Kiro Agent Chat.
6. Let Kiro inspect the environment and repository, create its spec plan, and then implement one vertical slice at a time.
7. Review every generated diff and test result. Do not ask the agent to implement all phases in one unreviewed operation.

## What is in this pack

- Product brief, UX requirements, quality bar and roadmap.
- Architecture and low-cost service matrix.
- API contract and versioned edit-manifest schema.
- Kiro steering files and phased Kiro specs.
- A minimal FastAPI health-check scaffold, Dockerfile, local Postgres/Redis Compose stack and backend test.
- Security, privacy, licensing, observability and cost guardrails.

## Local-first principles

- Local development must work without AWS credentials or paid AI API keys.
- `mock` providers are permitted for UI/contract tests only. They must be clearly labelled as demo data and never presented as real AI output.
- Real AI providers must be explicitly configured. Missing credentials must produce actionable configuration errors, not fake success.
- Keep storage, queue, transcription, language-model, image-search and image-generation providers behind interfaces.
- No upload, transcription, image generation or rendering should run synchronously inside an HTTP request.

## Current scaffold

The FastAPI scaffold exposes liveness and readiness checks. Kiro must build the product features from the specs. No production credentials, production bucket, AWS account, external API keys, generated media or private user data are included.

## Non-goals for the first MVP

- A full desktop-grade multitrack nonlinear editor.
- Automatic posting to Instagram or bypassing Instagram's platform rules.
- Training a proprietary foundation model.
- Automatically publishing AI-generated edits without a user review step.
- Bundled copyrighted stock footage, music, fonts or pretrained model weights.

## Product quality principle

**The user should spend more time telling stories and less time editing videos.**
