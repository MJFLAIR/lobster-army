import requests
from urllib.parse import urlparse

ALLOWED_DOMAINS = [
    "api.github.com",
    "raw.githubusercontent.com",
    "api.openai.com",
    "api.anthropic.com"
]

MAX_RESPONSE_SIZE = 100_000  # 100KB

def fetch_url(url: str, timeout: int = 10) -> dict:
    try:
        print(f"[FETCH_START] url={url}")
        
        parsed = urlparse(url)
        domain = parsed.netloc

        # Whitelist check
        if domain not in ALLOWED_DOMAINS:
            error_msg = f"Domain not allowed: {domain}"
            print(f"[FETCH_FAILED] url={url} error={error_msg}")
            return {
                "status": "failed",
                "error": error_msg,
                "url": url
            }

        # Block internal access
        if "127.0.0.1" in url or "localhost" in url or "169.254" in url:
            error_msg = "Internal network access blocked"
            print(f"[FETCH_FAILED] url={url} error={error_msg}")
            return {
                "status": "failed",
                "error": error_msg,
                "url": url
            }

        response = requests.get(url, timeout=timeout, stream=True)

        if response.status_code >= 400:
            return {
                "status": "failed",
                "error": f"HTTP error {response.status_code}",
                "url": url
            }

        content = ""

        for chunk in response.iter_content(chunk_size=1024):
            if chunk:
                content += chunk.decode("utf-8", errors="ignore")

                if len(content) > MAX_RESPONSE_SIZE:
                    print(f"[FETCH_FAILED] url={url} error=size_exceeded")
                    return {
                        "status": "failed",
                        "error": "Response size exceeded 100KB limit",
                        "url": url
                    }

        print(f"[FETCH_SUCCESS] url={url}")
        return {
            "status": "success",
            "status_code": response.status_code,
            "content": content,
            "url": url
        }

    except Exception as e:
        print(f"[FETCH_FAILED] url={url} error={str(e)}")
        return {
            "status": "failed",
            "error": str(e),
            "url": url
        }
