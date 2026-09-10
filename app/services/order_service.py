from app.database.db import get_db
from app.services.finance_service import finance_service
from app.services.settings_service import settings_service
from app.utils.helpers import now_str


class OrderService:
    def __init__(self):
        self._db = get_db()

    def create_order(self, order_type="dine-in", cashier_id=None, waiter_id=None,
                     rider_id=None, table_id=None, customer_name="", customer_phone="",
                     customer_address="", service_charge=0.0, instructions="",
                     customer_id=None, neighborhood_id=None, payment_method="Dinheiro",
                     change_needed=0, change_amount=0.0, payment_details=""):
        number = settings_service.next_order_number()
        order_id = self._db.execute(
            "INSERT INTO orders (order_number, order_type, table_id, waiter_id, rider_id, "
            "cashier_id, instructions, customer_name, customer_phone, customer_address, "
            "service_charge, customer_id, neighborhood_id, payment_method, change_needed, change_amount, payment_details) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (number, order_type, table_id, waiter_id, rider_id, cashier_id, instructions,
              customer_name, customer_phone, customer_address, float(service_charge or 0),
              customer_id, neighborhood_id, payment_method or "Dinheiro",
              int(change_needed or 0), float(change_amount or 0), payment_details or ""),
        )
        return self.get(order_id)

    def get(self, order_id):
        return self._db.fetchone(
            "SELECT o.*, w.name AS waiter_name, r.name AS rider_name, "
            "u.full_name AS cashier_name, t.table_no, t.seats FROM orders o "
            "LEFT JOIN staff w ON w.id=o.waiter_id "
            "LEFT JOIN staff r ON r.id=o.rider_id "
            "LEFT JOIN users u ON u.id=o.cashier_id "
            "LEFT JOIN tables t ON t.id=o.table_id WHERE o.id=?",
            (order_id,),
        )

    def get_items(self, order_id):
        return self._db.fetchall(
            "SELECT * FROM order_items WHERE order_id=? AND qty>0 ORDER BY id", (order_id,)
        )

    def get_item(self, item_id):
        return self._db.fetchone("SELECT * FROM order_items WHERE id=?", (item_id,))

    def get_pending_kot_items(self, order_id):
        items = self._db.fetchall("SELECT * FROM order_items WHERE order_id=? ORDER BY id", (order_id,))
        pending = []
        for item in items:
            row = dict(item)
            qty = float(row["qty"] or 0)
            printed_qty = float(row.get("kot_printed_qty") or 0)
            current_note = row.get("instructions") or ""
            printed_note = row.get("kot_printed_instructions") or ""
            delta_qty = round(qty - printed_qty, 3)
            note_changed = current_note != printed_note
            if delta_qty > 0:
                row["qty"] = delta_qty
                row["kot_action"] = "ADICIONAR"
                pending.append(row)
            elif delta_qty < 0:
                row["qty"] = abs(delta_qty)
                row["kot_action"] = "CANCELAR"
                pending.append(row)
            elif note_changed and qty > 0:
                row["qty"] = qty
                row["kot_action"] = "ALTERAR OBS"
                pending.append(row)
        return pending

    def mark_kot_printed(self, order_id, items):
        if not items:
            return
        last_item_id = 0
        for item in items:
            item = dict(item)
            item_id = int(item["id"])
            current = self._db.fetchone("SELECT qty, instructions FROM order_items WHERE id=? AND order_id=?", (item_id, order_id))
            if not current:
                continue
            self._db.execute(
                "UPDATE order_items SET kot_printed_qty=?, kot_printed_instructions=? WHERE id=? AND order_id=?",
                (float(current["qty"] or 0), current["instructions"] or "", item_id, order_id),
            )
            last_item_id = max(last_item_id, item_id)
        if last_item_id:
            self._db.execute(
                "UPDATE orders SET last_kot_item_id=MAX(COALESCE(last_kot_item_id,0), ?) WHERE id=?",
                (last_item_id, order_id),
            )

    def get_open_order_for_table(self, table_id):
        return self._db.fetchone(
            "SELECT o.* FROM orders o WHERE o.table_id=? AND o.status IN ('open','request_bill') "
            "ORDER BY o.id DESC LIMIT 1",
            (table_id,),
        )

    def get_item_addons(self, item_id):
        return self._db.fetchall(
            "SELECT * FROM order_item_addons WHERE order_item_id=? ORDER BY id", (item_id,)
        )

    def add_item(self, order_id, product_id=None, name=None, price=0.0, qty=1, instructions="", addons=None):
        if product_id:
            product = self._db.fetchone("SELECT * FROM products WHERE id=?", (product_id,))
            if not product:
                raise ValueError("Produto não encontrado.")
            name = product["name"]
            price = product["price"]
        item_id = self._db.execute(
            "INSERT INTO order_items (order_id, product_id, name, price, qty, instructions) VALUES (?,?,?,?,?,?)",
            (order_id, product_id, name, price, qty, instructions),
        )
        for addon in addons or []:
            addon_id = int(addon.get("addon_id") or addon.get("id") or 0)
            addon_qty = float(addon.get("qty") or 1)
            row = self._db.fetchone("SELECT * FROM add_ons WHERE id=? AND is_active=1", (addon_id,))
            if not row or addon_qty <= 0:
                continue
            self._db.execute(
                "INSERT INTO order_item_addons (order_item_id, addon_id, name, price, qty) VALUES (?,?,?,?,?)",
                (item_id, row["id"], row["name"], row["price"], addon_qty),
            )
        self._recalc(order_id)
        return item_id

    def update_qty(self, item_id, qty):
        if qty <= 0:
            self.remove_item(item_id)
            return
        self._db.execute("UPDATE order_items SET qty=? WHERE id=?", (qty, item_id))
        row = self._db.fetchone("SELECT order_id FROM order_items WHERE id=?", (item_id,))
        if row:
            self._recalc(row["order_id"])

    def set_item_instructions(self, item_id, instructions):
        self._db.execute(
            "UPDATE order_items SET instructions=? WHERE id=?", (instructions, item_id)
        )

    def remove_item(self, item_id):
        row = self._db.fetchone("SELECT order_id, kot_printed_qty FROM order_items WHERE id=?", (item_id,))
        if row and float(row["kot_printed_qty"] or 0) > 0:
            self._db.execute("UPDATE order_items SET qty=0 WHERE id=?", (item_id,))
        else:
            self._db.execute("DELETE FROM order_items WHERE id=?", (item_id,))
        if row:
            self._recalc(row["order_id"])

    def set_order_instructions(self, order_id, instructions):
        self._db.execute("UPDATE orders SET instructions=? WHERE id=?", (instructions, order_id))

    def set_discount(self, order_id, discount_value, discount_type="amount"):
        self._db.execute(
            "UPDATE orders SET discount=?, discount_type=? WHERE id=?",
            (float(discount_value or 0), discount_type, order_id),
        )
        self._recalc(order_id)

    def set_waiter(self, order_id, waiter_id):
        self._db.execute("UPDATE orders SET waiter_id=? WHERE id=?", (waiter_id, order_id))

    def set_rider(self, order_id, rider_id):
        self._db.execute("UPDATE orders SET rider_id=? WHERE id=?", (rider_id, order_id))

    def set_service_charge(self, order_id, amount):
        self._db.execute(
            "UPDATE orders SET service_charge=? WHERE id=?", (float(amount or 0), order_id))
        self._recalc(order_id)

    def set_payment_method(self, order_id, payment_method):
        self._db.execute(
            "UPDATE orders SET payment_method=? WHERE id=?",
            (payment_method or "Dinheiro", order_id),
        )

    def set_payment_details(self, order_id, payment_method=None, change_needed=None, change_amount=None, payment_details=None):
        updates = []
        params = []
        if payment_method is not None:
            updates.append("payment_method=?")
            params.append(payment_method or "Dinheiro")
        if change_needed is not None:
            updates.append("change_needed=?")
            params.append(1 if change_needed else 0)
        if change_amount is not None:
            updates.append("change_amount=?")
            params.append(float(change_amount or 0))
        if payment_details is not None:
            updates.append("payment_details=?")
            params.append(payment_details or "")
        if not updates:
            return
        params.append(order_id)
        self._db.execute(f"UPDATE orders SET {', '.join(updates)} WHERE id=?", params)

    def set_customer_info(self, order_id, customer_id=None, name=None, phone=None, address=None):
        self._db.execute(
            "UPDATE orders SET customer_id=?, customer_name=?, customer_phone=?, customer_address=? WHERE id=?",
            (customer_id, name or "", phone or "", address or "", order_id))

    def transfer_order(self, order_id, to_table_id):
        order = self.get(order_id)
        if not order:
            raise ValueError("Pedido não encontrado.")
        if (order["table_id"] or -1) == to_table_id:
            return
        target = self._db.fetchone("SELECT status FROM tables WHERE id=?", (to_table_id,))
        if target and target["status"] != "free":
            raise ValueError("A mesa de destino está ocupada.")
        self._db.execute("UPDATE orders SET table_id=? WHERE id=?", (to_table_id, order_id))
        if order["table_id"]:
            self._db.execute(
                "UPDATE tables SET status='free', current_order_id=NULL WHERE id=?",
                (order["table_id"],))
        self._db.execute(
            "UPDATE tables SET status='occupied', current_order_id=? WHERE id=?",
            (order_id, to_table_id))

    def merge_orders(self, source_id, target_id):
        if source_id == target_id:
            raise ValueError("Escolha mesas diferentes.")
        source = self.get(source_id)
        target = self.get(target_id)
        if not source or not target:
            raise ValueError("Pedidos não encontrados.")
        items = self.get_items(source_id)
        for it in items:
            new_item_id = self._db.execute(
                "INSERT INTO order_items (order_id, product_id, name, price, qty, instructions) "
                "VALUES (?,?,?,?,?,?)",
                (target_id, it["product_id"], it["name"], it["price"], it["qty"], it["instructions"]))
            for addon in self.get_item_addons(it["id"]):
                self._db.execute(
                    "INSERT INTO order_item_addons (order_item_id, addon_id, name, price, qty) VALUES (?,?,?,?,?)",
                    (new_item_id, addon["addon_id"], addon["name"], addon["price"], addon["qty"]),
                )
        self._db.execute("DELETE FROM order_items WHERE order_id=?", (source_id,))
        self._recalc(target_id)
        self.manual_close(source_id)

    def _recalc(self, order_id):
        order = self.get(order_id)
        items = self.get_items(order_id)
        subtotal = 0.0
        for item in items:
            item_qty = float(item["qty"] or 0)
            addons = self.get_item_addons(item["id"])
            addons_total = sum(float(a["price"] or 0) * float(a["qty"] or 0) for a in addons)
            subtotal += (float(item["price"] or 0) + addons_total) * item_qty
        subtotal = round(subtotal, 2)
        discount = float(order["discount"] or 0)
        if order["discount_type"] == "percent":
            discount = round(subtotal * discount / 100.0, 2)
        discount = min(discount, subtotal)
        tax_rate = settings_service.get_float("tax_rate", 0.0)
        tax = 0.0
        if tax_rate > 0 and self._tax_applies(order["order_type"]):
            tax_base = subtotal
            if subtotal > 0 and discount > 0:
                tax_base = subtotal - discount
            tax = round(max(0.0, tax_base) * tax_rate / 100.0, 2)
        service_charge = float(order["service_charge"] or 0)
        total = round(subtotal - discount + tax + service_charge, 2)
        self._db.execute(
            "UPDATE orders SET subtotal=?, discount=?, tax=?, total=? WHERE id=?",
            (subtotal, discount, tax, total, order_id),
        )

    def _tax_applies(self, order_type):
        key = {
            "dine-in": "tax_dinein",
            "takeaway": "tax_takeaway",
            "delivery": "tax_delivery",
        }.get(order_type, "tax_dinein")
        return settings_service.get(key, "1") == "1"

    def request_bill(self, order_id):
        self._db.execute(
            "UPDATE orders SET status='request_bill' WHERE id=?", (order_id,)
        )
        order = self.get(order_id)
        if order and order["table_id"]:
            table_service = self._db.fetchone("SELECT id FROM tables WHERE id=?", (order["table_id"],))
            if table_service:
                self._db.execute(
                    "UPDATE tables SET status='request_bill', current_order_id=? WHERE id=?",
                    (order_id, order["table_id"]),
                )

    def finalize(self, order_id, payment_method="Dinheiro", payment_details=None):
        updates = ["status='paid'", "payment_method=?", "closed_at=?"]
        params = [payment_method, now_str()]
        if payment_details is not None:
            updates.append("payment_details=?")
            params.append(payment_details or "")
        self._db.execute(
            f"UPDATE orders SET {', '.join(updates)} WHERE id=?",
            (*params, order_id),
        )
        order = self.get(order_id)
        if order and order["table_id"]:
            self._db.execute(
                "UPDATE tables SET status='free', current_order_id=NULL WHERE id=?",
                (order["table_id"],),
            )

    
        try:
            finance_service.record_sale(order["total"], f"Venda #{order['order_number']}")
        except Exception:
            pass

    def manual_close(self, order_id):
        self._db.execute(
            "UPDATE orders SET status='closed', closed_at=? WHERE id=?",
            (now_str(), order_id),
        )
        order = self.get(order_id)
        if order and order["table_id"]:
            self._db.execute(
                "UPDATE tables SET status='free', current_order_id=NULL WHERE id=?",
                (order["table_id"],),
            )

    def recent(self, limit=20):
        return self._db.fetchall(
            "SELECT o.*, t.table_no, w.name AS waiter_name, r.name AS rider_name, "
            "u.full_name AS cashier_name "
            "FROM orders o LEFT JOIN tables t ON t.id=o.table_id "
            "LEFT JOIN staff w ON w.id=o.waiter_id "
            "LEFT JOIN staff r ON r.id=o.rider_id "
            "LEFT JOIN users u ON u.id=o.cashier_id "
            "ORDER BY o.id DESC LIMIT ?",
            (limit,),
        )

    def list_by_type_and_status(self, order_type, statuses):
        ph = ",".join("?" for _ in statuses)
        return self._db.fetchall(
            f"SELECT o.*, w.name AS waiter_name, r.name AS rider_name, "
            f"u.full_name AS cashier_name, t.table_no FROM orders o "
            f"LEFT JOIN staff w ON w.id=o.waiter_id "
            f"LEFT JOIN staff r ON r.id=o.rider_id "
            f"LEFT JOIN users u ON u.id=o.cashier_id "
            f"LEFT JOIN tables t ON t.id=o.table_id "
            f"WHERE o.order_type=? AND o.status IN ({ph}) ORDER BY o.id DESC",
            [order_type, *statuses],
        )

    def paid_today(self):
        return self._db.fetchall(
            "SELECT o.*, t.table_no, w.name AS waiter_name FROM orders o "
            "LEFT JOIN tables t ON t.id=o.table_id "
            "LEFT JOIN staff w ON w.id=o.waiter_id "
            "WHERE o.status='paid' AND date(o.created_at)=date('now','localtime') "
            "ORDER BY o.id DESC"
        )

    def list_by_customer(self, customer_id, limit=500):
        return self._db.fetchall(
            "SELECT o.*, t.table_no, w.name AS waiter_name, r.name AS rider_name, "
            "u.full_name AS cashier_name FROM orders o "
            "LEFT JOIN tables t ON t.id=o.table_id "
            "LEFT JOIN staff w ON w.id=o.waiter_id "
            "LEFT JOIN staff r ON r.id=o.rider_id "
            "LEFT JOIN users u ON u.id=o.cashier_id "
            "WHERE o.customer_id=? ORDER BY o.id DESC LIMIT ?",
            (customer_id, limit),
        )


order_service = OrderService()
