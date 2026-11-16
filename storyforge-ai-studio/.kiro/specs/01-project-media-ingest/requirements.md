# Spec 01 — Projects and media ingest

## Goal
Allow a signed-in creator to create a project and securely record/import one or more videos.

### Project management
- Create, list, view, rename and delete projects.
- A project belongs to exactly one verified user.
- Deletion cascades to project media, jobs, transcript, manifests, suggestions and exports, with explicit deletion status.

### Media ingest
- Import from gallery/files or record in-app.
- Show accepted format, max file size and max duration before upload.
- Upload is resumable/retryable/cancellable and has visible progress.
- Server validates file signature, codec, duration, dimensions and streams using ffprobe.
- Originals are immutable and stored privately.
- A completion event enqueues validation/analysis; HTTP request does not process video.
- Client survives temporary network loss and app background/foreground transitions.

### Security
- Upload grants are short-lived and scoped to one user/project/object.
- Server enforces quota and project ownership.
- No public ACL; no provider secrets in mobile bundle.
