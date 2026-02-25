"""Cron service for scheduled task execution."""

import asyncio
import json
import uuid
from datetime import datetime
from pathlib import Path

from loguru import logger

from kubemin_agent.cron.types import CronJob, ScheduleType


class CronService:
    """
    Service for managing and executing scheduled tasks.

    Supports cron expressions, interval-based, and one-time schedules.
    Jobs are persisted to a JSON file.
    """

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.jobs_file = data_dir / "cron" / "jobs.json"
        self.jobs_file.parent.mkdir(parents=True, exist_ok=True)
        self._jobs: dict[str, CronJob] = {}
        self._running = False
        self._load_jobs()

    def _load_jobs(self) -> None:
        """Load jobs from persistent storage."""
        if not self.jobs_file.exists():
            return

        try:
            data = json.loads(self.jobs_file.read_text(encoding="utf-8"))
            for item in data:
                job = CronJob(
                    id=item["id"],
                    name=item["name"],
                    message=item["message"],
                    schedule_type=ScheduleType(item["schedule_type"]),
                    schedule_value=item["schedule_value"],
                    channel=item.get("channel", ""),
                    chat_id=item.get("chat_id", ""),
                    enabled=item.get("enabled", True),
                    created_at=item.get("created_at", ""),
                    last_run=item.get("last_run"),
                )
                self._jobs[job.id] = job
            logger.debug(f"Loaded {len(self._jobs)} cron jobs")
        except Exception as e:
            logger.error(f"Failed to load cron jobs: {e}")

    def _save_jobs(self) -> None:
        """Save jobs to persistent storage."""
        data = []
        for job in self._jobs.values():
            data.append({
                "id": job.id,
                "name": job.name,
                "message": job.message,
                "schedule_type": job.schedule_type.value,
                "schedule_value": job.schedule_value,
                "channel": job.channel,
                "chat_id": job.chat_id,
                "enabled": job.enabled,
                "created_at": job.created_at,
                "last_run": job.last_run,
            })
        self.jobs_file.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def add_job(
        self,
        name: str,
        message: str,
        schedule_type: ScheduleType,
        schedule_value: str,
        channel: str = "",
        chat_id: str = "",
    ) -> CronJob:
        """
        Add a new scheduled job.

        Args:
            name: Human-readable job name.
            message: Message to send when triggered.
            schedule_type: Type of schedule.
            schedule_value: Schedule specification.
            channel: Target channel for output.
            chat_id: Target chat ID for output.

        Returns:
            The created CronJob.
        """
        job = CronJob(
            id=str(uuid.uuid4())[:8],
            name=name,
            message=message,
            schedule_type=schedule_type,
            schedule_value=schedule_value,
            channel=channel,
            chat_id=chat_id,
        )
        self._jobs[job.id] = job
        self._save_jobs()
        logger.info(f"Cron job added: {job.name} ({job.id})")
        return job

    def remove_job(self, job_id: str) -> bool:
        """Remove a job by ID."""
        if job_id in self._jobs:
            del self._jobs[job_id]
            self._save_jobs()
            logger.info(f"Cron job removed: {job_id}")
            return True
        return False

    def list_jobs(self) -> list[CronJob]:
        """List all jobs."""
        return list(self._jobs.values())

    async def run(self, execute_callback) -> None:
        """
        Run the cron service loop.

        Args:
            execute_callback: Async callback to execute when a job triggers.
        """
        self._running = True
        logger.info("Cron service started")

        while self._running:
            now = datetime.now()

            for job in self._jobs.values():
                if not job.enabled:
                    continue

                if self._should_run(job, now):
                    try:
                        job.last_run = now.isoformat()
                        self._save_jobs()
                        await execute_callback(job)
                    except Exception as e:
                        logger.error(f"Cron job execution failed: {job.name} - {e}")

            await asyncio.sleep(30)  # Check every 30 seconds

    def _should_run(self, job: CronJob, now: datetime) -> bool:
        """Check if a job should run at the given time."""
        if job.schedule_type == ScheduleType.EVERY:
            if not job.last_run:
                return True
            last = datetime.fromisoformat(job.last_run)
            interval = int(job.schedule_value)
            return (now - last).total_seconds() >= interval

        if job.schedule_type == ScheduleType.CRON:
            try:
                from croniter import croniter

                cron = croniter(job.schedule_value, now)
                prev = cron.get_prev(datetime)
                if not job.last_run:
                    return True
                last = datetime.fromisoformat(job.last_run)
                return prev > last
            except Exception:
                return False

        if job.schedule_type == ScheduleType.AT:
            target = datetime.fromisoformat(job.schedule_value)
            if not job.last_run and now >= target:
                return True

        return False

    def stop(self) -> None:
        """Stop the cron service."""
        self._running = False
        logger.info("Cron service stopped")
