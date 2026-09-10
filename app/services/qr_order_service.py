from app.database.db import get_db
from app.services.order_service import order_service
from app.services.table_service import table_service
from app.utils.helpers import now_str


class QrOrderService:
    def __init__(self):
        self._db = get_db()

    def create_request(self, table_id, customer_name, items, notes=""):
        table = table_service.get(table_id)
        if not table:
            raise ValueError("Mesa nao encontrada.")
        customer_name = (customer_name or "").strip()
        if not customer_name:
            raise ValueError("Informe seu nome.")
        if not items:
            raise ValueError("Adicione pelo menos um item.")
        request_id = self._db.execute(
            "INSERT INTO qr_order_requests (table_id, customer_name, notes) VALUES (?,?,?)",
            (table_id, customer_name, (notes or "").strip()),
        )
        for item in items:
            product_id = int(item.get("product_id") or 0)
            product = self._db.fetchone("SELECT * FROM products WHERE id=? AND is_active=1", (product_id,))
            qty = float(item.get("qty") or 1)
            if not product or qty <= 0:
                continue
            item_id = self._db.execute(
                "INSERT INTO qr_order_request_items (request_id, product_id, name, price, qty, instructions) "
                "VALUES (?,?,?,?,?,?)",
                (request_id, product_id, product["name"], product["price"], qty, (item.get("instructions") or "").strip()),
            )
            if product["allow_addons"]:
                for addon in item.get("addons") or []:
                    addon_id = int(addon.get("addon_id") or 0)
                    addon_qty = float(addon.get("qty") or 1)
                    row = self._db.fetchone("SELECT * FROM add_ons WHERE id=? AND is_active=1", (addon_id,))
                    if row and addon_qty > 0:
                        self._db.execute(
                            "INSERT INTO qr_order_request_item_addons (request_item_id, addon_id, name, price, qty) "
                            "VALUES (?,?,?,?,?)",
                            (item_id, row["id"], row["name"], row["price"], addon_qty),
                        )
        if not self.items(request_id):
            self._db.execute("DELETE FROM qr_order_requests WHERE id=?", (request_id,))
            raise ValueError("Nenhum item valido no pedido.")
        return self.get(request_id)

    def list_pending(self):
        return self._db.fetchall(
            "SELECT r.*, t.table_no FROM qr_order_requests r "
            "LEFT JOIN tables t ON t.id=r.table_id WHERE r.status='pending' ORDER BY r.id"
        )

    def get(self, request_id):
        return self._db.fetchone(
            "SELECT r.*, t.table_no FROM qr_order_requests r "
            "LEFT JOIN tables t ON t.id=r.table_id WHERE r.id=?",
            (request_id,),
        )

    def items(self, request_id):
        return self._db.fetchall("SELECT * FROM qr_order_request_items WHERE request_id=? ORDER BY id", (request_id,))

    def item_addons(self, request_item_id):
        return self._db.fetchall(
            "SELECT * FROM qr_order_request_item_addons WHERE request_item_id=? ORDER BY id", (request_item_id,)
        )

    def reject(self, request_id, staff_id=None):
        self._db.execute(
            "UPDATE qr_order_requests SET status='rejected', handled_at=?, handled_by=? WHERE id=? AND status='pending'",
            (now_str(), staff_id, request_id),
        )

    def accept(self, request_id, waiter_id=None):
        request = self.get(request_id)
        if not request or request["status"] != "pending":
            raise ValueError("Pedido QR nao esta pendente.")
        order = order_service.get_open_order_for_table(request["table_id"])
        if not order:
            order = order_service.create_order(
                order_type="dine-in",
                table_id=request["table_id"],
                waiter_id=waiter_id,
                customer_name=request["customer_name"],
            )
            table_service.set_status(request["table_id"], "occupied", order["id"])
        elif waiter_id and not order["waiter_id"]:
            order_service.set_waiter(order["id"], waiter_id)
            order = order_service.get(order["id"])
        if order and not (order["customer_name"] or "").strip():
            order_service.set_customer_info(order["id"], name=request["customer_name"])
            order = order_service.get(order["id"])
        added_item_ids = []
        for item in self.items(request_id):
            addons = [
                {"addon_id": addon["addon_id"], "qty": addon["qty"]}
                for addon in self.item_addons(item["id"])
            ]
            item_id = order_service.add_item(
                order["id"], product_id=item["product_id"], qty=item["qty"],
                instructions=(item["instructions"] or "").strip(), addons=addons
            )
            added_item_ids.append(item_id)
        self._db.execute(
            "UPDATE qr_order_requests SET status='accepted', handled_at=?, handled_by=? WHERE id=?",
            (now_str(), waiter_id, request_id),
        )
        return order_service.get(order["id"]), added_item_ids


qr_order_service = QrOrderService()
