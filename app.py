import os
import threading
import time
import json
import hashlib
import base64
import math
import random
import logging
import requests
import socketio as sio_client
from flask import Flask, render_template_string, request, jsonify
from flask_socketio import SocketIO, emit
from gevent import monkey
monkey.patch_all()

# ==========================================
# CẤU HÌNH HỆ THỐNG
# ==========================================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logging.getLogger('engineio').setLevel(logging.WARNING)
logging.getLogger('urllib3').setLevel(logging.WARNING)

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'change-me-please')
# Dùng gevent cho SocketIO
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent', ping_timeout=60, ping_interval=25)

GLOBAL_HISTORY = []
GLOBAL_AI_WEIGHTS = {k: 1.0 for k in ["trend", "pattern", "frequency", "momentum", "symmetry", "alternating", "fibonacci", "chaos", "shadow", "markov1", "markov2", "markov3", "rsi_indicator", "macd_cross", "pivot_reversal", "cluster_3", "parity", "golden_ratio", "quantum", "anti_bait", "smart_breaker", "ngram_4", "ngram_5", "elliott_wave", "contrarian", "bollinger_bands", "mean_reversion", "mirror_reflection", "martingale_trap", "poisson_prob", "harmonic_cycle", "breakout_hunter", "volume_fakeout", "time_decay", "neural_bias", "twin_peaks"]}
GLOBAL_AI_WEIGHTS["anti_bait"] = 2.0
GLOBAL_AI_WEIGHTS["smart_breaker"] = 2.0
GLOBAL_AI_WEIGHTS["contrarian"] = 2.0
GLOBAL_MODEL_STREAK = {k: 0 for k in GLOBAL_AI_WEIGHTS.keys()}

WEB_USERS = {}
HISTORY_FILE = "bet_history.json"

def init_user_state():
    return {
        "profit_loss": 0, "auto_bet": False, "x2_mode": False,
        "win_streak": 0, "lose_streak": 0, "total_win": 0, "total_lose": 0, "total_sessions": 0,
        "base_bet": 10000, "current_bet": 10000, "target_profit": None, "current_prediction": None,
        "waiting_for_result": False, "has_bet": False, "balance": 0, "last_preds": {}, 
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
        with open(HISTORY_FILE, 'w', encoding='utf-8') as f: json.dump(data, f, ensure_ascii=False, indent=2)
    except: pass

PERSISTED_HISTORY = load_history()

# ==========================================
# LOGIC API GAME (CÓ RETRY CHỐNG TIMEOUT)
# ==========================================
def md5_hash(t): return hashlib.md5(t.encode()).hexdigest()

def login_and_get_token(username, password):
    pw = md5_hash(password)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://tele68.com", "Referer": "https://tele68.com/"
    }
    
    # NẾU CÓ PROXY VIỆT NAM THÌ ĐIỀN VÀO ĐÂY (VD: "http://user:pass@ip:port")
    PROXY = None 
    proxies = {"http": PROXY, "https": PROXY} if PROXY else None

    url = f"https://apifo88daigia.tele68.com/api?c=3&un={username}&pw={pw}&cp=R&cl=R&pf=web&at="
    
    for attempt in range(3):
        try:
            # Timeout 40s để chờ Render free khởi động
            r = requests.get(url, headers=headers, timeout=40, proxies=proxies)
            r.raise_for_status()
            data = r.json()
            
            if not data.get("success"): 
                return {"_error": "Sai tài khoản hoặc mật khẩu!"}
                
            sk = data["sessionKey"]; sk += "=" * ((4 - len(sk) % 4) % 4)
            sd = json.loads(base64.b64decode(sk).decode())
            nickname = sd.get("nickname") or sd.get("nickName")
            at = data["accessToken"]
            
            r2 = requests.post("https://wlb.tele68.com/v1/lobby/auth/login?cp=R&cl=R&pf=web&at=",
                headers={"authority": "wlb.tele68.com", "content-type": "application/json", "User-Agent": headers["User-Agent"]},
                json={"nickName": nickname, "accessToken": at}, timeout=40, proxies=proxies)
                
            lobby = r2.json(); token = lobby.get("token")
            if not token: return {"_error": "Lỗi lấy token từ Lobby."}
            
            return {"token": token, "nickname": nickname, "money": lobby.get("remoteLoginResp", {}).get("money", 0)}
            
        except requests.exceptions.Timeout:
            if attempt == 2:
                return {"_error": "Server Game phản hồi quá chậm (Timeout 40s). Vui lòng thử lại!"}
            time.sleep(2)
        except Exception as e:
            return {"_error": f"Lỗi kết nối IP: {str(e)}"}

# ==========================================
# LOGIC 35 LÕI AI
# ==========================================
def make_prediction(history=None, last_preds_holder=None):
    history = history if history is not None else GLOBAL_HISTORY
    weights = GLOBAL_AI_WEIGHTS
    if len(history) < 10: return random.choice(["TAI", "XIU"])

    preds = {"TAI": 0.0, "XIU": 0.0}
    model_preds = {}
    last_item = history[-1]
    opp_item = "XIU" if last_item == "TAI" else "TAI"
    rs = "".join(["T" if x == "TAI" else "X" for x in history])
    streak = len(rs) - len(rs.rstrip(rs[-1]))

    model_preds["trend"] = last_item if history[-5:].count(last_item) >= 3 else opp_item
    model_preds["pattern"] = opp_item if rs.endswith(("TXTX","TTXX")) else last_item
    t1 = {"TAI":{"TAI":0,"XIU":0},"XIU":{"TAI":0,"XIU":0}}
    for i in range(len(history)-1): t1[history[i]][history[i+1]] += 1
    model_preds["markov1"] = "TAI" if t1[last_item]["TAI"] > t1[last_item]["XIU"] else "XIU"
    model_preds["markov2"] = "TAI" if history[-2:] == ["TAI","TAI"] else "XIU"
    model_preds["markov3"] = opp_item if history[-3:] == [last_item]*3 else model_preds["markov2"]
    model_preds["frequency"] = "XIU" if history[-20:].count("TAI") > 10 else "TAI"
    model_preds["momentum"] = "TAI" if sum([i+1 if r=="TAI" else -(i+1) for i,r in enumerate(history[-5:])]) > 0 else "XIU"
    model_preds["symmetry"] = opp_item if len(rs)>=6 and rs[-6:-3]==rs[-3:][::-1] else last_item
    model_preds["alternating"] = opp_item
    model_preds["fibonacci"] = opp_item if streak in [3,5,8,13] else last_item
    model_preds["chaos"] = opp_item if sum(1 for i in range(len(rs[-10:])-1) if rs[-10:][i]!=rs[-10:][i+1])>=7 else last_item
    model_preds["shadow"] = "TAI" if history[-50:].count("TAI")<25 else "XIU"
    rsi = rs[-10:].count("T")
    model_preds["rsi_indicator"] = "XIU" if rsi>=7 else ("TAI" if rsi<=3 else last_item)
    model_preds["macd_cross"] = "TAI" if rs[-3:].count("T")>(rs[-9:].count("T")/3) else "XIU"
    model_preds["pivot_reversal"] = history[-1] if history[-3]==history[-2] and history[-2]!=history[-1] else last_item
    model_preds["cluster_3"] = "TAI" if rs[-3:] in ["TTT","TXX","XTX","XXT"] else "XIU"
    model_preds["parity"] = opp_item if streak%2==0 else last_item
    model_preds["golden_ratio"] = "TAI" if (history[-30:].count("TAI")/30)<0.618 else "XIU"
    model_preds["quantum"] = random.choice(["TAI","XIU"])
    model_preds["anti_bait"] = opp_item if streak>=5 or rs.endswith("TXTXT") else last_item
    mx=1; cur=1
    for i in range(1,len(history)):
        if history[i]==history[i-1]: cur+=1
        else: mx=max(mx,cur); cur=1
    model_preds["smart_breaker"] = opp_item if streak>=mx-1 and streak>=3 else last_item
    l4=rs[-4:]; tc4=rs[:-1].count(l4+"T"); xc4=rs[:-1].count(l4+"X")
    model_preds["ngram_4"] = "TAI" if tc4>xc4 else ("XIU" if xc4>tc4 else opp_item)
    l5=rs[-5:]; tc5=rs[:-1].count(l5+"T"); xc5=rs[:-1].count(l5+"X")
    model_preds["ngram_5"] = "TAI" if tc5>xc5 else ("XIU" if xc5>tc5 else opp_item)
    model_preds["elliott_wave"] = last_item if rs.endswith("TXTXT") else ("XIU" if rs.endswith("TTXXTT") else opp_item)
    model_preds["contrarian"] = opp_item if streak in (4,6) else ("XIU" if rs[-6:]=="TXTXTX" else last_item)
    ma10 = rs[-10:].count("T")/10.0
    model_preds["bollinger_bands"] = "XIU" if ma10>=0.8 else ("TAI" if ma10<=0.2 else last_item)
    ttot = history[-100:].count("TAI") if len(history)>=100 else history.count("TAI")
    model_preds["mean_reversion"] = "TAI" if ttot < len(history[-100:])*0.45 else "XIU"
    model_preds["mirror_reflection"] = ("TAI" if rs[-8]=="T" else "XIU") if len(rs)>=8 else opp_item
    model_preds["martingale_trap"] = opp_item if streak in (3,7) else last_item
    model_preds["poisson_prob"] = "TAI" if history[-5:].count("TAI")%2==1 else "XIU"
    model_preds["harmonic_cycle"] = history[-4] if len(history)>=4 else opp_item
    model_preds["breakout_hunter"] = last_item if streak==1 and history[-2]==history[-3] else opp_item
    model_preds["volume_fakeout"] = last_item if len(rs)>=5 and rs[-5:] in ["TTTXT","XXXTX"] else opp_item
    model_preds["time_decay"] = opp_item
    model_preds["neural_bias"] = "TAI" if history[-7:].count("TAI")>3 else "XIU"
    model_preds["twin_peaks"] = opp_item if rs.endswith(("TTXTT","XXTXX")) else last_item

    if last_preds_holder is not None:
        last_preds_holder.clear(); last_preds_holder.update(model_preds)

    for m, p in model_preds.items(): preds[p] += math.pow(weights.get(m, 1.0), 1.5)
    return "TAI" if preds["TAI"] > preds["XIU"] else "XIU"

def update_global_weights(actual_result, last_preds):
    global GLOBAL_AI_WEIGHTS, GLOBAL_MODEL_STREAK
    if not last_preds: return
    for m, p in last_preds.items():
        if p == actual_result:
            GLOBAL_MODEL_STREAK[m] += 1
            GLOBAL_AI_WEIGHTS[m] = min(20.0, GLOBAL_AI_WEIGHTS[m] + 0.5 + 0.2*GLOBAL_MODEL_STREAK[m])
        else:
            GLOBAL_MODEL_STREAK[m] = 0
            GLOBAL_AI_WEIGHTS[m] = max(0.1, GLOBAL_AI_WEIGHTS[m] - 2.5)

# ==========================================
# GIAO DIỆN HTML/CSS/JS (ĐÃ FIX LỖI)
# ==========================================
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0">
<title>TOOL AUTO LC79</title>
<script src="https://cdn.socket.io/4.7.5/socket.io.min.js"></script>
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
* { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Inter', sans-serif; }
body { min-height: 100vh; background: #eef2ff; background-image: radial-gradient(circle at top right, #e0e7ff, transparent 40%), radial-gradient(circle at bottom left, #f3e8ff, transparent 40%); color: #1e293b; padding: 16px; }
.app { max-width: 500px; margin: 0 auto; }
.hidden { display: none !important; }
.header-banner { display: flex; align-items: center; gap: 14px; background: #fff; padding: 16px; border-radius: 20px; box-shadow: 0 4px 20px rgba(99,102,241,0.08); margin-bottom: 20px; }
.logo-79 { background: linear-gradient(135deg, #ef4444, #f59e0b); color: #fff; font-weight: 900; font-style: italic; padding: 8px 12px; border-radius: 10px; font-size: 18px; box-shadow: 0 4px 10px rgba(239,68,68,0.3); transform: skewX(-10deg); }
.header-text h1 { font-size: 18px; color: #4f46e5; margin-bottom: 4px; }
.header-text p { font-size: 12px; color: #64748b; }
.login-card { background: #fff; border-radius: 20px; padding: 24px; box-shadow: 0 8px 30px rgba(99,102,241,0.12); }
.card-title { font-size: 13px; font-weight: 600; color: #1e293b; text-transform: uppercase; display: flex; align-items: center; gap: 8px; padding-bottom: 12px; margin-bottom: 20px; border-bottom: 1px solid #e2e8f0; }
.input-group { margin-bottom: 16px; }
.input-group label { display: block; font-size: 11px; font-weight: 600; color: #64748b; text-transform: uppercase; margin-bottom: 8px; }
input { width: 100%; padding: 14px 16px; border-radius: 12px; border: 1px solid #e2e8f0; background: #f8fafc; color: #1e293b; font-size: 15px; transition: 0.2s; }
input:focus { outline: none; border-color: #8b5cf6; background: #fff; box-shadow: 0 0 0 4px rgba(139,92,246,0.1); }
button { width: 100%; padding: 15px; border-radius: 12px; border: none; background: linear-gradient(90deg, #6366f1, #8b5cf6); color: #fff; font-size: 15px; font-weight: 600; cursor: pointer; transition: 0.2s; display: flex; justify-content: center; align-items: center; gap: 8px; box-shadow: 0 4px 15px rgba(99,102,241,0.3); }
button:hover { transform: translateY(-2px); }
button:disabled { opacity: 0.7; }
.btn-danger { background: linear-gradient(90deg, #ef4444, #dc2626); }
.btn-row { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 16px; }
.toggle { background: #f1f5f9; color: #64748b; box-shadow: none; border: 1px solid #e2e8f0; }
.toggle.active { background: #fef3c7; color: #d97706; border-color: #fde68a; }
.btn-small { width: auto; padding: 8px 14px; font-size: 12px; margin: 0; border-radius: 8px; }
.btn-small.danger { background: #fee2e2; color: #ef4444; box-shadow: none; }
.msg { margin-top: 16px; font-size: 13px; text-align: center; min-height: 20px; }
.card { background: #fff; border-radius: 20px; padding: 20px; margin-bottom: 16px; box-shadow: 0 4px 20px rgba(99,102,241,0.06); }
h3 { font-size: 14px; color: #1e293b; margin-bottom: 16px; }
.topbar { display: flex; justify-content: space-between; align-items: center; background: #fff; padding: 16px; border-radius: 20px; margin-bottom: 16px; box-shadow: 0 4px 20px rgba(99,102,241,0.06); }
.user { display: flex; align-items: center; gap: 12px; }
.avatar { width: 44px; height: 44px; border-radius: 50%; background: #e0e7ff; color: #6366f1; display: flex; align-items: center; justify-content: center; font-size: 20px; }
.user-info b { font-size: 15px; color: #1e293b; }
.uname { font-size: 12px; color: #64748b; }
.bal-wrap { text-align: right; }
.bal-label { font-size: 11px; color: #64748b; }
.bal { font-size: 16px; font-weight: 700; color: #16a34a; }
.status-bar { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; margin-bottom: 16px; }
.st-item { background: #fff; border-radius: 14px; padding: 12px 8px; text-align: center; box-shadow: 0 4px 15px rgba(99,102,241,0.05); }
.st-label { font-size: 10px; color: #64748b; font-weight: 600; }
.st-val { font-size: 14px; font-weight: 700; color: #4f46e5; margin-top: 4px; }
.stats-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; }
.stat-cell { background: #f8fafc; border-radius: 12px; padding: 12px 4px; text-align: center; }
.stat-cell span { display: block; font-size: 18px; font-weight: 800; }
.stat-cell label { font-size: 10px; color: #64748b; }
.stat-cell.win span { color: #16a34a; } .stat-cell.lose span { color: #dc2626; } .stat-cell.total span { color: #4f46e5; } .stat-cell.rate span { color: #d97706; }
.head-row { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.history-list { max-height: 300px; overflow-y: auto; }
.empty { text-align: center; color: #94a3b8; padding: 20px; font-size: 13px; }
.h-item { display: flex; justify-content: space-between; padding: 12px; margin-bottom: 8px; border-radius: 12px; border: 1px solid #e2e8f0; }
.h-item.h-win { border-color: #bbf7d0; background: #f0fdf4; } .h-item.h-lose { border-color: #fecaca; background: #fef2f2; }
.h-session { font-weight: 700; font-size: 13px; } .h-detail { font-size: 11px; color: #64748b; }
.h-profit { font-weight: 700; font-size: 14px; text-align: right; } .h-item.h-win .h-profit { color: #16a34a; } .h-item.h-lose .h-profit { color: #dc2626; }
.log { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 12px; padding: 12px; height: 160px; overflow-y: auto; font-family: monospace; font-size: 12px; color: #475569; }
</style>
</head>
<body>
<div class="app">
  <section id="login-panel">
    <div class="header-banner">
      <div class="logo-79">LC79</div>
      <div class="header-text"><h1>TOOL AUTO LC79</h1><p>Hệ thống phân tích cầu & dự đoán Tài Xỉu tự động</p></div>
    </div>
    <div class="login-card">
      <div class="card-title"><span>➜]</span> ĐĂNG NHẬP GAME</div>
      <div class="input-group"><label>TÀI KHOẢN</label><input id="username" placeholder="username"></div>
      <div class="input-group"><label>MẬT KHẨU</label><input id="password" type="password" placeholder="••••••••"></div>
      <div class="input-group"><label>NHẬP KEY BẢN QUYỀN</label><input id="license-key" placeholder="KEY-XXXXX"></div>
      <button id="btn-login">🔒 ĐĂNG NHẬP</button>
      <p id="login-msg" class="msg"></p>
    </div>
  </section>

  <section id="dashboard" class="hidden">
    <div class="topbar">
      <div class="user"><div class="avatar">👤</div><div class="user-info"><b id="nickname">-</b><div class="uname" id="uname-sub">-</div></div></div>
      <div class="bal-wrap"><div class="bal-label">Số dư</div><div class="bal">💰 <span id="balance">0</span></div></div>
    </div>
    <div class="status-bar">
      <div class="st-item"><div class="st-label">Phiên</div><div class="st-val" id="session">-</div></div>
      <div class="st-item"><div class="st-label">AI Dự đoán</div><div class="st-val" id="prediction">--</div></div>
      <div class="st-item"><div class="st-label">Lãi / Lỗ</div><div class="st-val" id="pl">0</div></div>
      <div class="st-item"><div class="st-label">Chuỗi</div><div class="st-val" id="streak">0</div></div>
    </div>
    <div class="card">
      <h3>📊 Thống kê tổng</h3>
      <div class="stats-grid">
        <div class="stat-cell win"><span id="total-win">0</span><label>Thắng</label></div>
        <div class="stat-cell lose"><span id="total-lose">0</span><label>Thua</label></div>
        <div class="stat-cell total"><span id="total-sessions">0</span><label>Tổng phiên</label></div>
        <div class="stat-cell rate"><span id="win-rate">0%</span><label>Tỷ lệ</label></div>
      </div>
    </div>
    <div class="card">
      <h3>⚙️ Cài đặt cược</h3>
      <div class="input-group"><label>Tiền cược gốc (Win)</label><input id="base-bet" type="number" value="10000"></div>
      <div class="input-group"><label>Mục tiêu chốt lãi (tùy chọn)</label><input id="target" type="number" placeholder="VD: 500000"></div>
      <div class="btn-row"><button id="btn-autobet" class="toggle">▶ Bật Auto</button><button id="btn-x2" class="toggle">⚡ X2</button></div>
      <button id="btn-start" style="background: linear-gradient(135deg, #22c55e, #16a34a); margin-top:10px;">🎯 Bắt đầu Bot</button>
      <button id="btn-stop" class="btn-danger" style="margin-top:10px;">⏹ Dừng Bot</button>
    </div>
    <div class="card">
      <div class="head-row"><h3>📜 Lịch sử thắng/thua</h3><button id="btn-reset" class="btn-small danger">🗑 Reset</button></div>
      <div id="history-list" class="history-list"><div class="empty">Chưa có lịch sử cược</div></div>
    </div>
    <div class="card"><h3>📡 Log hoạt động</h3><div id="log" class="log"></div></div>
  </section>
</div>

<script>
const socket = io();
let autoOn = false, x2On = false;
const $ = id => document.getElementById(id);
function log(msg) { const el = $('log'); const d = document.createElement('div'); d.textContent = `[${new Date().toLocaleTimeString()}] ${msg}`; el.appendChild(d); el.scrollTop = el.scrollHeight; }
function fmt(n) { return (n || 0).toLocaleString('vi-VN'); }

$('btn-login').onclick = async () => {
  const un = $('username').value.trim();
  const pw = $('password').value.trim();
  const key = $('license-key').value.trim();
  const msgEl = $('login-msg');
  if (!un || !pw) { msgEl.style.color = '#ef4444'; msgEl.textContent = '⚠️ Nhập đủ Tài khoản & Mật khẩu'; return; }
  if (!key) { msgEl.style.color = '#ef4444'; msgEl.textContent = '⚠️ Nhập KEY bản quyền'; return; }
  
  msgEl.style.color = '#d97706'; msgEl.textContent = '⏳ Đang xác thực API Game (Tối đa 40s)...';
  $('btn-login').disabled = true; $('btn-login').innerHTML = '⏳ ĐANG XỬ LÝ...';
  
  try {
    const r = await fetch('/api/login', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({username: un, password: pw, key: key})
    });
    const j = await r.json();
    if (!j.ok) {
      msgEl.style.color = '#ef4444'; msgEl.textContent = '❌ ' + (j.msg || 'Lỗi đăng nhập');
      $('btn-login').disabled = false; $('btn-login').innerHTML = '🔒 ĐĂNG NHẬP';
      return;
    }
    $('login-panel').classList.add('hidden'); $('dashboard').classList.remove('hidden');
    $('nickname').textContent = j.nickname; $('uname-sub').textContent = '@' + j.username;
    $('balance').textContent = fmt(j.money);
    window._token = j.token; window._nickname = j.nickname; window._username = j.username; window._money = j.money;
    socket.emit('start_bot', {token: j.token, nickname: j.nickname, username: j.username, money: j.money});
    log('✅ Đăng nhập thành công: ' + j.nickname);
  } catch (e) {
    msgEl.style.color = '#ef4444'; msgEl.textContent = '❌ Lỗi kết nối Server!';
    $('btn-login').disabled = false; $('btn-login').innerHTML = '🔒 ĐĂNG NHẬP';
  }
};

$('btn-start').onclick = () => { if(window._token) { socket.emit('start_bot', {token: window._token, nickname: window._nickname, username: window._username, money: window._money}); log('🚀 Khởi động Bot'); } };
$('btn-stop').onclick = () => { autoOn=false; $('btn-autobet').classList.remove('active'); $('btn-autobet').textContent='▶ Bật Auto'; socket.emit('set_autobet',{on:false}); socket.disconnect(); socket.connect(); log('⏹ Dừng Bot'); };
$('btn-autobet').onclick = () => { if(!window._token) return; autoOn=!autoOn; const b=parseInt($('base-bet').value)||10000; socket.emit('set_autobet',{on:autoOn, base_bet:b}); $('btn-autobet').classList.toggle('active', autoOn); $('btn-autobet').textContent = autoOn?'⏸ Tắt Auto':'▶ Bật Auto'; };
$('btn-x2').onclick = () => { x2On=!x2On; socket.emit('set_x2',{on:x2On}); $('btn-x2').classList.toggle('active', x2On); $('btn-x2').textContent = x2On?'⚡ X2 BẬT':'⚡ X2'; };
$('btn-reset').onclick = () => { if(confirm('Xoá toàn bộ lịch sử?')) socket.emit('reset_history'); };

socket.on('user_info', d => { $('nickname').textContent=d.nickname; $('uname-sub').textContent='@'+(d.username||''); $('balance').textContent=fmt(d.balance); $('total-win').textContent=d.total_win; $('total-lose').textContent=d.total_lose; $('total-sessions').textContent=d.total_sessions; renderHistory(d.history); });
socket.on('new_session', d => { $('session').textContent='#'+d.session; const p=d.prediction; if(p==='TAI'){$('prediction').textContent='🔵 TÀI';$('prediction').style.color='#3b82f6';}else if(p==='XIU'){$('prediction').textContent='🔴 XỈU';$('prediction').style.color='#ef4444';}else{$('prediction').textContent='⏳';} });
socket.on('result', d => { $('pl').textContent=fmt(d.profit_loss); $('streak').textContent=d.win_streak; $('balance').textContent=fmt(d.balance); $('total-win').textContent=d.total_win; $('total-lose').textContent=d.total_lose; $('total-sessions').textContent=d.total_sessions; if(d.entry) prependHistory(d.entry); });
socket.on('history_reset_ack', () => renderHistory([]));

function renderHistory(list) { const el=$('history-list'); if(!list||list.length===0){el.innerHTML='<div class="empty">Chưa có lịch sử</div>';return;} el.innerHTML=list.slice().reverse().map(html).join(''); }
function prependHistory(e) { const el=$('history-list'); if(el.querySelector('.empty'))el.innerHTML=''; el.insertAdjacentHTML('afterbegin', html(e)); }
function html(h) { const w=h.outcome==='WIN'; return `<div class="h-item ${w?'h-win':'h-lose'}"><div><div class="h-session">#${h.session}</div><div class="h-detail">Đoán ${h.prediction} → KQ ${h.result}</div></div><div><div class="h-profit">${h.profit>0?'+':''}${fmt(h.profit)}</div><div class="h-time">${h.time}</div></div></div>`; }
</script>
</body>
</html>
'''

@app.route('/')
def index(): 
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/login', methods=['POST'])
def api_login():
    try:
        data = request.get_json(force=True, silent=True) or {}
        res = login_and_get_token(data.get('username','').strip(), data.get('password','').strip())
        if "_error" in res: return jsonify({"ok": False, "msg": res["_error"]})
        return jsonify({"ok": True, "nickname": res.get("nickname"), "money": int(res.get("money",0)), "token": res["token"], "username": data.get('username','')})
    except Exception as e:
        return jsonify({"ok": False, "msg": f"Server Web lỗi: {str(e)}"})

@socketio.on('connect')
def on_connect(): WEB_USERS[request.sid] = init_user_state()

@socketio.on('disconnect')
def on_disconnect():
    u = WEB_USERS.pop(request.sid, None)
    if u and u.get("sio"):
        try: u["sio"].disconnect()
        except: pass

@socketio.on('start_bot')
def on_start_bot(data):
    u = WEB_USERS.get(request.sid)
    if not u or not data.get('token'): return
    u["token"] = data['token']; u["nickname"] = data.get('nickname','User'); u["username"] = data.get('username',''); u["balance"] = int(data.get('money',0))
    if u["nickname"] in PERSISTED_HISTORY:
        u["history"] = PERSISTED_HISTORY[u["nickname"]]
        u["total_win"] = sum(1 for h in u["history"] if h.get("outcome")=="WIN")
        u["total_lose"] = sum(1 for h in u["history"] if h.get("outcome")=="LOSE")
        u["total_sessions"] = len(u["history"]); u["profit_loss"] = sum(h.get("profit",0) for h in u["history"])
    emit('user_info', {'nickname':u["nickname"],'username':u["username"],'balance':u["balance"],'history':u["history"][-50:],'total_win':u["total_win"],'total_lose':u["total_lose"],'total_sessions':u["total_sessions"],'profit_loss':u["profit_loss"]})
    threading.Thread(target=_run_ws, args=(request.sid, u["token"]), daemon=True).start()

def _run_ws(sid, token):
    cli = sio_client.Client(reconnection=True, logger=False, engineio_logger=False)
    @cli.event(namespace='/txmd5')
    def connect(): socketio.emit('log', {'msg': '🟢 Đã kết nối API Game!'}, to=sid)

    @cli.on('new-session', namespace='/txmd5')
    def on_new_session(data):
        u = WEB_USERS.get(sid)
        if not u: return
        u["session_id"] = data.get('id','N/A'); u["has_bet"] = False
        pred = make_prediction(last_preds_holder=u["last_preds"]) if len(GLOBAL_HISTORY) >= 10 else None
        u["current_prediction"] = pred
        u["current_bet"] = u["base_bet"] * (2 ** min(u["win_streak"], 3)) if (u["x2_mode"] and u["win_streak"] >= 1) else u["base_bet"]
        socketio.emit('new_session', {'session':u["session_id"],'prediction':pred,'bet':u["current_bet"],'auto':u["auto_bet"]}, to=sid)

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
        result = data.get('resultTruyenThong'); dices = data.get('dices', [0,0,0])
        if result in ["TAI","XIU"]:
            GLOBAL_HISTORY.append(result)
            if len(GLOBAL_HISTORY) > 2000: GLOBAL_HISTORY.pop(0)
            update_global_weights(result, u.get("last_preds", {})); u["last_preds"] = {}
        
        bet_result, profit_delta = None, 0
        if u["waiting_for_result"] and u["current_prediction"]:
            u["total_sessions"] += 1
            if u["current_prediction"] == result:
                profit_delta = int(u["current_bet"]*0.98); u["profit_loss"] += profit_delta; u["win_streak"] += 1; u["lose_streak"] = 0; u["total_win"] += 1; bet_result = "WIN"
            else:
                profit_delta = -u["current_bet"]; u["profit_loss"] += profit_delta; u["lose_streak"] += 1; u["win_streak"] = 0; u["total_lose"] += 1; bet_result = "LOSE"
            u["waiting_for_result"] = False
            entry = {"session":u["session_id"],"prediction":u["current_prediction"],"result":result,"bet":u["current_bet"],"profit":profit_delta,"outcome":bet_result,"dices":dices,"time":time.strftime("%H:%M:%S %d/%m")}
            u["history"].append(entry); PERSISTED_HISTORY[u["nickname"]] = u["history"]; save_history(PERSISTED_HISTORY)
        
        socketio.emit('result', {'result':result,'dices':dices,'profit_loss':u["profit_loss"],'win_streak':u["win_streak"],'balance':u["balance"],'bet_result':bet_result,'total_win':u["total_win"],'total_lose':u["total_lose"],'total_sessions':u["total_sessions"],'entry':u["history"][-1] if bet_result else None}, to=sid)

    try:
        cli.connect('https://wtxmd52.tele68.com', socketio_path='txmd5/', namespaces=['/txmd5'], transports=['websocket'], auth={"token": token}, headers={"User-Agent":"Mozilla/5.0"})
        u = WEB_USERS.get(sid)
        if u: u["sio"] = cli
        cli.wait()
    except Exception: pass

@socketio.on('set_autobet')
def set_autobet(d):
    u = WEB_USERS.get(request.sid)
    if u: u["auto_bet"] = bool(d.get('on')); u["base_bet"] = int(d.get('base_bet', 10000)); emit('autobet_ack', {'on': u["auto_bet"]})
@socketio.on('set_x2')
def set_x2(d):
    u = WEB_USERS.get(request.sid)
    if u: u["x2_mode"] = bool(d.get('on'))
@socketio.on('reset_history')
def reset_history():
    u = WEB_USERS.get(request.sid)
    if u:
        u["history"]=[]; u["total_win"]=0; u["total_lose"]=0; u["total_sessions"]=0; u["profit_loss"]=0
        if u["nickname"]: PERSISTED_HISTORY[u["nickname"]]=[]; save_history(PERSISTED_HISTORY)
        emit('history_reset_ack', {'ok':True})

if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
