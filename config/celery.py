"""Celery application for Track P scheduled work.

The broker is optional: with no ``CELERY_BROKER_URL`` configured, tasks execute
eagerly inside the calling process. That keeps ``manage.py run_forecasts`` and
the Celery beat schedule behaviourally identical on a laptop and in production.
"""

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("messforecast")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


@app.task(bind=True, ignore_result=True)
def debug_task(self):  # pragma: no cover - operational helper
    return {"request_id": self.request.id}
