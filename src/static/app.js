const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const today = () => new Date().toLocaleDateString("sv"); // YYYY-MM-DD（本地时区）
const addDays = (iso, n) => { const d = new Date(iso + "T00:00"); d.setDate(d.getDate() + n); return d.toLocaleDateString("sv"); };
const splitList = (s) => s.split(/[,，、\s]+/).map((x) => x.trim()).filter(Boolean);

// 出错时后端返回公共库的格式 {"Error": {"Title", "Method", "ErrorMsg"}}。
// 公共库的中间件遇到未处理的异常时 HTTP 状态码也是 200，所以成功的响应也要检查 Error。
async function api(path, opts = {}) {
  const res = await fetch(path, { headers: { "Content-Type": "application/json" }, ...opts });
  if (res.status === 204) return null;
  let data = null;
  try { data = await res.json(); } catch {}
  const err = data && !Array.isArray(data) ? data.Error ?? (res.ok ? null : data.detail) : null;
  if (err || !res.ok) {
    throw new Error(typeof err === "string" ? err : err?.ErrorMsg || (err ? JSON.stringify(err) : res.statusText));
  }
  return data;
}

function toast(msg) {
  const t = $("#toast"); t.textContent = msg; t.classList.add("show");
  clearTimeout(t._h); t._h = setTimeout(() => t.classList.remove("show"), Math.max(1800, msg.length * 120));
}

const statusLabel = (f) => ({
  expired: `过期 ${-f.days_left} 天`,
  expiring: f.days_left === 0 ? "今天到期" : `剩 ${f.days_left} 天`,
  fresh: "新鲜",
  none: "不限期",
})[f.status];
const isUrgent = (f) => f.status === "expired" || f.status === "expiring";
const md = (iso) => iso.slice(5).replace("-", "/");                       // 2026-11-21 → 11/21
// 已存天数：优先用后端给的 days_stored，没有就按存入日期自己算（本地时区）
const daysSince = (iso) => Math.round((new Date(today() + "T00:00") - new Date(iso + "T00:00")) / 86400000);
const storedText = (f) => {
  const d = Number.isFinite(f.days_stored) ? f.days_stored : daysSince(f.added_date);
  return d <= 0 ? "今天" : `${d}天前`;
};

// ---------------------------------------------------------------- 主题（自动 / 浅色 / 深色）
// 自动 = 跟随浏览器报告的系统深浅色；有些手机浏览器不报告，可以手动固定。选择保存在本机浏览器。
const THEMES = ["auto", "light", "dark"];
const THEME_TEXT = { auto: "自动", light: "浅色", dark: "深色" };
const darkMQ = matchMedia("(prefers-color-scheme: dark)");
const themeMetas = $$('meta[name="theme-color"]').map((m) => ({ el: m, content: m.content, media: m.media }));

function getTheme() {
  try { const t = localStorage.getItem("theme"); return THEMES.includes(t) ? t : "auto"; } catch { return "auto"; }
}
function applyTheme(t) {
  if (t === "auto") delete document.documentElement.dataset.theme;
  else document.documentElement.dataset.theme = t;
  // 手动固定时，地址栏颜色也固定；自动时恢复按系统切换
  themeMetas.forEach(({ el, content, media }) => {
    if (t === "auto") { el.media = media; el.content = content; }
    else { el.removeAttribute("media"); el.content = t === "dark" ? "#1a2029" : "#ffffff"; }
  });
  const sys = darkMQ.matches ? "深色" : "浅色";
  const btn = $("#theme-toggle");
  btn.textContent = t === "auto" ? `🌓 自动（${sys}）` : t === "dark" ? "🌙 深色" : "☀️ 浅色";
  btn.title = `当前：${THEME_TEXT[t]}；浏览器报告的系统模式：${sys}。点击切换：自动 → 浅色 → 深色`;
}
$("#theme-toggle").addEventListener("click", () => {
  const next = THEMES[(THEMES.indexOf(getTheme()) + 1) % THEMES.length];
  try { if (next === "auto") localStorage.removeItem("theme"); else localStorage.setItem("theme", next); } catch {}
  applyTheme(next);
  toast(`主题：${THEME_TEXT[next]}`);
});
darkMQ.addEventListener?.("change", () => applyTheme(getTheme()));   // 系统切换夜间模式时更新按钮文字
applyTheme(getTheme());

// ---------------------------------------------------------------- 标签页
$$(".tab").forEach((btn) => btn.addEventListener("click", () => {
  $$(".tab").forEach((b) => b.classList.toggle("active", b === btn));
  $$(".panel").forEach((p) => p.classList.toggle("active", p.id === btn.dataset.tab));
  if (btn.dataset.tab === "recommend") loadRecommend();
  if (btn.dataset.tab === "library") loadRecipes();
  if (btn.dataset.tab === "shopping") loadShopping();
}));
const switchTab = (name) => $(`.tab[data-tab="${name}"]`).click();

// ---------------------------------------------------------------- 冰箱
let foods = [];
const foodForm = $("#food-form");

// 数量只能从这些里选
const SHORTAGE = "缺货";   // 选"缺货" = 加入补货清单，不放进冰箱
const QUANTITIES = [SHORTAGE, "见底", ...Array.from({ length: 10 }, (_, i) => `${i + 1}份`), "很多"];
const DEFAULT_QTY = "1份";
foodForm.quantity.innerHTML = QUANTITIES.map((q) => `<option${q === DEFAULT_QTY ? " selected" : ""}>${q}</option>`).join("");

/** 设置数量；不在选项里的旧数据（如"3 个"）临时加一个选项，避免编辑时丢失。 */
function setQuantity(q) {
  $$("option.legacy", foodForm.quantity).forEach((o) => o.remove());
  if (q && !QUANTITIES.includes(q)) {
    foodForm.quantity.insertAdjacentHTML("afterbegin", `<option class="legacy" value="${esc(q)}">${esc(q)}（旧）</option>`);
  }
  foodForm.quantity.value = q || DEFAULT_QTY;
  syncShortage();
}
const qtyClass = (q) => q === "见底" ? "qty-low" : q === "很多" ? "qty-many" : "";

// 选了"缺货"：不需要保质期，保存按钮变成"加入补货清单"
function syncShortage() {
  const out = foodForm.quantity.value === SHORTAGE;
  const cb = $("#no-expiry");
  if (!cb) return;
  if (out) setNoExpiry(true);
  cb.disabled = out;
  $$(".quick button", foodForm).forEach((b) => (b.disabled = out));
  $("button[type=submit]", foodForm).textContent = out ? "加入补货清单" : "保存";
}
foodForm.quantity.addEventListener("change", () => {
  if (foodForm.quantity.value !== SHORTAGE && $("#no-expiry").disabled) setNoExpiry(false);
  syncShortage();
});

// "不设保质期"：勾上后禁用日期框，提交时不带 expiry_date
const noExpiry = $("#no-expiry");
function setNoExpiry(on) {
  noExpiry.checked = on;
  foodForm.expiry_date.disabled = on;
  foodForm.expiry_date.required = !on;
}
noExpiry.addEventListener("change", () => setNoExpiry(noExpiry.checked));

function resetFoodForm() {
  foodForm.reset();
  setNoExpiry(false);
  setQuantity(DEFAULT_QTY);
  foodForm.id.value = "";
  foodForm.added_date.value = today();
  foodForm.expiry_date.value = addDays(today(), 7);
  $("#food-form-title").textContent = "添加食材";
  $("#food-cancel").hidden = true;
  $$("#presets button").forEach((b) => b.classList.remove("picked"));
}

async function loadFoods() {
  foods = await api("/api/foods");
  renderFoods();
}

// 种类筛选下拉：表单里的种类 + 数据里出现过的种类，带数量（冰箱页和补货清单页共用）
function renderCategoryFilter(sel = $("#food-category"), items = foods) {
  const cur = sel.value;
  const count = {};
  items.forEach((f) => { count[f.category] = (count[f.category] || 0) + 1; });
  const cats = [...new Set([...[...foodForm.category.options].map((o) => o.value), ...Object.keys(count)])];
  sel.innerHTML = `<option value="">全部种类</option>` + cats.map((c) =>
    `<option value="${esc(c)}"${count[c] ? "" : " disabled"}>${esc(c)}（${count[c] || 0}）</option>`).join("");
  sel.value = cats.includes(cur) ? cur : "";
}

function renderFoods() {
  const counts = { expired: 0, expiring: 0, fresh: 0, none: 0 };
  foods.forEach((f) => counts[f.status]++);
  $("#summary").innerHTML = `
    <div class="stat"><b>${foods.length}</b>全部食材</div>
    <div class="stat expired"><b>${counts.expired}</b>已过期</div>
    <div class="stat expiring" title="食材 3 天内到期；药品 2 个月内到期（在 config.json 里设置）"><b>${counts.expiring}</b>快过期</div>
    <div class="stat fresh"><b>${counts.fresh + counts.none}</b>新鲜</div>`;
  renderCategoryFilter();

  const q = $("#food-search").value.trim();
  const cat = $("#food-category").value;
  const st = $("#food-filter").value;
  const list = foods.filter((f) => (!q || f.name.includes(q) || f.category.includes(q))
    && (!cat || f.category === cat) && (!st || f.status === st));
  $("#food-list").innerHTML = list.length ? list.map((f) => `
    <tr class="${f.status}">
      <td class="c-name">${esc(f.name)}${f.note ? `<span class="note">${esc(f.note)}</span>` : ""}</td>
      <td class="c-qty"><span class="${qtyClass(f.quantity)}">${esc(f.quantity)}</span></td>
      <td class="c-cat">${esc(f.category)}</td>
      <td class="c-added">${md(f.added_date)} <small>${storedText(f)}</small></td>
      <td class="c-expiry">${isUrgent(f) ? md(f.expiry_date) : ""}</td>
      <td class="c-status"><span class="badge ${f.status}">${statusLabel(f)}</span></td>
      <td class="c-meta">${[f.quantity ? `<span class="${qtyClass(f.quantity)}">${esc(f.quantity)}</span>` : "",
        esc(f.category), `存入 ${md(f.added_date)}（${storedText(f)}）`,
        isUrgent(f) ? `<span class="due">到期 ${md(f.expiry_date)}</span>` : ""].filter(Boolean).join(" · ")}</td>
      <td class="ops"><button data-edit="${f.id}">编辑</button>${f.quantity === "见底" ? ""
        : `<button data-low="${f.id}" title="数量改为见底，补货清单页会提醒">见底</button>`}<button
        data-eaten="${f.id}" title="从冰箱移除，并加入补货清单">吃完</button><button
        data-del="${f.id}" class="danger" title="直接删除，不加入补货清单">删除</button></td>
    </tr>`).join("")
    : `<tr><td colspan="7" class="empty">${foods.length ? "没有匹配的食材" : "冰箱空空如也，先添加一些食材吧"}</td></tr>`;
}

foodForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const data = Object.fromEntries(new FormData(foodForm));
  const id = data.id; delete data.id;
  if (data.expiry_date && data.expiry_date < data.added_date) return toast("保质期不能早于存入日期");
  try {
    const r = await api(id ? `/api/foods/${id}` : "/api/foods", { method: id ? "PUT" : "POST", body: JSON.stringify(data) });
    if (data.quantity === SHORTAGE) toast(r.duplicate ? `「${r.name}」已经在补货清单里了` : `已加入补货清单：${r.name}`);
    else toast((id ? "已更新" : `已添加：${r.name}`) + (r.restocked ? "，已从补货清单移除" : ""));
    resetFoodForm();
    loadFoods();
    loadShopping();
  } catch (err) { toast("保存失败：" + err.message); }
});

$("#food-cancel").addEventListener("click", resetFoodForm);

// 食材预设：点一下自动填名称、分类、数量和保质期
let presets = [];
async function loadPresets() {
  presets = await api("/api/presets");
  $("#presets").innerHTML = presets.length
    ? `<span>常用：</span>` + presets.map((p, i) =>
        `<button type="button" data-preset="${i}" title="冷藏约 ${p.shelf_days} 天">${esc(p.name)}</button>`).join("")
    : "";
}
function applyPreset(p) {
  foodForm.name.value = p.name;
  foodForm.category.value = p.category || "其他";
  setQuantity(QUANTITIES.includes(p.quantity) ? p.quantity : DEFAULT_QTY);
  setNoExpiry(false);
  foodForm.expiry_date.value = addDays(foodForm.added_date.value || today(), p.shelf_days ?? 7);
  $$("#presets button").forEach((b) => b.classList.toggle("picked", presets[b.dataset.preset] === p));
}
$("#presets").addEventListener("click", (e) => {
  const p = presets[e.target.dataset.preset];
  if (!p) return;
  applyPreset(p);
  foodForm.quantity.focus();
});

// ---------------------------------------------------------------- 名称下拉：食谱里用到的食材 + 文字筛选
let ingredientIndex = [];   // [{name, count, kind: "main" | "seasoning"}]，按使用次数排序
let comboItems = [], comboActive = -1;
let armedForget = null;   // 点过 × 、等待第二次确认的输入记录名
const nameInput = foodForm.name, comboList = $("#name-combo");

const KIND_ORDER = { history: 0, main: 1, member: 2, seasoning: 3 };
const KIND_TEXT = { history: "我记录过的", main: "食谱主料", member: "大类里的食材", seasoning: "调料" };

// 输入记录：输入过的每样东西和最近用的种类（删了食材也保留），用于名称建议和自动选种类
let itemHistory = [], historyMap = new Map();
async function loadHistory() {
  itemHistory = await api("/api/history");
  historyMap = new Map(itemHistory.map((h) => [h.name, h]));
  buildIngredientIndex();
}
// 名称是记录过的就自动选上次用的种类（form 是冰箱页或补货清单页的表单）
function fillCategoryFromHistory(form) {
  const h = historyMap.get(form.name.value.trim());
  if (h && [...form.category.options].some((o) => o.value === h.category)) form.category.value = h.category;
  return h;
}

function buildIngredientIndex() {
  const m = new Map();
  const groupNames = new Set(groups.map((g) => g.name));
  // 记录过的排最前，最近用过的在前（后端已排好）；同时出现在食谱里的也归到这一组
  itemHistory.forEach((h, order) => m.set(h.name, {
    name: h.name, count: 0, kind: "history", category: h.category, uses: h.use_count, order }));
  for (const r of library) {
    for (const [list, kind] of [[r.ingredients, "main"], [r.seasonings, "seasoning"]]) {
      for (const n of new Set(list)) {
        if (groupNames.has(n)) continue;          // 大类名（如"菌菇"）不是具体食材，不放进冰箱名称下拉
        const e = m.get(n) || { name: n, count: 0, kind };
        e.count++;
        if (kind === "main" && e.kind !== "history") e.kind = "main";   // 在任一道菜里当过主料就算主料
        m.set(n, e);
      }
    }
  }
  // 大类里列出的具体食材（如"羊角菇"），即使还没有食谱直接用到，也能在下拉里选
  for (const g of groups) {
    for (const n of g.members) {
      if (!groupNames.has(n) && !m.has(n)) m.set(n, { name: n, count: 0, kind: "member", group: g.name });
    }
  }
  ingredientIndex = [...m.values()].sort((a, b) => KIND_ORDER[a.kind] - KIND_ORDER[b.kind]
    || (a.kind === "history" ? a.order - b.order : b.count - a.count || a.name.localeCompare(b.name, "zh")));
  renderShopHints();
  // 食谱编辑器的食材名提示：大类名 + 食谱里用过的主料
  $("#ing-hints").innerHTML = [...groups.map((g) => [g.name, `大类：${g.members.slice(0, 6).join("、")}…`]),
    ...ingredientIndex.filter((x) => x.kind === "main").map((x) => [x.name, ""])]
    .map(([v, l]) => `<option value="${esc(v)}"${l ? ` label="${esc(l)}"` : ""}>`).join("");
}

function renderCombo() {
  const q = nameInput.value.trim();
  const have = new Set(foods.filter((f) => f.status !== "expired").map((f) => f.name));
  comboItems = ingredientIndex.filter((x) => !q || x.name.includes(q)).slice(0, 80);
  comboActive = -1;
  const mark = (s) => q ? esc(s).replaceAll(esc(q), `<mark>${esc(q)}</mark>`) : esc(s);
  let lastKind = null;
  comboList.innerHTML = comboItems.length ? comboItems.map((x, i) => {
    const head = x.kind !== lastKind ? `<li class="combo-group" role="presentation">${KIND_TEXT[x.kind]}</li>` : "";
    lastKind = x.kind;
    const info = x.kind === "history" ? `${esc(x.category)} · ${x.uses} 次`
      : x.kind === "member" ? `属于${esc(x.group)}` : `${x.count} 道菜`;
    // 删除记录要两次确认：点 × 先变成红色的"删除？"（第 1 次），再点它弹出确认框（第 2 次）
    const forget = x.kind !== "history" ? ""
      : x.name === armedForget
        ? `<button type="button" class="combo-forget armed" data-forget-confirm="${esc(x.name)}" title="再点一次确认删除">删除？</button>`
        : `<button type="button" class="combo-forget" data-forget="${esc(x.name)}" title="删除这条记录（打错的名字）" aria-label="删除记录">×</button>`;
    return `${head}<li class="combo-item" role="option" data-i="${i}">
      <span>${mark(x.name)}${have.has(x.name) ? ` <em class="have-tag">已有</em>` : ""}</span>
      <small>${info}${forget}</small></li>`;
  }).join("") : `<li class="combo-empty">${ingredientIndex.length ? `没有"${esc(q)}"，直接保存即可，下次就会出现在这里` : "还没有记录"}</li>`;
  comboList.hidden = false;
  nameInput.setAttribute("aria-expanded", "true");
}

function closeCombo() {
  armedForget = null;
  comboList.hidden = true;
  nameInput.setAttribute("aria-expanded", "false");
}

function pickCombo(i) {
  const x = comboItems[i];
  if (!x) return;
  const p = presets.find((p) => p.name === x.name);
  if (p) applyPreset(p); else nameInput.value = x.name;
  fillCategoryFromHistory(foodForm);   // 记录过的用上次的种类（比预设的优先）
  closeCombo();
  foodForm.quantity.focus();
}

function moveCombo(d) {
  const items = $$(".combo-item", comboList);
  if (!items.length) return;
  comboActive = (comboActive + d + items.length) % items.length;
  items.forEach((el, i) => el.classList.toggle("active", i === comboActive));
  items[comboActive].scrollIntoView({ block: "nearest" });
}

nameInput.addEventListener("focus", renderCombo);
nameInput.addEventListener("input", () => { armedForget = null; renderCombo(); });   // 打字就取消待删除
nameInput.addEventListener("keydown", (e) => {
  if (comboList.hidden && (e.key === "ArrowDown" || e.key === "ArrowUp")) { renderCombo(); return; }
  if (e.key === "ArrowDown") { e.preventDefault(); moveCombo(1); }
  else if (e.key === "ArrowUp") { e.preventDefault(); moveCombo(-1); }
  else if (e.key === "Enter" && !comboList.hidden && comboActive >= 0) { e.preventDefault(); pickCombo(comboActive); }
  else if (e.key === "Escape") closeCombo();
});
// 用 mousedown 而不是 click：避免输入框先失焦把列表关掉
comboList.addEventListener("mousedown", async (e) => {
  const arm = e.target.closest("[data-forget]");
  if (arm) {      // 第 1 次确认：× 变成"删除？"，列表保持打开
    e.preventDefault();
    armedForget = arm.dataset.forget;
    renderCombo();
    return;
  }
  const forget = e.target.closest("[data-forget-confirm]");
  if (forget) {   // 第 2 次确认：弹出确认框
    e.preventDefault();
    const name = forget.dataset.forgetConfirm;
    armedForget = null;
    if (!confirm(`删除输入记录「${name}」？\n（只是不再出现在建议里，冰箱里的东西不受影响）`)) {
      nameInput.focus();
      renderCombo();
      return;
    }
    try {
      await api(`/api/history/${encodeURIComponent(name)}`, { method: "DELETE" });
      await loadHistory();
      renderCombo();
      nameInput.focus();
    } catch (err) { toast("删除失败：" + err.message); }
    return;
  }
  const li = e.target.closest(".combo-item");
  if (!li) return;
  e.preventDefault();
  pickCombo(+li.dataset.i);
});
nameInput.addEventListener("blur", () => setTimeout(closeCombo, 100));
// 直接打出记录过的完整名字（没从下拉里选）也自动选种类
nameInput.addEventListener("input", () => fillCategoryFromHistory(foodForm));
$$(".quick button").forEach((b) => b.addEventListener("click", () => {
  if (foodForm.quantity.value === SHORTAGE) setQuantity(DEFAULT_QTY);
  setNoExpiry(false);
  foodForm.expiry_date.value = addDays(foodForm.added_date.value || today(), +b.dataset.days);
}));
$("#food-search").addEventListener("input", renderFoods);
$("#food-category").addEventListener("change", renderFoods);
$("#food-filter").addEventListener("change", renderFoods);

$("#food-list").addEventListener("click", async (e) => {
  const editId = e.target.dataset.edit, delId = e.target.dataset.del;
  if (editId) {
    const f = foods.find((x) => x.id == editId);
    for (const k of ["id", "name", "category", "added_date", "note"]) foodForm[k].value = f[k];
    setQuantity(f.quantity);
    setNoExpiry(!f.expiry_date);
    foodForm.expiry_date.value = f.expiry_date || addDays(f.added_date, 7);
    $("#food-form-title").textContent = `编辑：${f.name}`;
    $("#food-cancel").hidden = false;
    foodForm.scrollIntoView({ behavior: "smooth" });
  } else if (delId) {
    const f = foods.find((x) => x.id == delId);
    if (!confirm(`确定删除「${f.name}」吗？\n（不会加入补货清单；想提醒自己再买请用"吃完"）`)) return;
    await api(`/api/foods/${delId}`, { method: "DELETE" });
    toast("已删除"); loadFoods().then(renderShopping);
  } else if (e.target.dataset.low || e.target.dataset.eaten) {
    const id = e.target.dataset.low || e.target.dataset.eaten;
    const f = foods.find((x) => x.id == id);
    const eaten = !!e.target.dataset.eaten;
    // 吃完：数量改为"缺货"，存入日期改为今天（= 加入补货清单的日期），后端会清掉保质期
    const body = { name: f.name, category: f.category, note: f.note, added_date: eaten ? today() : f.added_date,
                   expiry_date: eaten ? null : f.expiry_date, quantity: eaten ? SHORTAGE : "见底" };
    try {
      const r = await api(`/api/foods/${id}`, { method: "PUT", body: JSON.stringify(body) });
      toast(eaten ? (r.duplicate ? `${f.name} 吃完了（补货清单里已有）` : `${f.name} 吃完了，已加入补货清单`)
                  : `${f.name} 标记为见底`);
      await loadFoods();
      loadShopping();
    } catch (err) { toast("操作失败：" + err.message); }
  }
});

// ---------------------------------------------------------------- 补货清单
let shopping = [];
const shopForm = $("#shop-form");
shopForm.category.innerHTML = [...foodForm.category.options].map((o) => `<option${o.value === "其他" ? " selected" : ""}>${esc(o.value)}</option>`).join("");

async function addShortage(name, category = "其他", note = "") {
  return api("/api/foods", { method: "POST", body: JSON.stringify({ name, category, note, quantity: SHORTAGE }) });
}

// 每次添加 / 修改食材或补货后都会调用这里，顺便刷新输入记录（后端在保存时已经记下了）
async function loadShopping() {
  shopping = await api("/api/shopping");
  renderShopping();
  loadHistory().catch(() => {});
}

function renderShopping() {
  const n = shopping.length;
  $("#shop-count").textContent = n;
  $("#shop-count").hidden = !n;
  // 按种类筛选（同时作用于"快用完了"）。药品等排在最下面由后端排好
  renderCategoryFilter($("#shop-category"), shopping);
  const cat = $("#shop-category").value;
  const list = shopping.filter((s) => !cat || s.category === cat);
  $("#shop-summary").textContent = !n ? "" : cat ? `${cat} ${list.length} 样 / 共 ${n} 样` : `共 ${n} 样`;
  $("#shop-list").innerHTML = list.length ? list.map((s) => `
    <div class="shop-item">
      <div class="shop-main">
        <b>${esc(s.name)}</b> <span class="muted">${esc(s.category)}</span>
        ${s.note ? `<div class="note">${esc(s.note)}</div>` : ""}
        <div class="muted small">加入于 ${md(s.added_date)}（${storedText(s)}）</div>
      </div>
      <div class="shop-ops">
        <button class="primary" data-bought="${s.id}">✅ 买到了</button>
        <button data-unshop="${s.id}">删除</button>
      </div>
    </div>`).join("")
    : n ? `<div class="empty">没有要买的${esc(cat)}</div>`
    : `<div class="empty">补货清单是空的 👍<br><small>食材数量选"缺货"，或在上面直接添加</small></div>`;

  // 冰箱里"见底"的食材，提示加入清单
  const inList = new Set(shopping.map((s) => s.name));
  const low = foods.filter((f) => f.quantity === "见底" && (!cat || f.category === cat));
  $("#low-wrap").hidden = !low.length;
  $("#low-list").innerHTML = low.map((f) => `
    <div class="shop-item">
      <div class="shop-main"><b>${esc(f.name)}</b> <span class="muted">${esc(f.category)}</span>
        <div class="muted small">存入 ${md(f.added_date)}（${storedText(f)}）</div></div>
      <div class="shop-ops">${inList.has(f.name) ? `<span class="badge have">已在清单</span>`
        : `<button data-low="${f.id}">加入补货清单</button>`}</div>
    </div>`).join("");
}

// 补货清单页"要买什么"的提示：记录过的在前（带上次的种类），然后是食谱里的食材
function renderShopHints() {
  const names = [...new Set([...ingredientIndex.map((x) => x.name), ...foods.map((f) => f.name)])];
  $("#shop-hints").innerHTML = names.map((x) => {
    const h = historyMap.get(x);
    return `<option value="${esc(x)}"${h ? ` label="${esc(h.category)}"` : ""}>`;
  }).join("");
}
shopForm.name.addEventListener("input", () => fillCategoryFromHistory(shopForm));

$("#shop-category").addEventListener("change", renderShopping);

shopForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    const r = await addShortage(shopForm.name.value.trim(), shopForm.category.value, shopForm.note.value.trim());
    toast(r.duplicate ? `「${r.name}」已经在清单里了` : `已加入：${r.name}`);
    shopForm.name.value = ""; shopForm.note.value = "";
    shopForm.name.focus();
    loadShopping();
  } catch (err) { toast("添加失败：" + err.message); }
});

// 买到了：跳到食材页，预填好表单，保存后后端会自动把清单里这一项删掉
function restock(item) {
  switchTab("fridge");
  resetFoodForm();
  const p = presets.find((p) => p.name === item.name);
  if (p) applyPreset(p);
  else { foodForm.name.value = item.name; foodForm.category.value = item.category; }
  $("#food-form-title").textContent = `补货：${item.name}（保存后自动从补货清单移除）`;
  $("#food-cancel").hidden = false;
  foodForm.scrollIntoView({ behavior: "smooth" });
  foodForm.quantity.focus();
}

$("#shopping").addEventListener("click", async (e) => {
  const d = e.target.dataset;
  if (d.bought) restock(shopping.find((s) => s.id == d.bought));
  else if (d.unshop) {
    const s = shopping.find((s) => s.id == d.unshop);
    if (!confirm(`从补货清单删除「${s.name}」？`)) return;
    await api(`/api/foods/${d.unshop}`, { method: "DELETE" });
    toast("已删除"); loadShopping();
  } else if (d.low) {
    const f = foods.find((f) => f.id == d.low);
    await addShortage(f.name, f.category);
    toast(`已加入补货清单：${f.name}`); loadShopping();
  }
});

// 今日一荤一素里"还需要买"的食材一键加入
$("#daily-shopping").addEventListener("click", async (e) => {
  if (!e.target.classList.contains("add-missing")) return;
  const names = JSON.parse(e.target.dataset.names);
  const rs = await Promise.all(names.map((n) => addShortage(n)));
  const added = rs.filter((r) => !r.duplicate).length;
  toast(added ? `已加入补货清单 ${added} 样` + (added < names.length ? `（${names.length - added} 样已在清单里）` : "") : "都已经在补货清单里了");
  loadShopping();
});

// ---------------------------------------------------------------- 推荐
let recipeCache = {};
const typeBadge = (r, clickable = false) =>
  `<span class="badge type-${r.type === "荤" ? "meat" : "veg"}${clickable ? " toggle" : ""}"
     ${clickable ? `data-toggle-type="${r.id}" title="点击切换荤/素"` : ""}>${r.type || "?"}</span>`;

// 食材标签：大类名加虚线框，鼠标悬停显示包含哪些；推荐里显示实际用的是冰箱里哪样（菌菇（干香菇））
function ingBadge(x, cls, r = null, extra = "") {
  const g = groups.find((g) => g.name === x);
  const used = r?.used?.[x];
  return `<span class="badge ${cls}${g ? " group" : ""}"${g ? ` title="大类，包含：${esc(g.expanded.join("、"))}"` : ""}>${esc(x)}${
    used ? `<small>（${esc(used)}）</small>` : ""}${extra}</span>`;
}

// hits：食谱库按原材料筛选时命中的食材 / 调料名，卡片上高亮
function recipeCard(r, { recommend = false, hits = null } = {}) {
  recipeCache[r.id] = r;
  const hitSeasonings = hits ? r.seasonings.filter((x) => hits.has(x)) : [];
  const tags = recommend
    ? r.have.map((x) => ingBadge(x, "have", r)).join("") + r.missing.map((x) => ingBadge(x, "missing")).join("")
    : r.ingredients.map((x) => ingBadge(x, hits?.has(x) ? "fresh hit" : "fresh")).join("") +
      hitSeasonings.map((x) => ingBadge(x, "seasoning hit")).join("");
  return `
    <div class="card recipe" data-recipe="${r.id}">
      <h3><span>${typeBadge(r, !recommend)} ${esc(r.name)}</span>
        ${recommend ? "" : `<span class="card-ops"><button class="del" data-edit-recipe="${r.id}">编辑</button><button class="del" data-del-recipe="${r.id}">删除</button></span>`}</h3>
      <div class="meta">⏱ ${r.minutes} 分钟${recommend ? ` · ${r.missing.length ? `还缺 ${r.missing.length} 种` : "食材齐全 ✅"}` : ""}</div>
      ${recommend ? `<div class="bar"><i style="width:${r.match_rate * 100}%"></i></div>` : ""}
      <div>${tags}</div>
      ${recommend && r.uses_expiring.length ? `<div class="hint">♻ 可消耗临期：${r.uses_expiring.map(esc).join("、")}</div>` : ""}
    </div>`;
}

// 分段按钮（全部/荤菜/素菜）
function segValue(id) { return $(`#${id} .on`).dataset.type; }
function bindSeg(id, onChange) {
  $(`#${id}`).addEventListener("click", (e) => {
    if (e.target.dataset.type === undefined) return;
    $$(`#${id} button`).forEach((b) => b.classList.toggle("on", b === e.target));
    onChange();
  });
}

// 今日一荤一素：各取排名第 idx 个，"换一换"轮换到下一个
let daily = { 荤: [], 素: [] }, dailyIdx = { 荤: 0, 素: 0 };
let recommendList = [];

function renderDaily() {
  const pick = (t) => daily[t].length ? daily[t][dailyIdx[t] % daily[t].length] : null;
  const slot = (t) => {
    const r = pick(t), n = daily[t].length;
    const head = `<div class="daily-head"><b>${t === "荤" ? "🍖 荤菜" : "🥬 素菜"}</b>
      ${n > 1 ? `<button data-shuffle="${t}">换一换 (${dailyIdx[t] % n + 1}/${n})</button>` : ""}</div>`;
    return `<div class="daily-slot">${head}${r ? recipeCard(r, { recommend: true })
      : `<div class="card empty">没有可做的${t}菜，试试放宽"最多缺少"或添加食材</div>`}</div>`;
  };
  $("#daily").innerHTML = slot("荤") + slot("素");

  const missing = [...new Set(["荤", "素"].flatMap((t) => pick(t)?.missing ?? []))];
  $("#daily-shopping").innerHTML = missing.length
    ? `🛒 还需要买：${missing.map((x) => `<span class="badge missing-buy">${esc(x)}</span>`).join("")}
       <button type="button" class="add-missing" data-names="${esc(JSON.stringify(missing))}">加入补货清单</button>`
    : (pick("荤") && pick("素") ? "✅ 两道菜的食材冰箱里都有" : "");
}

function renderRecommendList() {
  const t = segValue("recommend-type");
  const list = recommendList.filter((r) => !t || r.type === t);
  $("#recommend-list").innerHTML = list.length
    ? list.map((r) => recipeCard(r, { recommend: true })).join("")
    : `<div class="empty card">没有合适的食谱。试试放宽"最多缺少"条件，或往冰箱里添加更多食材。</div>`;
}

async function loadRecommend() {
  const mm = $("#max-missing").value;
  [daily, recommendList] = await Promise.all([api(`/api/daily?max_missing=${mm}`), api(`/api/recommend?max_missing=${mm}`)]);
  dailyIdx = { 荤: 0, 素: 0 };
  renderDaily();
  renderRecommendList();
}
$("#max-missing").addEventListener("change", loadRecommend);
bindSeg("recommend-type", renderRecommendList);
$("#daily").addEventListener("click", (e) => {
  const t = e.target.dataset.shuffle;
  if (!t) return;
  e.stopPropagation();
  dailyIdx[t]++;
  renderDaily();
});

// ---------------------------------------------------------------- 食谱库
let library = [];
async function loadRecipes() {
  library = await api("/api/recipes");
  renderLibrary();
  buildIngredientIndex();
}
// 按原材料筛选：每个词都要在食谱里找到（多个词 = 同时用到）。
// 食材名包含这个词就算，比如"牛"能找到牛肉、牛腩；食谱写的是大类（如"菌菇"）时，
// 这个词和大类里某个食材完全相同（如"羊角菇"）也算。大类不按包含匹配，否则"牛"会因为"牛肝菌"找到菌菇的菜。
function ingredientHits(r, words, withSeasoning) {
  const names = withSeasoning ? [...r.ingredients, ...r.seasonings] : r.ingredients;
  const matchesWord = (n, w) => n.includes(w) || !!groups.find((g) => g.name === n)?.expanded.includes(w);
  const hits = new Set();
  for (const w of words) {
    const found = names.filter((n) => matchesWord(n, w));
    if (!found.length) return null;
    found.forEach((n) => hits.add(n));
  }
  return hits;
}

function renderLibrary() {
  const t = segValue("library-type");
  const words = splitList($("#library-ing").value);
  const withSeasoning = $("#library-ing-seasoning").checked;
  const list = [];
  for (const r of library) {
    if (t && r.type !== t) continue;
    const hits = words.length ? ingredientHits(r, words, withSeasoning) : null;
    if (words.length && !hits) continue;
    list.push({ r, hits });
  }
  const meat = library.filter((r) => r.type === "荤").length;
  $("#recipe-count").textContent = `共 ${library.length} 道（荤 ${meat} / 素 ${library.length - meat}）` +
    (words.length ? `，用到「${words.join("、")}」的有 ${list.length} 道` : "");
  $("#recipe-list").innerHTML = list.map(({ r, hits }) => recipeCard(r, { hits })).join("")
    || `<div class="empty card">${words.length ? `没有用到「${esc(words.join("、"))}」的食谱` : "没有食谱"}</div>`;
}
bindSeg("library-type", renderLibrary);
$("#library-ing").addEventListener("input", renderLibrary);
$("#library-ing-seasoning").addEventListener("change", renderLibrary);

$("#recipe-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = e.target;
  const body = {
    name: f.name.value.trim(),
    minutes: +f.minutes.value || 20,
    type: f.type.value || null,
    ingredients: splitList(f.ingredients.value),
    seasonings: splitList(f.seasonings.value),
    steps: f.steps.value.split("\n").map((s) => s.trim()).filter(Boolean),
  };
  try {
    const r = await api("/api/recipes", { method: "POST", body: JSON.stringify(body) });
    toast(`已添加${r.type}菜：${r.name}（${r.type_reason}）`); f.reset(); loadRecipes();
  } catch (err) { toast("添加失败：" + err.message); }
});

// 卡片点击：切换荤素 / 删除 / 查看详情
document.addEventListener("click", async (e) => {
  const toggleId = e.target.dataset.toggleType;
  if (toggleId) {
    const r = recipeCache[toggleId];
    const type = r.type === "荤" ? "素" : "荤";
    await api(`/api/recipes/${toggleId}`, { method: "PATCH", body: JSON.stringify({ type }) });
    toast(`「${r.name}」改为${type}菜`); loadRecipes(); return;
  }
  const editId = e.target.dataset.editRecipe;
  if (editId) {
    $("#recipe-dialog").close();
    editRecipe(editId); return;
  }
  const delId = e.target.dataset.delRecipe;
  if (delId) {
    if (!confirm(`确定从食谱库删除「${recipeCache[delId].name}」吗？`)) return;
    await api(`/api/recipes/${delId}`, { method: "DELETE" });
    toast("已删除"); loadRecipes(); return;
  }
  const card = e.target.closest("[data-recipe]");
  if (!card) return;
  const r = recipeCache[card.dataset.recipe];
  $("#dlg-title").textContent = `${r.name}（${r.type}菜 · ${r.minutes} 分钟）`;
  const amt = (x) => r.amounts?.[x] ? ` ${esc(r.amounts[x])}` : "";
  $("#dlg-body").innerHTML = `
    <p><b>主要食材：</b>${r.ingredients.map((x) => ingBadge(x, r.missing?.includes(x) ? "missing" : "have", r, amt(x))).join("")}</p>
    ${r.seasonings.length ? `<p><b>调料：</b>${r.seasonings.map((x) => esc(x) + amt(x)).join("、")}</p>` : ""}
    ${r.steps.length ? `<b>步骤：</b><ol>${r.steps.map((s) => `<li>${esc(s)}</li>`).join("")}</ol>` : ""}
    ${r.source_url ? `<p class="src"><a href="${esc(r.source_url)}" target="_blank" rel="noopener">查看原菜谱 →</a></p>` : ""}`;
  $("#dlg-edit").dataset.editRecipe = r.id;
  $("#recipe-dialog").showModal();
});

// ---------------------------------------------------------------- 从链接导入
const ROLE_TEXT = { main: "主料", seasoning: "调料", skip: "删除" };
const ie = $("#import-editor");
let ieSource = "", ieEditId = null;   // ieEditId 有值 = 编辑已有食谱，否则 = 保存为新食谱

/** 打开食谱编辑器。recipe 至少包含 name/minutes/steps/ingredients（[{name, amount, role}]）。 */
function openEditor(recipe, { title, editId = null, typeValue = "", hint = "" }) {
  ieEditId = editId;
  ieSource = recipe.source_url || "";
  $("#import-dialog h2").textContent = title;
  ie.name.value = recipe.name;
  ie.minutes.value = recipe.minutes;
  ie.type.value = typeValue;
  ie.steps.value = recipe.steps.join("\n");
  $("#ie-src").innerHTML = ieSource
    ? `来源：<a href="${esc(ieSource)}" target="_blank" rel="noopener">${esc(ieSource.slice(0, 60))}${ieSource.length > 60 ? "…" : ""}</a>`
    : "";
  $("#ie-type-hint").textContent = hint;
  $("#ie-ings").innerHTML = recipe.ingredients.map(ingRow).join("");
  $("button[value=save]", ie).textContent = editId ? "保存修改" : "保存到食谱库";
  updateIeCounts();
  $("#import-dialog").showModal();
}

function editRecipe(id) {
  const r = library.find((x) => x.id == id) || recipeCache[id];
  const row = (name, role) => ({ name, amount: r.amounts?.[name] || "", role });
  openEditor({
    ...r,
    ingredients: [...r.ingredients.map((x) => row(x, "main")), ...r.seasonings.map((x) => row(x, "seasoning"))],
  }, { title: `编辑食谱：${r.name}`, editId: r.id, typeValue: r.type });
}

function ingRow(ing = { name: "", amount: "", role: "main" }) {
  const roles = Object.entries(ROLE_TEXT).map(([k, t]) =>
    `<button type="button" data-role="${k}" class="${ing.role === k ? "on" : ""}">${t}</button>`).join("");
  return `
    <div class="ing-row role-${ing.role}" data-role="${ing.role}" data-orig="${ing.role}">
      <input class="ing-name" value="${esc(ing.name)}" placeholder="食材名或大类" list="ing-hints">
      <input class="ing-amount" value="${esc(ing.amount)}" placeholder="用量">
      <div class="seg role-seg">${roles}</div>
    </div>`;
}

function setRole(row, role) {
  row.dataset.role = role;
  row.className = `ing-row role-${role}`;
  $$(".role-seg button", row).forEach((b) => b.classList.toggle("on", b.dataset.role === role));
}

function updateIeCounts() {
  const rows = $$("#ie-ings .ing-row");
  const n = (r) => rows.filter((x) => x.dataset.role === r).length;
  $(".ie-head b").textContent = `食材（主料 ${n("main")} · 调料 ${n("seasoning")} · 删除 ${n("skip")}）`;
}

$("#import-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const btn = $("button", e.target), url = e.target.url.value.trim();
  btn.disabled = true; btn.textContent = "识别中…";
  try {
    const d = await api("/api/recipes/import", { method: "POST", body: JSON.stringify({ url }) });
    openEditor(d, {
      title: "编辑导入的食谱",
      hint: `按当前主料预计为${d.type}菜（${d.type_reason}）` + (d.exists ? "　⚠ 食谱库里已有同名食谱，请改个名字" : ""),
    });
    e.target.reset();
  } catch (err) { toast("识别失败：" + err.message); }
  finally { btn.disabled = false; btn.textContent = "识别食材"; }
});

$("#ie-ings").addEventListener("click", (e) => {
  const role = e.target.dataset.role;
  if (!role || e.target.tagName !== "BUTTON") return;
  setRole(e.target.closest(".ing-row"), role);
  updateIeCounts();
});
$(".ie-bulk").addEventListener("click", (e) => {
  const mode = e.target.dataset.bulk;
  if (!mode) return;
  $$("#ie-ings .ing-row").forEach((row) => {
    if (mode === "restore") setRole(row, row.dataset.orig);
    else if (row.dataset.role === "seasoning") setRole(row, "skip");
  });
  updateIeCounts();
});
$("#ie-add").addEventListener("click", () => {
  $("#ie-ings").insertAdjacentHTML("beforeend", ingRow());
  $("#ie-ings .ing-row:last-child .ing-name").focus();
  updateIeCounts();
});
$("#ie-cancel").addEventListener("click", () => $("#import-dialog").close());

ie.addEventListener("submit", async (e) => {
  e.preventDefault();
  const rows = $$("#ie-ings .ing-row").map((r) => ({
    name: $(".ing-name", r).value.trim(), amount: $(".ing-amount", r).value.trim(), role: r.dataset.role,
  })).filter((x) => x.name && x.role !== "skip");
  const ingredients = rows.filter((x) => x.role === "main").map((x) => x.name);
  if (!ingredients.length) return toast("至少保留一个主料");
  const body = {
    name: ie.name.value.trim(),
    minutes: +ie.minutes.value || 20,
    type: ie.type.value || null,
    ingredients,
    seasonings: rows.filter((x) => x.role === "seasoning").map((x) => x.name),
    amounts: Object.fromEntries(rows.filter((x) => x.amount).map((x) => [x.name, x.amount])),
    steps: ie.steps.value.split("\n").map((s) => s.trim()).filter(Boolean),
    source_url: ieSource,
  };
  try {
    const r = ieEditId
      ? await api(`/api/recipes/${ieEditId}`, { method: "PUT", body: JSON.stringify(body) })
      : await api("/api/recipes", { method: "POST", body: JSON.stringify(body) });
    $("#import-dialog").close();
    toast(ieEditId ? `已保存：${r.name}（${r.type}菜）` : `已导入${r.type}菜：${r.name}（${r.type_reason}）`);
    loadRecipes();
    if ($("#recommend").classList.contains("active")) loadRecommend();
  } catch (err) { toast("保存失败：" + err.message); }
});

// ---------------------------------------------------------------- 食材大类（右上角齿轮）
let groups = [];
const groupForm = $("#group-form");

async function loadGroups() {
  groups = await api("/api/groups");
  renderGroups();
  buildIngredientIndex();
  renderLibrary();   // 食谱卡片上的大类标记
}

function renderGroups() {
  $("#group-list").innerHTML = groups.length ? groups.map((g) => `
    <div class="group-item">
      <div><b>${esc(g.name)}</b>
        <div class="members">${g.members.map((m) => groups.some((x) => x.name === m)
          ? `<u title="也是大类">${esc(m)}</u>` : esc(m)).join("、")}</div></div>
      <div class="ops"><button type="button" data-edit-group="${g.id}">编辑</button><button
        type="button" class="danger" data-del-group="${g.id}">删除</button></div>
    </div>`).join("")
    : `<div class="empty">还没有大类</div>`;
}

function resetGroupForm() {
  groupForm.reset();
  groupForm.id.value = "";
  $("#group-form-title").textContent = "新建大类";
  $("#group-cancel").hidden = true;
}

$("#open-groups").addEventListener("click", () => {
  resetGroupForm();
  $("#groups-dialog").showModal();
  loadGroups().catch((err) => toast("读取大类失败：" + err.message));
});
$("#group-cancel").addEventListener("click", resetGroupForm);

$("#group-list").addEventListener("click", async (e) => {
  const d = e.target.dataset;
  if (d.editGroup) {
    const g = groups.find((g) => g.id == d.editGroup);
    groupForm.id.value = g.id;
    groupForm.name.value = g.name;
    groupForm.members.value = g.members.join("、");
    $("#group-form-title").textContent = `编辑：${g.name}`;
    $("#group-cancel").hidden = false;
    groupForm.name.focus();
  } else if (d.delGroup) {
    const g = groups.find((g) => g.id == d.delGroup);
    const used = library.filter((r) => r.ingredients.includes(g.name)).length;
    if (!confirm(`删除大类「${g.name}」？` + (used ? `\n有 ${used} 道食谱用到了它，删除后只能匹配叫"${g.name}"的食材。` : ""))) return;
    try {
      await api(`/api/groups/${g.id}`, { method: "DELETE" });
      toast("已删除"); resetGroupForm(); await loadGroups(); refreshAfterGroups();
    } catch (err) { toast("删除失败：" + err.message); }
  }
});

groupForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const id = groupForm.id.value;
  const body = { name: groupForm.name.value.trim(), members: splitList(groupForm.members.value) };
  if (!body.members.length) return toast("至少包含一样食材");
  try {
    const g = await api(id ? `/api/groups/${id}` : "/api/groups", { method: id ? "PUT" : "POST", body: JSON.stringify(body) });
    toast(`已保存大类：${g.name}（${g.members.length} 样）`);
    resetGroupForm(); await loadGroups(); refreshAfterGroups();
  } catch (err) { toast("保存失败：" + err.message); }
});

// 大类改了，推荐结果和食谱卡片上的标记跟着更新
function refreshAfterGroups() {
  if ($("#recommend").classList.contains("active")) loadRecommend();
}

// ---------------------------------------------------------------- 启动
resetFoodForm();
api("/api/version").then((v) => { $("#app-version").textContent = "v" + v.version; }).catch(() => {});
loadPresets();
loadFoods().then(loadShopping);
loadRecipes();
loadGroups();
loadHistory();
