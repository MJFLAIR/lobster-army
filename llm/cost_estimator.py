MODEL_COST_PER_1K = {
    "gpt-4o": 0.005,
    "gpt-4o-mini": 0.00015,
    "gemini-1.5-pro": 0.0035,
    "gemini-1.5-flash": 0.000075
}


def estimate_cost(model: str, tokens: int) -> float:
    rate = MODEL_COST_PER_1K.get(model, 0)
    return (tokens / 1000.0) * rate
