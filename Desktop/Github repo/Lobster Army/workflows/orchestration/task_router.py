import logging

def execute_plan(plan: dict, agent_registry: dict) -> list:
    """
    Sequentially executes a validated PM Agent execution plan.
    Returns a structured trace of the execution.
    """
    execution_plan = plan.get("execution_plan", [])
    trace = []
    
    for step in execution_plan:
        step_order = step.get("step_order")
        agent_name = step.get("agent", step.get("assigned_agent"))
        instruction = step.get("instruction")
        
        # 2. validate minimal fields
        if step_order is None or not agent_name or not instruction:
            trace.append({
                "step_order": step_order if step_order is not None else -1,
                "agent": agent_name if agent_name else "unknown",
                "status": "skipped"
            })
            continue

        # 3. resolve agent
        handler = agent_registry.get(agent_name)
        if not handler:
            trace.append({
                "step_order": step_order,
                "agent": agent_name,
                "status": "skipped"
            })
            continue

        from workflows.learning.knowledge_injector import enrich_instruction_with_learnings
        enriched_instruction = enrich_instruction_with_learnings(
            agent_name=agent_name,
            base_instruction=instruction
        )
        
        # ---- TOOL LAYER START ----
        final_instruction = enriched_instruction

        if step.get("url"):
            from tools.fetch_url import fetch_url
            web_result = fetch_url(step["url"])

            if web_result["status"] == "success":
                safe_content = web_result["content"]
                MAX_PROMPT_CHARS = 8000
                if len(safe_content) > MAX_PROMPT_CHARS:
                    safe_content = (
                        safe_content[:MAX_PROMPT_CHARS] +
                        "\n\n...[WEB CONTENT TRUNCATED FOR CONTEXT LIMIT]..."
                    )

                web_context = (
                    f"### WEB CONTEXT ###\n"
                    f"URL: {step['url']}\n"
                    f"Content:\n{safe_content}\n\n"
                )
                print(f"[TOOL_USED] tool=fetch_url url={step['url']} status=success")
            else:
                web_context = (
                    f"### WEB CONTEXT FAILED ###\n"
                    f"URL: {step['url']}\n"
                    f"Error: {web_result['error']}\n\n"
                )
                print(f"[TOOL_USED] tool=fetch_url url={step['url']} status=failed")

            final_instruction = web_context + final_instruction

        file_path = step.get("file_path")
        if file_path:
            from workflows.tools.read_file import read_file
            file_result = read_file(file_path)
            
            if file_result.get("status") == "success":
                file_content = file_result["content"]
                MAX_CONTEXT_CHARS = 8000
                if len(file_content) > MAX_CONTEXT_CHARS:
                    truncated_content = file_content[:MAX_CONTEXT_CHARS] + "\n...[TRUNCATED]"
                else:
                    truncated_content = file_content

                context_block = (
                    f"### FILE CONTEXT ###\n"
                    f"Path: {file_path}\n"
                    f"Content:\n{truncated_content}\n\n"
                    f"### TASK ###\n"
                )
                final_instruction = context_block + final_instruction
                logging.info(f"[TOOL_USED] tool=read_file path={file_path} status=success")
            else:
                logging.warning(f"[TOOL_USED] tool=read_file path={file_path} status=failed")
        # ---- TOOL LAYER END ----

        logging.info("[TASK_ROUTER_STEP_START]", extra={
            "step": step_order,
            "agent": agent_name
        })
        
        status = "failed"
        error_msg = None
        result = None
        
        try:
            result = handler(final_instruction)
            
            # Extract status safely if handler returns structured dicts
            if isinstance(result, dict) and "status" in result:
                status = result["status"]
                if status == "failed":
                    error_msg = result.get("error", "Agent explicitly failed internally")
            else:
                status = "success"

            # ---- AUTO WRITE (generalized + self-healing + LLM-driven path) ----
            if status == "success" and isinstance(result, dict):
                output_path = result.get("target_file") or step.get("output_path")
                content = result.get("code") or result.get("content")

                if output_path and content:
                    from workflows.tools.write_file import write_file
                    write_result = write_file(
                        path=output_path,
                        content=content,
                        overwrite=step.get("overwrite", True)
                    )

                    result["write_file"] = write_result

                    if write_result["status"] == "failed":
                        status = "failed"
                        error_msg = f"Write Tool Failed: {write_result['error']}"
                        result["status"] = "failed"
                        result["error"] = error_msg
                        logging.warning(f"[TOOL_USED] tool=write_file path={output_path} status=failed")
                    else:
                        logging.info(f"[TOOL_USED] tool=write_file path={output_path} status=success")
            # ---- AUTO WRITE END ----
                
        except Exception as e:
            status = "failed"
            error_msg = str(e)
            
        if status == "failed":
            logging.error("[TASK_ROUTER_STEP_ERROR]", extra={
                "step": step_order,
                "agent": agent_name,
                "error": error_msg
            })
            
        logging.info("[TASK_ROUTER_STEP_END]", extra={
            "step": step_order,
            "agent": agent_name,
            "status": status
        })
        
        trace_entry = {
            "step_order": step_order,
            "agent": agent_name,
            "status": status,
            "instruction": final_instruction
        }
        if error_msg:
            trace_entry["error"] = error_msg
        if result is not None:
            trace_entry["output"] = result
            
        trace.append(trace_entry)
            
    return trace
