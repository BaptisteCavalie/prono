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
    body = ui.build_page(request.args.to_dict(flat=False))
    return Response(body, content_type="text/html; charset=utf-8")


@app.get("/<path:_rest>")
def fallback(_rest: str):
    return home()


# Vercel entrypoint
handler = app
