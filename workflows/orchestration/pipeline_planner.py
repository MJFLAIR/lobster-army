import logging

def build_execution_plan(pipeline: str) -> dict:
    logging.info("[EXECUTION_PLAN_BUILD_START]", extra={"pipeline": pipeline})
    
    try:
        stages = []
        
        if pipeline == "review_only":
            stages = [
                {"stage": 1, "agent": "review", "action": "review"}
            ]
        elif pipeline == "planning_pipeline":
            stages = [
                {"stage": 1, "agent": "pm", "action": "plan"}
            ]
        elif pipeline == "code_pipeline":
            stages = [
                {"stage": 1, "agent": "code", "action": "implement"},
                {"stage": 2, "agent": "review", "action": "final_review"}
            ]
        elif pipeline == "code_pipeline_with_tests":
            stages = [
                {"stage": 1, "agent": "code", "action": "implement"},
                {"stage": 2, "agent": "review", "action": "test_review"},
                {"stage": 3, "agent": "review", "action": "final_review"}
            ]
        elif pipeline == "code_with_doc_review":
            stages = [
                {"stage": 1, "agent": "code", "action": "implement"},
                {"stage": 2, "agent": "review", "action": "doc_review"},
                {"stage": 3, "agent": "review", "action": "final_review"}
            ]
        else:
            logging.error("[EXECUTION_PLAN_BUILD_ERROR]", extra={
                "pipeline": pipeline,
                "error": f"Unknown pipeline format: {pipeline}"
            })
            pipeline = "planning_pipeline"
            stages = [
                {"stage": 1, "agent": "pm", "action": "plan"}
            ]
            
        plan = {
            "pipeline": pipeline,
            "stages": stages
        }
        
        logging.info("[EXECUTION_PLAN_BUILD_SUCCESS]", extra={
            "pipeline": plan["pipeline"],
            "stage_count": len(stages)
        })
        
        return plan

    except Exception as e:
        logging.error("[EXECUTION_PLAN_BUILD_ERROR]", extra={
            "pipeline": pipeline,
            "error": str(e)
        })
        return {
            "pipeline": pipeline,
            "stages": []
        }
