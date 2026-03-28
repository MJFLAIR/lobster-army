# 🦞 Lobster Army
## Runtime Phase 1–2 Development Log
Status: Gateway + Firestore Lock Fully Verified

---

# 1. Project Objective

Build a secure, auditable, distributed task execution core where:

Local IDE submits JSON → Firestore → Runtime Worker atomically locks and executes.

Target Architecture:

Local IDE  
→ Gateway API  
→ Firestore (tasks + command_queue)  
→ Runtime Lock  
→ Worker Execution  

---

# 2. Phase 1 – Firestore Runtime Lock Core

## Objective

Validate:

- Atomic Firestore transaction lock
- Dual-collection state sync
- Proper state transition control

---

## 2.1 Issues Resolved

### Gunicorn crash (macOS fork + Python 3.13)
Switched to Flask dev server for local validation.

### Firestore ADC error
Solved via:
gcloud auth application-default login

### Missing HTTP return
Ensured all routes return jsonify(...).

### Firestore composite index required
Created index for:
- status
- created_at
- __name__

### Python 3.13 Firestore get() issue
Replaced doc.get(...) with:
data = doc.to_dict() or {}

---

## 2.2 Lock Validation

Manual Firestore insertion:

tasks/{id}
command_queue/{id}

POST /cron/tick

Result:
{"ok": true, "picked": 1}

State transition confirmed:
PENDING → RUNNING

Atomic lock verified.

---

# 3. Phase 2 – Secure Task Ingress Gateway

## Objective

Replace manual Firestore document creation with:

POST /tasks

---

## 3.1 Gateway Endpoint

Added in runtime/app.py:

POST /tasks

Responsibilities:

- Validate JSON
- Construct Task domain object
- Call DB.create_task(task)
- Return task_id

---

## 3.2 Domain Model Integration

Task defined in:
workflows/storage/models.py

Removed legacy payload usage in DB layer.
Now storing full Task fields explicitly.

---

## 3.3 Full Pipeline Test

curl POST /tasks

Response:
{"ok": true, "task_id": 1771582536496}

Firestore auto-created:

tasks/{id}
command_queue/{id}

Then:

POST /cron/tick

Response:
{"ok": true, "picked": 1, "task_id": 1771582536496}

State updated to RUNNING.
attempts incremented.
locked_by set.

---

# 4. Current System State

Completed:

- Firestore atomic transaction lock
- Secure Gateway ingress
- Task Domain Model
- DB write consistency
- State transition: PENDING → RUNNING
- Composite index
- Python 3.13 compatibility fixes

Not Yet Implemented:

- Worker execution logic
- mark_task_completed
- mark_task_failed
- Event logging
- Cost tracking
- AG flow integration

---

# 5. Verified Task Lifecycle

Local JSON  
→ POST /tasks  
→ Gateway  
→ Task Object  
→ DB.create_task  
→ Firestore  
→ POST /cron/tick  
→ Transaction Lock  
→ RUNNING  

Core runtime skeleton is now stable.

---

# 6. Milestone

Lobster Army Runtime v1 – Core Infrastructure Stable.

This completes the foundation layer.
System is ready for execution layer implementation.