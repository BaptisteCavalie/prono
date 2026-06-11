from pathlib import Path
import sys

from flask import Flask, Response, request

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import ui

app = Flask(__name__)


@app.get("/")
def home():
    body = ui.handle_request(request.args.to_dict())
    return Response(body, mimetype="text/html; charset=utf-8")


@app.get("/<path:_rest>")
def fallback(_rest: str):
    # 404 léger, comme le serveur stdlib : ne pas rejouer tout le pipeline
    # pour les favicons et les scans de bots (coût serverless inutile).
    return Response("Not found", status=404, mimetype="text/plain")


# Vercel entrypoint
handler = app
