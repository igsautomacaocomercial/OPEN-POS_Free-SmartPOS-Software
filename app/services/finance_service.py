import datetime

from app.database.db import get_db


def _now():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class FinanceService:
    def __init__(self, database=None):
        self._db = database or get_db()

    # ----------------------- Caixa -----------------------
    def open_session(self, opening_amount):
        if self.current_session():
            raise ValueError("Já existe um caixa aberto.")
        return self._db.execute(
            "INSERT INTO cash_sessions (opening_amount) VALUES (?)",
            (float(opening_amount),),
        )

    def current_session(self):
        return self._db.fetchone(
            "SELECT * FROM cash_sessions WHERE status='open' ORDER BY id DESC LIMIT 1"
        )

    def sessions(self, limit=50):
        return self._db.fetchall(
            "SELECT * FROM cash_sessions ORDER BY id DESC LIMIT ?", (limit,)
        )

    def add_move(self, session_id, kind, amount, reason):
        if kind not in ("entrada", "saida"):
            raise ValueError("kind deve ser entrada ou saida")
        self._db.execute(
            "INSERT INTO cash_moves (session_id, kind, amount, reason) VALUES (?,?,?,?)",
            (session_id, kind, float(amount), reason),
        )

    def record_sale(self, amount, note):
        session = self.current_session()
        if session:
            self.add_move(session["id"], "entrada", amount, note or "Venda")

    def record_expense(self, amount, note):
        session = self.current_session()
        if session:
            self.add_move(session["id"], "saida", amount, note or "Despesa")

    def close_session(self, session_id, closing_amount, note=""):
        self._db.execute(
            "UPDATE cash_sessions SET status='closed', closing_amount=?, closing_note=?, "
            "closed_at=? WHERE id=? AND status='open'",
            (float(closing_amount), note, _now(), session_id),
        )

    def summary(self, session_id):
        rows = self._db.fetchall(
            "SELECT kind, SUM(amount) AS total FROM cash_moves WHERE session_id=? GROUP BY kind",
            (session_id,),
        )
        entrada = 0.0
        saida = 0.0
        for r in rows:
            if r["kind"] == "entrada":
                entrada = float(r["total"] or 0)
            elif r["kind"] == "saida":
                saida = float(r["total"] or 0)
        return {"entrada": entrada, "saida": saida, "liquido": entrada - saida}

    def movements(self, session_id, limit=500):
        return self._db.fetchall(
            "SELECT * FROM cash_moves WHERE session_id=? ORDER BY id DESC LIMIT ?",
            (session_id, limit),
        )

    # ------------------- Contas a Pagar -------------------
    def add_payable(self, description, amount, due_date, notes="", account_id=None):
        if not description.strip():
            raise ValueError("Informe a descrição.")
        if float(amount) <= 0:
            raise ValueError("Informe um valor válido.")
        self._db.execute(
            "INSERT INTO accounts_payable (description, amount, due_date, notes, account_id) "
            "VALUES (?,?,?,?,?)",
            (description.strip(), float(amount), due_date, notes.strip(), account_id),
        )

    def list_payables(self, status="all", page=1, per_page=100000, today=None):
        return self._list_bills("accounts_payable", status, page, per_page, today)

    def count_payables(self, status="all", today=None):
        return self._count_bills("accounts_payable", status, today)

    def pay_bill(self, bill_id):
        self._db.execute(
            "UPDATE accounts_payable SET status='paid', paid_at=? WHERE id=?",
            (_now(), bill_id),
        )

    def delete_payable(self, bill_id):
        self._db.execute("DELETE FROM accounts_payable WHERE id=?", (bill_id,))

    # ------------------- Contas a Receber -------------------
    def add_receivable(self, description, amount, due_date, notes="", account_id=None):
        if not description.strip():
            raise ValueError("Informe a descrição.")
        if float(amount) <= 0:
            raise ValueError("Informe um valor válido.")
        self._db.execute(
            "INSERT INTO accounts_receivable (description, amount, due_date, notes, account_id) "
            "VALUES (?,?,?,?,?)",
            (description.strip(), float(amount), due_date, notes.strip(), account_id),
        )

    def list_receivables(self, status="all", page=1, per_page=100000, today=None):
        return self._list_bills("accounts_receivable", status, page, per_page, today)

    def count_receivables(self, status="all", today=None):
        return self._count_bills("accounts_receivable", status, today)

    def receive_bill(self, bill_id):
        self._db.execute(
            "UPDATE accounts_receivable SET status='paid', paid_at=? WHERE id=?",
            (_now(), bill_id),
        )

    def delete_receivable(self, bill_id):
        self._db.execute("DELETE FROM accounts_receivable WHERE id=?", (bill_id,))

    # ---------------- Paginação e Filtros ----------------
    STATUS_ENUM = {"paid": "paid", "pending": "pending", "overdue": "overdue", "ontime": "ontime"}

    @staticmethod
    def _today_str():
        return datetime.date.today().strftime("%Y-%m-%d")

    @staticmethod
    def _status_clause(table, status, today=None):
        today = today or FinanceService._today_str()
        if status == "paid":
            return f"({table}.status='paid')"
        if status == "pending":
            return f"({table}.status='pending')"
        if status == "overdue":
            return f"({table}.status='pending' AND COALESCE({table}.due_date,'') <> '' AND {table}.due_date < '{today}')"
        if status == "ontime":
            return (f"({table}.status='pending' AND "
                    f"(COALESCE({table}.due_date,'') = '' OR {table}.due_date >= '{today}'))")
        return "1=1"

    def _list_bills(self, table, status="all", page=1, per_page=100000, today=None):
        page = max(1, int(page))
        per_page = max(1, int(per_page))
        offset = (page - 1) * per_page
        clause = self._status_clause(table, status, today)
        return self._db.fetchall(
            f"SELECT {table}.*, ca.name AS account_name FROM {table} "
            f"LEFT JOIN chart_accounts ca ON ca.id={table}.account_id "
            f"WHERE {clause} "
            f"ORDER BY ({table}.status='pending') DESC, "
            f"COALESCE({table}.due_date,'9999-12-31') ASC "
            f"LIMIT ? OFFSET ?",
            (per_page, offset),
        )

    def _count_bills(self, table, status="all", today=None):
        clause = self._status_clause(table, status, today)
        row = self._db.fetchone(
            f"SELECT COUNT(*) AS c FROM {table} WHERE {clause}"
        )
        return row["c"] if row else 0

    def count_movements(self, session_id):
        row = self._db.fetchone(
            "SELECT COUNT(*) AS c FROM cash_moves WHERE session_id=?", (session_id,)
        )
        return row["c"] if row else 0

    def movements_page(self, session_id, page=1, per_page=50):
        page = max(1, int(page))
        per_page = max(1, int(per_page))
        offset = (page - 1) * per_page
        return self._db.fetchall(
            "SELECT * FROM cash_moves WHERE session_id=? ORDER BY id DESC LIMIT ? OFFSET ?",
            (session_id, per_page, offset),
        )

    # ---------------- Relatórios de Financeiro ----------------
    def sessions_between(self, start, end):
        return self._db.fetchall(
            "SELECT * FROM cash_sessions WHERE date(COALESCE(opened_at,'')) BETWEEN ? AND ? "
            "ORDER BY id DESC",
            (start, end),
        )

    def movements_between(self, start, end):
        return self._db.fetchall(
            "SELECT cm.*, cs.opening_amount AS opening_amount FROM cash_moves cm "
            "LEFT JOIN cash_sessions cs ON cs.id=cm.session_id "
            "WHERE date(COALESCE(cm.created_at,'')) BETWEEN ? AND ? ORDER BY cm.id DESC",
            (start, end),
        )

    def _bills_between(self, table, start, end):
        return self._db.fetchall(
            f"SELECT b.*, ca.name AS account_name FROM {table} b "
            f"LEFT JOIN chart_accounts ca ON ca.id=b.account_id "
            f"WHERE (COALESCE(b.due_date,'') <> '' AND date(b.due_date) BETWEEN ? AND ?) "
            f"OR (b.status='paid' AND COALESCE(b.paid_at,'') <> '' "
            f"AND date(b.paid_at) BETWEEN ? AND ?) "
            f"ORDER BY (b.status='pending') DESC, COALESCE(b.due_date,'9999-12-31') ASC",
            (start, end, start, end),
        )

    def payables_between(self, start, end):
        return self._bills_between("accounts_payable", start, end)

    def receivables_between(self, start, end):
        return self._bills_between("accounts_receivable", start, end)


finance_service = FinanceService()