"""Cron service for scheduled task execution."""

import asyncio
import json
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Awaitable, Callable

from loguru import logger

from kubemin_agent.cron.types import CronJob, ScheduleType


class CronService:
    """
    Service for managing and executing scheduled tasks.

    Supports cron expressions, interval-based, and one-time schedules.
    Jobs are persisted to a JSON file.
    """

    MISFIRE_GRACE_SECONDS = 60

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
            changed = False
            now = datetime.now()
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
                    run_on_startup=item.get("run_on_startup", False),
                    misfire_policy=(
                        "run_once" if item.get("misfire_policy") == "run_once" else "skip"
                    ),
                    created_at=item.get("created_at", ""),
                    last_run=item.get("last_run"),
                    next_run=item.get("next_run"),
                )
                if not job.next_run:
                    computed = self._bootstrap_next_run(job, now)
                    job.next_run = computed.isoformat() if computed else None
                    changed = True
                self._jobs[job.id] = job
            logger.debug(f"Loaded {len(self._jobs)} cron jobs")
            if changed:
                self._save_jobs()
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
                "run_on_startup": job.run_on_startup,
                "misfire_policy": job.misfire_policy,
                "created_at": job.created_at,
                "last_run": job.last_run,
                "next_run": job.next_run,
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
        run_on_startup: bool = False,
        misfire_policy: str = "skip",
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
            run_on_startup: Whether to execute once immediately when service starts.
            misfire_policy: Policy when a schedule is missed ('skip' | 'run_once').

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
            run_on_startup=run_on_startup,
            misfire_policy="run_once" if misfire_policy == "run_once" else "skip",
        )
        next_run = self._bootstrap_next_run(job, datetime.now())
        job.next_run = next_run.isoformat() if next_run else None
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

    async def run(self, execute_callback: Callable[[CronJob], Awaitable[None]]) -> None:
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
                        next_run = self._compute_next_run(job, now)
                        job.next_run = next_run.isoformat() if next_run else None
                        if job.schedule_type == ScheduleType.AT and next_run is None:
                            job.enabled = False
                        self._save_jobs()
                        await execute_callback(job)
                    except Exception as e:
                        logger.error(f"Cron job execution failed: {job.name} - {e}")

            await asyncio.sleep(30)  # Check every 30 seconds

    def _should_run(self, job: CronJob, now: datetime) -> bool:
        """Check if a job should run at the given time."""
        if not job.next_run:
            next_run = self._bootstrap_next_run(job, now)
            job.next_run = next_run.isoformat() if next_run else None
            self._save_jobs()
        if not job.next_run:
            return False

        try:
            scheduled_at = datetime.fromisoformat(job.next_run)
        except ValueError:
            repaired = self._bootstrap_next_run(job, now)
            job.next_run = repaired.isoformat() if repaired else None
            self._save_jobs()
            return False

        if now < scheduled_at:
            return False

        overdue_seconds = (now - scheduled_at).total_seconds()
        if overdue_seconds > self.MISFIRE_GRACE_SECONDS and job.misfire_policy == "skip":
            repaired = self._advance_next_run_to_future(job, now, scheduled_at)
            job.next_run = repaired.isoformat() if repaired else None
            self._save_jobs()
            return False
        return True

    def _bootstrap_next_run(self, job: CronJob, now: datetime) -> datetime | None:
        """Compute first next_run for new/legacy jobs."""
        if not job.last_run and job.run_on_startup:
            return now
        if job.last_run:
            try:
                return self._compute_next_run(job, datetime.fromisoformat(job.last_run))
            except ValueError:
                return self._compute_next_run(job, now)
        return self._compute_next_run(job, now)

    def _compute_next_run(self, job: CronJob, reference: datetime) -> datetime | None:
        """Compute the next schedule after the given reference time."""
        if job.schedule_type == ScheduleType.EVERY:
            interval_seconds = int(job.schedule_value)
            return reference + timedelta(seconds=interval_seconds)

        if job.schedule_type == ScheduleType.CRON:
            from croniter import croniter

            cron = croniter(job.schedule_value, reference)
            return cron.get_next(datetime)

        if job.schedule_type == ScheduleType.AT:
            target = datetime.fromisoformat(job.schedule_value)
            if reference < target:
                return target
            return None

        return None

    def _advance_next_run_to_future(
        self,
        job: CronJob,
        now: datetime,
        scheduled_at: datetime,
    ) -> datetime | None:
        """Advance next_run until it moves to the future for skip policy."""
        if job.schedule_type == ScheduleType.AT:
            return None

        next_run = scheduled_at
        while next_run <= now:
            computed = self._compute_next_run(job, next_run)
            if computed is None:
                return None
            next_run = computed
        return next_run

    def stop(self) -> None:
        """Stop the cron service."""
        self._running = False
        logger.info("Cron service stopped")
