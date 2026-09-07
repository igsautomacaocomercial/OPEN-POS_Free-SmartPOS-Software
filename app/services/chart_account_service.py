from app.database.db import get_db


class ChartAccountService:
    def __init__(self):
        self._db = get_db()

    def list_all(self):
        return self._db.fetchall(
            "SELECT * FROM chart_accounts ORDER BY type, sort_order, name"
        )

    def list_active(self):
        return self._db.fetchall(
            "SELECT * FROM chart_accounts WHERE is_active=1 ORDER BY type, sort_order, name"
        )

    def add(self, name, code="", account_type="entrada"):
        if not name.strip():
            raise ValueError("Informe o nome da conta.")
        n = self._db.fetchone(
            "SELECT COALESCE(MAX(sort_order),0)+1 n FROM chart_accounts WHERE type=?",
            (account_type,),
        )
        self._db.execute(
            "INSERT INTO chart_accounts (code, name, type, sort_order) VALUES (?,?,?,?)",
            (code.strip(), name.strip(), account_type, n["n"] if n else 1),
        )

    def update(self, account_id, name, code="", account_type="entrada", is_active=True):
        self._db.execute(
            "UPDATE chart_accounts SET code=?, name=?, type=?, is_active=? WHERE id=?",
            (code.strip(), name.strip(), account_type, 1 if is_active else 0, account_id),
        )

    def delete(self, account_id):
        used = self._db.fetchone(
            "SELECT (SELECT COUNT(*) FROM accounts_payable WHERE account_id=?) + "
            "(SELECT COUNT(*) FROM accounts_receivable WHERE account_id=?) c",
            (account_id, account_id),
        )
        if used and used["c"] > 0:
            raise ValueError(
                "Esta conta está vinculada a lançamentos. Desative-a em vez de excluí-la."
            )
        self._db.execute("DELETE FROM chart_accounts WHERE id=?", (account_id,))


chart_account_service = ChartAccountService()