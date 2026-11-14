import os
import threading
import time
import json
import hashlib
import base64
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
SERVER_LOGS = [] # Lưu log để gửi lên web

def init_user_state():
    return {
        "profit_loss": 0, "auto_bet": False, "win_streak": 0, "total_win": 0, "total_lose": 0, 
        "base_bet": 10000, "current_bet": 10000, "current_prediction": None,
        "waiting_for_result": False, "has_bet": False, "balance": 0, 
        "session_id": None, "nickname": "", "sio": None, "token": None, "history": []
    }

def save_history(data):
    try:
        with open(HISTORY_FILE, 'w', encoding='utf-8') as f: json.dump(data, f, ensure_ascii=False)
    except: pass

PERSISTED_HISTORY = {}
if os.path.exists(HISTORY_FILE):
    try:
        with open(HISTORY_FILE, 'r', encoding='utf-8') as f: PERSISTED_HISTORY = json.load(f)
    except: pass

def md5_hash(t): return hashlib.md5(t.encode()).hexdigest()

def log_server(msg):
    global SERVER_LOGS
    print(msg)
    SERVER_LOGS.append(f"[{time.strftime('%H:%M:%S')}] {msg}")
    if len(SERVER_LOGS) > 20: SERVER_LOGS.pop(0)

def login_and_get_token(username, password):
    pw = md5_hash(password)
    headers = {"User-Agent": "Mozilla/5.0", "Origin": "https://tele68.com"}
    url = f"https://apifo88daigia.tele68.com/api?c=3&un={username}&pw={pw}&cp=R&cl=R&pf=web&at="
    try:
        log_server(f"Đang gọi API cho: {username}")
        r = requests.get(url, headers=headers, timeout=15) # Giảm timeout tránh treo Render
        data = r.json()
        
        if not data.get("success"): 
            return {"_error": "Sai tài khoản hoặc mật khẩu!"}
            
        sk = data["sessionKey"]; sk += "=" * ((4 - len(sk) % 4) % 4)
        nickname = json.loads(base64.b64decode(sk).decode()).get("nickname")
        log_server(f"Lấy token thành công: {nickname}")
        
        r2 = requests.post("https://wlb.tele68.com/v1/lobby/auth/login?cp=R&cl=R&pf=web&at=", 
                           headers=headers, json={"nickName": nickname, "accessToken": data["accessToken"]}, timeout=15)
        lobby = r2.json(); token = lobby.get("token")
        if not token: return {"_error": "Lỗi lấy token Lobby."}
        
        return {"token": token, "nickname": nickname, "money": lobby.get("remoteLoginResp", {}).get("money", 0)}
        
    except requests.exceptions.Timeout:
        return {"_error": "Mạng Render gọi sang Game bị Timeout (Quá 15s)!"}
    except Exception as e:
        return {"_error": f"Lỗi API: {str(e)}"}

def make_prediction():
    if len(GLOBAL_HISTORY) < 10: return random.choice(["TAI", "XIU"])
    rs = "".join(["T" if x == "TAI" else "X" for x in GLOBAL_HISTORY])
    last = GLOBAL_HISTORY[-1]
    opp = "XIU" if last == "TAI" else "TAI"
    score = {"TAI": 0, "XIU": 0}
    score[last] += 1.2
    score[opp if rs[-3:] in ["TTT", "XXX"] else last] += 1.5
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
.app { width: 100%; max-width: 450px; }
.hidden { display: none !important; }
.card { background: #fff; border-radius: 16px; padding: 20px; box-shadow: 0 4px 15px rgba(0,0,0,0.05); margin-bottom: 16px; }
.header { text-align: center; margin-bottom: 20px; }
.header h1 { color: #4f46e5; font-size: 22px; font-weight: 800; }
.header p { color: #64748b; font-size: 13px; }
.input-group { margin-bottom: 15px; }
.input-group label { display: block; font-size: 11px; font-weight: 700; color: #64748b; text-transform: uppercase; margin-bottom: 6px; }
input { width: 100%; padding: 12px; border-radius: 10px; border: 1px solid #e2e8f0; background: #f8fafc; font-size: 15px; outline: none; }
input:focus { border-color: #6366f1; background: #fff; }
button { width: 100%; padding: 14px; border-radius: 10px; border: none; background: linear-gradient(90deg, #6366f1, #8b5cf6); color: #fff; font-size: 15px; font-weight: 700; cursor: pointer; }
button:disabled { opacity: 0.5; }
.msg { text-align: center; font-size: 13px; margin-top: 10px; min-height: 20px; }
.log-box { margin-top: 15px; background: #0f172a; color: #38bdf8; padding: 10px; border-radius: 8px; font-family: monospace; font-size: 11px; display: none; max-height: 120px; overflow-y: auto; }
.topbar { display: flex; justify-content: space-between; align-items: center; }
.bal { font-size: 18px; font-weight: 800; color: #16a34a; }
.grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; margin-top: 15px; }
.st-item { background: #f8fafc; padding: 12px; border-radius: 10px; text-align: center; border: 1px solid #e2e8f0; }
.st-label { font-size: 10px; color: #64748b; font-weight: 700; }
.st-val { font-size: 16px; font-weight: 800; color: #4f46e5; margin-top: 4px; }
.btn-row { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 10px; }
.btn-grey { background: #f1f5f9; color: #475569; border: 1px solid #e2e8f0; }
.btn-grey.active { background: #fef3c7; color: #d97706; border-color: #fde68a; }
.history-item { display: flex; justify-content: space-between; padding: 10px; border-radius: 8px; margin-bottom: 6px; font-size: 13px; border: 1px solid #e2e8f0; }
.history-item.win { background: #f0fdf4; color: #16a34a; }
.history-item.lose { background: #fef2f2; color: #dc2626; }
</style>
</head>
<body>
<div class="app">
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
      <div id="server-log" class="log-box"></div>
    </div>
  </section>

  <section id="dashboard" class="hidden">
    <div class="card">
      <div class="topbar">
        <div>
          <b id="nickname" style="font-size:16px;">-</b>
        </div>
        <div style="text-align:right;">
          <div style="font-size:11px; color:#64748b;">SỐ DƯ</div>
          <div class="bal">💰 <span id="balance">0</span></div>
        </div>
      </div>
      <div class="grid">
        <div class="st-item"><div class="st-label">AI Dự đoán</div><div class="st-val" id="prediction">--</div></div>
        <div class="st-item"><div class="st-label">Lãi / Lỗ</div><div class="st-val" id="pl">0</div></div>
        <div class="st-item"><div class="st-label">Thắng / Thua</div><div class="st-val" id="win-lose">0 / 0</div></div>
        <div class="st-item"><div class="st-label">Chuỗi thắng</div><div class="st-val" id="streak">0</div></div>
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
  </section>
</div>

<script>
const socket = io();
let autoOn = false;
const $ = id => document.getElementById(id);
function fmt(n) { return (n || 0).toLocaleString('vi-VN'); }

$('btn-login').onclick = async () => {
  const un = $('username').value.trim();
  const pw = $('password').value.trim();
  const msg = $('login-msg');
  const logBox = $('server-log');
  
  if (!un || !pw) { msg.style.color = '#ef4444'; msg.textContent = 'Vui lòng nhập đủ thông tin!'; return; }
  
  msg.style.color = '#d97706'; msg.textContent = '⏳ Đang kết nối (Chờ 20s)...';
  $('btn-login').disabled = true;
  logBox.style.display = 'block';
  logBox.innerHTML = 'Đang gửi yêu cầu đến Render...';
  
  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 20000); // 20s Timeout
    
    const r = await fetch('/api/login', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({username: un, password: pw}),
      signal: controller.signal
    });
    clearTimeout(timeoutId);
    
    // Nếu Render trả về lỗi 502, 504 (HTML)
    if (!r.ok) {
        const text = await r.text();
        throw new Error(`Render báo lỗi ${r.status}. Hãy thử lại!`);
    }

    const j = await r.json();
    
    if (!j.ok) {
      msg.style.color = '#ef4444'; msg.textContent = '❌ ' + j.msg;
      $('btn-login').disabled = false;
      logBox.innerHTML += `<br>Lỗi: ${j.msg}`;
      return;
    }
    
    // Đăng nhập thành công
    $('login-panel').style.opacity = '0';
    setTimeout(() => {
        $('login-panel').classList.add('hidden');
        $('dashboard').classList.remove('hidden');
    }, 300);

    $('nickname').textContent = j.nickname;
    $('balance').textContent = fmt(j.money);
    socket.emit('start_bot', {token: j.token, nickname: j.nickname, money: j.money});
    
  } catch (e) {
    $('btn-login').disabled = false;
    msg.style.color = '#ef4444';
    
    if (e.name === 'AbortError') {
        msg.textContent = '❌ Timeout 20s! Render quá tải.';
        logBox.innerHTML += `<br>Lỗi: Fetch bị hủy do quá 20s.`;
    } else {
        msg.textContent = '❌ ' + e.message;
        logBox.innerHTML += `<br>Lỗi: ${e.message}`;
    }
  }
};

$('btn-autobet').onclick = () => {
  autoOn = !autoOn;
  socket.emit('set_autobet', {on: autoOn, base_bet: parseInt($('base-bet').value) || 10000});
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
  const p = d.prediction;
  $('prediction').textContent = p === 'TAI' ? '🔵 TÀI' : (p === 'XIU' ? '🔴 XỈU' : '...');
  $('prediction').style.color = p === 'TAI' ? '#3b82f6' : '#ef4444';
});
socket.on('result', d => { 
  $('pl').textContent = fmt(d.profit_loss); 
  $('pl').style.color = d.profit_loss >= 0 ? '#16a34a' : '#dc2626';
  $('streak').textContent = d.win_streak; 
  $('balance').textContent = fmt(d.balance); 
  $('win-lose').textContent = d.total_win + ' / ' + d.total_lose;
  if(d.entry) prependHistory(d.entry); 
});

function renderHistory(list) { 
  const el = $('history-list'); 
  if(!list || list.length === 0) { el.innerHTML = '<div style="text-align:center; color:#94a3b8; padding:10px;">Chưa có dữ liệu</div>'; return; } 
  el.innerHTML = list.slice().reverse().map(html).join(''); 
}
function prependHistory(e) { 
  const el = $('history-list'); 
  if(el.innerHTML.includes('Chưa có')) el.innerHTML = ''; 
  el.insertAdjacentHTML('afterbegin', html(e)); 
}
function html(h) { 
  const w = h.outcome === 'WIN'; 
  return `<div class="history-item ${w?'win':'lose'}"><div>Phiên #${h.session} - ${h.prediction}</div><div><b>${h.profit>0?'+':''}${fmt(h.profit)}</b></div></div>`; 
}
</script>
</body>
</html>
'''

@app.route('/')
def index(): return render_template_string(HTML_TEMPLATE)

@app.route('/api/login', methods=['POST'])
def api_login():
    try:
        data = request.json or {}
        res = login_and_get_token(data.get('username','').strip(), data.get('password','').strip())
        if "_error" in res: 
            return jsonify({"ok": False, "msg": res["_error"]})
        return jsonify({"ok": True, "nickname": res.get("nickname"), "money": int(res.get("money",0)), "token": res["token"]})
    except Exception as e:
        log_server(f"Lỗi API: {str(e)}")
        return jsonify({"ok": False, "msg": f"Lỗi Server Web: {str(e)}"})

@socketio.on('connect')
def on_connect(): WEB_USERS[request.sid] = init_user_state()

@socketio.on('start_bot')
def on_start_bot(data):
    u = WEB_USERS.get(request.sid)
    if not u: return
    u["token"] = data['token']; u["nickname"] = data['nickname']; u["balance"] = int(data['money'])
    if u["nickname"] in PERSISTED_HISTORY:
        u["history"] = PERSISTED_HISTORY[u["nickname"]]
        u["total_win"] = sum(1 for h in u["history"] if h.get("outcome")=="WIN")
        u["total_lose"] = sum(1 for h in u["history"] if h.get("outcome")=="LOSE")
        u["profit_loss"] = sum(h.get("profit",0) for h in u["history"])
    emit('user_info', {'nickname':u["nickname"],'balance':u["balance"],'history':u["history"][-50:],'total_win':u["total_win"],'total_lose':u["total_lose"],'profit_loss':u["profit_loss"]})
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
            if u["current_prediction"] == result:
                profit_delta = int(u["current_bet"]*0.98); u["profit_loss"] += profit_delta; u["win_streak"] += 1; u["total_win"] += 1; bet_result = "WIN"
            else:
                profit_delta = -u["current_bet"]; u["profit_loss"] += profit_delta; u["win_streak"] = 0; u["total_lose"] += 1; bet_result = "LOSE"
            u["waiting_for_result"] = False
            entry = {"session":u["session_id"],"prediction":u["current_prediction"],"result":result,"profit":profit_delta,"outcome":bet_result}
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
