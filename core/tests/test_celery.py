"""
Tests for Celery task functionality in the E-Sign application.
"""

import pytest
from django.test import override_settings
from core.tasks import test_task


@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
def test_celery_task_execution():
    """
    Test that the Celery test task executes correctly.
    
    This test verifies that:
    - The test_task can be called and executed
    - The task returns the expected result
    - Celery configuration is working properly
    """
    # Execute the task
    result = test_task.delay()
    
    # Assert the result is what we expect
    assert result.result == "Task executed"
    
    # Verify the task completed successfully
    assert result.successful() is True
