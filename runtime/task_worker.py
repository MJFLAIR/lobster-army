from workflows.task_manager import TaskManager
from workflows.storage.db import DB
from router.task_router import TaskRouter

import logging
import json

class TaskWorker:
    def run_task(self, task_id: int):
        task_obj = DB.get_task(task_id)
        task = task_obj.__dict__ if task_obj else {}

        meta = task.get("meta_json")
        if isinstance(meta, str):
            try:
                import json
                meta = json.loads(meta)
                task["meta_json"] = meta
            except Exception:
                pass

        if isinstance(meta, dict):
            c_files = meta.get("changed_files")
            if not c_files:
                pr_num = meta.get("pr_number")
                if not pr_num and isinstance(meta.get("pull_request"), dict):
                    pr_num = meta["pull_request"].get("number")
                
                repo_str = meta.get("repository")
                if isinstance(repo_str, dict):
                    repo_str = repo_str.get("full_name")
                
                if pr_num and isinstance(repo_str, str):
                    try:
                        import os, requests
                        token = os.getenv("GITHUB_TOKEN")
                        headers = {"Accept": "application/vnd.github+json", "User-Agent": "lobster-army"}
                        if token:
                            headers["Authorization"] = f"token {token}"
                        
                        url = f"https://api.github.com/repos/{repo_str}/pulls/{pr_num}/files"
                        logging.info(f"[GITHUB_API] Fetching changed files: {url}")
                        r = requests.get(url, headers=headers, timeout=10)
                        
                        if r.status_code == 200:
                            meta["changed_files"] = [f.get("filename") for f in r.json() if isinstance(f, dict) and f.get("filename")]
                            logging.info(f"[GITHUB_API] Fetched {len(meta['changed_files'])} changed files")
                        else:
                            logging.warning(f"[GITHUB_API] Failed to fetch changed files, status: {r.status_code}")
                    except Exception as e:
                        logging.warning(f"[GITHUB_API] Exception fetching changed files: {e}")

        task_router = TaskRouter()

        try:
            from workflows.enrichment.task_enricher import enrich_task
            task = enrich_task(task)
        except Exception as e:
            logging.error(f"[TASK_ENRICHER_ERROR] Failed to inject enricher: {e}")

        try:
            from workflows.orchestration.execution_tracer import ExecutionTracer
            tracer = ExecutionTracer(task_id)
            meta_input = meta.get("input", task.get("description", "")) if isinstance(meta, dict) else task.get("description", "")
            task_type = meta.get("task_type", "unknown") if isinstance(meta, dict) else "unknown"
            tracer.set_task_info(task_type, meta_input)
        except Exception as e:
            logging.error(f"[TRACER_INIT_ERROR] {e}")
            tracer = None

        decision = task_router.route(task)

        logging.info("[TASK_ROUTER_DECISION]", extra={"decision": decision})
        if tracer:
            tracer.record_router(decision)

        try:
            from workflows.orchestration.pipeline_planner import build_execution_plan
            execution_plan = build_execution_plan(decision)
            
            meta = task.get("meta")
            if not isinstance(meta, dict):
                meta = task.get("meta_json")
            if not isinstance(meta, dict):
                meta = {}
            task["meta"] = meta
            
            task["meta"]["execution_plan"] = execution_plan
            
            logging.info("[TASK_EXECUTION_PLAN_ATTACHED]", extra={
                "pipeline": execution_plan.get("pipeline"),
                "stage_count": len(execution_plan.get("stages", []))
            })
        except Exception as e:
            logging.error("[EXECUTION_PLAN_ATTACH_ERROR]", extra={"error": str(e)})

        if task_obj:
            if task.get("source") == "github":
                meta_json = task.get("meta_json") or {}
                if not isinstance(meta_json, dict):
                    # tolerate JSON string; if parse fails, fallback to empty dict
                    if isinstance(meta_json, str):
                        try:
                            meta_json = json.loads(meta_json)
                        except Exception:
                            meta_json = {}
                    else:
                        meta_json = {}

                # IMPORTANT: even if json.loads succeeds, it might not be a dict
                if not isinstance(meta_json, dict):
                    meta_json = {}

                action = (
                    meta_json.get("action")
                    or meta_json.get("github_action")
                    or (meta_json.get("event") or {}).get("action")  # tolerate nested
                    or "unknown_action"
                )

                repo_val = (
                    meta_json.get("repository")
                    or meta_json.get("repo")
                    or meta_json.get("repository_full_name")
                    or (meta_json.get("event") or {}).get("repository")
                )

                repo = "unknown_repo"
                if isinstance(repo_val, dict):
                    repo = (
                        repo_val.get("full_name")
                        or (
                            f"{((repo_val.get('owner') or {}).get('login') or '').strip()}/"
                            f"{(repo_val.get('name') or '').strip()}"
                        ).strip("/")
                        or "unknown_repo"
                    )
                elif isinstance(repo_val, str):
                    repo = repo_val.strip() or "unknown_repo"

                pr_number = None

                pr_val = meta_json.get("pull_request") or (meta_json.get("event") or {}).get("pull_request")
                if isinstance(pr_val, dict):
                    pr_number = pr_val.get("number")
                elif isinstance(pr_val, int):
                    pr_number = pr_val
                elif isinstance(pr_val, str):
                    # tolerate numeric string
                    try:
                        pr_number = int(pr_val.strip())
                    except Exception:
                        pr_number = None

                if pr_number is None:
                    pr_number = (
                        meta_json.get("pull_request_number")
                        or meta_json.get("pr_number")
                        or meta_json.get("number")  # common in PR event root
                        or (meta_json.get("event") or {}).get("pull_request_number")
                        or (meta_json.get("event") or {}).get("pr_number")
                        or (meta_json.get("event") or {}).get("number")
                    )

                # final normalize to int or None
                if pr_number is not None and not isinstance(pr_number, int):
                    try:
                        pr_number = int(str(pr_number).strip())
                    except Exception:
                        pr_number = None

                keys_preview = []
                try:
                    keys_preview = list(meta_json.keys())[:30] if isinstance(meta_json, dict) else []
                except Exception:
                    keys_preview = []

                logging.info(
                    "[PR_META_KEYS] meta_type=%s keys=%s extracted_action=%s extracted_repo=%s extracted_pr=%s",
                    type(meta_json).__name__,
                    keys_preview,
                    action,
                    repo,
                    pr_number,
                )

                logging.info(f"[PR_EVENT] action={action} repo={repo} pr={pr_number}")
                logging.info(f"[PR_GATE_PRECHECK] repo={repo} pr={pr_number} action={action}")

                gate_actions = {"opened", "synchronize"}
                if action in gate_actions and pr_number is not None:
                    logging.info(
                        "[PR_GATE_TRIGGERED] repo=%s pr=%s action=%s",
                        repo,
                        pr_number,
                        action,
                    )

                    author = "unknown_author"

                    def _login(v):
                        if isinstance(v, dict):
                            return (v.get("login") or "").strip() or None
                        if isinstance(v, str):
                            return v.strip() or None
                        return None

                    pr_obj = meta_json.get("pull_request") or (meta_json.get("event") or {}).get("pull_request")
                    logging.info("[PR_AUTHOR_DEBUG] pull_request=%s", pr_obj)
                    sender_obj = meta_json.get("sender") or (meta_json.get("event") or {}).get("sender")
                    user_obj = meta_json.get("user") or (meta_json.get("event") or {}).get("user")

                    # pull_request.user.login (preferred)
                    if isinstance(pr_obj, dict):
                        u = pr_obj.get("user")
                        author = _login(u) or author

                    # sender.login fallback
                    if author == "unknown_author":
                        author = _login(sender_obj) or author

                    # user.login fallback
                    if author == "unknown_author":
                        author = _login(user_obj) or author

                    allowlist_users = {"MJFLAIR"}

                    if author in allowlist_users:
                        logging.info("[PR_GATE_PASS] repo=%s pr=%s action=%s author=%s", repo, pr_number, action, author)
                        
                        from workflows.agents.llm_review_gate import run_llm_review
                        review = run_llm_review(str(task_id), meta_json)
                        logging.info(
                            "[PR_LLM_RESULT] decision=%s score=%s",
                            review.get("decision"),
                            review.get("score"),
                        )
                        
                        from workflows.actions.github_comment import try_post_pr_comment
                        try_post_pr_comment(str(task_id), meta_json, review)

                        from workflows.actions.github_label import try_apply_pr_labels
                        try_apply_pr_labels(str(task_id), meta_json, review)

                        from workflows.actions.github_merge import try_merge_pr
                        try_merge_pr(str(task_id), meta_json, review)
                    else:
                        logging.info("[PR_GATE_BLOCK] repo=%s pr=%s action=%s author=%s", repo, pr_number, action, author)

        # 事件可以保留（可審計）
        DB.emit_event(task_id, "EXECUTION_STARTED", {"task_id": task_id})

        # --- PHASE C3: EXECUTION ENGINE ---
        plan = task.get("meta", {}).get("execution_plan")
        
        # STEP 1 Validation (Fallback to Single Legacy Execution)
        if not isinstance(plan, dict) or not isinstance(plan.get("stages"), list) or len(plan["stages"]) == 0:
            result = TaskManager().execute(task_id, context={"router_decision": decision, "execution_tracer": tracer})
            if result is None:
                result_summary = {"message": "execution finished", "task_id": task_id}
                cost_json = {"model": "none", "input_tokens": 0, "output_tokens": 0, "estimated_usd": 0}
            else:
                result_summary = result.get("result_summary", {"task_id": task_id})
                cost_json = result.get("cost_json", {"model": "unknown"})
            DB.emit_event(task_id, "EXECUTION_FINISHED", {"task_id": task_id})
            
            trace_output = tracer.finalize("SUCCESS") if tracer else {}
            return result_summary, cost_json, trace_output

        # STEP 2 Add execution context container
        execution_context = {
            "stage_outputs": [],
            "last_output": None
        }
        task["meta"]["execution_context"] = execution_context
        task["meta"]["healing_log"] = []
        task["meta"]["retry_summary"] = {
            "total_retries": 0,
            "recovered_stages": 0,
            "failed_stages": 0
        }
        task["meta"]["sent_sitreps"] = []
        
        logging.info("[EXECUTION_ENGINE_START]", extra={"pipeline": plan.get("pipeline")})
        
        # STEP 3 Stage Execution Loop
        for stage in plan["stages"]:
            retry_count = 0
            logging.info("[STAGE_EXECUTION_START]", extra={
                "stage": stage.get("stage"),
                "agent": stage.get("agent"),
                "action": stage.get("action")
            })
            
            # STEP 4 Map agent to executor / modify task
            task["meta"]["current_stage"] = stage
            task["meta"]["stage_index"] = stage.get("stage")
            task["meta"]["stage_agent"] = stage.get("agent")
            task["meta"]["stage_action"] = stage.get("action")
            task["meta"]["stage_status"] = "running"
            
            # --- PHASE C4: AGENT BINDING ---
            try:
                from workflows.orchestration.agent_binder import bind_stage_agent
                agent_binding = bind_stage_agent(stage)
            except Exception as e:
                agent_binding = {
                    "stage_agent": stage.get("agent"),
                    "bound_role": "pm",
                    "stage_action": stage.get("action"),
                    "binding_source": "fallback_on_error"
                }
                logging.error("[AGENT_BINDING_FATAL_ERROR]", extra={"error": str(e)})

            task["meta"]["agent_binding"] = agent_binding
            task["meta"]["bound_role"] = agent_binding.get("bound_role")
            task["meta"]["stage_agent"] = agent_binding.get("stage_agent")
            task["meta"]["stage_action"] = agent_binding.get("stage_action")
            
            # STEP 7 Context passing
            task["meta"]["previous_output"] = execution_context["last_output"]
            
            # STEP 5 Execute stage
            try:
                execute_context = {
                    "router_decision": decision,
                    "bound_role": agent_binding.get("bound_role"),
                    "stage_action": agent_binding.get("stage_action"),
                    "stage_index": stage.get("stage"),
                    "execution_tracer": tracer
                }
                
                try:
                    from workflows.orchestration.agent_dispatcher import dispatch_agent_execution
                    result = dispatch_agent_execution(task_id, execute_context)
                except Exception as dispatch_e:
                    logging.error("[AGENT_DISPATCH_FATAL]", extra={"error": str(dispatch_e)})
                    result = TaskManager().execute(task_id, context=execute_context)
                
                # STEP 6 Capture result
                stage_result = {
                    "stage": stage.get("stage"),
                    "agent": stage.get("agent"),
                    "action": stage.get("action"),
                    "status": "success",
                    "output": result
                }
                execution_context["stage_outputs"].append(stage_result)
                execution_context["last_output"] = result
                
                logging.info("[STAGE_EXECUTION_SUCCESS]", extra={
                    "stage": stage.get("stage"),
                    "agent": stage.get("agent"),
                    "action": stage.get("action")
                })
                continue
                
            except Exception as e:
                # --- PHASE C7: SELF HEALING LAYER ---
                try:
                    from workflows.orchestration.failure_classifier import classify_failure
                    from workflows.orchestration.retry_policy import should_retry
                    from workflows.orchestration.healing_tracker import build_healing_record
                    
                    failure_info = classify_failure(e)
                    logging.info("[FAILURE_CLASSIFIED]", extra={
                        "stage": stage.get("stage"),
                        "failure_type": failure_info["failure_type"],
                        "retryable": failure_info["retryable"]
                    })
                    
                    retry_info = should_retry(stage, failure_info, retry_count)
                    logging.info("[RETRY_POLICY_DECISION]", extra={
                        "stage": stage.get("stage"),
                        "allow_retry": retry_info["allow_retry"],
                        "retry_count": retry_count
                    })
                    
                    if retry_info["allow_retry"]:
                        retry_count += 1
                        
                    healing_record = build_healing_record(stage, failure_info, retry_info, retry_count, str(e))
                    task["meta"]["healing_log"].append(healing_record)
                    
                    logging.info("[HEALING_RECORD_ATTACHED]", extra={
                        "stage": stage.get("stage"),
                        "failure_type": failure_info["failure_type"],
                        "retry_attempted": healing_record["retry_attempted"]
                    })
                    
                    if retry_info["allow_retry"]:
                        # Retry logic
                        task["meta"]["retry_summary"]["total_retries"] += 1
                        
                        logging.info("[STAGE_RETRY_START]", extra={
                            "stage": stage.get("stage"),
                            "retry_count": retry_count
                        })
                        
                        try:
                            result = self._execute_stage(task_id, execute_context)
                                
                            task["meta"]["retry_summary"]["recovered_stages"] += 1
                            stage_result = {
                                "stage": stage.get("stage"),
                                "agent": stage.get("agent"),
                                "action": stage.get("action"),
                                "status": "recovered",
                                "output": result
                            }
                            execution_context["stage_outputs"].append(stage_result)
                            execution_context["last_output"] = result
                            
                            healing_record["outcome"] = "recovered"
                            
                            logging.info("[STAGE_RETRY_SUCCESS]", extra={
                                "stage": stage.get("stage"),
                                "retry_count": retry_count
                            })
                            continue
                            
                        except Exception as retry_e:
                            task["meta"]["retry_summary"]["failed_stages"] += 1
                            stage_result = {
                                "stage": stage.get("stage"),
                                "agent": stage.get("agent"),
                                "action": stage.get("action"),
                                "status": "failed",
                                "error": str(retry_e)
                            }
                            execution_context["stage_outputs"].append(stage_result)
                            
                            healing_record["outcome"] = "failed"
                            
                            logging.info("[STAGE_RETRY_FAILED]", extra={
                                "stage": stage.get("stage"),
                                "retry_count": retry_count,
                                "error": str(retry_e)
                            })
                            
                            from workflows.strategy.strategy_classifier import classify_issue
                            from workflows.strategy.micro_fix_engine import apply_micro_fix
                            from workflows.strategy.escalation_engine import create_sitrep

                            issue_type = classify_issue(failure_info, str(retry_e))

                            if issue_type == "micro_fix":
                                fix_result = apply_micro_fix(stage, str(retry_e))
                                logging.info("[STRATEGY_MICRO_FIX_RESULT]", extra=fix_result)
                            elif issue_type == "escalate":
                                sitrep = create_sitrep(task_id, failure_info, execution_context)
                                logging.warning("[STRATEGY_ESCALATED]", extra=sitrep)
                                
                                try:
                                    dedupe_key = f"{sitrep.get('task_id')}_{sitrep.get('failure_type')}_{sitrep.get('agent')}_{sitrep.get('pipeline')}"
                                    sent_sitreps = task.setdefault("meta", {}).setdefault("sent_sitreps", [])
                                    if dedupe_key in sent_sitreps:
                                        logging.info("[ESCALATION_DELIVERY_SKIPPED_DUPLICATE]", extra={"dedupe_key": dedupe_key})
                                    else:
                                        sent_sitreps.append(dedupe_key)
                                        from workflows.strategy.escalation_delivery import deliver_sitrep
                                        delivery_result = deliver_sitrep(sitrep)
                                        logging.info("[SITREP_DELIVERY_RESULT]", extra={
                                            "task_id": sitrep.get("task_id"),
                                            "github_status": delivery_result.get("github", {}).get("status"),
                                            "discord_status": delivery_result.get("discord", {}).get("status")
                                        })
                                except Exception as delivery_e:
                                    logging.warning("[STRATEGY_DELIVERY_FAIL]", extra={"error": str(delivery_e)})
                            
                            break
                    else:
                        task["meta"]["retry_summary"]["failed_stages"] += 1
                        stage_result = {
                            "stage": stage.get("stage"),
                            "agent": stage.get("agent"),
                            "action": stage.get("action"),
                            "status": "failed",
                            "error": str(e)
                        }
                        execution_context["stage_outputs"].append(stage_result)
                        
                        healing_record["outcome"] = "failed"
                        
                        from workflows.strategy.strategy_classifier import classify_issue
                        from workflows.strategy.micro_fix_engine import apply_micro_fix
                        from workflows.strategy.escalation_engine import create_sitrep

                        issue_type = classify_issue(failure_info, str(e))

                        if issue_type == "micro_fix":
                            fix_result = apply_micro_fix(stage, str(e))
                            logging.info("[STRATEGY_MICRO_FIX_RESULT]", extra=fix_result)
                        elif issue_type == "escalate":
                            sitrep = create_sitrep(task_id, failure_info, execution_context)
                            logging.warning("[STRATEGY_ESCALATED]", extra=sitrep)
                            
                            try:
                                dedupe_key = f"{sitrep.get('task_id')}_{sitrep.get('failure_type')}_{sitrep.get('agent')}_{sitrep.get('pipeline')}"
                                sent_sitreps = task.setdefault("meta", {}).setdefault("sent_sitreps", [])
                                if dedupe_key in sent_sitreps:
                                    logging.info("[ESCALATION_DELIVERY_SKIPPED_DUPLICATE]", extra={"dedupe_key": dedupe_key})
                                else:
                                    sent_sitreps.append(dedupe_key)
                                    from workflows.strategy.escalation_delivery import deliver_sitrep
                                    delivery_result = deliver_sitrep(sitrep)
                                    logging.info("[SITREP_DELIVERY_RESULT]", extra={
                                        "task_id": sitrep.get("task_id"),
                                        "github_status": delivery_result.get("github", {}).get("status"),
                                        "discord_status": delivery_result.get("discord", {}).get("status")
                                    })
                            except Exception as delivery_e:
                                logging.warning("[STRATEGY_DELIVERY_FAIL]", extra={"error": str(delivery_e)})
                        
                        break
                        
                except Exception as healing_system_error:
                    logging.error("[HEALING_SYSTEM_FATAL]", extra={"error": str(healing_system_error)})
                    stage_result = {
                        "stage": stage.get("stage"),
                        "agent": stage.get("agent"),
                        "action": stage.get("action"),
                        "status": "failed",
                        "error": str(e)
                    }
                    execution_context["stage_outputs"].append(stage_result)
                    break
                
        # STEP 9 Final Status
        has_failure = any(s.get("status") == "failed" for s in execution_context["stage_outputs"])
        task["meta"]["execution_status"] = "partial_failed" if has_failure else "completed"
        
        logging.info("[EXECUTION_ENGINE_COMPLETE]", extra={
            "status": task["meta"]["execution_status"],
            "stages_run": len(execution_context["stage_outputs"])
        })
        
        # We need to return the expected format for API completion
        last_output = execution_context["last_output"]
        if not isinstance(last_output, dict):
            result_summary = {"message": "execution engine finished", "task_id": task_id, "status": task["meta"]["execution_status"]}
            cost_json = {"model": "none", "input_tokens": 0, "output_tokens": 0, "estimated_usd": 0}
        else:
            result_summary = last_output.get("result_summary", {"task_id": task_id, "status": task["meta"]["execution_status"]})
            cost_json = last_output.get("cost_json", {"model": "unknown"})
        
        DB.emit_event(task_id, "EXECUTION_FINISHED", {"task_id": task_id})
        
        try:
            from workflows.learning.learning_extractor import extract_learning_records
            from workflows.learning.learning_store import append_learning_records
            
            records = extract_learning_records(task)
            
            if records:
                append_learning_records(records)
            
                logging.info("[LEARNING_RECORDS_STORED]", extra={
                    "count": len(records)
                })
        except Exception as e:
            logging.error(f"[LEARNING_SYSTEM_FATAL] {str(e)}")
            
        trace_output = tracer.finalize("SUCCESS" if task["meta"]["execution_status"] == "completed" else "FAILED") if tracer else {}    
        return result_summary, cost_json, trace_output

    def _execute_stage(self, task_id, execute_context):
        try:
            from workflows.orchestration.agent_dispatcher import dispatch_agent_execution
            
            logging.info("[EXECUTION_PATH]", extra={
                "mode": "dispatcher"
            })
            execute_context["execution_mode"] = "dispatcher"
            
            return dispatch_agent_execution(task_id, execute_context)
            
        except Exception as dispatch_error:
            
            logging.info("[EXECUTION_PATH]", extra={
                "mode": "fallback_task_manager",
                "error": str(dispatch_error)
            })
            execute_context["execution_mode"] = "fallback_task_manager"
            
            from workflows.task_manager import TaskManager
            return TaskManager().execute(task_id, context=execute_context)