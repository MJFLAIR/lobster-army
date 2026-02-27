from runtime.app import create_app
from runtime.cron_tick import handle_tick
from workflows.storage.db import DB
import sys

app = create_app()

print("Invoking handle_tick()...")
with app.app_context():
    resp = handle_tick()
    print("Tick Response:", resp)

task = DB.get_task(1016)
if task:
    print("Task 1016 Status:", task.status)
else:
    print("Task 1016 not found.")
