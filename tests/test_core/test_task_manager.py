"""Tests for task manager."""

from do_my_tasks.core.task_manager import TaskManager
from do_my_tasks.models.task import TaskPriority, TaskStatus


def test_create_and_list_task(db_session_factory):
    """Test creating and listing tasks."""
    manager = TaskManager(db_session_factory)

    task = manager.create(
        title="Fix login bug",
        project_name="myapp",
        priority=TaskPriority.HIGH,
        date="2026-03-10",
    )
    assert task.id is not None
    assert task.title == "Fix login bug"
    assert task.priority == TaskPriority.HIGH.value

    tasks = manager.list(date="2026-03-10")
    assert len(tasks) == 1
    assert tasks[0].title == "Fix login bug"


def test_complete_task(db_session_factory):
    """Test completing a task."""
    manager = TaskManager(db_session_factory)
    task = manager.create(title="Task 1", project_name="p", date="2026-03-10")

    result = manager.update_status(task.id, TaskStatus.COMPLETED)
    assert result is not None
    assert result.status == TaskStatus.COMPLETED.value
    assert result.completed_date is not None


def test_delete_task(db_session_factory):
    """Test deleting a task."""
    manager = TaskManager(db_session_factory)
    task = manager.create(title="Task 1", project_name="p", date="2026-03-10")

    assert manager.delete(task.id)
    assert manager.list() == []


def test_rollover_tasks(db_session_factory):
    """Test rolling over incomplete tasks."""
    manager = TaskManager(db_session_factory)

    # Create tasks for day 1
    manager.create(title="Task A", project_name="p", date="2026-03-10", priority=TaskPriority.HIGH)
    task_b = manager.create(title="Task B", project_name="p", date="2026-03-10")
    # Complete task B
    manager.update_status(task_b.id, TaskStatus.COMPLETED)

    # Rollover
    rolled = manager.rollover("2026-03-10", "2026-03-11")
    assert rolled == 1  # Only Task A (Task B was completed)

    # Check new tasks on day 2
    day2_tasks = manager.list(date="2026-03-11")
    assert len(day2_tasks) == 1
    assert day2_tasks[0].title == "Task A"
    assert day2_tasks[0].rollover_count == 1

    # Check original task is marked as rolled over
    day1_tasks = manager.list(date="2026-03-10", status=TaskStatus.ROLLED_OVER.value)
    assert len(day1_tasks) == 1


def test_rollover_requires_review(db_session_factory):
    """Test that tasks with >3 rollovers get requires_review flag."""
    manager = TaskManager(db_session_factory)

    # Create a task and roll it over 4 times
    manager.create(title="Stale task", project_name="p", date="2026-03-07")

    for day_offset in range(4):
        from_day = f"2026-03-{7 + day_offset:02d}"
        to_day = f"2026-03-{8 + day_offset:02d}"
        manager.rollover(from_day, to_day)

    # The task on day 11 should have requires_review=True (rollover_count=4 > 3)
    tasks = manager.list(date="2026-03-11")
    assert len(tasks) == 1
    assert tasks[0].requires_review is True
    assert tasks[0].rollover_count == 4


def test_filter_by_project(db_session_factory):
    """Test filtering tasks by project."""
    manager = TaskManager(db_session_factory)
    manager.create(title="Task 1", project_name="app1", date="2026-03-10")
    manager.create(title="Task 2", project_name="app2", date="2026-03-10")

    app1_tasks = manager.list(project_name="app1")
    assert len(app1_tasks) == 1
    assert app1_tasks[0].project_name == "app1"
