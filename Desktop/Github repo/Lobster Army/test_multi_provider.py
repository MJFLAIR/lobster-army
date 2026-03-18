import os
import json
import traceback

from tools.real_llm_client import RealLLMClient


TEST_PROMPT = 'Return JSON {"message": "hello"}'
SYSTEM_PROMPT = "You must return valid JSON only."


def run_test(provider: str, model: str):
    print("\n" + "=" * 60)
    print(f"Testing Provider: {provider}")
    print(f"Model: {model}")
    print("=" * 60)

    os.environ["LLM_MODE"] = "real"

    try:
        client = RealLLMClient(provider=provider, model=model)

        result = client.complete(
            prompt=TEST_PROMPT,
            system_prompt=SYSTEM_PROMPT
        )

        print("✅ SUCCESS")
        print("Raw Result:")
        print(json.dumps(result, indent=2))

        try:
            parsed = json.loads(result["content"])
            print("Parsed JSON:")
            print(json.dumps(parsed, indent=2))
        except Exception:
            print("⚠ Could not parse JSON content")

    except Exception as e:
        print("❌ FAILED")
        print("Error:", str(e))
        traceback.print_exc()


if __name__ == "__main__":
    # ====== OPENAI TEST ======
    run_test(
        provider="openai",
        model="gpt-4o-mini"
    )

    # ====== GEMINI TEST ======
    run_test(
        provider="gemini",
        model="gemini-1.5-flash"
    )
