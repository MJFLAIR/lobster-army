from utils.identifier import normalize_identifier


class Quartermaster:
    def get_equipment(self, role: str, context: dict = None) -> dict:
        """
        Returns:
        {
            "provider": "openai" | "gemini",
            "model": "<REAL_MODEL_NAME>"
        }
        """
        context = context or {}
        complexity = context.get("complexity", "medium")
        normalized_role = normalize_identifier(role)

        # Base routing
        if normalized_role in ["feature_coder", "autofix_medic", "auto_fix_medic"]:
            provider = "openai"
            model = "gpt-4o"
        elif normalized_role in ["reviewer", "pm_agent", "pm"]:
            provider = "gemini"
            model = "gemini-1.5-flash"
        elif normalized_role in ["summarizer", "insight_agent"]:
            provider = "openai"
            model = "gpt-4o-mini"
        else:
            provider = "openai"
            model = "gpt-4o-mini"

        # Complexity override (SAFE)
        if complexity == "high":
            if normalized_role in ["feature_coder", "autofix_medic", "auto_fix_medic"]:
                provider = "openai"
                model = "gpt-4o"
            else:
                provider = "gemini"
                model = "gemini-1.5-pro"

        return {
            "provider": provider,
            "model": model
        }
