from app.database.db import get_db


class AddonService:
    def __init__(self):
        self._db = get_db()

    def list_all(self):
        return self._db.fetchall("SELECT * FROM add_ons ORDER BY sort_order, name")

    def list_active(self):
        return self._db.fetchall("SELECT * FROM add_ons WHERE is_active=1 ORDER BY sort_order, name")

    def get(self, addon_id):
        return self._db.fetchone("SELECT * FROM add_ons WHERE id=?", (addon_id,))

    def add(self, name, price, sort_order=0):
        name = (name or "").strip()
        if not name:
            raise ValueError("Informe o nome do adicional.")
        self._db.execute(
            "INSERT INTO add_ons (name, price, sort_order) VALUES (?,?,?)",
            (name, float(price or 0), int(sort_order or 0)),
        )

    def update(self, addon_id, name, price, is_active=True, sort_order=0):
        name = (name or "").strip()
        if not name:
            raise ValueError("Informe o nome do adicional.")
        self._db.execute(
            "UPDATE add_ons SET name=?, price=?, is_active=?, sort_order=? WHERE id=?",
            (name, float(price or 0), 1 if is_active else 0, int(sort_order or 0), addon_id),
        )

    def delete(self, addon_id):
        used = self._db.fetchone("SELECT COUNT(*) c FROM order_item_addons WHERE addon_id=?", (addon_id,))
        if used and used["c"] > 0:
            raise ValueError("Este adicional ja foi usado em pedidos. Desative em vez de excluir.")
        self._db.execute("DELETE FROM add_ons WHERE id=?", (addon_id,))


addon_service = AddonService()
