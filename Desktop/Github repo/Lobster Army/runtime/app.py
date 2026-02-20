from flask import Flask, jsonify
from runtime.cron_tick import handle_tick

def create_app() -> Flask:
    app = Flask(__name__)

    @app.get("/health")
    def health():
        return jsonify({"status": "ok", "service": "runtime", "version": "1.0.9"})

    @app.post("/cron/tick")
    def cron_tick():
        return handle_tick()

    return app

app = create_app()
