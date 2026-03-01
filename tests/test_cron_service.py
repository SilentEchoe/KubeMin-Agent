"""Tests for CronService."""

import json
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from freezegun import freeze_time

from kubemin_agent.cron.service import CronService
from kubemin_agent.cron.types import ScheduleType


@pytest.fixture
def workspace(tmp_path: Path):
    """Temporary workspace."""
    return tmp_path


def test_cron_service_init_and_storage(workspace):
    """Test initializing CronService and saving/loading jobs."""
    # Write some existing jobs
    jobs_dir = workspace / "cron"
    jobs_dir.mkdir(parents=True)
    jobs_file = jobs_dir / "jobs.json"

    existing_data = [
        {
            "id": "job-1",
            "name": "Test Job",
            "message": "Hello",
            "schedule_type": "every",
            "schedule_value": "60",
            "channel": "local",
            "chat_id": "123",
            "enabled": True,
            "created_at": "2024-01-01T00:00:00",
            "last_run": None
        }
    ]
    jobs_file.write_text(json.dumps(existing_data))

    # Initialize service, it should load the job
    service = CronService(workspace)

    jobs = service.list_jobs()
    assert len(jobs) == 1
    assert jobs[0].name == "Test Job"
    assert jobs[0].message == "Hello"
    assert jobs[0].schedule_value == "60"

    # Add new job
    service.add_job(
        name="New Job",
        message="Hi",
        schedule_type=ScheduleType.AT,
        schedule_value="2024-02-01T00:00:00"
    )

    # Check it saved
    saved_data = json.loads(jobs_file.read_text())
    assert len(saved_data) == 2

    # Remove job
    assert service.remove_job("job-1") is True
    assert service.remove_job("non-existent") is False

    saved_data = json.loads(jobs_file.read_text())
    assert len(saved_data) == 1
    assert saved_data[0]["name"] == "New Job"


def test_should_run_every(workspace):
    """Test the _should_run logic for 'every' schedule."""
    service = CronService(workspace)
    job = service.add_job("Interval", "Msg", ScheduleType.EVERY, "60")

    now = datetime(2024, 1, 1, 12, 0, 0)

    # Never run before -> should run
    assert service._should_run(job, now) is True

    # Run recently -> should not run
    job.last_run = datetime(2024, 1, 1, 11, 59, 30).isoformat()
    assert service._should_run(job, now) is False

    # Run long ago -> should run
    job.last_run = datetime(2024, 1, 1, 11, 58, 0).isoformat()
    assert service._should_run(job, now) is True


def test_should_run_at(workspace):
    """Test the _should_run logic for one-time 'at' schedule."""
    service = CronService(workspace)
    target_time = "2024-01-01T12:00:00"
    job = service.add_job("OneTime", "Msg", ScheduleType.AT, target_time)

    # Before target -> don't run
    assert service._should_run(job, datetime(2024, 1, 1, 11, 59, 59)) is False

    # After target, not run yet -> should run
    assert service._should_run(job, datetime(2024, 1, 1, 12, 0, 1)) is True

    # After target, already run -> don't run
    job.last_run = datetime(2024, 1, 1, 12, 0, 1).isoformat()
    assert service._should_run(job, datetime(2024, 1, 1, 12, 0, 5)) is False


def test_should_run_cron(workspace):
    """Test the _should_run logic for 'cron' expressions."""
    # Note: Requires croniter plugin for tests to pass this branch
    service = CronService(workspace)

    # Every hour on the hour
    job = service.add_job("CronJob", "Msg", ScheduleType.CRON, "0 * * * *")

    with freeze_time("2024-01-01 12:01:00"):
        # Never run before -> should run
        assert service._should_run(job, datetime.now()) is True

        # Ran recently after the last tick -> shouldn't run
        # Last tick was 12:00:00. If last_run is 12:00:30, prev > last evaluates as False.
        job.last_run = "2024-01-01T12:00:30"
        assert service._should_run(job, datetime.now()) is False

        # Ran before the last tick -> should run
        # Last tick was 12:00:00. If last_run is 11:59:00, prev > last evaluates as True.
        job.last_run = "2024-01-01T11:59:00"
        assert service._should_run(job, datetime.now()) is True


@pytest.mark.asyncio
async def test_cron_service_run_loop(workspace):
    """Test the main async run loop executes jobs and respects `_running` flag."""
    service = CronService(workspace)

    # Create two jobs, one that should run, one that shouldn't
    job_run = service.add_job("Run Me", "Yes", ScheduleType.EVERY, "10")
    job_skip = service.add_job("Skip Me", "No", ScheduleType.AT, "2099-01-01T00:00:00")
    job_disabled = service.add_job("Disabled", "No", ScheduleType.EVERY, "10")
    job_disabled.enabled = False

    mock_callback = AsyncMock()

    # We patch sleep to simulate the tick and gracefully stop the loop after one iteration
    async def mock_sleep(seconds):
        service.stop()

    with patch("kubemin_agent.cron.service.asyncio.sleep", side_effect=mock_sleep):
        await service.run(mock_callback)

    # Only the eligible, enabled job should have run
    mock_callback.assert_called_once_with(job_run)
    assert job_run.last_run is not None
    assert job_skip.last_run is None
    assert job_disabled.last_run is None
