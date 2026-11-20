# SkyBook: сервер для Railway (python server.py; PORT берётся из окружения)
# Отдаёт только index.html, models/ и vendor/ (server.py и bookings.jsonl наружу не видны).
# Покупки пишутся в bookings.jsonl (DATA_DIR можно вынести на Railway Volume).
# Необязательно: TG_TOKEN и TG_CHAT в переменных окружения — уведомление в Telegram о каждой покупке.
import os, re, json, secrets, threading, urllib.request
from flask import Flask, send_from_directory, request, jsonify

app = Flask(__name__, static_folder=None)
ROOT = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(os.environ.get("DATA_DIR", ROOT), "bookings.jsonl")
lock = threading.Lock()
SEAT = re.compile(r"^\d{1,2}[A-F]$")

def rows():
    try:
        with open(DB, encoding="utf-8") as f:
            return [json.loads(l) for l in f if l.strip()]
    except FileNotFoundError:
        return []

def notify(b):
    tok, chat = os.environ.get("TG_TOKEN"), os.environ.get("TG_CHAT")
    if not (tok and chat):
        return
    text = (f"✈ Новая покупка {b['code']}\nМесто {b['seat']} ({b['cls']}) · ${b['total']}\n"
            f"{b['name']} · {b['phone']}\n{b.get('flight','')} · {b.get('date','')}")
    try:
        req = urllib.request.Request(f"https://api.telegram.org/bot{tok}/sendMessage",
            json.dumps({"chat_id": chat, "text": text}).encode(), {"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=8)
    except Exception:
        pass

@app.route("/")
def index():
    return send_from_directory(ROOT, "index.html")

@app.route("/models/<path:p>")
def models(p):
    return send_from_directory(os.path.join(ROOT, "models"), p)

@app.route("/vendor/<path:p>")
def vendor(p):
    return send_from_directory(os.path.join(ROOT, "vendor"), p)

@app.get("/api/seats")
def seats():
    return jsonify(taken=[r["seat"] for r in rows()])

@app.post("/api/book")
def book():
    d = request.get_json(silent=True) or {}
    seat, name, phone = str(d.get("seat", "")).upper(), str(d.get("name", "")).strip()[:80], str(d.get("phone", "")).strip()[:30]
    if not SEAT.match(seat) or len(name) < 2 or len(phone) < 5:
        return jsonify(error="bad request"), 400
    with lock:
        if any(r["seat"] == seat for r in rows()):
            return jsonify(error="taken"), 409
        b = {"code": secrets.token_hex(3).upper(), "seat": seat, "cls": str(d.get("cls", ""))[:8],
             "total": int(d.get("total") or 0), "name": name, "phone": phone, "bag": str(d.get("bag", ""))[:20],
             "meal": bool(d.get("meal")), "flex": bool(d.get("flex")), "flight": str(d.get("flight", ""))[:12], "date": str(d.get("date", ""))[:20]}
        with open(DB, "a", encoding="utf-8") as f:
            f.write(json.dumps(b, ensure_ascii=False) + "\n")
    threading.Thread(target=notify, args=(b,), daemon=True).start()
    return jsonify(ok=True, code=b["code"])

@app.after_request
def cache(r):
    if r.mimetype in ("model/gltf-binary", "application/octet-stream", "image/jpeg") and request.path.startswith("/models"):
        r.headers["Cache-Control"] = "public, max-age=86400"
    return r

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
