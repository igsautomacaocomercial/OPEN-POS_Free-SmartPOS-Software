from app.database.db import get_db


class CustomerService:
    def __init__(self):
        self._db = get_db()

    def list_all(self, include_inactive=True):
        if include_inactive:
            return self._db.fetchall("SELECT * FROM customers ORDER BY name")
        return self._db.fetchall(
            "SELECT * FROM customers WHERE is_active=1 ORDER BY name")

    def list_active(self):
        return self._db.fetchall(
            "SELECT * FROM customers WHERE is_active=1 ORDER BY name")

    def find_by_phone(self, phone, active_only=True):
        p = (phone or "").strip()
        if not p:
            return None
        sql = "SELECT * FROM customers WHERE (phone=? OR phone LIKE ?)"
        if active_only:
            sql += " AND is_active=1"
        return self._db.fetchone(sql + " ORDER BY id LIMIT 1", (p, f"%{p}%"))

    def search(self, term, include_inactive=True):
        term = (term or "").strip()
        if not term:
            return self.list_all(include_inactive)
        sql = ("SELECT * FROM customers WHERE (name LIKE ? OR phone LIKE ? "
               "OR document LIKE ?)")
        params = [f"%{term}%", f"%{term}%", f"%{term}%"]
        if not include_inactive:
            sql += " AND is_active=1"
        sql += " ORDER BY name"
        return self._db.fetchall(sql, params)

    def get(self, customer_id):
        return self._db.fetchone("SELECT * FROM customers WHERE id=?", (customer_id,))

    def add(self, name, phone, address="", notes="", document="", cep="", email="",
            entity_type="PF", city="", state="", neighborhood="", is_active=True):
        self._db.execute(
            "INSERT INTO customers (name, phone, address, notes, document, cep, email, "
            "entity_type, city, state, neighborhood, is_active) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (name.strip(), phone.strip(), address.strip(), notes.strip(), document.strip(),
             cep.strip(), email.strip(), entity_type or "PF", city.strip(), state.strip(),
             neighborhood.strip(), 1 if is_active else 0),
        )

    def add_or_get(self, name, phone, address=""):
        existing = self.find_by_phone(phone, active_only=True)
        if existing:
            return existing
        self.add(name, phone, address)
        return self.find_by_phone(phone, active_only=True)

    def update(self, customer_id, name, phone, address="", notes="", document="", cep="",
               email="", entity_type="PF", city="", state="", neighborhood="", is_active=None):
        if is_active is None:
            cur = self._db.fetchone("SELECT is_active FROM customers WHERE id=?", (customer_id,))
            is_active = bool(cur["is_active"]) if cur else True
        self._db.execute(
            "UPDATE customers SET name=?, phone=?, address=?, notes=?, document=?, cep=?, "
            "email=?, entity_type=?, city=?, state=?, neighborhood=?, is_active=? WHERE id=?",
            (name.strip(), phone.strip(), address.strip(), notes.strip(), document.strip(),
             cep.strip(), email.strip(), entity_type or "PF", city.strip(), state.strip(),
             neighborhood.strip(), 1 if is_active else 0, customer_id),
        )

    def set_active(self, customer_id, is_active=True):
        self._db.execute(
            "UPDATE customers SET is_active=? WHERE id=?", (1 if is_active else 0, customer_id))

    def delete(self, customer_id):
        self._db.execute("DELETE FROM customers WHERE id=?", (customer_id,))


class SupplierService:
    def __init__(self):
        self._db = get_db()

    def list_all(self, include_inactive=True):
        if include_inactive:
            return self._db.fetchall("SELECT * FROM suppliers ORDER BY name")
        return self._db.fetchall(
            "SELECT * FROM suppliers WHERE is_active=1 ORDER BY name")

    def list_active(self):
        return self._db.fetchall(
            "SELECT * FROM suppliers WHERE is_active=1 ORDER BY name")

    def search(self, term, include_inactive=True):
        term = (term or "").strip()
        if not term:
            return self.list_all(include_inactive)
        sql = ("SELECT * FROM suppliers WHERE (name LIKE ? OR phone LIKE ? "
               "OR document LIKE ?)")
        params = [f"%{term}%", f"%{term}%", f"%{term}%"]
        if not include_inactive:
            sql += " AND is_active=1"
        sql += " ORDER BY name"
        return self._db.fetchall(sql, params)

    def get(self, supplier_id):
        return self._db.fetchone("SELECT * FROM suppliers WHERE id=?", (supplier_id,))

    def add(self, name, phone="", document="", cep="", email="", address="", city="",
            state="", neighborhood="", notes=""):
        self._db.execute(
            "INSERT INTO suppliers (name, phone, document, cep, email, address, city, state, "
            "neighborhood, notes) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (name.strip(), phone.strip(), document.strip(), cep.strip(), email.strip(),
             address.strip(), city.strip(), state.strip(), neighborhood.strip(), notes.strip()),
        )

    def update(self, supplier_id, name, phone="", document="", cep="", email="", address="",
               city="", state="", neighborhood="", notes="", is_active=True):
        self._db.execute(
            "UPDATE suppliers SET name=?, phone=?, document=?, cep=?, email=?, address=?, "
            "city=?, state=?, neighborhood=?, notes=?, is_active=? WHERE id=?",
            (name.strip(), phone.strip(), document.strip(), cep.strip(), email.strip(),
             address.strip(), city.strip(), state.strip(), neighborhood.strip(), notes.strip(),
             1 if is_active else 0, supplier_id),
        )

    def delete(self, supplier_id):
        self._db.execute("DELETE FROM suppliers WHERE id=?", (supplier_id,))


class NeighborhoodService:
    def __init__(self):
        self._db = get_db()

    def list_all(self):
        return self._db.fetchall("SELECT * FROM neighborhoods ORDER BY name")

    def list_active(self):
        return self._db.fetchall(
            "SELECT * FROM neighborhoods WHERE is_active=1 ORDER BY name"
        )

    def get(self, neighborhood_id):
        return self._db.fetchone(
            "SELECT * FROM neighborhoods WHERE id=?", (neighborhood_id,)
        )

    def add(self, name, fee):
        self._db.execute(
            "INSERT INTO neighborhoods (name, delivery_fee) VALUES (?,?)",
            (name.strip(), float(fee or 0)),
        )

    def update(self, neighborhood_id, name, fee, is_active=True):
        self._db.execute(
            "UPDATE neighborhoods SET name=?, delivery_fee=?, is_active=? WHERE id=?",
            (name.strip(), float(fee or 0), 1 if is_active else 0, neighborhood_id),
        )

    def delete(self, neighborhood_id):
        self._db.execute("DELETE FROM neighborhoods WHERE id=?", (neighborhood_id,))


class PaymentMethodService:
    def __init__(self):
        self._db = get_db()

    def list_all(self):
        return self._db.fetchall(
            "SELECT * FROM payment_methods ORDER BY sort_order, name"
        )

    def list_active(self):
        return self._db.fetchall(
            "SELECT * FROM payment_methods WHERE is_active=1 ORDER BY sort_order, name"
        )

    def list_active_names(self):
        return [r["name"] for r in self.list_active()]

    def add(self, name):
        n = self._db.fetchone(
            "SELECT COALESCE(MAX(sort_order),0)+1 n FROM payment_methods"
        )
        self._db.execute(
            "INSERT INTO payment_methods (name, sort_order) VALUES (?,?)",
            (name.strip(), n["n"] if n else 1),
        )

    def update(self, method_id, name, is_active=True):
        self._db.execute(
            "UPDATE payment_methods SET name=?, is_active=? WHERE id=?",
            (name.strip(), 1 if is_active else 0, method_id),
        )

    def delete(self, method_id):
        used = self._db.fetchone(
            "SELECT COUNT(*) c FROM orders WHERE payment_method=(SELECT name FROM payment_methods WHERE id=?)",
            (method_id,),
        )
        if used and used["c"] > 0:
            raise ValueError(
                "Este método já foi usado em pedidos. Desative-o em vez de excluí-lo."
            )
        self._db.execute("DELETE FROM payment_methods WHERE id=?", (method_id,))


customer_service = CustomerService()
neighborhood_service = NeighborhoodService()
payment_service = PaymentMethodService()
supplier_service = SupplierService()