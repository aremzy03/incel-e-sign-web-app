"""
Celery tasks for the E-Sign application.
"""

from celery import shared_task


@shared_task
def test_task():
    """
    Simple test task to verify Celery is working correctly.
    
    Returns:
        str: Success message indicating task execution
    """
    print("Celery is working!")
    return "Task executed"
