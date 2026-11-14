import eventlet
eventlet.monkey_patch()

import os, threading, time, json
from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit
import socketio as sio_client
from bot_engine import (login_and_get_token, make_prediction, update_global_weights,
                        GLOBAL_HISTORY, GLOBAL_AI_WEIGHTS)

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'change-me-please')
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet',
                    ping_timeout=60, ping_interval=25)

WEB_USERS = {}
HISTORY_FILE = "bet_history.json"

def init_user_state():
    return {
        "profit_loss": 0, "auto_bet": False, "x2_mode": False,
        "win_streak": 0, "lose_streak": 0,
        "total_win": 0, "total_lose": 0, "total_sessions": 0,
        "base_bet": 10000, "current_bet": 10000,
        "target_profit": None, "current_prediction": None,
        "waiting_for_result": False, "has_bet": False,
        "balance": 0, "last_preds": {}, "session_id": None,
        "nickname": "", "username": "", "sio": None, "token": None,
        "history": []
    }

def load_history():
    try:
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except: pass
    return {}

def save_history(data):
    try:
        with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("Save history error:", e)

PERSISTED_HISTORY = load_history()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/login', methods=['POST'])
def api_login():
    try:
        data = request.get_json(force=True, silent=True) or {}
        username = (data.get('username') or '').strip()
        password = (data.get('password') or '').strip()
        if not username or not password:
            return jsonify({"ok": False, "msg": "Thiếu tài khoản hoặc mật khẩu"})

        print(f"[LOGIN] Trying: {username}")
        res = login_and_get_token(username, password)
        print(f"[LOGIN] Result keys: {list(res.keys())}")

        if "_error" in res:
            return jsonify({"ok": False, "msg": res["_error"]})

        if "token" not in res or not res["token"]:
            return jsonify({"ok": False, "msg": "API không trả token"})

        return jsonify({
            "ok": True,
            "nickname": res.get("nickname") or username,
            "money": int(res.get("money", 0)),
            "token": res["token"],
            "username": username
        })
    except Exception as e:
        print(f"[LOGIN ERROR] {e}")
        return jsonify({"ok": False, "msg": f"Server error: {str(e)}"})

@app.route('/api/health')
def health():
    return jsonify({"ok": True, "time": time.time()})

# ==========================================
@socketio.on('connect')
def on_connect():
    WEB_USERS[request.sid] = init_user_state()
    print(f"[+] Client: {request.sid}")

@socketio.on('disconnect')
def on_disconnect():
    u = WEB_USERS.pop(request.sid, None)
    if u:
        if u.get("sio"):
            try: u["sio"].disconnect()
            except: pass
        if u.get("nickname"):
            PERSISTED_HISTORY[u["nickname"]] = u["history"]
            save_history(PERSISTED_HISTORY)

@socketio.on('start_bot')
def on_start_bot(data):
    u = WEB_USERS.get(request.sid)
    if not u: return
    token = data.get('token')
    nickname = data.get('nickname', 'User')
    username = data.get('username', '')
    if not token: return emit('log', {'msg': '❌ Thiếu token'})

    u["token"] = token
    u["nickname"] = nickname
    u["username"] = username
    u["balance"] = int(data.get('money', 0))

    if nickname in PERSISTED_HISTORY:
        u["history"] = PERSISTED_HISTORY[nickname]
        u["total_win"] = sum(1 for h in u["history"] if h.get("outcome") == "WIN")
        u["total_lose"] = sum(1 for h in u["history"] if h.get("outcome") == "LOSE")
        u["total_sessions"] = len(u["history"])
        u["profit_loss"] = sum(h.get("profit", 0) for h in u["history"])

    emit('user_info', {
        'nickname': nickname,
        'username': username,
        'balance': u["balance"],
        'history': u["history"][-50:],
        'total_win': u["total_win"],
        'total_lose': u["total_lose"],
        'total_sessions': u["total_sessions"],
        'profit_loss': u["profit_loss"]
    })

    threading.Thread(target=_run_ws, args=(request.sid, token), daemon=True).start()

def _persist_user(u):
    if u.get("nickname"):
        PERSISTED_HISTORY[u["nickname"]] = u["history"]
        save_history(PERSISTED_HISTORY)

def _run_ws(sid, token):
    cli = sio_client.Client(reconnection=True, logger=False, engineio_logger=False)

    @cli.event(namespace='/txmd5')
    def connect():
        socketio.emit('log', {'msg': '🟢 Đã kết nối API Game!'}, to=sid)

    @cli.on('new-session', namespace='/txmd5')
    def on_new_session(data):
        u = WEB_USERS.get(sid)
        if not u: return
        u["session_id"] = data.get('id','N/A')
        u["has_bet"] = False

        if u["auto_bet"] and u["target_profit"] and u["profit_loss"] >= u["target_profit"]:
            u["auto_bet"] = False
            socketio.emit('log', {'msg': f'🏆 ĐẠT TARGET! Lãi: {u["profit_loss"]:,} Win. Auto OFF.'}, to=sid)
            socketio.emit('autobet_ack', {'on': False, 'base_bet': u["base_bet"]}, to=sid)

        pred = None
        u["last_preds"] = {}
        if len(GLOBAL_HISTORY) >= 10:
            pred = make_prediction(last_preds_holder=u["last_preds"])
        u["current_prediction"] = pred

        if u["x2_mode"] and u["win_streak"] >= 1:
            u["current_bet"] = u["base_bet"] * (2 ** min(u["win_streak"], 3))
        else:
            u["current_bet"] = u["base_bet"]

        socketio.emit('new_session', {
            'session': u["session_id"], 'prediction': pred,
            'bet': u["current_bet"], 'auto': u["auto_bet"],
            'history_len': len(GLOBAL_HISTORY)
        }, to=sid)

    @cli.on('tick-update', namespace='/txmd5')
    def on_tick(data):
        u = WEB_USERS.get(sid)
        if not u: return
        if (data.get('state') == 'BETTING' and u["auto_bet"]
                and u["current_prediction"] and not u["has_bet"]):
            cli.emit('bet', {"type": u["current_prediction"], "amount": u["current_bet"]}, namespace='/txmd5')
            u["has_bet"] = True
            u["waiting_for_result"] = True
            socketio.emit('bet_placed', {
                'amount': u["current_bet"], 'type': u["current_prediction"]
            }, to=sid)

    @cli.on('bet-result', namespace='/txmd5')
    def on_bet_result(data):
        u = WEB_USERS.get(sid)
        if u and "postBalance" in data:
            u["balance"] = data["postBalance"]
            socketio.emit('balance', {'balance': u["balance"]}, to=sid)

    @cli.on('session-result', namespace='/txmd5')
    def on_result(data):
        u = WEB_USERS.get(sid)
        if not u: return
        result = data.get('resultTruyenThong')
        dices = data.get('dices', [0,0,0])

        if result in ["TAI","XIU"]:
            GLOBAL_HISTORY.append(result)
            if len(GLOBAL_HISTORY) > 2000: GLOBAL_HISTORY.pop(0)
            update_global_weights(result, u.get("last_preds", {}))
            u["last_preds"] = {}

        bet_result = None
        profit_delta = 0
        if u["waiting_for_result"] and u["current_prediction"]:
            u["total_sessions"] += 1
            if u["current_prediction"] == result:
                profit_delta = int(u["current_bet"] * 0.98)
                u["profit_loss"] += profit_delta
                u["win_streak"] += 1
                u["lose_streak"] = 0
                u["total_win"] += 1
                bet_result = "WIN"
            else:
                profit_delta = -u["current_bet"]
                u["profit_loss"] += profit_delta
                u["lose_streak"] += 1
                u["win_streak"] = 0
                u["total_lose"] += 1
                bet_result = "LOSE"
            u["waiting_for_result"] = False

            entry = {
                "session": u["session_id"],
                "prediction": u["current_prediction"],
                "result": result,
                "bet": u["current_bet"],
                "profit": profit_delta,
                "outcome": bet_result,
                "dices": dices,
                "time": time.strftime("%H:%M:%S %d/%m")
            }
            u["history"].append(entry)
            if len(u["history"]) > 500:
                u["history"] = u["history"][-500:]
            _persist_user(u)

        socketio.emit('result', {
            'result': result, 'dices': dices,
            'profit_loss': u["profit_loss"],
            'win_streak': u["win_streak"], 'lose_streak': u["lose_streak"],
            'balance': u["balance"], 'bet_result': bet_result,
            'profit_delta': profit_delta,
            'total_win': u["total_win"], 'total_lose': u["total_lose"],
            'total_sessions': u["total_sessions"],
            'entry': u["history"][-1] if bet_result else None
        }, to=sid)

    try:
        cli.connect('https://wtxmd52.tele68.com', socketio_path='txmd5/',
                    namespaces=['/txmd5'], transports=['websocket'],
                    auth={"token": token}, headers={"User-Agent":"Mozilla/5.0"})
        u = WEB_USERS.get(sid)
        if u: u["sio"] = cli
        cli.wait()
    except Exception as e:
        socketio.emit('log', {'msg': f'⚠️ Lỗi kết nối: {e}'}, to=sid)

# ==========================================
@socketio.on('set_autobet')
def set_autobet(d):
    u = WEB_USERS.get(request.sid)
    if not u: return
    u["auto_bet"] = bool(d.get('on'))
    if d.get('base_bet'): u["base_bet"] = int(d['base_bet'])
    emit('autobet_ack', {'on': u["auto_bet"], 'base_bet': u["base_bet"]})

@socketio.on('set_x2')
def set_x2(d):
    u = WEB_USERS.get(request.sid)
    if not u: return
    u["x2_mode"] = bool(d.get('on'))
    emit('x2_ack', {'on': u["x2_mode"]})

@socketio.on('set_target')
def set_target(d):
    u = WEB_USERS.get(request.sid)
    if not u: return
    try:
        u["target_profit"] = int(d.get('target'))
        emit('target_ack', {'target': u["target_profit"]})
    except: pass

@socketio.on('get_history')
def get_history():
    u = WEB_USERS.get(request.sid)
    if not u: return
    emit('history_data', {
        'history': u["history"][-100:],
        'total_win': u["total_win"], 'total_lose': u["total_lose"],
        'total_sessions': u["total_sessions"], 'profit_loss': u["profit_loss"]
    })

@socketio.on('reset_history')
def reset_history():
    u = WEB_USERS.get(request.sid)
    if not u: return
    u["history"] = []
    u["total_win"] = 0; u["total_lose"] = 0; u["total_sessions"] = 0
    u["profit_loss"] = 0; u["win_streak"] = 0; u["lose_streak"] = 0
    if u["nickname"]:
        PERSISTED_HISTORY[u["nickname"]] = []
        save_history(PERSISTED_HISTORY)
    emit('history_reset_ack', {'ok': True})
    emit('history_data', {
        'history': [], 'total_win': 0, 'total_lose': 0,
        'total_sessions': 0, 'profit_loss': 0
    })

@socketio.on('get_weights')
def get_weights():
    top = sorted(GLOBAL_AI_WEIGHTS.items(), key=lambda x: -x[1])[:15]
    emit('weights', {'list': top})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    socketio.run(app, host="0.0.0.0", port=port)
