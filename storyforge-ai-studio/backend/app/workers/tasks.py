from app.workers.celery_app import celery_app


@celery_app.task(bind=True, autoretry_for=(TimeoutError,), retry_backoff=True, max_retries=3)
def scaffold_health_task(self) -> dict[str, str]:
    """A harmless worker smoke-test task; replace with idempotent domain jobs."""
    return {"status": "ok", "task_id": str(self.request.id)}
