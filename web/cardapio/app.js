const state = {tableId: null, customer: '', categoryId: null, products: [], addons: [], cart: [], pendingProduct: null};
const $ = (id) => document.getElementById(id);

function api(path, options = {}) {
  const headers = Object.assign({'Content-Type': 'application/json'}, options.headers || {});
  return fetch(path, Object.assign({}, options, {headers})).then(async (res) => {
    let data = null;
    try { data = await res.json(); } catch (_) {}
    if (!res.ok) throw new Error((data && data.detail) || 'Falha na comunicacao.');
    return data;
  });
}

function show(screen) {
  document.querySelectorAll('.screen').forEach((el) => el.classList.remove('active'));
  $(screen).classList.add('active');
  const inMenu = screen === 'menu-screen';
  $('bottom-bar').classList.toggle('hidden', !inMenu);
  document.body.classList.toggle('has-bottom', inMenu);
}

function toast(text) {
  $('toast').textContent = text;
  $('toast').classList.remove('hidden');
  setTimeout(() => $('toast').classList.add('hidden'), 2600);
}

function money(value) {
  return Number(value || 0).toLocaleString('pt-BR', {style: 'currency', currency: 'BRL'});
}

async function init() {
  state.tableId = Number(new URLSearchParams(location.search).get('table_id') || 0);
  if (!state.tableId) {
    $('start-screen').innerHTML = '<div class="card"><h2>Link invalido</h2><p>Abra o cardapio pelo QR Code da mesa.</p></div>';
    return;
  }
  try {
    const table = await api(`/api/menu/table/${state.tableId}`);
    $('table-label').textContent = `Mesa ${table.table_no}`;
  } catch (err) {
    $('start-screen').innerHTML = `<div class="card"><h2>Erro</h2><p>${err.message}</p></div>`;
  }
}

async function startMenu() {
  state.customer = $('customer-name').value.trim();
  if (!state.customer) return toast('Informe seu nome.');
  show('menu-screen');
  await Promise.all([loadCategories(), loadProducts(), loadAddons()]);
  renderCart();
}

async function loadCategories() {
  const cats = await api('/api/menu/categories');
  const list = $('category-list');
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
  const q = $('product-search').value.trim();
  const params = new URLSearchParams();
  if (q) params.set('q', q);
  if (state.categoryId) params.set('category_id', state.categoryId);
  state.products = await api(`/api/menu/products?${params.toString()}`);
  const list = $('product-list');
  list.innerHTML = '';
  state.products.forEach((product) => {
    const card = document.createElement('button');
    card.className = 'product-card';
    const photo = product.image_url
      ? `<img class="product-photo" src="${product.image_url}" alt="${product.name}">`
      : `<div class="product-photo placeholder">IMG</div>`;
    card.innerHTML = `<div class="product-info">${photo}<div><strong>${product.name}</strong><small>${product.category_name || ''}</small><span>${product.price_label}</span></div></div><div class="add">+</div>`;
    card.onclick = () => addProduct(product);
    list.appendChild(card);
  });
}

async function loadAddons() {
  state.addons = await api('/api/menu/addons');
}

function addProduct(product) {
  if (product.allow_addons && state.addons.length) {
    state.pendingProduct = product;
    $('addon-title').textContent = `Adicionais - ${product.name}`;
    $('item-note').value = '';
    const list = $('addon-list');
    list.innerHTML = '';
    state.addons.forEach((addon) => {
      const row = document.createElement('div');
      row.className = 'addon-row';
      row.innerHTML = `<label><input type="checkbox" value="${addon.id}"> ${addon.name}</label><small>+ ${addon.price_label}</small>`;
      list.appendChild(row);
    });
    $('addon-modal').classList.remove('hidden');
    return;
  }
  pushCart(product, [], '');
}

function selectedAddons() {
  return Array.from($('addon-list').querySelectorAll('input:checked')).map((input) => {
    const addon = state.addons.find((a) => a.id === Number(input.value));
    return {addon_id: addon.id, name: addon.name, price: addon.price, qty: 1};
  });
}

function pushCart(product, addons, instructions) {
  state.cart.push({product_id: product.id, name: product.name, price: product.price, qty: 1, addons, instructions});
  renderCart();
  toast('Item adicionado.');
}

function renderCart() {
  const list = $('cart-list');
  const count = state.cart.reduce((sum, item) => sum + Number(item.qty || 0), 0);
  const total = state.cart.reduce((sum, item) => sum + itemTotal(item), 0);
  $('cart-count').textContent = `${count} ${count === 1 ? 'item' : 'itens'}`;
  $('cart-total').textContent = money(total);
  $('bottom-total').textContent = money(total);
  if (!state.cart.length) {
    list.className = 'cart-list empty';
    list.textContent = 'Nenhum item.';
    return;
  }
  list.className = 'cart-list';
  list.innerHTML = '';
  state.cart.forEach((item, idx) => {
    const addons = (item.addons || []).map((a) => `<small>+ ${a.name} (${money(a.price)})</small>`).join('');
    const row = document.createElement('div');
    row.className = 'cart-item';
    row.innerHTML = `<div><strong>${item.name}</strong>${addons}<small>${item.instructions || ''}</small><strong>${money(itemTotal(item))}</strong></div>`;
    const qty = document.createElement('div');
    qty.className = 'qty';
    const minus = document.createElement('button'); minus.textContent = '-'; minus.onclick = () => changeQty(idx, -1);
    const label = document.createElement('strong'); label.textContent = item.qty;
    const plus = document.createElement('button'); plus.textContent = '+'; plus.onclick = () => changeQty(idx, 1);
    qty.append(minus, label, plus);
    row.appendChild(qty);
    list.appendChild(row);
  });
}

function itemTotal(item) {
  const addons = (item.addons || []).reduce((sum, a) => sum + Number(a.price || 0) * Number(a.qty || 1), 0);
  return (Number(item.price || 0) + addons) * Number(item.qty || 0);
}

function changeQty(idx, delta) {
  state.cart[idx].qty += delta;
  if (state.cart[idx].qty <= 0) state.cart.splice(idx, 1);
  renderCart();
}

async function sendOrder() {
  if (!state.cart.length) return toast('Adicione pelo menos um item.');
  $('send-order').disabled = true;
  try {
    await api('/api/menu/order', {method: 'POST', body: JSON.stringify({table_id: state.tableId, customer_name: state.customer, items: state.cart})});
    state.cart = [];
    renderCart();
    show('done-screen');
  } catch (err) {
    toast(err.message);
  } finally {
    $('send-order').disabled = false;
  }
}

$('start-btn').onclick = startMenu;
$('new-order').onclick = () => show('menu-screen');
$('send-order').onclick = sendOrder;
$('product-search').oninput = () => loadProducts();
$('addon-skip').onclick = () => { const p = state.pendingProduct; $('addon-modal').classList.add('hidden'); pushCart(p, [], $('item-note').value.trim()); };
$('addon-confirm').onclick = () => { const p = state.pendingProduct; $('addon-modal').classList.add('hidden'); pushCart(p, selectedAddons(), $('item-note').value.trim()); };
$('addon-modal').onclick = (event) => { if (event.target.id === 'addon-modal') $('addon-modal').classList.add('hidden'); };
init();
