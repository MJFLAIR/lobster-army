from flask import Flask, request, jsonify
from gateway.discord_verify import verify_discord_interaction
from gateway.outbound import post_async_ack
from gateway.ide_relay import verify_ide_relay
from workflows.storage.db import DB
from tools.input_sanitizer import InputSanitizer

def register_routes(app: Flask) -> None:
    @app.get("/health")
    def health():
        return jsonify({"status": "ok", "service": "gateway", "version": "1.0.9"})

    @app.post("/discord/interactions")
    def discord_interactions():
        if not verify_discord_interaction(request):
            return jsonify({"error": "invalid signature"}), 401

        payload = request.get_json(force=True, silent=False)

        # Discord ping
        if payload.get("type") == 1:
            return jsonify({"type": 1})

        cmd = InputSanitizer.normalize_discord_payload(payload)
        task_id = DB.create_task_from_command(cmd, source="discord_slash")
        DB.enqueue_task(task_id)
        return post_async_ack(cmd, task_id)

    @app.post("/discord/webhook")
    def discord_webhook_ingress():
        token = request.headers.get("X-Webhook-Token", "")
        if not InputSanitizer.verify_shared_token(token):
            return jsonify({"error": "unauthorized"}), 401

        payload = request.get_json(force=True, silent=True) or {}
        cmd = InputSanitizer.normalize_webhook_payload(payload)

        task_id = DB.create_task_from_command(cmd, source="discord_webhook")
        DB.enqueue_task(task_id)
        return jsonify({"ok": True, "task_id": task_id})

    @app.post("/ide/relay")
    def ide_relay():
        if not verify_ide_relay(request):
            return jsonify({"error": "unauthorized"}), 401

        payload = request.get_json(force=True, silent=False)
        cmd = InputSanitizer.normalize_ide_payload(payload)

        task_id = DB.create_task_from_command(cmd, source="ide_chat")
        DB.enqueue_task(task_id)
        return jsonify({"ok": True, "task_id": task_id})
