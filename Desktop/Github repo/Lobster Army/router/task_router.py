class TaskRouter:
    def route(self, task: dict) -> str:
        import logging
        
        meta = task.get("meta")
        if not isinstance(meta, dict):
            meta = task.get("meta_json")

        if not isinstance(meta, dict):
            meta = {}

        # 🔥 normalize back to task
        task["meta"] = meta
            
        file_types = meta.get("file_types")
        if isinstance(file_types, dict):
            logging.info("[TASK_ROUTER_V3_START]", extra={"file_types": file_types})
            
            code = file_types.get("code")
            test = file_types.get("test")
            doc = file_types.get("doc")
            other = file_types.get("other")

            code_list = code if isinstance(code, list) else []
            test_list = test if isinstance(test, list) else []
            doc_list = doc if isinstance(doc, list) else []
            other_list = other if isinstance(other, list) else []
            
            has_code = len(code_list) > 0
            has_test = len(test_list) > 0
            has_doc = len(doc_list) > 0
            total_files = len(code_list) + len(test_list) + len(doc_list) + len(other_list)
            
            decision = None
            if has_code and has_test:
                decision = "code_pipeline_with_tests"
            elif has_code and has_doc and not has_test:
                decision = "code_with_doc_review"
            elif total_files > 0 and has_doc and not has_code and not has_test:
                decision = "review_only"
            elif total_files > 0 and has_test and not has_code:
                decision = "review_only"
            elif has_code:
                decision = "code_pipeline"
            else:
                decision = "planning_pipeline"
                
            logging.info("[TASK_ROUTER_V3_DECISION]", extra={
                "decision": decision,
                "has_code": has_code,
                "has_test": has_test,
                "has_doc": has_doc,
                "total_files": total_files
            })
            return self._apply_learning_override(decision)

        # Existing v1 fallback routing logic
        meta = task.get("meta_json", {}) or {}

        pr = meta.get("pull_request") or (meta.get("event") or {}).get("pull_request") or {}
        if not isinstance(pr, dict):
            pr = {}

        changed_files = meta.get("changed_files", [])

        head = pr.get("head") or {}
        branch = head.get("ref", "")
        if not isinstance(branch, str):
            branch = ""

        labels_data = pr.get("labels", [])
        labels = []
        if isinstance(labels_data, list):
            for l in labels_data:
                if isinstance(l, dict):
                    labels.append(l.get("name", "").lower())
                elif isinstance(l, str):
                    labels.append(l.lower())

        # Rule 1: docs/test only → review_only
        if isinstance(changed_files, list) and len(changed_files) > 0:
            if all(self._is_doc_or_test_file(f) for f in changed_files):
                logging.info("Legacy routing decision", extra={"reason": "docs_or_test_only"})
                return self._apply_learning_override("review_only")

        # Rule 2: fix branch → code_pipeline
        if branch.startswith("fix/") or branch.startswith("bugfix/"):
            logging.info("Legacy routing decision", extra={"reason": "fix_branch"})
            return self._apply_learning_override("code_pipeline")

        # Rule 3: task label → planning
        if any("task" in lbl or "automation" in lbl for lbl in labels):
            logging.info("Legacy routing decision", extra={"reason": "task_label"})
            return self._apply_learning_override("planning_pipeline")

        logging.info("Legacy routing decision", extra={"reason": "default_fallback"})
        return self._apply_learning_override("review_only")

    def _is_doc_or_test_file(self, filename: str) -> bool:
        if not isinstance(filename, str):
            return False

        f = filename.lower()

        if f.endswith(('.md', '.txt', '.json', '.yaml', '.yml', '.toml', '.ini', '.cfg', '.conf')):
            return True

        if 'docs/' in f or 'test/' in f or 'tests/' in f or 'test_' in f or '_test' in f:
            return True

        return False

    def _apply_learning_override(self, decision: str) -> str:
        try:
            import logging
            from workflows.learning.learning_adapter import get_routing_hint
            hint = get_routing_hint(decision)

            if hint.get("override_pipeline"):
                logging.info("[LEARNING_ROUTER_OVERRIDE]", extra={
                    "from": decision,
                    "to": hint["override_pipeline"],
                    "reason": hint.get("reason", "")
                })
                return hint["override_pipeline"]
        except Exception as e:
            import logging
            logging.warning("[ROUTER_ADAPTER_FAIL]", extra={"error": str(e)})
            
        return decision