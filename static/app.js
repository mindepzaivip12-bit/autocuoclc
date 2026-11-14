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

// ==================== ĐĂNG NHẬP ====================
$('btn-login').onclick = async () => {
  const un = $('username').value.trim();
  const pw = $('password').value.trim();
  if (!un || !pw) { $('login-msg').textContent = '⚠️ Nhập đủ tài khoản & mật khẩu'; return; }
  $('login-msg').textContent = '⏳ Đang đăng nhập...';
  $('login-msg').style.color = '#facc15';
  try {
    const r = await fetch('/api/login', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({username: un, password: pw})
    });
    const j = await r.json();
    if (!j.ok) { $('login-msg').textContent = '❌ ' + j.msg; $('login-msg').style.color = '#f87171'; return; }

    $('login-panel').classList.add('hidden');
    $('dashboard').classList.remove('hidden');
    $('nickname').textContent = j.nickname;
    $('uname-sub').textContent = '@' + j.username;
    $('balance').textContent = fmt(j.money);
    window._token = j.token;
    window._nickname = j.nickname;
    window._username = j.username;
    window._money = j.money;

    // Khởi động bot luôn để nhận lịch sử
    socket.emit('start_bot', {
      token: j.token,
      nickname: j.nickname,
      money: j.money
    });
    botRunning = true;
    log('✅ Đăng nhập thành công: ' + j.nickname);
  } catch(e) {
    $('login-msg').textContent = '❌ Lỗi mạng: ' + e.message;
    $('login-msg').style.color = '#f87171';
  }
};

// ==================== START / STOP ====================
$('btn-start').onclick = () => {
  if (!window._token) return log('❌ Chưa đăng nhập');
  socket.emit('start_bot', {
    token: window._token,
    nickname: window._nickname,
    money: window._money
  });
  botRunning = true;
  log('🚀 Bot đang khởi động...');
};

$('btn-stop').onclick = () => {
  autoOn = false;
  $('btn-autobet').classList.remove('active');
  $('btn-autobet').textContent = '▶ Bật Auto Cược';
  socket.emit('set_autobet', { on: false });
  socket.disconnect();
  socket.connect();
  botRunning = false;
  log('⏹ Đã dừng bot & tắt Auto');
};

// ==================== AUTO BET TOGGLE ====================
$('btn-autobet').onclick = () => {
  if (!window._token) return log('❌ Chưa đăng nhập');
  autoOn = !autoOn;
  const base = parseInt($('base-bet').value) || 10000;
  socket.emit('set_autobet', { on: autoOn, base_bet: base });
  $('btn-autobet').classList.toggle('active', autoOn);
  $('btn-autobet').textContent = autoOn ? '⏸ Tắt Auto Cược' : '▶ Bật Auto Cược';
  log(autoOn ? `✅ Auto Cược BẬT (gốc ${fmt(base)} Win)` : '🔴 Auto Cược TẮT');
};

$('btn-x2').onclick = () => {
  x2On = !x2On;
  socket.emit('set_x2', { on: x2On });
  $('btn-x2').classList.toggle('active', x2On);
  $('btn-x2').textContent = x2On ? '⚡ X2: BẬT' : '⚡ X2 Cầu Thông';
  log(x2On ? '⚡ X2 Cầu Thông BẬT' : 'X2 TẮT');
};

$('target').onchange = () => {
  const t = parseInt($('target').value);
  if (t > 0) {
    socket.emit('set_target', { target: t });
    log('🎯 Target chốt lãi: ' + fmt(t) + ' Win');
  }
};

$('base-bet').onchange = () => {
  const b = parseInt($('base-bet').value);
  if (b >= 1000 && autoOn) {
    socket.emit('set_autobet', { on: true, base_bet: b });
    log('💸 Đổi tiền cược gốc: ' + fmt(b) + ' Win');
  }
};

// ==================== RESET HISTORY ====================
$('btn-reset').onclick = () => {
  if (!confirm('Bạn có chắc muốn xoá toàn bộ lịch sử thắng/thua?')) return;
  socket.emit('reset_history');
  log('🗑 Đã gửi yêu cầu reset lịch sử');
};

// ==================== WEIGHTS ====================
$('btn-weights').onclick = () => socket.emit('get_weights');

// ==================== SOCKET EVENTS ====================

// Thông tin user sau khi login
socket.on('user_info', d => {
  $('nickname').textContent = d.nickname;
  $('balance').textContent = fmt(d.balance);
  $('pl').textContent = fmt(d.profit_loss);
  $('pl').style.color = d.profit_loss >= 0 ? '#22c55e' : '#ef4444';
  $('total-win').textContent = d.total_win;
  $('total-lose').textContent = d.total_lose;
  $('total-sessions').textContent = d.total_sessions;
  updateWinRate(d.total_win, d.total_sessions);
  renderHistory(d.history);
});

// Phiên mới
socket.on('new_session', d => {
  $('session').textContent = '#' + d.session;
  const pred = d.prediction;
  if (pred === 'TAI') {
    $('prediction').textContent = '🔵 TÀI';
    $('prediction').style.color = '#3b82f6';
  } else if (pred === 'XIU') {
    $('prediction').textContent = '🔴 XỈU';
    $('prediction').style.color = '#ef4444';
  } else {
    $('prediction').textContent = '⏳ ...';
    $('prediction').style.color = '#94a3b8';
  }
  if (d.auto && pred) {
    log(`🎯 Phiên #${d.session} → Auto cược ${fmt(d.bet)} vào ${pred}`);
  } else {
    log(`🔔 Phiên #${d.session} | AI: ${pred || 'đang học'} (data: ${d.history_len})`);
  }
});

// Đã đặt cược
socket.on('bet_placed', d => {
  log(`🚀 VÀO TIỀN: ${fmt(d.amount)} vào ${d.type}`);
});

// Kết quả
socket.on('result', d => {
  const emoji = d.result === 'TAI' ? '🔵 TÀI' : '🔴 XỈU';
  let extra = '';
  if (d.bet_result === 'WIN') extra = ` ✅ THẮNG +${fmt(d.profit_delta)}`;
  else if (d.bet_result === 'LOSE') extra = ` ❌ THUA ${fmt(d.profit_delta)}`;
  log(`🎲 KQ: ${emoji} (${d.dices.join('-')})${extra} | Lãi: ${fmt(d.profit_loss)} | Chuỗi: ${d.win_streak}`);

  $('pl').textContent = fmt(d.profit_loss);
  $('pl').style.color = d.profit_loss >= 0 ? '#22c55e' : '#ef4444';
  $('streak').textContent = d.win_streak;
  $('balance').textContent = fmt(d.balance);
  $('total-win').textContent = d.total_win;
  $('total-lose').textContent = d.total_lose;
  $('total-sessions').textContent = d.total_sessions;
  updateWinRate(d.total_win, d.total_sessions);

  if (d.entry) prependHistory(d.entry);
});

socket.on('balance', d => {
  $('balance').textContent = fmt(d.balance);
});

socket.on('log', d => log(d.msg));

socket.on('weights', d => {
  $('weights').innerHTML = d.list.map(([k,v]) =>
    `<div class="item"><span>${k}</span><span class="score">${v.toFixed(2)}</span></div>`
  ).join('');
});

socket.on('autobet_ack', d => {
  autoOn = d.on;
  $('btn-autobet').classList.toggle('active', autoOn);
  $('btn-autobet').textContent = autoOn ? '⏸ Tắt Auto Cược' : '▶ Bật Auto Cược';
});

socket.on('x2_ack', d => {
  x2On = d.on;
  $('btn-x2').classList.toggle('active', x2On);
  $('btn-x2').textContent = x2On ? '⚡ X2: BẬT' : '⚡ X2 Cầu Thông';
});

socket.on('history_data', d => {
  renderHistory(d.history);
  $('total-win').textContent = d.total_win;
  $('total-lose').textContent = d.total_lose;
  $('total-sessions').textContent = d.total_sessions;
  $('pl').textContent = fmt(d.profit_loss);
  $('pl').style.color = d.profit_loss >= 0 ? '#22c55e' : '#ef4444';
  updateWinRate(d.total_win, d.total_sessions);
});

socket.on('history_reset_ack', () => {
  log('✅ Đã reset toàn bộ lịch sử');
  renderHistory([]);
});

// ==================== HELPERS ====================
function updateWinRate(win, total) {
  const rate = total > 0 ? ((win / total) * 100).toFixed(1) : 0;
  $('win-rate').textContent = rate + '%';
}

function renderHistory(list) {
  const el = $('history-list');
  if (!list || list.length === 0) {
    el.innerHTML = '<div class="empty">Chưa có lịch sử cược</div>';
    return;
  }
  el.innerHTML = list.slice().reverse().map(h => {
    const isWin = h.outcome === 'WIN';
    const cls = isWin ? 'h-win' : 'h-lose';
    const icon = isWin ? '✅' : '❌';
    const pred = h.prediction === 'TAI' ? '🔵 TÀI' : '🔴 XỈU';
    const res = h.result === 'TAI' ? '🔵 TÀI' : '🔴 XỈU';
    const profit = h.profit >= 0 ? `+${fmt(h.profit)}` : fmt(h.profit);
    return `
      <div class="h-item ${cls}">
        <div class="h-left">
          <div class="h-icon">${icon}</div>
          <div>
            <div class="h-session">#${h.session || '-'}</div>
            <div class="h-detail">Đoán ${pred} → KQ ${res}</div>
          </div>
        </div>
        <div class="h-right">
          <div class="h-profit">${profit}</div>
          <div class="h-time">${h.time || ''}</div>
        </div>
      </div>
    `;
  }).join('');
}

function prependHistory(entry) {
  const el = $('history-list');
  if (el.querySelector('.empty')) el.innerHTML = '';
  const isWin = entry.outcome === 'WIN';
  const cls = isWin ? 'h-win' : 'h-lose';
  const icon = isWin ? '✅' : '❌';
  const pred = entry.prediction === 'TAI' ? '🔵 TÀI' : '🔴 XỈU';
  const res = entry.result === 'TAI' ? '🔵 TÀI' : '🔴 XỈU';
  const profit = entry.profit >= 0 ? `+${fmt(entry.profit)}` : fmt(entry.profit);
  const html = `
    <div class="h-item ${cls}">
      <div class="h-left">
        <div class="h-icon">${icon}</div>
        <div>
          <div class="h-session">#${entry.session || '-'}</div>
          <div class="h-detail">Đoán ${pred} → KQ ${res}</div>
        </div>
      </div>
      <div class="h-right">
        <div class="h-profit">${profit}</div>
        <div class="h-time">${entry.time || ''}</div>
      </div>
    </div>
  `;
  el.insertAdjacentHTML('afterbegin', html);
  // Giới hạn 100 item
  while (el.children.length > 100) el.removeChild(el.lastChild);
}
