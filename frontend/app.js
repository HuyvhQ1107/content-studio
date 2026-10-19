const $ = (id) => document.getElementById(id);
const STEPS = ["Tìm hiểu chủ đề", "Viết bài blog", "Soạn bài mạng xã hội"];
const EXAMPLES = ["Những đột phá mới của Generative AI", "Xu hướng xe điện năm nay", "Cách doanh nghiệp nhỏ ứng dụng AI"];

let me = null, inviteRequired = false, authMode = "login";
let chats = [], currentId = null, msgs = [], epoch = 0;
let opts = { lang: "Vietnamese", social: true };
try { opts = { ...opts, ...JSON.parse(localStorage.getItem("cs_opts")) }; } catch {}
const saveOpts = () => { try { localStorage.setItem("cs_opts", JSON.stringify(opts)); } catch {} };
const isBusy = () => msgs.some((m) => m.status === "running");

async function api(path, method = "GET", body) {
  const r = await fetch(path, {
    method, headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  let data = null; try { data = await r.json(); } catch {}
  if (r.status === 401 && !path.startsWith("/api/auth/")) {
    showAuth("Phiên đăng nhập đã hết hạn. Hãy đăng nhập lại.");
    const err = new Error("Phiên đăng nhập đã hết hạn"); err.auth = true; throw err;
  }
  if (!r.ok) throw new Error(typeof data?.detail === "string" ? data.detail : "Dữ liệu không hợp lệ");
  return data;
}

/* Markdown nhỏ gọn: escape HTML trước nên an toàn */
function md(src) {
  const esc = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  const inline = (s) => esc(s)
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/(?<![*\w])\*(?!\s)(.+?)\*(?![*\w])/g, "<em>$1</em>")
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\[([^\]]+)\]\((https?:\/\/[^\s)"]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
  const out = []; let list = null;
  const close = () => { if (list) { out.push(`</${list}>`); list = null; } };
  for (const line of String(src).split("\n")) {
    let m;
    if ((m = line.match(/^(#{1,4})\s+(.*)/))) { close(); const n = m[1].length + 1; out.push(`<h${n}>${inline(m[2])}</h${n}>`); }
    else if ((m = line.match(/^\s*[-*•]\s+(.*)/))) { if (list !== "ul") { close(); out.push("<ul>"); list = "ul"; } out.push(`<li>${inline(m[1])}</li>`); }
    else if ((m = line.match(/^\s*\d+\.\s+(.*)/))) { if (list !== "ol") { close(); out.push("<ol>"); list = "ol"; } out.push(`<li>${inline(m[1])}</li>`); }
    else if (!line.trim()) close();
    else { close(); out.push(`<p>${inline(line)}</p>`); }
  }
  close();
  return out.join("");
}

const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };

function renderSide() {
  $("hist").replaceChildren(...chats.map((c) => {
    const item = el("div", "item" + (c.id === currentId ? " on" : ""));
    const pick = el("button", "pick", c.title); pick.type = "button"; pick.title = c.title;
    pick.onclick = () => openChat(c.id);
    const del = el("button", "del", "✕"); del.type = "button"; del.setAttribute("aria-label", "Xoá cuộc trò chuyện");
    del.onclick = async () => {
      if (c.id === currentId && isBusy()) return;
      if (!confirm("Xoá cuộc trò chuyện này? Không thể hoàn tác.")) return;
      try { await api(`/api/conversations/${c.id}`, "DELETE"); } catch (e) { if (!e.auth) $("notice").textContent = e.message; return; }
      chats = chats.filter((x) => x.id !== c.id);
      if (currentId === c.id) openChat(null); else refresh();
    };
    item.append(pick, del);
    return item;
  }));
}

function renderBot(m) {
  const wrap = el("div", "msg bot");
  wrap.append(el("div", "avatar", "AI"));
  const body = el("div", "body"); wrap.append(body);

  if (m.status === "running") {
    const ol = el("ol", "steps");
    STEPS.slice(0, m.total).forEach((name, i) => ol.append(el("li", i < m.done ? "done" : i === m.done ? "run" : "", name)));
    body.append(ol);
  } else if (m.status === "error") {
    body.append(el("div", "err", "Không tạo được nội dung: " + m.error));
  } else {
    const tasks = [...m.result.tasks].reverse(); // bài cuối trước
    const tab = Math.min(m.tab || 0, tasks.length - 1);
    const tabs = el("div", "tabs"); tabs.setAttribute("role", "tablist");
    tasks.forEach((t, i) => {
      const b = el("button", "", t.title); b.type = "button"; b.role = "tab";
      b.setAttribute("aria-selected", i === tab);
      b.onclick = () => { m.tab = i; refresh(); };
      tabs.append(b);
    });
    const content = el("div", "md"); content.innerHTML = md(tasks[tab].output);
    const k = m.result.tokens;
    const meta = el("div", "meta");
    const copy = el("button", "", "Sao chép"); copy.type = "button";
    copy.onclick = async () => { await navigator.clipboard.writeText(tasks[tab].output); copy.textContent = "Đã sao chép"; setTimeout(() => (copy.textContent = "Sao chép"), 1500); };
    meta.append(copy, el("span", "", `${k.total.toLocaleString("vi-VN")} token`));
    body.append(tabs, content, meta);
  }
  return wrap;
}

function renderThread() {
  const has = currentId !== null;
  $("empty").hidden = has; $("thread").hidden = !has;
  if (!has) return;
  $("thread").replaceChildren(...msgs.map((m) => {
    if (m.role === "user") { const w = el("div", "msg user"); w.append(el("div", "bubble", m.text)); return w; }
    return renderBot(m);
  }));
}

function refresh(scrollDown) {
  renderSide(); renderThread();
  $("send").disabled = isBusy();
  if (scrollDown) $("scroll").scrollTop = $("scroll").scrollHeight;
}

async function poll(m) {
  const ep = epoch;
  while (m.status === "running") {
    await new Promise((r) => setTimeout(r, 2000));
    if (ep !== epoch) return; // đã chuyển cuộc trò chuyện hoặc đăng xuất
    try {
      const j = await api(`/api/messages/${m.id}`);
      if (ep !== epoch) return;
      Object.assign(m, { status: j.status, done: j.done, total: j.total, result: j.result, error: j.error });
      m.tab = 0;
      refresh(m.status !== "running");
    } catch { /* mất kết nối tạm thời: thử lại ở vòng sau */ }
  }
}

async function loadChats() { chats = (await api("/api/conversations")).conversations; }

async function openChat(id) {
  epoch++; currentId = id; msgs = [];
  $("app").classList.remove("open"); $("notice").textContent = "";
  if (id !== null) {
    try { msgs = (await api(`/api/conversations/${id}`)).messages; }
    catch (e) { if (!e.auth) $("notice").textContent = e.message; currentId = null; }
  }
  refresh(true);
  msgs.filter((m) => m.status === "running").forEach(poll);
}

async function send(text) {
  text = text.trim();
  if (!text || isBusy()) return;
  $("notice").textContent = ""; $("send").disabled = true;
  try {
    const d = await api("/api/chat", "POST", {
      conversation_id: currentId, topic: text, language: opts.lang, with_social: opts.social,
    });
    currentId = d.conversation.id;
    chats = [d.conversation, ...chats.filter((c) => c.id !== currentId)];
    msgs.push(...d.messages);
    $("input").value = ""; autosize(); refresh(true);
    poll(msgs[msgs.length - 1]);
  } catch (e) { if (!e.auth) $("notice").textContent = e.message; refresh(); }
}

function autosize() { const t = $("input"); t.style.height = "auto"; t.style.height = t.scrollHeight + "px"; }

/* Đăng nhập / đăng ký */
function setAuthMsg(text, ok = false) {
  $("authMsg").textContent = text;
  $("authMsg").className = "msg" + (ok ? " ok" : "");
}

function renderAuthMode() {
  const login = authMode === "login";
  $("authTitle").textContent = login ? "Đăng nhập" : "Tạo tài khoản";
  $("authGo").textContent = login ? "Đăng nhập" : "Tạo tài khoản";
  $("authSwap").textContent = login ? "Chưa có tài khoản? Tạo tài khoản" : "Đã có tài khoản? Đăng nhập";
  $("pass").autocomplete = login ? "current-password" : "new-password";
  $("inviteRow").hidden = login || !inviteRequired;
  setAuthMsg("");
}

function showAuth(msg = "") { epoch++; me = null; $("auth").hidden = false; renderAuthMode(); if (msg) setAuthMsg(msg); }

async function enter() {
  $("auth").hidden = true; $("who").textContent = me;
  await loadChats(); await openChat(null);
}

$("authSwap").onclick = () => { authMode = authMode === "login" ? "register" : "login"; renderAuthMode(); };
$("authForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const username = $("user").value.trim(), password = $("pass").value;
  if (!/^[A-Za-z0-9_.-]{3,30}$/.test(username)) { setAuthMsg("Tên đăng nhập gồm 3–30 ký tự: chữ không dấu, số, dấu _ . -"); return; }
  if (password.length < 8) { setAuthMsg("Mật khẩu cần ít nhất 8 ký tự."); return; }
  $("authGo").disabled = true;
  try {
    const d = await api(`/api/auth/${authMode}`, "POST", { username, password, invite_code: $("invite").value });
    $("pass").value = "";
    if (authMode === "register") {
      // Đăng ký xong: quay về trang đăng nhập với form trống
      $("user").value = ""; $("invite").value = "";
      authMode = "login"; renderAuthMode();
      setAuthMsg("Đăng ký thành công. Hãy đăng nhập.", true);
      $("user").focus();
    } else {
      me = d.username;
      await enter();
    }
  } catch (err) { if (!err.auth) setAuthMsg(err.message); }
  $("authGo").disabled = false;
});
$("logout").onclick = async () => {
  try { await api("/api/auth/logout", "POST"); } catch {}
  chats = []; msgs = []; currentId = null; showAuth();
};


/* Sự kiện */
$("input").addEventListener("input", autosize);
$("input").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); send($("input").value); }
});
$("send").onclick = () => send($("input").value);
$("newChat").onclick = () => { openChat(null); $("input").focus(); };
$("menu").onclick = () => $("app").classList.add("open");
$("app").addEventListener("click", (e) => { if (e.target === $("app")) $("app").classList.remove("open"); });
$("lang").onchange = (e) => { opts.lang = e.target.value; saveOpts(); };
$("social").onchange = (e) => { opts.social = e.target.checked; saveOpts(); };

/* Khởi tạo */
$("lang").value = opts.lang; $("social").checked = opts.social;
$("chips").replaceChildren(...EXAMPLES.map((t) => { const b = el("button", "", t); b.type = "button"; b.onclick = () => send(t); return b; }));
(async () => {
  try {
    const st = await (await fetch("/api/auth/me")).json();
    inviteRequired = st.invite_required;
    if (st.user) { me = st.user; await enter(); } else showAuth();
  } catch { showAuth(); setAuthMsg("Không kết nối được máy chủ."); }
})();