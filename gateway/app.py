from flask import Flask
from gateway.routes import register_routes

def create_app() -> Flask:
    app = Flask(__name__)
    register_routes(app)
    return app

app = create_app()
