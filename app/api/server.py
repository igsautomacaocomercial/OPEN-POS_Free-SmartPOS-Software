import secrets
import threading
from io import BytesIO
from pathlib import Path

from fastapi import Body, Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from app.config import BASE_DIR, PRODUCT_IMAGES_DIR
from app.printing.printer_service import print_kot, print_request_bill
from app.services.addon_service import addon_service
from app.services.order_service import order_service
from app.services.product_service import product_service
from app.services.qr_order_service import qr_order_service
from app.services.settings_service import settings_service
from app.services.staff_service import staff_service
from app.services.table_service import table_service
from app.utils.helpers import fmt_money

_sessions = {}
_sessions_lock = threading.RLock()
_order_locks = {}
_order_locks_lock = threading.RLock()
_table_open_lock = threading.RLock()


def _as_dict(row):
    return dict(row) if hasattr(row, "keys") else row


def _money(value):
    return fmt_money(value, settings_service.get("currency", "R$"))


def _public_staff(row):
    row = _as_dict(row)
    return {"id": row["id"], "name": row["name"]}


def _order_lock(order_id):
    with _order_locks_lock:
        lock = _order_locks.get(int(order_id))
        if lock is None:
            lock = threading.RLock()
            _order_locks[int(order_id)] = lock
        return lock


def _current_staff(authorization: str | None = Header(default=None)):
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Sessao invalida.")
    token = authorization.split(" ", 1)[1].strip()
    with _sessions_lock:
        staff = _sessions.get(token)
    if not staff:
        raise HTTPException(status_code=401, detail="Sessao expirada.")
    return staff


def _table_order(table_id, create=False, waiter_id=None):
    with _table_open_lock:
        order = order_service.get_open_order_for_table(table_id)
        if order or not create:
            return order
        order = order_service.create_order(order_type="dine-in", table_id=table_id, waiter_id=waiter_id)
        table_service.set_status(table_id, "occupied", order["id"])
        return order_service.get(order["id"])


def _item_order(item_id):
    item = order_service.get_item(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item nao encontrado.")
    order = order_service.get(item["order_id"])
    if not order or order["status"] not in ("open", "request_bill"):
        raise HTTPException(status_code=400, detail="Pedido nao pode ser alterado.")
    return item, order


def _order_payload(order):
    if not order:
        return None
    order = _as_dict(order)
    items = [_as_dict(i) for i in order_service.get_items(order["id"])]

    def item_payload(item):
        addons = [_as_dict(a) for a in order_service.get_item_addons(item["id"])]
        addon_total = sum(float(a["price"] or 0) * float(a["qty"] or 0) for a in addons)
        unit_total = float(item["price"] or 0) + addon_total
        return {
            "id": item["id"],
            "product_id": item["product_id"],
            "name": item["name"],
            "qty": item["qty"],
            "price": item["price"],
            "unit_total": unit_total,
            "line_total": unit_total * float(item["qty"] or 0),
            "instructions": item["instructions"] or "",
            "addons": addons,
        }

    return {
        "id": order["id"],
        "order_number": order["order_number"],
        "status": order["status"],
        "table_id": order.get("table_id"),
        "table_no": order.get("table_no"),
        "waiter_id": order.get("waiter_id"),
        "waiter_name": order.get("waiter_name"),
        "subtotal": order.get("subtotal") or 0,
        "discount": order.get("discount") or 0,
        "tax": order.get("tax") or 0,
        "service_charge": order.get("service_charge") or 0,
        "total": order.get("total") or 0,
        "total_label": _money(order.get("total") or 0),
        "instructions": order.get("instructions") or "",
        "items": [item_payload(item) for item in items],
    }


def _table_payload(table):
    table = _as_dict(table)
    return {
        "id": table["id"],
        "table_no": table["table_no"],
        "seats": table["seats"],
        "status": table["status"],
        "waiter_name": table.get("waiter_name"),
        "current_total": table.get("current_total") or 0,
        "current_total_label": _money(table.get("current_total") or 0),
        "opened_at": table.get("opened_at"),
    }


def _public_product_payload(row):
    image_path = row["image_path"] if "image_path" in row.keys() else ""
    return {
        "id": row["id"],
        "name": row["name"],
        "price": row["price"],
        "price_label": _money(row["price"]),
        "category_id": row["category_id"],
        "category_name": row["category_name"],
        "allow_addons": bool(row["allow_addons"]),
        "image_url": f"/product-images/{image_path}" if image_path else "",
    }


def _qr_request_payload(request):
    request = _as_dict(request)
    items = []
    total = 0.0
    for item in qr_order_service.items(request["id"]):
        item = _as_dict(item)
        addons = [_as_dict(a) for a in qr_order_service.item_addons(item["id"])]
        addon_total = sum(float(a["price"] or 0) * float(a["qty"] or 0) for a in addons)
        unit_total = float(item["price"] or 0) + addon_total
        line_total = unit_total * float(item["qty"] or 0)
        total += line_total
        items.append({**item, "addons": addons, "unit_total": unit_total, "line_total": line_total})
    return {
        "id": request["id"],
        "table_id": request["table_id"],
        "table_no": request["table_no"],
        "customer_name": request["customer_name"],
        "status": request["status"],
        "notes": request["notes"],
        "created_at": request["created_at"],
        "total": total,
        "total_label": _money(total),
        "items": items,
    }


def create_app():
    app = FastAPI(title="Open POS Local API", version="0.1.0")
    web_dir = Path(BASE_DIR) / "web" / "garcom"
    menu_dir = Path(BASE_DIR) / "web" / "cardapio"
    if web_dir.exists():
        app.mount("/garcom/assets", StaticFiles(directory=str(web_dir)), name="garcom-assets")
    if menu_dir.exists():
        app.mount("/cardapio/assets", StaticFiles(directory=str(menu_dir)), name="cardapio-assets")
    app.mount("/product-images", StaticFiles(directory=str(PRODUCT_IMAGES_DIR)), name="product-images")

    @app.get("/")
    def root():
        return RedirectResponse("/garcom")

    @app.get("/garcom")
    def waiter_app():
        index = web_dir / "index.html"
        if not index.exists():
            raise HTTPException(status_code=404, detail="App do garcom nao encontrado.")
        return FileResponse(str(index))

    @app.get("/garcom/service-worker.js")
    def waiter_service_worker():
        service_worker = web_dir / "service-worker.js"
        if not service_worker.exists():
            raise HTTPException(status_code=404, detail="Service worker nao encontrado.")
        return FileResponse(str(service_worker), media_type="text/javascript")

    @app.get("/cardapio")
    def customer_menu(table_id: int | None = None):
        index = menu_dir / "index.html"
        if not index.exists():
            raise HTTPException(status_code=404, detail="Cardapio digital nao encontrado.")
        return FileResponse(str(index))

    @app.get("/api/health")
    def health():
        return {"ok": True, "app": "Open POS", "module": "local-api"}

    @app.get("/api/waiters")
    def waiters():
        return [_public_staff(row) for row in staff_service.list_waiters()]

    @app.post("/api/waiter/login")
    def waiter_login(payload: dict = Body(...)):
        staff_id = payload.get("staff_id")
        staff = next((s for s in staff_service.list_waiters() if int(s["id"]) == int(staff_id or 0)), None)
        if not staff:
            raise HTTPException(status_code=401, detail="Atendente invalido ou inativo.")
        token = secrets.token_urlsafe(32)
        public = _public_staff(staff)
        with _sessions_lock:
            _sessions[token] = public
        return {"token": token, "staff": public}

    @app.get("/api/waiter/me")
    def waiter_me(staff=Depends(_current_staff)):
        return staff

    @app.get("/api/waiter/tables")
    def waiter_tables(staff=Depends(_current_staff)):
        return [_table_payload(row) for row in table_service.list_all()]

    @app.get("/api/waiter/tables/{table_id}")
    def waiter_table(table_id: int, staff=Depends(_current_staff)):
        table = table_service.get(table_id)
        if not table:
            raise HTTPException(status_code=404, detail="Mesa nao encontrada.")
        order = _table_order(table_id)
        return {"table": _table_payload(table), "order": _order_payload(order)}

    @app.get("/api/waiter/categories")
    def categories(staff=Depends(_current_staff)):
        return [_as_dict(row) for row in product_service.list_categories()]

    @app.get("/api/waiter/products")
    def products(q: str = "", category_id: int | None = None, staff=Depends(_current_staff)):
        rows = product_service.list_active(q.strip(), category_id)
        return [
            _public_product_payload(row)
            for row in rows
        ]

    @app.get("/api/waiter/addons")
    def addons(staff=Depends(_current_staff)):
        return [
            {"id": row["id"], "name": row["name"], "price": row["price"], "price_label": _money(row["price"])}
            for row in addon_service.list_active()
        ]

    @app.get("/api/menu/table/{table_id}")
    def public_table(table_id: int):
        table = table_service.get(table_id)
        if not table:
            raise HTTPException(status_code=404, detail="Mesa nao encontrada.")
        return {"id": table["id"], "table_no": table["table_no"]}

    @app.get("/cardapio/qr/{table_id}.svg")
    def table_qr(table_id: int, request: Request):
        table = table_service.get(table_id)
        if not table:
            raise HTTPException(status_code=404, detail="Mesa nao encontrada.")
        try:
            import qrcode
            import qrcode.image.svg
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Dependencia qrcode indisponivel: {exc}") from exc
        url = f"{str(request.base_url).rstrip('/')}/cardapio?table_id={table_id}"
        img = qrcode.make(url, image_factory=qrcode.image.svg.SvgImage)
        buf = BytesIO()
        img.save(buf)
        return Response(content=buf.getvalue(), media_type="image/svg+xml")

    @app.get("/api/menu/categories")
    def public_categories():
        return [_as_dict(row) for row in product_service.list_categories()]

    @app.get("/api/menu/products")
    def public_products(q: str = "", category_id: int | None = None):
        return [_public_product_payload(row) for row in product_service.list_active(q.strip(), category_id)]

    @app.get("/api/menu/addons")
    def public_addons():
        return [
            {"id": row["id"], "name": row["name"], "price": row["price"], "price_label": _money(row["price"])}
            for row in addon_service.list_active()
        ]

    @app.post("/api/menu/order")
    def public_order(payload: dict = Body(...)):
        try:
            request = qr_order_service.create_request(
                int(payload.get("table_id") or 0),
                payload.get("customer_name") or "",
                payload.get("items") or [],
                payload.get("notes") or "",
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "request": _qr_request_payload(request)}

    @app.get("/api/waiter/qr-requests")
    def waiter_qr_requests(staff=Depends(_current_staff)):
        return [_qr_request_payload(row) for row in qr_order_service.list_pending()]

    @app.post("/api/waiter/qr-requests/{request_id}/reject")
    def reject_qr_request(request_id: int, staff=Depends(_current_staff)):
        qr_order_service.reject(request_id, staff["id"])
        return {"ok": True}

    @app.post("/api/waiter/qr-requests/{request_id}/accept")
    def accept_qr_request(request_id: int, staff=Depends(_current_staff)):
        try:
            order, item_ids = qr_order_service.accept(request_id, staff["id"])
            items = [dict(i) for i in order_service.get_items(order["id"]) if i["id"] in item_ids]
            if items:
                print_kot(order, items=items)
                order_service.mark_kot_printed(order["id"], items)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "order": _order_payload(order_service.get(order["id"]))}

    @app.post("/api/waiter/tables/{table_id}/items")
    def add_table_item(table_id: int, payload: dict = Body(...), staff=Depends(_current_staff)):
        product_id = int(payload.get("product_id") or 0)
        qty = float(payload.get("qty") or 1)
        instructions = str(payload.get("instructions") or "").strip()
        addons = payload.get("addons") or []
        if product_id <= 0 or qty <= 0:
            raise HTTPException(status_code=400, detail="Produto/quantidade invalidos.")
        order = _table_order(table_id, create=True, waiter_id=staff["id"])
        if not order:
            raise HTTPException(status_code=400, detail="Nao foi possivel abrir a mesa.")
        if not order["waiter_id"]:
            order_service.set_waiter(order["id"], staff["id"])
        with _order_lock(order["id"]):
            order_service.add_item(order["id"], product_id=product_id, qty=qty, instructions=instructions, addons=addons)
        return {"ok": True, "order": _order_payload(order_service.get(order["id"]))}

    @app.patch("/api/waiter/items/{item_id}")
    def update_item(item_id: int, payload: dict = Body(...), staff=Depends(_current_staff)):
        _item, order = _item_order(item_id)
        qty = payload.get("qty")
        instructions = payload.get("instructions")
        with _order_lock(order["id"]):
            if qty is not None:
                order_service.update_qty(item_id, float(qty))
            if instructions is not None:
                order_service.set_item_instructions(item_id, str(instructions).strip())
        return {"ok": True, "order": _order_payload(order_service.get(order["id"]))}

    @app.delete("/api/waiter/items/{item_id}")
    def delete_item(item_id: int, staff=Depends(_current_staff)):
        _item, order = _item_order(item_id)
        with _order_lock(order["id"]):
            order_service.remove_item(item_id)
        return {"ok": True, "order": _order_payload(order_service.get(order["id"]))}

    @app.post("/api/waiter/tables/{table_id}/send-kot")
    def send_kot(table_id: int, staff=Depends(_current_staff)):
        order = _table_order(table_id)
        if not order:
            raise HTTPException(status_code=400, detail="Mesa sem pedido aberto.")
        with _order_lock(order["id"]):
            order = order_service.get(order["id"])
            items = order_service.get_pending_kot_items(order["id"])
            if not items:
                return {"ok": True, "printed": False, "message": "Nao ha novos itens para imprimir."}
            print_kot(order, items=items)
            order_service.mark_kot_printed(order["id"], items)
        return {"ok": True, "printed": True, "message": "KOT enviado para cozinha."}

    @app.post("/api/waiter/tables/{table_id}/request-bill")
    def request_bill(table_id: int, staff=Depends(_current_staff)):
        order = _table_order(table_id)
        if not order:
            raise HTTPException(status_code=400, detail="Mesa sem pedido aberto.")
        if not order_service.get_items(order["id"]):
            raise HTTPException(status_code=400, detail="Pedido vazio.")
        order_service.request_bill(order["id"])
        print_request_bill(order_service.get(order["id"]))
        return {"ok": True, "message": "Conta solicitada."}

    return app
