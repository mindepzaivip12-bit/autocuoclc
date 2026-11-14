const socket = io();
let botRunning = false;
let autoOn = false, x2On = false;

const $ = id => document.getElementById(id);

function log(msg) {
  const el = $('log');
  const d = document.createElement('div');
  d.textContent = `[${new Date().toLocaleTimeString()}] ${msg}`;
  el.appendChild(d);
  el.scrollTop = el.scrollHeight;
}

// ====== ĐĂNG NHẬP ======
$('btn-login').onclick = async () => {
  const un = $('username').value.trim();
  const pw = $('password').value.trim();
  if (!un || !pw) return $('login-msg').textContent = '⚠️ Nhập đủ tài khoản & mật khẩu';
  $('login-msg').textContent = '⏳ Đang đăng nhập...';
  try {
    const r = await fetch('/api/login', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({username: un, password: pw})
    });
    const j = await r.json();
    if (!j.ok) { $('login-msg').textContent = '❌ ' + j.msg; return; }
    $('login-panel').classList.add('hidden');
    $('dashboard').classList.remove('hidden');
    $('nickname').textContent = j.nickname;
    $('balance').textContent = j.money.toLocaleString();
    window._token = j.token;
    log('✅ Đăng nhập thành công: ' + j.nickname);
  } catch(e) {
    $('login-msg').textContent = '❌ Lỗi mạng: ' + e.message;
  }
};

// ====== BẮT ĐẦU / DỪNG ======
$('btn-start').onclick = () => {
  if (!window._token) return log('❌ Chưa đăng nhập');
  socket.emit('start_bot', { token: window._token });
  botRunning = true;
  log('🚀 Bot đang khởi động...');
};

$('btn-stop').onclick = () => {
  socket.disconnect(); socket.connect();
  botRunning = false; log('⏹ Đã dừng bot');
};

// ====== TOGGLE AUTO / X2 ======
$('btn-autobet').onclick = () => {
  autoOn = !autoOn;
  const base = parseInt($('base-bet').value) || 10000;
  socket.emit('set_autobet', { on: autoOn, base_bet: base });
  $('btn-autobet').classList.toggle('active', autoOn);
  $('btn-autobet').textContent = autoOn ? '⏸ Tắt Auto Bet' : '▶ Bật Auto Bet';
  log(autoOn ? `✅ Auto Bet BẬT (cược ${base.toLocaleString()})` : '🔴 Auto Bet TẮT');
};

$('btn-x2').onclick = () => {
  x2On = !x2On;
  socket.emit('set_x2', { on: x2On });
  $('btn-x2').classList.toggle('active', x2On);
  log(x2On ? '⚡ X2 Cầu Thông BẬT' : 'X2 TẮT');
};

$('target').onchange = () => {
  const t = parseInt($('target').value);
  if (t > 0) { socket.emit('set_target', { target: t }); log('🎯 Target: ' + t.toLocaleString()); }
};

$('btn-weights').onclick = () => socket.emit('get_weights');

// ====== SOCKET EVENTS ======
socket.on('new_session', d => {
  $('session').textContent = '#' + d.session;
  const pred = d.prediction;
  $('prediction').textContent = pred === 'TAI' ? '🔵 TÀI' : (pred === 'XIU' ? '🔴 XỈU' : '⏳ ...');
  $('prediction').style.color = pred === 'TAI' ? '#3b82f6' : (pred === 'XIU' ? '#ef4444' : '#94a3b8');
  if (d.auto) log(`🎯 Phiên mới → Auto cược ${d.bet.toLocaleString()} vào ${pred}`);
  else log(`🔔 Phiên #${d.session} | AI: ${pred || 'đang học...'} (data: ${d.history_len})`);
});

socket.on('bet_placed', d => log(`🚀 VÀO TIỀN: ${d.amount.toLocaleString()} vào ${d.type}`));

socket.on('result', d => {
  const emoji = d.result === 'TAI' ? '🔵 TÀI' : '🔴 XỈU';
  log(`🎲 KQ: ${emoji} (${d.dices.join('-')}) | Lãi: ${d.profit_loss.toLocaleString()} | Chuỗi: ${d.win_streak}`);
  $('pl').textContent = d.profit_loss.toLocaleString();
  $('pl').style.color = d.profit_loss >= 0 ? '#22c55e' : '#ef4444';
  $('streak').textContent = d.win_streak;
  $('balance').textContent = d.balance.toLocaleString();
});

socket.on('balance', d => $('balance').textContent = d.balance.toLocaleString());
socket.on('log', d => log(d.msg));

socket.on('weights', d => {
  $('weights').innerHTML = d.list.map(([k,v]) =>
    `<div class="item"><span>${k}</span><span class="score">${v.toFixed(2)}</span></div>`
  ).join('');
});
