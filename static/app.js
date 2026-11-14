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
  const msgEl = $('login-msg');

  if (!un || !pw) {
    msgEl.style.color = '#f87171';
    msgEl.textContent = '⚠️ Vui lòng nhập đủ tài khoản & mật khẩu';
    return;
  }

  msgEl.style.color = '#facc15';
  msgEl.textContent = '⏳ Đang đăng nhập... (chờ 15s)';
  $('btn-login').disabled = true;
  $('btn-login').textContent = '⏳ Đang xử lý...';

  // Timeout 20s phía client
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 20000);

  try {
    const r = await fetch('/api/login', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({username: un, password: pw}),
      signal: controller.signal
    });
    clearTimeout(timer);

    let j;
    try {
      j = await r.json();
    } catch (e) {
      throw new Error('Server không trả JSON. HTTP ' + r.status);
    }

    if (!j.ok) {
      msgEl.style.color = '#f87171';
      msgEl.textContent = '❌ ' + (j.msg || 'Đ
