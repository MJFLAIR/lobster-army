# Lobster Army v1.0.9 — ChatOps-First (Both + Async), Cloud Run Only Runtime

A production-oriented, safety-first **single-founder** AI execution system on **GCP Cloud Run** with **ChatOps**:

- **Discord Slash (Interactions)** + **Discord Webhook** + **IDE Chat Relay**
- **Async mode** (Ingress/Worker/Egress split) so Cloud Run can **scale-to-zero**
- **PM-only human interface** by default (Code/Review work silently; failures trigger @you)

**Runtime policy:** Lobster agents (PM/Code/Review) run **ONLY on Cloud Run**.  
**Local policy:** local machine is **DEV/TEST only** (venv/pytest/AST/gates). No Lobster runtime server runs locally.

---

## 0) Non-Negotiable Requirements (Must Implement)

### 0.1 Runtime Policy (Cloud Run only)
- **Gateway** and **Runtime** run only on Cloud Run.
- Local is allowed only for:
  - venv + install deps
  - lint/format gates
  - pytest
  - AST validation
  - hard-rule checks
  - (optional) dry-run scripts that never call real LLMs

### 0.2 ChatOps: Both + Async
- Support **both**:
  1) **Discord Interactions** (Slash commands → verified Ed25519 signatures)
  2) **Discord Webhook** (simple ingestion with shared token)
  3) **IDE Chat Relay** (IDE sends HTTPS POST with relay token)
- **Async design**:
  - Gateway **acks immediately**
  - Runtime executes later
  - Results posted via webhook / follow-up message

### 0.3 PM-only Human Interface (Token Saving)
- Default: only **PM** communicates with humans.
- Code/Review are silent unless:
  - explicit command flag (e.g. `/lobster debug on`)
  - failure triggers escalation
  - human approval is required

### 0.4 Safety & Control (Hard Rules)
1) Agents may only write to: `src/`, `tests/`, `.lobster/tmp/`, `build/`
2) Agents must never read/modify: `.env*`, `.github/workflows/*`, `.git/hooks/*`, `credentials*`, `secrets*`, `~/.ssh/*`, `~/.aws/*`, `gateway/`, `runtime/`, `tools/`, `workflows/`, `config/`, `docs/`
3) All tool usage must pass **ToolGate** allowlist (command + args validation).
4) All git refs must pass **RefSanitizer**.
5) Never amend commits. Every attempt = new commit.
6) Sequential execution only (no parallel subtasks).
7) Unified timeouts for operations and LLM calls.
8) Cloud Run must require auth (no unauthenticated public access).
9) Runtime `pip install` disabled by default.
10) **Network deny-by-default** enforced via `tools/network_client.py`; AST blocks direct network libs in business code.

### 0.5 Persistence & Observability
- **Cloud SQL (Postgres)** is the source of truth for tasks/events/cost.
- Cloud Run filesystem is ephemeral; never use it for persistence.
- Every significant step emits a JSON event:
  - persisted to DB
  - mirrored to logs (one JSON per line)

---

## 1) Architecture (Ingress / Worker / Egress)

### 1.1 Components
**A) Chat Gateway (Cloud Run) — Ingress + Egress**
- Receives:
  - Discord Slash (Interactions endpoint)
  - Discord Webhook ingestion
  - IDE Relay ingestion
- Verifies authenticity:
  - Discord Ed25519 signature verification
  - Shared token for webhook ingestion
  - Relay token for IDE relay
- Creates a task record in DB
- Enqueues task in DB
- Returns an immediate ack
- Posts completion/failure to Discord webhook (and optionally follow-up)

**B) Lobster Runtime (Cloud Run) — Worker**
- Triggered async via:
  - **Cloud Scheduler → Runtime `/cron/tick`** every 1 minute (MVP)
  - optional: Pub/Sub in later versions
- Pulls pending tasks with DB lock
- Runs **PM → Code → Review** sequentially
- Tool execution must use ToolGate wrappers only
- Writes events and cost tracking to DB
- Marks task done/failed and emits report payload for Gateway to post

**C) Cloud SQL (Postgres)**
- tasks / events / cost / command_queue / (optional) chat_sessions

**D) Secret Manager**
- Stores all API keys/tokens (OpenAI, Gemini, GitHub PAT, Discord, IDE relay token)
- Runtime reads secrets **at execution time** (in-memory only)
- Uses Cloud Run service account short-lived credentials
- Audit logs enabled

---

## 2) Model Policy (Fixed + Human Approval Upgrade)

### 2.1 Default fixed models (no auto-upgrade)
- PM: `gemini-1.5-flash`
- Code: `gpt-4o-mini`
- Review: `gemini-1.5-pro`

### 2.2 Two-stage escalation (human approval required)
- PM can re-plan/split/change tools/prompts.
- PM cannot upgrade to expensive models automatically.
- If repeated failures or review score below threshold:
  - PM posts `HUMAN_APPROVAL_REQUIRED` event and @you in Discord
  - You approve upgrade for **specific subtask only** (approve command)

### 2.3 Loop & budget caps (hard stops)
- Max attempts per subtask: 3
- Max review retries: 2
- Per-task budget hard limit: config
- Daily budget hard limit: config
- Exceeding hard limit aborts and posts “Needs human” report.

---

## 3) Network Allowlist (Application Layer)
- Deny-by-default.
- All outbound HTTP must go through `tools/network_client.py`.
- AST validator blocks `requests/httpx/urllib/socket` in business code.
- Default allowlist domains:
  - `api.openai.com`
  - `generativelanguage.googleapis.com`
  - `api.github.com`
  - `discord.com`
  - `discordapp.com`

---

## 4) tool_pool / api_pool (Deploy-time hot-plug only)

### 4.1 tool_pool
Each tool has a manifest:
- name, version, entrypoint
- inputs/outputs schema (minimal)
- required secrets (aliases)
- net policy
- timeout
- permissions (read/write paths)

**Hot-plug rule:** Tools change only by GitHub push → CI → deploy (no runtime downloads).

### 4.2 api_pool
- Secrets stored in Secret Manager
- Code references **aliases** only
- Runtime reads secrets in-memory only (no persistence)

---

## 5) CI Gates (Reduce Review Token Spend)
Before calling Review agent:
1) Gate 1: lint/format (deterministic)
2) Gate 2: pytest
3) Gate 3: AST validator + hard rules + diff guards  
Only if all pass: Review agent is called (or becomes lightweight).

---

## 6) Repository Layout (Must Match)

```text
lobster-army/
├── README.md
├── requirements.txt
├── Dockerfile
├── .gitignore
│
├── .github/workflows/
│   └── deploy.yml
│
├── config/
│   ├── models.yaml
│   ├── security.yaml
│   ├── timeouts.yaml
│   ├── network.yaml
│   ├── tool_pool.yaml
│   └── api_pool.yaml
│
├── gateway/                      # Cloud Run: ingress+egress
│   ├── app.py
│   ├── routes.py
│   ├── discord_verify.py
│   ├── outbound.py
│   └── ide_relay.py
│
├── runtime/                      # Cloud Run: worker
│   ├── app.py
│   ├── task_worker.py
│   └── cron_tick.py
│
├── src/                          # agent-generated business code (writable)
├── tests/                        # agent-generated tests (writable)
│
├── tool_pool/                    # deploy-time tool plugins (read-only by agents)
│   ├── __init__.py
│   ├── repo_tree_summary.py
│   └── apply_patch.py
│
├── tools/                        # read-only wrappers + guards
│   ├── tool_gate.py
│   ├── ref_sanitizer.py
│   ├── input_sanitizer.py
│   ├── filesystem.py
│   ├── git_client.py
│   ├── test_runner.py
│   ├── ast_validator.py
│   ├── network_client.py
│   ├── llm_client.py
│   ├── tool_pool_loader.py
│   └── cost_tracker.py
│
├── workflows/                    # read-only orchestration
│   ├── task_manager.py
│   ├── agents/
│   │   ├── prompts.py
│   │   ├── pm_agent.py
│   │   ├── code_agent.py
│   │   └── review_agent.py
│   └── storage/
│       ├── db.py
│       ├── models.py
│       └── migrations/          # alembic
│
├── scripts/
│   ├── check_hard_rules.py
│   └── init_db.py
│
└── docs/
    ├── SECURITY.md
    ├── ARCHITECTURE.md
    └── OPERATIONS.md

Writable by agents: src/, tests/, .lobster/tmp/, build/ Read-only (agents must not edit): tools/, workflows/, .github/, config/, gateway/, runtime/, tool_pool/, docs/

7) Config Files (Exact Content)
7.1 config/models.yaml


models:
  pm:
    primary: "gemini-1.5-flash"
    daily_budget_usd: 0.10
    per_task_budget_usd: 0.05

  code:
    primary: "gpt-4o-mini"
    daily_budget_usd: 1.50
    per_task_budget_usd: 0.30

  review:
    primary: "gemini-1.5-pro"
    daily_budget_usd: 0.15
    per_task_budget_usd: 0.05

escalation_policy:
  require_human_approval_for:
    - "upgrade_model"
    - "increase_budget"
  review_score_threshold: 90
  max_attempts_per_subtask: 3
  max_review_retries: 2

budget_alerts:
  daily_warning_threshold: 0.80
  daily_hard_limit: 2.50
  per_task_warning_threshold: 0.80
  per_task_hard_limit: 1.00

7.2 config/timeouts.yaml


timeouts:
  operation_timeout_seconds: 300
  llm_timeout_seconds: 300
  retry_backoff_seconds: [5, 15, 45]

  max_retries:
    fixable: 3
    test_error: 1
    infra_retriable: 3

hard_timeout:
  status: "FAILED_INFRA"
  terminal: true
  no_retry: true
  message: "Operation exceeded timeout. Split task into smaller subtasks."

7.3 config/security.yaml


security:
  ast_scan_directories: ["src", "tests"]

  writable_paths:
    - "src/"
    - "tests/"
    - ".lobster/tmp/"
    - "build/"

  sensitive_deny_patterns:
    - ".env*"
    - ".git/hooks/*"
    - ".github/workflows/*"
    - "~/.ssh/*"
    - "~/.aws/*"
    - "~/.config/*"
    - "**/credentials*"
    - "**/secrets*"

  git_ref_patterns:
    checkout_allowed: "^(task/\\d+)$"
    merge_allowed: "^task/\\d+$"
    tag_allowed: "^lobster/task-\\d+/complete$"

  diff_guards:
    max_files_changed: 20
    max_total_diff_lines: 2000

7.4 config/network.yaml


network:
  mode: "deny_by_default"
  allowlist_domains:
    - "api.openai.com"
    - "generativelanguage.googleapis.com"
    - "api.github.com"
    - "discord.com"
    - "discordapp.com"
  notes: "All outbound HTTP must use tools/network_client.py"

7.5 config/tool_pool.yaml


tool_pool:
  registry_package: "tool_pool"
  tools:
    - name: "repo_tree_summary"
      version: "1.0"
      entrypoint: "tool_pool.repo_tree_summary:run"
      required_secrets: []
      net_policy: "none"
      timeout_seconds: 10

    - name: "apply_patch"
      version: "1.0"
      entrypoint: "tool_pool.apply_patch:run"
      required_secrets: []
      net_policy: "none"
      timeout_seconds: 30

7.6 config/api_pool.yaml


api_pool:
  aliases:
    openai:
      secret_name: "openai-key"
      purpose: "LLM calls"
      scope: "prod"
      owner: "user"
      rotation: "manual"
    gemini:
      secret_name: "gemini-key"
      purpose: "LLM calls"
      scope: "prod"
      owner: "user"
      rotation: "manual"
    github_pat:
      secret_name: "github-pat"
      purpose: "GitHub repo operations"
      scope: "prod"
      owner: "user"
      rotation: "manual"
    discord_public_key:
      secret_name: "discord-public-key"
      purpose: "Verify Discord interactions (Ed25519)"
      scope: "prod"
      owner: "user"
      rotation: "manual"
    discord_webhook_url:
      secret_name: "discord-webhook-url"
      purpose: "Post results to Discord"
      scope: "prod"
      owner: "user"
      rotation: "manual"
    ide_relay_token:
      secret_name: "ide-relay-token"
      purpose: "Authenticate IDE relay to Gateway"
      scope: "prod"
      owner: "user"
      rotation: "manual"


8) Cloud SQL Schema (Minimum)
Tables:
tasks
	•	id (serial pk)
	•	source (discord_slash | discord_webhook | ide_chat)
	•	requester_id (text)
	•	channel_id (text)
	•	correlation_id (text) (idempotency key)
	•	description (text)
	•	status (text)
	•	created_at, updated_at
	•	branch_name (text)
	•	plan_json (jsonb)
	•	result_summary (text)
	•	cost_json (jsonb)
events
	•	id (serial pk)
	•	task_id (fk)
	•	ts (timestamp)
	•	event_type (text)
	•	payload_json (jsonb)
command_queue
	•	id (serial pk)
	•	task_id (fk)
	•	status (PENDING|RUNNING|DONE|FAILED)
	•	locked_by (text)
	•	locked_at (timestamp)
	•	attempts (int)
chat_sessions (optional)
	•	id, platform, channel_id, last_message_ref, timestamps

9) Cost Tracking (Must Implement)
Per task store:
	•	model used per step (pm/code/review)
	•	input_tokens/output_tokens (if available)
	•	estimated_usd
	•	timestamps
	•	cumulative daily usage
Events:
	•	COST_UPDATE
	•	BUDGET_WARN
	•	BUDGET_HARD_STOP
Escalation:
	•	Any model upgrade or budget increase must produce event HUMAN_APPROVAL_REQUIRED containing:
	•	reason
	•	recommended override
	•	estimated incremental cost

10) GitHub Integration (Explicit)
Auth:
	•	Fine-grained GitHub PAT stored in Secret Manager (alias github_pat)
	•	Minimal permissions:
	•	Contents: Read/Write
	•	Metadata: Read
Webhook Setup:
	•	URL: `https://<gateway-url>/api/webhook/github`
	•	Content type: `application/json`
	•	Events: `pull_request` only
	•	Secret: Configured as `GITHUB_WEBHOOK_SECRET` environment variable
Merge strategy (no PR required for MVP):
	•	PM creates task/<id>
	•	Code commits sequentially
	•	Review PASS → runtime merges into main (--no-ff), pushes main, tags lobster/task-<id>/complete

11) Async Triggering (MVP: Scheduler Tick)
MVP choice:
	•	Cloud Scheduler calls runtime/cron/tick every 1 minute
	•	Runtime:
	•	picks next PENDING task atomically (DB lock)
	•	runs worker
	•	writes events and marks DONE/FAILED
This avoids long connections and works with scale-to-zero.

Appendix A — Gateway/Runtime Code Skeletons
A.1 gateway/app.py


from flask import Flask
from gateway.routes import register_routes

def create_app() -> Flask:
    app = Flask(__name__)
    register_routes(app)
    return app

app = create_app()

A.2 gateway/routes.py


from flask import Flask, request, jsonify
from gateway.discord_verify import verify_discord_interaction
from gateway.outbound import post_async_ack
from gateway.ide_relay import verify_ide_relay
from workflows.storage.db import DB
from tools.input_sanitizer import InputSanitizer

def register_routes(app: Flask) -> None:
    @app.get("/health")
    def health():
        return jsonify({"status": "ok", "service": "gateway", "version": "1.0.9"})

    @app.post("/discord/interactions")
    def discord_interactions():
        if not verify_discord_interaction(request):
            return jsonify({"error": "invalid signature"}), 401

        payload = request.get_json(force=True, silent=False)

        # Discord ping
        if payload.get("type") == 1:
            return jsonify({"type": 1})

        cmd = InputSanitizer.normalize_discord_payload(payload)
        task_id = DB.create_task_from_command(cmd, source="discord_slash")
        DB.enqueue_task(task_id)
        return post_async_ack(cmd, task_id)

    @app.post("/discord/webhook")
    def discord_webhook_ingress():
        token = request.headers.get("X-Webhook-Token", "")
        if not InputSanitizer.verify_shared_token(token):
            return jsonify({"error": "unauthorized"}), 401

        payload = request.get_json(force=True, silent=True) or {}
        cmd = InputSanitizer.normalize_webhook_payload(payload)

        task_id = DB.create_task_from_command(cmd, source="discord_webhook")
        DB.enqueue_task(task_id)
        return jsonify({"ok": True, "task_id": task_id})

    @app.post("/ide/relay")
    def ide_relay():
        if not verify_ide_relay(request):
            return jsonify({"error": "unauthorized"}), 401

        payload = request.get_json(force=True, silent=False)
        cmd = InputSanitizer.normalize_ide_payload(payload)

        task_id = DB.create_task_from_command(cmd, source="ide_chat")
        DB.enqueue_task(task_id)
        return jsonify({"ok": True, "task_id": task_id})

A.3 runtime/app.py


from flask import Flask, jsonify
from runtime.cron_tick import handle_tick

def create_app() -> Flask:
    app = Flask(__name__)

    @app.get("/health")
    def health():
        return jsonify({"status": "ok", "service": "runtime", "version": "1.0.9"})

    @app.post("/cron/tick")
    def cron_tick():
        return handle_tick()

    return app

app = create_app()

A.4 runtime/cron_tick.py


from flask import jsonify
from workflows.storage.db import DB
from runtime.task_worker import TaskWorker

def handle_tick():
    task = DB.lock_next_pending_task(lock_owner="runtime")
    if not task:
        return jsonify({"ok": True, "picked": 0})

    TaskWorker().run_task(task["task_id"])
    return jsonify({"ok": True, "picked": 1, "task_id": task["task_id"]})

A.5 runtime/task_worker.py


from workflows.task_manager import TaskManager
from workflows.storage.db import DB

class TaskWorker:
    def run_task(self, task_id: int) -> None:
        DB.emit_event(task_id, "TASK_START", {"task_id": task_id})
        try:
            TaskManager().execute(task_id)
            DB.mark_task_done(task_id)
            DB.emit_event(task_id, "TASK_DONE", {"task_id": task_id})
        except Exception as e:
            DB.mark_task_failed(task_id, str(e))
            DB.emit_event(task_id, "TASK_FAILED", {"error": str(e)})


Appendix B — Discord + IDE Relay (Verification + Protocol)
B.1 Discord Interactions verification (Ed25519)
gateway/discord_verify.py:


import nacl.signing
import nacl.exceptions
from flask import Request
from workflows.storage.db import Secrets

def verify_discord_interaction(request: Request) -> bool:
    sig = request.headers.get("X-Signature-Ed25519", "")
    ts = request.headers.get("X-Signature-Timestamp", "")
    if not sig or not ts:
        return False

    raw_body = request.get_data()
    message = ts.encode("utf-8") + raw_body

    public_key_hex = Secrets.get_secret_by_alias("discord_public_key")
    try:
        verify_key = nacl.signing.VerifyKey(bytes.fromhex(public_key_hex))
        verify_key.verify(message, bytes.fromhex(sig))
        return True
    except (ValueError, nacl.exceptions.BadSignatureError):
        return False

B.2 IDE Relay protocol (defined)
Endpoint: POST /ide/relay Auth header: X-IDE-Relay-Token: <token> (from Secret Manager alias ide_relay_token)
Body:


{
  "channel": "ag-ide",
  "requester_id": "mj",
  "correlation_id": "uuid-or-hash",
  "text": "Implement tool X and add tests",
  "meta": { "repo": "lobster-army", "branch_hint": "main" }
}

Gateway response:


{ "ok": true, "task_id": 123 }


Appendix C — GitHub Actions CI/CD (Complete)
.github/workflows/deploy.yml:


name: Deploy Lobster (Gateway + Runtime)

on:
  push:
    branches: [main]

env:
  PROJECT_ID: ${{ secrets.GCP_PROJECT_ID }}
  REGION: us-central1
  GATEWAY_SERVICE: lobster-gateway
  RUNTIME_SERVICE: lobster-runtime

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt

      - name: Lint (Gate 1)
        run: |
          python -m pip install ruff
          ruff check .

      - name: Tests (Gate 2)
        run: pytest -q

      - name: AST validation (Gate 3)
        run: python tools/ast_validator.py --scan src tests

      - name: Hard rules check (Gate 3)
        run: python scripts/check_hard_rules.py

  deploy:
    needs: test
    runs-on: ubuntu-latest
    permissions:
      contents: read
      id-token: write

    steps:
      - uses: actions/checkout@v4

      - name: Authenticate to Google Cloud (WIF)
        uses: google-github-actions/auth@v2
        with:
          workload_identity_provider: ${{ secrets.WIF_PROVIDER }}
          service_account: ${{ secrets.WIF_SERVICE_ACCOUNT }}

      - name: Set up gcloud
        uses: google-github-actions/setup-gcloud@v2

      - name: Deploy Gateway to Cloud Run
        run: |
          CONN_NAME="${{ secrets.CLOUD_SQL_CONN_NAME }}"
          gcloud run deploy $GATEWAY_SERVICE \
            --source . \
            --region $REGION \
            --project $PROJECT_ID \
            --no-allow-unauthenticated \
            --max-instances=1 \
            --concurrency=1 \
            --timeout=600 \
            --service-account "${{ secrets.GATEWAY_RUN_SA }}" \
            --add-cloudsql-instances "${CONN_NAME}" \
            --set-env-vars "SERVICE_ROLE=gateway,DB_INSTANCE_CONNECTION_NAME=${CONN_NAME},DB_NAME=lobster_tasks,DB_USER=lobster_user" \
            --set-secrets "DB_PASSWORD=db-password:latest,DISCORD_PUBLIC_KEY=discord-public-key:latest,DISCORD_WEBHOOK_URL=discord-webhook-url:latest,IDE_RELAY_TOKEN=ide-relay-token:latest,OPENAI_API_KEY=openai-key:latest,GEMINI_API_KEY=gemini-key:latest,GITHUB_PAT=github-pat:latest"

      - name: Deploy Runtime to Cloud Run
        run: |
          CONN_NAME="${{ secrets.CLOUD_SQL_CONN_NAME }}"
          gcloud run deploy $RUNTIME_SERVICE \
            --source . \
            --region $REGION \
            --project $PROJECT_ID \
            --no-allow-unauthenticated \
            --max-instances=1 \
            --concurrency=1 \
            --timeout=600 \
            --service-account "${{ secrets.RUNTIME_RUN_SA }}" \
            --add-cloudsql-instances "${CONN_NAME}" \
            --set-env-vars "SERVICE_ROLE=runtime,DB_INSTANCE_CONNECTION_NAME=${CONN_NAME},DB_NAME=lobster_tasks,DB_USER=lobster_user" \
            --set-secrets "DB_PASSWORD=db-password:latest,OPENAI_API_KEY=openai-key:latest,GEMINI_API_KEY=gemini-key:latest,GITHUB_PAT=github-pat:latest"


Appendix D — ToolGate (Allowlist Enforcement Skeleton)
tools/tool_gate.py:


from dataclasses import dataclass
from typing import List
from tools.ref_sanitizer import RefSanitizer

class SecurityError(Exception):
    pass

@dataclass(frozen=True)
class AllowedGit:
    pass

class ToolGate:
    FORBIDDEN_GIT_SUBCMDS = {"config", "remote", "submodule", "clean", "filter-branch"}
    FORBIDDEN_GIT_FLAGS = {"--amend", "-c", "--config", "--exec-path", "--upload-pack"}

    @staticmethod
    def validate_git_command(cmd: List[str]) -> None:
        if len(cmd) < 2 or cmd[0] != "git":
            raise SecurityError("Not a git command")

        subcmd = cmd[1]

        if subcmd in ToolGate.FORBIDDEN_GIT_SUBCMDS:
            raise SecurityError(f"Forbidden git subcommand: {subcmd}")

        for f in ToolGate.FORBIDDEN_GIT_FLAGS:
            if f in cmd:
                raise SecurityError(f"Forbidden git flag: {f}")

        if subcmd in {"status", "diff", "fetch"}:
            return

        if subcmd == "switch":
            if cmd[2:3] != ["-c"] or len(cmd) != 4:
                raise SecurityError("git switch must be: git switch -c task/<id>")
            if not RefSanitizer.validate(cmd[3], "checkout"):
                raise SecurityError(f"Invalid branch ref: {cmd[3]}")
            return

        if subcmd == "checkout":
            if len(cmd) != 3 or not RefSanitizer.validate(cmd[2], "checkout"):
                raise SecurityError("Invalid git checkout ref")
            return

        if subcmd == "add":
            if len(cmd) < 3:
                raise SecurityError("git add requires paths")
            return

        if subcmd == "commit":
            if cmd[2:3] != ["-m"] or len(cmd) != 4:
                raise SecurityError("git commit must be: git commit -m <msg>")
            msg = cmd[3]
            if "\n" in msg or len(msg) > 120:
                raise SecurityError("Commit message invalid")
            return

        if subcmd == "merge":
            if "--no-ff" not in cmd or len(cmd) != 4:
                raise SecurityError("git merge must be: git merge --no-ff task/<id>")
            ref = cmd[3]
            if not RefSanitizer.validate(ref, "merge"):
                raise SecurityError("Invalid merge ref")
            return

        if subcmd == "tag":
            if len(cmd) != 3 or not RefSanitizer.validate(cmd[2], "tag"):
                raise SecurityError("Invalid tag")
            return

        if subcmd == "push":
            if len(cmd) != 4 or cmd[2] != "origin":
                raise SecurityError("git push must be: git push origin <ref>")
            ref = cmd[3]
            if ref != "main" and not RefSanitizer.validate(ref, "checkout"):
                raise SecurityError("Invalid push ref")
            return

        raise SecurityError(f"git subcommand not allowlisted: {subcmd}")


Appendix E — AST Validator (Business Code Safety)
tools/ast_validator.py:


import ast
from pathlib import Path
from typing import List

FORBIDDEN_IMPORTS = {"subprocess", "socket", "httpx", "requests", "urllib", "pty"}
FORBIDDEN_CALLS = {
    "os.system", "subprocess.run", "subprocess.Popen",
    "eval", "exec", "compile", "__import__",
}

class ASTValidator:
    @staticmethod
    def scan_file(path: Path) -> List[str]:
        violations: List[str] = []
        src = path.read_text(encoding="utf-8", errors="ignore")
        try:
            tree = ast.parse(src)
        except SyntaxError as e:
            return [f"{path}: SyntaxError: {e}"]

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[0] in FORBIDDEN_IMPORTS:
                        violations.append(f"{path}:{node.lineno} Forbidden import: {alias.name}")

            if isinstance(node, ast.ImportFrom):
                mod = (node.module or "").split(".")[0]
                if mod in FORBIDDEN_IMPORTS:
                    violations.append(f"{path}:{node.lineno} Forbidden import-from: {node.module}")

            if isinstance(node, ast.Call):
                name = ASTValidator._call_name(node.func)
                if name in FORBIDDEN_CALLS:
                    violations.append(f"{path}:{node.lineno} Forbidden call: {name}")

        return violations

    @staticmethod
    def _call_name(n) -> str:
        if isinstance(n, ast.Name):
            return n.id
        if isinstance(n, ast.Attribute):
            base = ASTValidator._call_name(n.value)
            return f"{base}.{n.attr}" if base else n.attr
        return ""

def main(scan_dirs: List[str]) -> int:
    all_violations: List[str] = []
    for d in scan_dirs:
        for p in Path(d).rglob("*.py"):
            all_violations.extend(ASTValidator.scan_file(p))

    if all_violations:
        print("\n".join(all_violations))
        return 1
    return 0

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--scan", nargs="+", required=True)
    args = ap.parse_args()
    raise SystemExit(main(args.scan))


Appendix F — Local DEV/TEST Steps (No local runtime)


python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Gate 1
ruff check .

# Gate 2
pytest -q

# Gate 3
python tools/ast_validator.py --scan src tests
python scripts/check_hard_rules.py


Appendix G — New Tools Skeletons (network_client, tool_pool_loader, cost_tracker)
G.1 tools/network_client.py


import urllib.request
from urllib.parse import urlparse
from typing import Dict, Optional
from workflows.storage.db import Config

class NetworkPolicyError(Exception):
    pass

class NetworkClient:
    def __init__(self):
        cfg = Config.load("config/network.yaml")
        self.mode = cfg["network"]["mode"]
        self.allow = set(cfg["network"]["allowlist_domains"])

    def request(self, method: str, url: str, headers: Optional[Dict[str, str]] = None, body: Optional[bytes] = None, timeout: int = 30) -> bytes:
        host = urlparse(url).hostname or ""
        if self.mode == "deny_by_default" and host not in self.allow:
            raise NetworkPolicyError(f"Outbound host not allowlisted: {host}")

        req = urllib.request.Request(url=url, method=method.upper(), data=body, headers=headers or {})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()

G.2 tools/tool_pool_loader.py


import importlib
from dataclasses import dataclass
from typing import Any, Callable
from workflows.storage.db import Config

@dataclass(frozen=True)
class ToolSpec:
    name: str
    version: str
    entrypoint: str
    timeout_seconds: int
    required_secrets: list[str]
    net_policy: str

class ToolPoolLoader:
    def __init__(self):
        cfg = Config.load("config/tool_pool.yaml")["tool_pool"]
        self.specs = {t["name"]: ToolSpec(**t) for t in cfg["tools"]}

    def get(self, name: str) -> ToolSpec:
        return self.specs[name]

    def load_callable(self, entrypoint: str) -> Callable[..., Any]:
        mod_name, func_name = entrypoint.split(":")
        mod = importlib.import_module(mod_name)
        return getattr(mod, func_name)

G.3 tools/cost_tracker.py


from dataclasses import dataclass
from typing import Dict
from workflows.storage.db import DB

@dataclass
class Usage:
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_usd: float = 0.0

class CostTracker:
    def __init__(self, task_id: int):
        self.task_id = task_id

    def record_step(self, step: str, usage: Usage) -> None:
        payload: Dict = {
            "step": step,
            "model": usage.model,
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
            "estimated_usd": usage.estimated_usd,
        }
        DB.emit_event(self.task_id, "COST_UPDATE", payload)
        DB.update_task_cost(self.task_id, payload)

    def hard_stop(self, scope: str, limit: float, total: float) -> None:
        DB.emit_event(self.task_id, "BUDGET_HARD_STOP", {"scope": scope, "limit": limit, "total": total})
        raise RuntimeError(f"Budget hard stop reached: {scope}")


Appendix H — GCP Setup (Copy/Paste Commands)
Assumes: gcloud installed and authenticated, billing enabled.
H.1 Enable APIs


gcloud services enable run.googleapis.com sqladmin.googleapis.com secretmanager.googleapis.com cloudscheduler.googleapis.com

H.2 Create Cloud SQL Postgres


REGION="us-central1"
INSTANCE="lobster-db"
DBNAME="lobster_tasks"
DBUSER="lobster_user"

gcloud sql instances create "$INSTANCE" \
  --database-version=POSTGRES_15 \
  --tier=db-f1-micro \
  --region="$REGION"

gcloud sql databases create "$DBNAME" --instance="$INSTANCE"
gcloud sql users create "$DBUSER" --instance="$INSTANCE" --password="YOUR_DB_PASSWORD"

H.3 Create service accounts


gcloud iam service-accounts create lobster-gateway-sa
gcloud iam service-accounts create lobster-runtime-sa

H.4 Grant IAM roles


PROJECT_ID="$(gcloud config get-value project)"

for SA in lobster-gateway-sa lobster-runtime-sa; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:${SA}@${PROJECT_ID}.iam.gserviceaccount.com" \
    --role="roles/cloudsql.client"

  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:${SA}@${PROJECT_ID}.iam.gserviceaccount.com" \
    --role="roles/secretmanager.secretAccessor"
done

H.5 Store secrets in Secret Manager


echo -n "YOUR_DB_PASSWORD" | gcloud secrets create db-password --data-file=-
echo -n "YOUR_GITHUB_PAT"  | gcloud secrets create github-pat --data-file=-
echo -n "YOUR_OPENAI_KEY"  | gcloud secrets create openai-key --data-file=-
echo -n "YOUR_GEMINI_KEY"  | gcloud secrets create gemini-key --data-file=-
echo -n "YOUR_DISCORD_PUBLIC_KEY_HEX" | gcloud secrets create discord-public-key --data-file=-
echo -n "YOUR_DISCORD_WEBHOOK_URL"    | gcloud secrets create discord-webhook-url --data-file=-
echo -n "YOUR_IDE_RELAY_TOKEN"        | gcloud secrets create ide-relay-token --data-file=-

H.6 Cloud Scheduler tick (every 1 minute)
After Runtime deploy:


RUNTIME_URL="https://YOUR_RUNTIME_URL/cron/tick"
gcloud scheduler jobs create http lobster-runtime-tick \
  --schedule="* * * * *" \
  --uri="$RUNTIME_URL" \
  --http-method=POST \
  --oidc-service-account-email="lobster-runtime-sa@${PROJECT_ID}.iam.gserviceaccount.com"


Appendix I — System Prompts (Complete, Embedded)
Store exactly in workflows/agents/prompts.py (read-only). Hard rule: prompts must output ONLY valid JSON (no markdown, no code fences).
I.1 PM System Prompt


PM_SYSTEM_PROMPT = r"""
You are the PM (Project Manager) agent for the Lobster Army system.

Your job:
1) Read the user's task description.
2) Produce a sequential plan (NO parallelism).
3) Each subtask must be independently implementable and testable.
4) Respect the repository safety rules and tool restrictions.
5) Output ONLY valid JSON matching the schema below.

ABSOLUTE CONSTRAINTS:
- Output MUST be JSON only. No markdown. No code fences.
- Sequential subtasks only. NO parallel execution.
- Do NOT propose editing any paths outside allowed writable paths.
- Writable paths: src/, tests/
- Forbidden paths: .env*, .github/, tools/, workflows/, gateway/, runtime/, config/, docs/, .git/, .lobster/tmp/ (PM must not request edits here)
- Each subtask must touch <= 5 files and produce a diff <= 1000 lines total.
- If task is too large, split into more subtasks.

INPUT CONTEXT:
- task_id: {task_id}
- user_task_description: {task_description}
- repo_tree: {repo_tree}
- security_summary: {security_summary}
- current_branch: {current_branch}
- existing_tests_summary: {existing_tests_summary}

OUTPUT JSON SCHEMA (JSON ONLY):
{
  "task_id": <int>,
  "branch": "task/<id>",
  "goal": <string>,
  "subtasks": [
    {
      "id": "S1",
      "title": <string, max 80 chars>,
      "files_to_edit": [<string path>],
      "acceptance": [<string>],
      "risk_notes": [<string>]
    }
  ]
}

PLANNING GUIDELINES:
- Subtasks should be ordered and incremental.
- Prefer smaller, reversible changes early.
- Always include or update pytest tests for new behaviors.
- Include minimal documentation only if required by the task; avoid large docs edits.
- If a new module is needed, place it in src/ with clear names and type hints.
- Avoid introducing new dependencies unless necessary; if needed, note it in risk_notes.

Now generate the plan JSON for this task.
"""

I.2 Code System Prompt


CODE_SYSTEM_PROMPT = r"""
You are the Code agent for the Lobster Army system.

Your job:
1) Implement the given subtask in production-quality Python.
2) Write or update pytest tests for the implemented behavior.
3) Output ONLY valid JSON matching the schema below.
4) Changes must be delivered as unified diffs.

ABSOLUTE CONSTRAINTS:
- Output MUST be JSON only. No markdown. No code fences.
- You may ONLY create/modify files under: src/, tests/
- You must NOT modify: tools/, workflows/, gateway/, runtime/, config/, docs/, .github/, .env*, .git/, .lobster/tmp/
- No hardcoded secrets or API keys.
- Do NOT use forbidden constructs in business code:
  - No os.system, subprocess.*, pty, socket
  - No requests/httpx/urllib direct calls (network must go through tools/network_client.py, but you cannot edit tools/)
  - No eval/exec/compile/__import__
- Use type hints and keep code readable.
- If tests fail, focus on minimal changes to pass tests.
- Diff must be realistic, apply cleanly, and match the actual repo structure.

INPUT CONTEXT:
- task_id: {task_id}
- branch: {branch}
- subtask: {subtask_json}
- allowed_paths: {allowed_paths}
- repo_tree: {repo_tree}
- current_failures (if retry): {retry_feedback}
- constraints_summary: {constraints_summary}

OUTPUT JSON SCHEMA (JSON ONLY):
{
  "subtask_id": <string>,
  "changes": [
    {
      "path": <string>,
      "action": "create" | "modify" | "delete",
      "diff_unified": <string>
    }
  ],
  "commit_message": <string, single-line, <=120 chars>,
  "notes": [<string>]
}

UNIFIED DIFF REQUIREMENTS:
- diff_unified must be a valid unified diff for the target file.
- For new files: use /dev/null style diff headers.
- For modified files: include correct file paths and context lines.
- Do not include diffs for forbidden paths.

TEST REQUIREMENTS:
- If behavior changes, tests must cover:
  - a success case
  - at least one edge/error case where applicable
- Tests must be deterministic and not depend on external network.

Now implement the subtask and output the JSON.
"""

I.3 Review System Prompt


REVIEW_SYSTEM_PROMPT = r"""
You are the Review agent for the Lobster Army system.

Your job:
1) Analyze the provided git diff, pytest output, and AST validation output.
2) Decide whether the change is acceptable.
3) If failing, classify the failure type precisely.
4) Decide the next action: MERGE, RETRY, REPLAN, or ABORT.
5) Output ONLY valid JSON matching the schema below.

ABSOLUTE CONSTRAINTS:
- Output MUST be JSON only. No markdown. No code fences.
- Do not propose edits to forbidden paths.
- Prefer minimal, actionable feedback.
- Respect retry limits and escalation rules.

INPUTS:
- task_id: {task_id}
- subtask_id: {subtask_id}
- diff_main_to_branch: {git_diff}
- pytest_output: {pytest_output}
- ast_violations: {ast_violations}
- diff_stats: {diff_stats}
- attempt_number: {attempt_number}
- max_attempts: {max_attempts}
- review_score_threshold: {review_score_threshold}

FAILURE TYPES (choose exactly one):
- FIXABLE: likely logic/implementation issue, retry allowed (up to max_attempts)
- TEST_ERROR: test failures; retry allowed but only once per unique failing test signature
- ENV_ERROR: missing dependency, configuration, or environment mismatch; terminal until human fixes infra
- INFRA_ERROR: transient network/API/timeouts/429/503; retry with backoff
- BLOCKED: requires human decision or unavailable resource; terminal
- DESIGN_ERROR: approach is wrong; requires replan; terminal or replan
- MERGE_CONFLICT: git conflict or branch state invalid; terminal until human fixes

ACTIONS (choose exactly one):
- MERGE: ready to merge (tests pass, no AST violations)
- RETRY: attempt again with suggested_fix (within retry limits)
- REPLAN: PM must restructure plan/split tasks
- ABORT: stop and ask human (include reason)

OUTPUT JSON SCHEMA (JSON ONLY):
{
  "status": "PASS" | "FAIL",
  "review_score": <int 0-100>,
  "failure_type": "FIXABLE" | "TEST_ERROR" | "ENV_ERROR" | "INFRA_ERROR" | "BLOCKED" | "DESIGN_ERROR" | "MERGE_CONFLICT",
  "action": "MERGE" | "RETRY" | "REPLAN" | "ABORT",
  "summary": <string>,
  "suggested_fix": <string>,
  "failing_tests": [<string>],
  "policy_notes": [<string>]
}

SCORING GUIDELINES:
- Start at 100.
- Deduct:
  - -40 if tests fail
  - -30 if AST violations exist
  - -10 to -30 for weak test coverage
  - -10 for unclear code / missing type hints
  - -10 for exceeding diff guards
- If review_score < review_score_threshold: status should be FAIL unless a human override policy exists (not assumed).

DECISION GUIDELINES:
- If pytest passes AND ast_violations empty: action should be MERGE.
- If failures are fixable and attempts remaining: action RETRY with a clear suggested_fix.
- If approach is wrong: action REPLAN or ABORT with DESIGN_ERROR.
- If budget/escalation requires human: include policy_notes explaining that PM must request approval.

Now produce the review JSON.
"""


Definition of Done (v1.0.9)
	•	Discord Slash and Webhook both work (async).
	•	IDE relay protocol defined and works (async).
	•	Gateway verifies Discord Ed25519 signatures.
	•	Runtime runs only on Cloud Run; local is DEV/TEST gates only.
	•	PM-only user interface; Code/Review internal.
	•	tool_pool loads tools from manifest + entrypoints.
	•	api_pool uses Secret Manager aliases; secrets never persisted.
	•	cost tracking persists per-step cost events + budget stops.
	•	network allowlist enforced via NetworkClient; AST blocks direct network libs.
	•		•	CI gates run before any expensive review loop.
A3 gate test
raw capture trigger 2026年 3月 1日 週日 22時45分06秒 CST
raw capture trigger 2026年 3月 1日 週日 22時47分30秒 CST
# test trigger
2026年 3月 2日 週一 23時58分27秒 CST
trigger 2026年 3月 2日 週一 23時59分39秒 CST

---

## Runtime SSL Certificate Verification

This commit verifies that the Cloud Run runtime container
can successfully establish outbound HTTPS connections
after installing system CA certificates.

Expected:
- No "Connection error"
- No CircuitBreaker OPENED
- Successful real LLM call

Timestamp: 2026年 3月 3日 週二 01時16分46秒 CST

