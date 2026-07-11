"""
Celery tasks — wraps the async pipeline_runner in a sync Celery task
so it survives API server restarts and can be monitored/retried.
"""
from __future__ import annotations

import asyncio
import os

from sqlmodel import Session, select

from backend.db.database import engine
from backend.db.models import ScenarioRun
from backend.worker.celery_app import celery_app


@celery_app.task(bind=True, max_retries=2)
def run_pipeline_task(self, scenario_id: str, run_id: int) -> dict:
    """Run the full incident mesh pipeline and update the DB row on completion."""
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")

    # Update run status → running
    with Session(engine) as session:
        run = session.get(ScenarioRun, run_id)
        if run:
            run.status = "running"
            session.add(run)
            session.commit()

    try:
        from backend.api.pipeline_runner import run_pipeline  # lazy import

        asyncio.run(run_pipeline(scenario_id, redis_url, speed=4.0, mock=True))

        # Update run status → completed
        with Session(engine) as session:
            run = session.get(ScenarioRun, run_id)
            if run:
                run.status = "completed"
                session.add(run)
                session.commit()

        return {"status": "completed", "scenario_id": scenario_id}

    except Exception as exc:
        # Update run status → failed then re-raise for Celery retry
        with Session(engine) as session:
            run = session.get(ScenarioRun, run_id)
            if run:
                run.status = "failed"
                session.add(run)
                session.commit()
        raise self.retry(exc=exc, countdown=5)
