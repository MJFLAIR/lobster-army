class TaskRouter:
    def route(self, task: dict) -> dict:
        """
        Phase B - Shadow Mode Router
        Only makes decisions, does NOT control execution yet.
        """

        task_type = task.get("type", "unknown")

        if task_type == "code":
            return {
                "pipeline": "code_pipeline",
                "reason": "default code task",
                "confidence": 0.6,
            }

        return {
            "pipeline": "code_pipeline",
            "reason": "fallback default",
            "confidence": 0.3,
        }