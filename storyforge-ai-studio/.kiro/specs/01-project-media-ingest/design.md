# Spec 01 — Design

- Define SQLAlchemy models and Alembic migrations for Project, MediaAsset and Job.
- Implement project repository/service/API boundary.
- Introduce `ObjectStorage` protocol with LocalFilesystem adapter; S3-compatible adapter can follow after contract tests.
- For local uploads, use a dedicated upload endpoint with strict size limits; design signed multipart upload for S3/R2 production.
- Client uses repository abstraction and local draft metadata; upload state persisted for restart recovery.
- Use ffprobe JSON output parsed into a validated media metadata model.
- Store media checksums and content metadata; never place binaries in Postgres.
