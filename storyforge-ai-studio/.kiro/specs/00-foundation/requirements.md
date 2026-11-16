# Spec 00 — Foundation requirements

## Goal
Establish a reproducible monorepo foundation and the first runnable vertical slice.

## User stories and acceptance criteria

### Project setup
- As a developer, I can run the backend locally using documented commands.
- Given the documented environment, when I run the stack, then API, Postgres and Redis become healthy.
- If an optional service is unavailable, the API reports a safe degraded readiness state without exposing credentials.

### Mobile shell
- As a creator, I can open the mobile app and understand how to start a project.
- Home/New Project/Editor/Exports/Settings navigation exists and has meaningful empty states.
- The UI must not show actions as functional when not implemented.

### Developer quality
- Python tests, formatter and static analysis commands are documented and runnable.
- Flutter analyze/test run when Flutter is installed.
- Secrets are excluded from Git; no cloud resource is created.
