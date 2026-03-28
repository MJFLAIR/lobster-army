import hmac
import hashlib
import os

class GitHubWebhook:
    @staticmethod
    def verify_signature(payload_body: bytes, signature_header: str) -> bool:
        """
        Verify that the payload was sent from GitHub by validating the SHA256 signature.
        """
        if not signature_header:
            return False

        secret = os.environ.get("GITHUB_WEBHOOK_SECRET")
        if not secret:
            # If no secret is configured, we cannot verify. Fail safe.
            return False

        # GitHub sends the signature as 'sha256=...'
        if not signature_header.startswith("sha256="):
            return False

        signature = signature_header.split("sha256=", 1)[1]

        # Calculate expected signature
        hmac_gen = hmac.new(
            secret.encode('utf-8'),
            payload_body,
            hashlib.sha256
        )
        expected_signature = hmac_gen.hexdigest()

        # Use hmac.compare_digest to prevent timing attacks
        return hmac.compare_digest(expected_signature, signature)
