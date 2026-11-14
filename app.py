import os
import threading
import time
import json
import hashlib
import base64
import math
import random
import requests
import socketio as sio_client
from flask import Flask, render_template_string, request, jsonify
from flask_socketio import SocketIO, emit
from gevent import monkey
monkey.patch_all()

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent')

GLOBAL_HISTORY = []
WEB_USERS = {}
HISTORY_FILE = "bet_history.json"

def init_user_state():
    return {
        "profit_loss": 0, "auto_bet": False, "x2_mode": False,
        "win_streak": 0, "total_win": 0, "total_lose": 0, "total_sessions": 0,
        "base_bet": 10000, "current_bet": 10000, "current_prediction": None,
        "waiting_for_result": False, "has_bet": False, "balance": 0, 
        "session_id": None, "nickname": "", "username": "", "sio": None, "token": None, "history": []
    }

def load_history():
    try:
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, 'r', encoding='utf-8') as f: return json.load(f)
    except: pass
    return {}

def save_history(data):
    try:
        with open(HISTORY_FILE, 'w', encoding='utf-8') as f: json.dump(data, f, ensure_ascii=False)
    except: pass

PERSISTED_HISTORY = load_history()

def md5_hash(t): return hashlib.md5(t.encode()).hexdigest()

def login_and_get_token(username, password):
    pw = md5_hash(password)
    headers = {"User-Agent": "Mozilla/5.0", "Origin": "https://tele68.com"}
    url = f"https://apifo88daigia.tele68.com/api?c=3&un={username}&pw={pw}&cp=R&cl=R&pf=web&at="
    try:
        r = requests.get(url, headers=headers, timeout=30)
        data = r.json()
        if not data.get("success"): return {"_error": "Sai tài khoản hoặc mật khẩu!"}
        sk = data["sessionKey"]; sk += "=" * ((4 - len(sk) % 4) % 4)
        nickname = json.loads(base64.b64decode(sk).decode()).get("nickname")
        r2 = requests.post("https://wlb.tele68.com/v1/lobby/auth/login?cp=R&cl=R&pf=web&at=", 
                           headers=headers, json={"nickName": nickname, "accessToken": data["accessToken"]}, timeout=30)
        lobby = r2.json(); token = lobby.get("token")
        if not token: return {"_error": "Lỗi lấy token Lobby."}
        return {"token": token, "nickname": nickname, "money": lobby.get("remoteLoginResp", {}).get("money", 0)}
    except requests.exceptions.Timeout:
        return {"_error": "Timeout 30s. Vui lòng thử lại!"}
    except Exception as e:
        return {"_error": f"Lỗi: {str(e)}"}

def make_prediction():
    if len(GLOBAL_HISTORY) < 10: return random.choice(["TAI", "XIU"])
    rs = "".join(["T" if x == "TAI" else "X" for x in GLOBAL_HISTORY])
    last = GLOBAL_HISTORY[-1]
    opp = "XIU" if last == "TAI" else "TAI"
    
    score = {"TAI": 0, "XIU": 0}
    score["TAI" if last == "TAI" else "XIU"] += 1.2
    score[opp if rs[-3:] in ["TTT", "XXX"] else last] += 1.5
    score[opp if len(rs) >= 5 and rs[-5:] in ["TTTXT", "XXXTX"] else last] += 1.3
    score[opp if GLOBAL_HISTORY[-20:].count("TAI") > 14 else ("TAI" if GLOBAL_HISTORY[-20:].count("TAI") < 6 else last)] += 1.1
    
    return "TAI" if score["TAI"] > score["XIU"] else "XIU"

HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0">
<title>TOOL AUTO LC79</title>
<script src="https://cdn.socket.io/4.7.5/socket.io.min.js"></script>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, sans-serif; }
body { min-height: 100vh; background: #eef2ff; color: #1e293b; padding: 16px; display: flex; justify-content: center; }
.app { width: 100%; max-width: 450px; transition: 0.3s; }
.hidden { display: none !important; }
.card { background: #fff; border-radius: 16px; padding: 20px; box-shadow: 0 4px 15px rgba(0,0,0,0.05); margin-bottom: 16px; }
.header { text-align: center; margin-bottom: 20px; }
.header h1 { color: #4f46e5; font-size: 22px; font-weight: 800; }
.header p { color: #64748b; font-size: 13px; }
.input-group { margin-bottom: 15px; }
.input-group label { display: block; font-size: 11px; font-weight: 700; color: #64748b; text-transform: uppercase; margin-bottom: 6px; }
input { width: 100%; padding: 12px; border-radius: 10px; border: 1px solid #e2e8f0; background: #f8fafc; font-size: 15px; outline: none; transition: 0.2s; }
input:focus { border-color: #6366f1; background: #fff; box-shadow: 0 0 0 3px rgba(99,102,241,0.1); }
button { width: 100%; padding: 14px; border-radius: 10px; border: none; background: linear-gradient(90deg, #6366f1, #8b5cf6); color: #fff; font-size: 15px; font-weight: 700; cursor: pointer; transition: 0.2s; }
button:hover { opacity: 0.9; }
.btn-row { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 10px; }
.btn-grey { background: #f1f5f9; color: #475569; border: 1px solid #e2e8f0; }
.btn-grey.active { background: #fef3c7; color: #d97706; border-color: #fde68a; }
.msg { text-align: center; font-size: 13px; margin-top: 10px; min-height: 20px; }
.topbar { display: flex; justify-content: space-between; align-items: center; }
.bal { font-size: 18px; font-weight: 800; color: #16a34a; }
.grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; margin-top: 15px; }
.st-item { background: #f8fafc; padding: 12px; border-radius: 10px; text-align: center; border: 1px solid #e2e8f0; }
.st-label { font-size: 10px; color: #64748b; font-weight: 700; text-transform: uppercase; }
.st-val { font-size: 16px; font-weight: 800; color: #4f46e5; margin-top: 4px; }
.history-item { display: flex; justify-content: space-between; padding: 10px; border-radius: 8px; margin-bottom: 6px; font-size: 13px; border: 1px solid #e2e8f0; }
.history-item.win { background: #f0fdf4; border-color: #bbf7d0; color: #16a34a; }
.history-item.lose { background: #fef2f2; border-color: #fecaca; color: #dc2626; }
.log { background: #0f172a; color: #38bdf8; padding: 10px; border-radius: 8px; height: 120px; overflow-y: auto; font-family: monospace; font-size: 12px; }
</style>
</head>
<body>
<div class="app">
  <!-- FORM ĐĂNG NHẬP -->
  <section id="login-panel">
    <div class="header">
      <h1>TOOL AUTO LC79</h1>
      <p>Hệ thống phân tích cầu Tài Xỉu</p>
    </div>
    <div class="card">
      <div class="input-group"><label>TÀI KHOẢN</label><input id="username" placeholder="username"></div>
      <div class="input-group"><label>MẬT KHẨU</label><input id="password" type="password" placeholder="••••••••"></div>
      <div class="input-group"><label>KEY BẢN QUYỀN</label><input id="license-key" placeholder="KEY-XXXXX" value="VIP-PRO"></div>
      <button id="btn-login">ĐĂNG NHẬP NGAY</button>
      <p id="login-msg" class="msg"></p>
    </div>
  </section>

  <!-- BẢNG ĐIỀU KHIỂN -->
  <section id="dashboard" class="hidden">
    <div class="card">
      <div class="topbar">
        <div>
          <b id="nickname" style="font-size:16px;">-</b>
          <div id="uname-sub" style="font-size:12px; color:#64748b;">-</div>
        </div>
        <div style="text-align:right;">
          <div style="font-size:11px; color:#64748b;">SỐ DƯ</div>
          <div class="bal">💰 <span id="balance">0</span></div>
        </div>
      </div>
      <div class="grid">
        <div class="st-item"><div class="st-label">AI Dự đoán</div><div class="st-val" id="prediction">--</div></div>
        <div class="st-item"><div class="st-label">Lãi / Lỗ</div><div class="st-val" id="pl" style="color:#16a34a;">0</div></div>
        <div class="st-item"><div class="st-label">Thắng / Thua</div><div class="st-val" id="win-lose">0 / 0</div></div>
        <div class="st-item"><div class="st-label">Chuỗi thắng</div><div class="st-val" id="streak" style="color:#d97706;">0</div></div>
      </div>
    </div>

    <div class="card">
      <div class="input-group"><label>Tiền cược (Win)</label><input id="base-bet" type="number" value="10000"></div>
      <div class="btn-row">
        <button id="btn-autobet" class="btn-grey">▶ Bật Auto</button>
        <button id="btn-stop" style="background:#ef4444;">⏹ Dừng Bot</button>
      </div>
    </div>

    <div class="card">
      <div style="display:flex; justify-content:space-between; margin-bottom:10px;">
        <b style="font-size:14px;">Lịch sử gần đây</b>
        <button id="btn-reset" style="width:auto; padding:4px 10px; font-size:12px; background:#fee2e2; color:#ef4444;">Xoá</button>
      </div>
      <div id="history-list" style="max-height:200px; overflow-y:auto;">
        <div style="text-align:center; color:#94a3b8; font-size:13px; padding:10px;">Chưa có dữ liệu</div>
      </div>
    </div>

    <div class="card"><div id="log" class="log">Chờ kết nối...</div></div>
  </section>
</div>

<script>
const socket = io();
let autoOn = false;
const $ = id => document.getElementById(id);
function log(msg) { const el = $('log'); el.innerHTML += `<div>[${new Date().toLocaleTimeString()}] ${msg}</div>`; el.scrollTop = el.scrollHeight; }
function fmt(n) { return (n || 0).toLocaleString('vi-VN'); }

$('btn-login').onclick = async () => {
  const un = $('username').value.trim();
  const pw = $('password').value.trim();
  const msg = $('login-msg');
  if (!un || !pw) { msg.style.color = '#ef4444'; msg.textContent = 'Vui lòng nhập đủ thông tin!'; return; }
  
  msg.style.color = '#d97706'; msg.textContent = '⏳ Đang kết nối...';
  $('btn-login').disabled = true; $('btn-login').textContent = 'ĐANG XỬ LÝ...';
  
  try {
    const r = await fetch('/api/login', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({username: un, password: pw, key: $('license-key').value})
    });
    const j = await r.json();
    if (!j.ok) {
      msg.style.color = '#ef4444'; msg.textContent = '❌ ' + j.msg;
      $('btn-login').disabled = false; $('btn-login').textContent = 'ĐĂNG NHẬP NGAY';
      return;
    }
    
    // Chuyển màn hình mượt mà
    $('login-panel').style.opacity = '0';
    setTimeout(() => {
        $('login-panel').classList.add('hidden');
        $('dashboard').classList.remove('hidden');
    }, 300);

    $('nickname').textContent = j.nickname; $('uname-sub').textContent = '@' + j.username;
    $('balance').textContent = fmt(j.money);
    window._token = j.token; window._nickname = j.nickname; window._username = j.username;
    
    socket.emit('start_bot', {token: j.token, nickname: j.nickname, username: j.username, money: j.money});
    log('✅ Đăng nhập thành công!');
  } catch (e) {
    msg.style.color = '#ef4444'; msg.textContent = '❌ Lỗi mạng Server!';
    $('btn-login').disabled = false; $('btn-login').textContent = 'ĐĂNG NHẬP NGAY';
  }
};

$('btn-autobet').onclick = () => {
  autoOn = !autoOn;
  const b = parseInt($('base-bet').value) || 10000;
  socket.emit('set_autobet', {on: autoOn, base_bet: b});
  $('btn-autobet').classList.toggle('active', autoOn);
  $('btn-autobet').textContent = autoOn ? '⏸ Tắt Auto' : '▶ Bật Auto';
};

$('btn-stop').onclick = () => { socket.emit('set_autobet', {on: false}); location.reload(); };
$('btn-reset').onclick = () => { if(confirm('Xoá lịch sử?')) socket.emit('reset_history'); };

socket.on('user_info', d => { 
  $('balance').textContent = fmt(d.balance);
  $('win-lose').textContent = d.total_win + ' / ' + d.total_lose;
  renderHistory(d.history); 
});
socket.on('new_session', d => { 
  $('session').textContent = '#' + d.session;
  const p = d.prediction;
  $('prediction').textContent = p === 'TAI' ? '🔵 TÀI' : (p === 'XIU' ? '🔴 XỈU' : '...');
});
socket.on('result', d => { 
  $('pl').textContent = fmt(d.profit_loss); 
  $('pl').style.color = d.profit_loss >= 0 ? '#16a34a' : '#dc2626';
  $('streak').textContent = d.win_streak; 
  $('balance').textContent = fmt(d.balance); 
  $('win-lose').textContent = d.total_win + ' / ' + d.total_lose;
  if(d.entry) prependHistory(d.entry); 
});
socket.on('history_reset_ack', () => renderHistory([]));

function renderHistory(list) { 
  const el = $('history-list'); 
  if(!list || list.length === 0) { el.innerHTML = '<div style="text-align:center; color:#94a3b8; padding:10px;">Chưa có dữ liệu</div>'; return; } 
  el.innerHTML = list.slice().reverse().map(html).join(''); 
}
function prependHistory(e) { 
  const el = $('history-list'); 
  if(el.innerHTML.includes('Chưa có dữ liệu')) el.innerHTML = ''; 
  el.insertAdjacentHTML('afterbegin', html(e)); 
}
function html(h) { 
  const w = h.outcome === 'WIN'; 
  return `<div class="history-item ${w?'win':'lose'}"><div>Phiên #${h.session} - Đoán ${h.prediction}</div><div><b>${h.profit>0?'+':''}${fmt(h.profit)}</b></div></div>`; 
}
</script>
</body>
</html>
'''

@app.route('/')
def index(): return render_template_string(HTML_TEMPLATE)

@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.json or {}
    res = login_and_get_token(data.get('username','').strip(), data.get('password','').strip())
    if "_error" in res: return jsonify({"ok": False, "msg": res["_error"]})
    return jsonify({"ok": True, "nickname": res.get("nickname"), "money": int(res.get("money",0)), "token": res["token"], "username": data.get('username','')})

@socketio.on('connect')
def on_connect(): WEB_USERS[request.sid] = init_user_state()

@socketio.on('start_bot')
def on_start_bot(data):
    u = WEB_USERS.get(request.sid)
    if not u: return
    u["token"] = data['token']; u["nickname"] = data['nickname']; u["username"] = data['username']; u["balance"] = int(data['money'])
    if u["nickname"] in PERSISTED_HISTORY:
        u["history"] = PERSISTED_HISTORY[u["nickname"]]
        u["total_win"] = sum(1 for h in u["history"] if h.get("outcome")=="WIN")
        u["total_lose"] = sum(1 for h in u["history"] if h.get("outcome")=="LOSE")
        u["profit_loss"] = sum(h.get("profit",0) for h in u["history"])
    emit('user_info', {'nickname':u["nickname"],'username':u["username"],'balance':u["balance"],'history':u["history"][-50:],'total_win':u["total_win"],'total_lose':u["total_lose"],'profit_loss':u["profit_loss"]})
    threading.Thread(target=_run_ws, args=(request.sid, u["token"]), daemon=True).start()

def _run_ws(sid, token):
    cli = sio_client.Client(reconnection=True, logger=False, engineio_logger=False)
    @cli.on('new-session', namespace='/txmd5')
    def on_new_session(data):
        u = WEB_USERS.get(sid)
        if not u: return
        u["session_id"] = data.get('id','N/A'); u["has_bet"] = False
        pred = make_prediction() if len(GLOBAL_HISTORY) >= 10 else None
        u["current_prediction"] = pred
        u["current_bet"] = u["base_bet"]
        socketio.emit('new_session', {'session':u["session_id"],'prediction':pred}, to=sid)

    @cli.on('tick-update', namespace='/txmd5')
    def on_tick(data):
        u = WEB_USERS.get(sid)
        if u and data.get('state')=='BETTING' and u["auto_bet"] and u["current_prediction"] and not u["has_bet"]:
            cli.emit('bet', {"type": u["current_prediction"], "amount": u["current_bet"]}, namespace='/txmd5')
            u["has_bet"] = True; u["waiting_for_result"] = True

    @cli.on('bet-result', namespace='/txmd5')
    def on_bet_result(data):
        u = WEB_USERS.get(sid)
        if u and "postBalance" in data: u["balance"] = data["postBalance"]; socketio.emit('balance', {'balance': u["balance"]}, to=sid)

    @cli.on('session-result', namespace='/txmd5')
    def on_result(data):
        u = WEB_USERS.get(sid)
        if not u: return
        result = data.get('resultTruyenThong')
        if result in ["TAI","XIU"]:
            GLOBAL_HISTORY.append(result)
            if len(GLOBAL_HISTORY) > 2000: GLOBAL_HISTORY.pop(0)
        
        bet_result, profit_delta = None, 0
        if u["waiting_for_result"] and u["current_prediction"]:
            u["total_sessions"] += 1
            if u["current_prediction"] == result:
                profit_delta = int(u["current_bet"]*0.98); u["profit_loss"] += profit_delta; u["win_streak"] += 1; u["total_win"] += 1; bet_result = "WIN"
            else:
                profit_delta = -u["current_bet"]; u["profit_loss"] += profit_delta; u["win_streak"] = 0; u["total_lose"] += 1; bet_result = "LOSE"
            u["waiting_for_result"] = False
            entry = {"session":u["session_id"],"prediction":u["current_prediction"],"result":result,"bet":u["current_bet"],"profit":profit_delta,"outcome":bet_result}
            u["history"].append(entry); PERSISTED_HISTORY[u["nickname"]] = u["history"]; save_history(PERSISTED_HISTORY)
        
        socketio.emit('result', {'profit_loss':u["profit_loss"],'win_streak':u["win_streak"],'balance':u["balance"],'total_win':u["total_win"],'total_lose':u["total_lose"],'entry':u["history"][-1] if bet_result else None}, to=sid)

    try:
        cli.connect('https://wtxmd52.tele68.com', socketio_path='txmd5/', namespaces=['/txmd5'], transports=['websocket'], auth={"token": token}, headers={"User-Agent":"Mozilla/5.0"})
        u = WEB_USERS.get(sid)
        if u: u["sio"] = cli
        cli.wait()
    except Exception: pass

@socketio.on('set_autobet')
def set_autobet(d):
    u = WEB_USERS.get(request.sid)
    if u: u["auto_bet"] = bool(d.get('on')); u["base_bet"] = int(d.get('base_bet', 10000))

@socketio.on('reset_history')
def reset_history():
    u = WEB_USERS.get(request.sid)
    if u:
        u["history"]=[]; u["total_win"]=0; u["total_lose"]=0; u["profit_loss"]=0
        if u["nickname"]: PERSISTED_HISTORY[u["nickname"]]=[]; save_history(PERSISTED_HISTORY)
        emit('history_reset_ack', {'ok':True})

if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
