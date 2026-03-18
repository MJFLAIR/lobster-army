# Gemini Auth Diagnostic

This diagnostic mode logs which Gemini backend is being used without printing any secrets.

## How to enable

Set the following environment variables for the runtime:

- `DIAG_GEMINI=1`
- `LLM_MODE=real`
- `LLM_PROVIDER=gemini`
- `LLM_MODEL=gemini-1.5-flash` (or your desired Gemini model)

When enabled, the service will log a line like:

```
[GEMINI_DIAG] library=google-generativeai endpoint=generativelanguage.googleapis.com auth_mode=adc model=gemini-1.5-flash
```

Notes:
- `auth_mode=api_key` means `GEMINI_API_KEY` is present.
- `auth_mode=adc` means Application Default Credentials are being used.
- No credentials are printed.
