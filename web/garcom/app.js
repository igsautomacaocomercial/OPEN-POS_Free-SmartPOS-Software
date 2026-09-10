const state = {
  token: localStorage.getItem('openpos_waiter_token') || '',
  staff: JSON.parse(localStorage.getItem('openpos_waiter_staff') || 'null'),
  tableId: null,
  categoryId: null,
  searchTimer: null,
  installPrompt: null,
  addons: [],
  pendingProduct: null,
  pendingButton: null,
};

const $ = (id) => document.getElementById(id);

function show(screen) {
  document.querySelectorAll('.screen').forEach((el) => el.classList.remove('active'));
  $(screen).classList.add('active');
  const inTable = screen === 'table-screen';
  $('table-actions').classList.toggle('hidden', !inTable);
  document.body.classList.toggle('has-table-actions', inTable);
}

function qrItemText(item) {
  const addons = (item.addons || []).map((addon) => `<small>+ ${Number(addon.qty || 1).toLocaleString('pt-BR')}x ${addon.name}</small>`).join(' ');
  const note = item.instructions ? `<small>Obs: ${item.instructions}</small>` : '';
  return `${Number(item.qty || 1).toLocaleString('pt-BR')}x ${item.name} ${addons} ${note}`;
}

function toast(message) {
  const el = $('toast');
  el.textContent = message;
  el.classList.remove('hidden');
  setTimeout(() => el.classList.add('hidden'), 2600);
}

async function api(path, options = {}) {
  const headers = Object.assign({'Content-Type': 'application/json'}, options.headers || {});
  if (state.token) headers.Authorization = `Bearer ${state.token}`;
  const res = await fetch(path, Object.assign({}, options, {headers}));
  let data = null;
  try { data = await res.json(); } catch (_) {}
  if (!res.ok) throw new Error((data && data.detail) || 'Falha na comunicacao.');
  return data;
}

function syncHeader() {
  $('session-label').textContent = state.staff ? `Atendente: ${state.staff.name}` : 'Selecione o atendente';
  $('logout-btn').classList.toggle('hidden', !state.staff);
}

async function loadWaiters() {
  const list = $('waiter-list');
  list.innerHTML = '<p>Carregando...</p>';
  try {
    const waiters = await api('/api/waiters');
    if (!waiters.length) {
      list.innerHTML = '<p>Nenhum atendente ativo cadastrado.</p>';
      return;
    }
    list.innerHTML = '';
    waiters.forEach((waiter) => {
      const btn = document.createElement('button');
      btn.textContent = waiter.name;
      btn.onclick = () => login(waiter.id);
      list.appendChild(btn);
    });
  } catch (err) {
    list.innerHTML = `<p>${err.message}</p>`;
  }
}

async function login(staffId) {
  const data = await api('/api/waiter/login', {method: 'POST', body: JSON.stringify({staff_id: staffId})});
  state.token = data.token;
  state.staff = data.staff;
  localStorage.setItem('openpos_waiter_token', state.token);
  localStorage.setItem('openpos_waiter_staff', JSON.stringify(state.staff));
  syncHeader();
  show('tables-screen');
  loadTables();
}

function logout() {
  state.token = '';
  state.staff = null;
  state.tableId = null;
  localStorage.removeItem('openpos_waiter_token');
  localStorage.removeItem('openpos_waiter_staff');
  syncHeader();
  show('login-screen');
  loadWaiters();
}

function statusLabel(status) {
  return {free: 'Livre', occupied: 'Ocupada', request_bill: 'Pediu conta'}[status] || status;
}

async function loadTables() {
  const list = $('tables-list');
  list.innerHTML = '<p>Carregando mesas...</p>';
  try {
    refreshQrBadge();
    const tables = await api('/api/waiter/tables');
    list.innerHTML = '';
    tables.forEach((table) => {
      const btn = document.createElement('button');
      btn.className = `table-card ${table.status}`;
      btn.innerHTML = `<strong>${table.table_no}</strong><div>${statusLabel(table.status)}<span>${table.current_total_label}</span><span>${table.waiter_name || ''}</span></div>`;
      btn.onclick = () => openTable(table.id);
      list.appendChild(btn);
    });
  } catch (err) {
    toast(err.message);
    if (err.message.includes('Sessao')) logout();
  }
}

async function refreshQrBadge() {
  try {
    const requests = await api('/api/waiter/qr-requests');
    const count = requests.length;
    $('qr-requests-btn').textContent = count ? `Pedidos QR (${count})` : 'Pedidos QR';
  } catch (_) {}
}

async function loadQrRequests() {
  show('qr-screen');
  const list = $('qr-list');
  list.innerHTML = '<p>Carregando pedidos...</p>';
  try {
    const requests = await api('/api/waiter/qr-requests');
    if (!requests.length) {
      list.innerHTML = '<div class="card">Nenhum pedido QR pendente.</div>';
      return;
    }
    list.innerHTML = '';
    requests.forEach((req) => {
      const card = document.createElement('div');
      card.className = 'qr-card';
      card.innerHTML = `<h2>Mesa ${req.table_no} - ${req.customer_name}</h2><p>${req.created_at} - ${req.total_label}</p><ul>${req.items.map((item) => `<li>${qrItemText(item)}</li>`).join('')}</ul>`;
      const actions = document.createElement('div');
      actions.className = 'actions two';
      const reject = document.createElement('button');
      reject.className = 'danger';
      reject.textContent = 'Rejeitar';
      reject.onclick = () => handleQr(req.id, 'reject');
      const accept = document.createElement('button');
      accept.className = 'primary';
      accept.textContent = 'Aceitar e Imprimir';
      accept.onclick = () => handleQr(req.id, 'accept');
      actions.append(reject, accept);
      card.appendChild(actions);
      list.appendChild(card);
    });
  } catch (err) {
    toast(err.message);
  }
}

async function handleQr(requestId, action) {
  const confirmText = action === 'accept' ? 'Aceitar pedido e imprimir KOT?' : 'Rejeitar este pedido?';
  if (!confirm(confirmText)) return;
  try {
    await api(`/api/waiter/qr-requests/${requestId}/${action}`, {method: 'POST'});
    toast(action === 'accept' ? 'Pedido aceito.' : 'Pedido rejeitado.');
    await loadQrRequests();
    await refreshQrBadge();
  } catch (err) {
    toast(err.message);
  }
}

async function openTable(tableId) {
  state.tableId = tableId;
  show('table-screen');
  await Promise.all([loadTable(), loadCategories(), loadProducts(), loadAddons()]);
}

async function loadTable() {
  const data = await api(`/api/waiter/tables/${state.tableId}`);
  $('table-title').textContent = `Mesa ${data.table.table_no}`;
  $('table-subtitle').textContent = `${statusLabel(data.table.status)} - ${data.table.waiter_name || state.staff.name}`;
  renderItems(data.order);
}

function renderItems(order) {
  const list = $('items-list');
  const total = order ? order.total_label : 'R$ 0,00';
  const count = order ? order.items.reduce((sum, item) => sum + Number(item.qty || 0), 0) : 0;
  $('order-total').textContent = total;
  $('footer-total').textContent = total;
  $('items-count').textContent = `${count.toLocaleString('pt-BR')} ${count === 1 ? 'item' : 'itens'}`;
  if (!order || !order.items.length) {
    list.className = 'items-list empty';
    list.textContent = 'Sem itens.';
    return;
  }
  list.className = 'items-list';
  list.innerHTML = '';
  order.items.forEach((item) => {
    const row = document.createElement('div');
    row.className = 'item-row';
    const addonLines = (item.addons || []).map((addon) => `<small>+ ${Number(addon.qty || 1).toLocaleString('pt-BR')}x ${addon.name} (${money(addon.price)})</small>`).join('');
    row.innerHTML = `<div><strong>${item.name}</strong>${addonLines}<div class="line-total">${Number(item.qty).toLocaleString('pt-BR')} x ${money(item.unit_total || item.price)}</div></div>`;
    const qty = document.createElement('div');
    qty.className = 'qty';
    const minus = document.createElement('button');
    minus.textContent = '-';
    minus.onclick = () => changeQty(item, Number(item.qty) - 1);
    const plus = document.createElement('button');
    plus.textContent = '+';
    plus.onclick = () => changeQty(item, Number(item.qty) + 1);
    const del = document.createElement('button');
    del.textContent = 'Remover';
    del.className = 'danger';
    del.onclick = () => removeItem(item.id);
    qty.append(minus, plus, del);
    const note = document.createElement('input');
    note.className = 'note';
    note.placeholder = 'Observacao do item';
    note.value = item.instructions || '';
    note.onchange = () => updateItem(item.id, {instructions: note.value});
    row.append(qty, note);
    list.appendChild(row);
  });
}

function money(value) {
  return Number(value || 0).toLocaleString('pt-BR', {style: 'currency', currency: 'BRL'});
}

async function loadCategories() {
  const list = $('category-list');
  const cats = await api('/api/waiter/categories');
  list.innerHTML = '';
  const all = document.createElement('button');
  all.textContent = 'Todos';
  all.className = state.categoryId ? '' : 'active';
  all.onclick = () => { state.categoryId = null; loadCategories(); loadProducts(); };
  list.appendChild(all);
  cats.forEach((cat) => {
    const btn = document.createElement('button');
    btn.textContent = cat.name;
    btn.className = state.categoryId === cat.id ? 'active' : '';
    btn.onclick = () => { state.categoryId = cat.id; loadCategories(); loadProducts(); };
    list.appendChild(btn);
  });
}

async function loadProducts() {
  const list = $('product-list');
  const q = $('product-search').value.trim();
  const params = new URLSearchParams();
  if (q) params.set('q', q);
  if (state.categoryId) params.set('category_id', state.categoryId);
  const products = await api(`/api/waiter/products?${params.toString()}`);
  list.innerHTML = '';
  products.forEach((product) => {
    const card = document.createElement('button');
    card.className = 'product-card';
    card.innerHTML = `<div><strong>${product.name}</strong><small>${product.category_name || ''}</small><span>${product.price_label}</span></div><div class="add-badge">+</div>`;
    card.onclick = () => addProduct(product, card);
    list.appendChild(card);
  });
}

async function loadAddons() {
  state.addons = await api('/api/waiter/addons');
}

async function addProduct(product, button) {
  if (product.allow_addons && state.addons.length) {
    openAddonModal(product.id, button);
    return;
  }
  await addProductWithAddons(product.id, [], button);
}

function openAddonModal(productId, button) {
  state.pendingProduct = productId;
  state.pendingButton = button;
  const productName = button ? button.querySelector('strong').textContent : 'Produto';
  $('addon-title').textContent = `Adicionais - ${productName}`;
  const list = $('addon-list');
  list.innerHTML = '';
  state.addons.forEach((addon) => {
    const row = document.createElement('div');
    row.className = 'addon-row';
    row.innerHTML = `<label><input type="checkbox" value="${addon.id}"> ${addon.name}<small>+ ${addon.price_label}</small></label>`;
    list.appendChild(row);
  });
  $('addon-modal').classList.remove('hidden');
}

function selectedAddons() {
  return Array.from($('addon-list').querySelectorAll('input:checked')).map((input) => ({addon_id: Number(input.value), qty: 1}));
}

function closeAddonModal() {
  $('addon-modal').classList.add('hidden');
}

async function addPendingProduct(addons) {
  const productId = state.pendingProduct;
  const button = state.pendingButton;
  closeAddonModal();
  state.pendingProduct = null;
  state.pendingButton = null;
  if (!productId) return;
  await addProductWithAddons(productId, addons, button);
}

async function addProductWithAddons(productId, addons, button) {
  const badge = button && button.querySelector('.add-badge');
  if (button) button.disabled = true;
  if (badge) badge.textContent = '✓';
  try {
    await api(`/api/waiter/tables/${state.tableId}/items`, {method: 'POST', body: JSON.stringify({product_id: productId, qty: 1, addons})});
    await loadTable();
  } catch (err) {
    toast(err.message);
  } finally {
    if (button) button.disabled = false;
    if (badge) badge.textContent = '+';
  }
}

async function updateItem(itemId, payload) {
  await api(`/api/waiter/items/${itemId}`, {method: 'PATCH', body: JSON.stringify(payload)});
  await loadTable();
}

async function changeQty(item, qty) {
  if (qty <= 0) return removeItem(item.id);
  await updateItem(item.id, {qty});
}

async function removeItem(itemId) {
  await api(`/api/waiter/items/${itemId}`, {method: 'DELETE'});
  await loadTable();
}

async function sendKot() {
  $('send-kot').disabled = true;
  try {
    const data = await api(`/api/waiter/tables/${state.tableId}/send-kot`, {method: 'POST'});
    toast(data.message || 'KOT enviado.');
  } catch (err) {
    toast(err.message);
  } finally {
    $('send-kot').disabled = false;
  }
}

async function requestBill() {
  if (!confirm('Pedir conta desta mesa?')) return;
  try {
    const data = await api(`/api/waiter/tables/${state.tableId}/request-bill`, {method: 'POST'});
    toast(data.message || 'Conta solicitada.');
    await loadTable();
  } catch (err) {
    toast(err.message);
  }
}

$('logout-btn').onclick = logout;
$('refresh-tables').onclick = loadTables;
$('qr-requests-btn').onclick = loadQrRequests;
$('back-qr').onclick = () => { show('tables-screen'); loadTables(); };
$('back-tables').onclick = () => { show('tables-screen'); loadTables(); };
$('send-kot').onclick = sendKot;
$('request-bill').onclick = requestBill;
$('addon-skip').onclick = () => addPendingProduct([]);
$('addon-confirm').onclick = () => addPendingProduct(selectedAddons());
$('addon-modal').onclick = (event) => {
  if (event.target.id === 'addon-modal') closeAddonModal();
};
$('install-btn').onclick = async () => {
  if (!state.installPrompt) {
    toast('No Chrome, use o menu e toque em Instalar app ou Adicionar a tela inicial.');
    return;
  }
  state.installPrompt.prompt();
  await state.installPrompt.userChoice;
  state.installPrompt = null;
  $('install-btn').classList.add('hidden');
};
$('product-search').oninput = () => {
  clearTimeout(state.searchTimer);
  state.searchTimer = setTimeout(loadProducts, 250);
};

window.addEventListener('beforeinstallprompt', (event) => {
  event.preventDefault();
  state.installPrompt = event;
  $('install-btn').classList.remove('hidden');
});

window.addEventListener('appinstalled', () => {
  state.installPrompt = null;
  $('install-btn').classList.add('hidden');
});

setInterval(() => {
  if (state.token && $('tables-screen').classList.contains('active')) refreshQrBadge();
}, 10000);

if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/garcom/service-worker.js').catch(() => {});
  });
}

syncHeader();
if (state.token && state.staff) {
  show('tables-screen');
  loadTables();
} else {
  show('login-screen');
  loadWaiters();
}
