const socket = io();
let autoOn = false, x2On = false, botRunning = false;
const $ = id => document.getElementById(id);

function log(msg) {
  const el = $('log');
  const d = document.createElement('div');
  d.textContent = `[${new Date().toLocaleTimeString()}] ${msg}`;
  el.appendChild(d);
  el.scrollTop = el.scrollHeight;
}
function fmt(n) { return (n || 0).toLocaleString('vi-VN'); }

// ============ ĐĂNG NHẬP ============
$('btn-login').onclick = async () => {
  const un = $('username').value.trim();
  const pw = $('password').value.trim();
  const key = $('license-key').value.trim();
  const msgEl = $('login-msg');

  if (!un || !pw) {
    msgEl.style.color = '#ef4444';
    msgEl.textContent = '⚠️ Vui lòng nhập đủ Tài khoản và Mật khẩu';
    return;
  }

  // Kiểm tra key giả lập (Bạn có thể thay đổi logic này)
  if (!key) {
    msgEl.style.color = '#ef4444';
    msgEl.textContent = '⚠️ Vui lòng nhập KEY bản quyền';
    return;
  }

  msgEl.style.color = '#d97706';
  msgEl.textContent = '⏳ Đang xác thực API Game (Chờ tối đa 35s)...';
  $('btn-login').disabled = true;
  $('btn-login').innerHTML = '⏳ ĐANG XỬ LÝ...';

  try {
    const r = await fetch('/api/login', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({username: un, password: pw, key: key})
    });
    
    const j = await r.json();

    if (!j.ok) {
      msgEl.style.color = '#ef4444';
      msgEl.textContent = '❌ ' + (j.msg || 'Đăng nhập thất bại');
      $('btn-login').disabled = false;
      $('btn-login').innerHTML = '<span class="lock-icon">🔒</span> ĐĂNG NHẬP';
      return;
    }

    // Đăng nhập thành công
    $('login-panel').classList.add('hidden');
    $('dashboard').classList.remove('hidden');
    $('nickname').textContent = j.nickname;
    $('uname-sub').textContent = '@' + j.username;
    $('balance').textContent = fmt(j.money);
    window._token = j.token;
    window._nickname = j.nickname;
    window._username = j.username;
    window._money = j.money;

    socket.emit('start_bot', {
      token: j.token, nickname: j.nickname, username: j.username, money: j.money
    });
    botRunning = true;
    log('✅ Đăng nhập thành công: ' + j.nickname);
    log('🔄 Đang kết nối API Game...');
  } catch (e) {
    msgEl.style.color = '#ef4444';
    msgEl.textContent = '❌ Lỗi kết nối Server Web. Vui lòng thử lại!';
    $('btn-login').disabled = false;
    $('btn-login').innerHTML = '<span class="lock-icon">🔒</span> ĐĂNG NHẬP';
  }
};

$('password').addEventListener('keypress', e => { if (e.key === 'Enter') $('btn-login').click(); });
$('license-key').addEventListener('keypress', e => { if (e.key === 'Enter') $('btn-login').click(); });

// ============ START / STOP ============
$('btn-start').onclick = () => {
  if (!window._token) return log('❌ Chưa đăng nhập');
  socket.emit('start_bot', { token: window._token, nickname: window._nickname, username: window._username, money: window._money });
  botRunning = true;
  log('🚀 Bot đang khởi động...');
};

$('btn-stop').onclick = () => {
  autoOn = false;
  $('btn-autobet').classList.remove('active');
  $('btn-autobet').textContent = '▶ Bật Auto';
  socket.emit('set_autobet', { on: false });
  socket.disconnect(); socket.connect();
  botRunning = false;
  log('⏹ Đã dừng bot & tắt Auto');
};

// ============ AUTO / X2 / TARGET ============
$('btn-autobet').onclick = () => {
  if (!window._token) return log('❌ Chưa đăng nhập');
  autoOn = !autoOn;
  const base = parseInt($('base-bet').value) || 10000;
  socket.emit('set_autobet', { on: autoOn, base_bet: base });
  $('btn-autobet').classList.toggle('active', autoOn);
  $('btn-autobet').textContent = autoOn ? '⏸ Tắt Auto' : '▶ Bật Auto';
  log(autoOn ? `✅ Auto BẬT (gốc ${fmt(base)} Win)` : '🔴 Auto TẮT');
};

$('btn-x2').onclick = () => {
  x2On = !x2On;
  socket.emit('set_x2', { on: x2On });
  $('btn-x2').classList.toggle('active', x2On);
  $('btn-x2').textContent = x2On ? '⚡ X2 BẬT' : '⚡ X2';
  log(x2On ? '⚡ X2 BẬT' : 'X2 TẮT');
};

$('target').onchange = () => {
  const t = parseInt($('target').value);
  if (t > 0) { socket.emit('set_target', { target: t }); log('🎯 Target: ' + fmt(t) + ' Win'); }
};

$('btn-reset').onclick = () => {
  if (!confirm('Xoá toàn bộ lịch sử thắng/thua?')) return;
  socket.emit('reset_history');
  log('🗑 Đã gửi yêu cầu reset');
};

$('btn-weights').onclick = () => socket.emit('get_weights');

// ============ SOCKET EVENTS ============
socket.on('user_info', d => {
  $('nickname').textContent = d.nickname;
  $('uname-sub').textContent = '@' + (d.username || '');
  $('balance').textContent = fmt(d.balance);
  $('pl').textContent = fmt(d.profit_loss);
  $('pl').style.color = d.profit_loss >= 0 ? '#16a34a' : '#dc2626';
  $('total-win').textContent = d.total_win;
  $('total-lose').textContent = d.total_lose;
  $('total-sessions').textContent = d.total_sessions;
  updateWinRate(d.total_win, d.total_sessions);
  renderHistory(d.history);
  log('✅ Đã đồng bộ dữ liệu người chơi');
});

socket.on('new_session', d => {
  $('session').textContent = '#' + d.session;
  const pred = d.prediction;
  if (pred === 'TAI') { $('prediction').textContent = '🔵 TÀI'; $('prediction').style.color = '#3b82f6'; }
  else if (pred === 'XIU') { $('prediction').textContent = '🔴 XỈU'; $('prediction').style.color = '#ef4444'; }
  else { $('prediction').textContent = '⏳ ...'; $('prediction').style.color = '#94a3b8'; }

  if (d.auto && pred) log(`🎯 Phiên #${d.session} → Auto ${fmt(d.bet)} vào ${pred}`);
  else log(`🔔 Phiên #${d.session} | AI: ${pred || 'học'} (data: ${d.history_len})`);
});

socket.on('bet_placed', d => log(`🚀 VÀO TIỀN: ${fmt(d.amount)} vào ${d.type}`));

socket.on('result', d => {
  const emoji = d.result === 'TAI' ? '🔵 TÀI' : '🔴 XỈU';
  let extra = '';
  if (d.bet_result === 'WIN') extra = ` ✅ +${fmt(d.profit_delta)}`;
  else if (d.bet_result === 'LOSE') extra = ` ❌ ${fmt(d.profit_delta)}`;
  log(`🎲 ${emoji} (${d.dices.join('-')})${extra} | Lãi: ${fmt(d.profit_loss)} | Chuỗi: ${d.win_streak}`);

  $('pl').textContent = fmt(d.profit_loss);
  $('pl').style.color = d.profit_loss >= 0 ? '#16a34a' : '#dc2626';
  $('streak').textContent = d.win_streak;
  $('balance').textContent = fmt(d.balance);
  $('total-win').textContent = d.total_win;
  $('total-lose').textContent = d.total_lose;
  $('total-sessions').textContent = d.total_sessions;
  updateWinRate(d.total_win, d.total_sessions);
  if (d.entry) prependHistory(d.entry);
});

socket.on('balance', d => $('balance').textContent = fmt(d.balance));
socket.on('log', d => log(d.msg));

socket.on('weights', d => {
  $('weights').innerHTML = d.list.map(([k,v]) =>
    `<div class="item"><span>${k}</span><span class="score">${v.toFixed(2)}</span></div>`
  ).join('');
});

socket.on('autobet_ack', d => {
  autoOn = d.on; $('btn-autobet').classList.toggle('active', autoOn);
  $('btn-autobet').textContent = autoOn ? '⏸ Tắt Auto' : '▶ Bật Auto';
});

socket.on('x2_ack', d => {
  x2On = d.on; $('btn-x2').classList.toggle('active', x2On);
  $('btn-x2').textContent = x2On ? '⚡ X2 BẬT' : '⚡ X2';
});

socket.on('history_data', d => {
  renderHistory(d.history);
  $('total-win').textContent = d.total_win;
  $('total-lose').textContent = d.total_lose;
  $('total-sessions').textContent = d.total_sessions;
  $('pl').textContent = fmt(d.profit_loss);
  $('pl').style.color = d.profit_loss >= 0 ? '#16a34a' : '#dc2626';
  updateWinRate(d.total_win, d.total_sessions);
});

socket.on('history_reset_ack', () => { log('✅ Đã reset lịch sử'); renderHistory([]); });

function updateWinRate(win, total) { $('win-rate').textContent = total > 0 ? ((win/total)*100).toFixed(1) + '%' : '0%'; }
function renderHistory(list) {
  const el = $('history-list');
  if (!list || list.length === 0) { el.innerHTML = '<div class="empty">Chưa có lịch sử cược</div>'; return; }
  el.innerHTML = list.slice().reverse().map(historyItemHTML).join('');
}
function prependHistory(entry) {
  const el = $('history-list');
  if (el.querySelector('.empty')) el.innerHTML = '';
  el.insertAdjacentHTML('afterbegin', historyItemHTML(entry));
  while (el.children.length > 100) el.removeChild(el.lastChild);
}
function historyItemHTML(h) {
  const isWin = h.outcome === 'WIN';
  const cls = isWin ? 'h-win' : 'h-lose';
  const icon = isWin ? '✅' : '❌';
  const pred = h.prediction === 'TAI' ? '🔵 TÀI' : '🔴 XỈU';
  const res = h.result === 'TAI' ? '🔵 TÀI' : '🔴 XỈU';
  const profit = h.profit >= 0 ? `+${fmt(h.profit)}` : fmt(h.profit);
  return `
    <div class="h-item ${cls}">
      <div class="h-left"><div class="h-icon">${icon}</div><div><div class="h-session">#${h.session || '-'}</div><div class="h-detail">Đoán ${pred} → KQ ${res}</div></div></div>
      <div class="h-right"><div class="h-profit">${profit}</div><div class="h-time">${h.time || ''}</div></div>
    </div>
  `;
}
