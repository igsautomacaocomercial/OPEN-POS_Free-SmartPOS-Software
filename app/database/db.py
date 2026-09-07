import shutil
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

from app.config import DB_PATH
from app.utils.helpers import hash_password

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    salt TEXT NOT NULL,
    full_name TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('admin','manager','cashier')),
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category_id INTEGER REFERENCES categories(id) ON DELETE SET NULL,
    name TEXT NOT NULL,
    price REAL NOT NULL DEFAULT 0,
    cost REAL NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS tables (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    table_no TEXT UNIQUE NOT NULL,
    seats INTEGER NOT NULL DEFAULT 2,
    status TEXT NOT NULL DEFAULT 'free',
    current_order_id INTEGER
);

CREATE TABLE IF NOT EXISTS staff (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'Garçom',
    phone TEXT,
    is_active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS customers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    phone TEXT UNIQUE NOT NULL,
    document TEXT NOT NULL DEFAULT '',
    cep TEXT NOT NULL DEFAULT '',
    email TEXT NOT NULL DEFAULT '',
    entity_type TEXT NOT NULL DEFAULT 'PF',
    address TEXT NOT NULL DEFAULT '',
    city TEXT NOT NULL DEFAULT '',
    state TEXT NOT NULL DEFAULT '',
    neighborhood TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS suppliers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    document TEXT NOT NULL DEFAULT '',
    phone TEXT NOT NULL DEFAULT '',
    cep TEXT NOT NULL DEFAULT '',
    email TEXT NOT NULL DEFAULT '',
    address TEXT NOT NULL DEFAULT '',
    city TEXT NOT NULL DEFAULT '',
    state TEXT NOT NULL DEFAULT '',
    neighborhood TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS neighborhoods (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    delivery_fee REAL NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS payment_methods (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    sort_order INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_number TEXT UNIQUE NOT NULL,
    order_type TEXT NOT NULL DEFAULT 'dine-in',
    table_id INTEGER,
    waiter_id INTEGER,
    rider_id INTEGER,
    cashier_id INTEGER,
    status TEXT NOT NULL DEFAULT 'open',
    subtotal REAL NOT NULL DEFAULT 0,
    discount REAL NOT NULL DEFAULT 0,
    discount_type TEXT NOT NULL DEFAULT 'amount',
    service_charge REAL NOT NULL DEFAULT 0,
    tax REAL NOT NULL DEFAULT 0,
    total REAL NOT NULL DEFAULT 0,
    instructions TEXT NOT NULL DEFAULT '',
    customer_name TEXT NOT NULL DEFAULT '',
    customer_phone TEXT NOT NULL DEFAULT '',
    customer_address TEXT NOT NULL DEFAULT '',
    payment_method TEXT NOT NULL DEFAULT 'Dinheiro',
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    closed_at TEXT
);

CREATE TABLE IF NOT EXISTS order_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    product_id INTEGER,
    name TEXT NOT NULL,
    price REAL NOT NULL DEFAULT 0,
    qty REAL NOT NULL DEFAULT 1,
    instructions TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS expense_categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS expenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category_id INTEGER REFERENCES expense_categories(id) ON DELETE SET NULL,
    category_name TEXT,
    description TEXT NOT NULL DEFAULT '',
    amount REAL NOT NULL DEFAULT 0,
    expense_date TEXT NOT NULL DEFAULT (date('now','localtime')),
    created_by INTEGER,
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS accounts_payable (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    description TEXT NOT NULL,
    account_id INTEGER,
    amount REAL NOT NULL DEFAULT 0,
    due_date TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    paid_at TEXT,
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE TABLE IF NOT EXISTS accounts_receivable (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    description TEXT NOT NULL,
    account_id INTEGER,
    amount REAL NOT NULL DEFAULT 0,
    due_date TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    paid_at TEXT,
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE TABLE IF NOT EXISTS cash_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    opened_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    opening_amount REAL NOT NULL DEFAULT 0,
    closed_at TEXT,
    closing_amount REAL,
    closing_note TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'open'
);
CREATE TABLE IF NOT EXISTS cash_moves (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL REFERENCES cash_sessions(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    reason TEXT NOT NULL DEFAULT '',
    amount REAL NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS chart_accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL DEFAULT '',
    name TEXT NOT NULL,
    type TEXT NOT NULL DEFAULT 'entrada' CHECK(type IN ('entrada','saida')),
    is_active INTEGER NOT NULL DEFAULT 1,
    sort_order INTEGER NOT NULL DEFAULT 0,
    UNIQUE(code, name)
);

CREATE INDEX IF NOT EXISTS idx_orders_created ON orders(created_at);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS idx_order_items_order ON order_items(order_id);
CREATE INDEX IF NOT EXISTS idx_expenses_date ON expenses(expense_date);
"""

_DEFAULT_SETTINGS = {
    "store_name": "Open POS",
    "store_logo": "",
    "store_email": "contato@sualoja.com.br",
    "store_phone": "(11) 99999-9999",
    "store_address": "Sua Rua, 123 - Sua Cidade",
    "currency": "R$",
    "tax_name": "Imposto",
    "tax_rate": "0",
    "receipt_footer": "Obrigado pela preferência!",
    "receipt_show_logo": "1",
    "receipt_show_address": "1",
    "delivery_charge": "0",
    "takeaway_charge": "0",
    "tax_dinein": "1",
    "tax_takeaway": "1",
    "tax_delivery": "1",
    "next_order_number": "1000",
    "printer_name": "",
    "printer_encoding": "cp437",
    "printer_cols": "42",
    "printer_cut": "1",
    "auto_backup": "0",
    "auto_backup_hours": "24",
}


class Database:
    _instance = None
    _lock = threading.RLock()

    def __init__(self, path: Path | None = None):
        self._conn = sqlite3.connect(str(path or DB_PATH), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._tls = threading.local()

    @classmethod
    def get(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
                cls._instance.init_schema()
                cls._instance.seed()
            return cls._instance

    @contextmanager
    def cursor(self):
        with self._lock:
            cur = self._conn.cursor()
            try:
                yield cur
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise
            finally:
                cur.close()

    def fetchall(self, sql, params=()):
        with self._lock:
            return self._conn.execute(sql, params).fetchall()

    def fetchone(self, sql, params=()):
        with self._lock:
            return self._conn.execute(sql, params).fetchone()

    def execute(self, sql, params=()):
        with self._lock:
            cur = self._conn.execute(sql, params)
            self._conn.commit()
            return cur.lastrowid

    def executemany(self, sql, seq):
        with self._lock:
            self._conn.executemany(sql, seq)
            self._conn.commit()

    def init_schema(self):
        self._conn.executescript(_SCHEMA)
        self._conn.commit()
        self._migrate()

    def _migrate(self):
        cols = {r["name"] for r in self._conn.execute("PRAGMA table_info(orders)").fetchall()}
        for name, ddl in {
            "customer_name": "TEXT NOT NULL DEFAULT ''",
            "customer_phone": "TEXT NOT NULL DEFAULT ''",
            "customer_address": "TEXT NOT NULL DEFAULT ''",
            "service_charge": "REAL NOT NULL DEFAULT 0",
            "rider_id": "INTEGER",
            "customer_id": "INTEGER",
            "neighborhood_id": "INTEGER",
        }.items():
            if name not in cols:
                self._conn.execute(f"ALTER TABLE orders ADD COLUMN {name} {ddl}")
        pcols = {r["name"] for r in self._conn.execute("PRAGMA table_info(products)").fetchall()}
        for name in ("stock", "barcode"):
            if name in pcols:
                self._conn.execute(f"ALTER TABLE products DROP COLUMN {name}")
        for table in ("accounts_payable", "accounts_receivable"):
            cols = {r["name"] for r in self._conn.execute(
                f"PRAGMA table_info({table})").fetchall()}
            if "account_id" not in cols:
                self._conn.execute(f"ALTER TABLE {table} ADD COLUMN account_id INTEGER")
        ccols = {r["name"] for r in self._conn.execute("PRAGMA table_info(customers)").fetchall()}
        for name, ddl in {
            "document": "TEXT NOT NULL DEFAULT ''",
            "cep": "TEXT NOT NULL DEFAULT ''",
            "email": "TEXT NOT NULL DEFAULT ''",
            "entity_type": "TEXT NOT NULL DEFAULT 'PF'",
            "city": "TEXT NOT NULL DEFAULT ''",
            "state": "TEXT NOT NULL DEFAULT ''",
            "neighborhood": "TEXT NOT NULL DEFAULT ''",
            "is_active": "INTEGER NOT NULL DEFAULT 1",
        }.items():
            if name not in ccols:
                self._conn.execute(f"ALTER TABLE customers ADD COLUMN {name} {ddl}")
        self._conn.execute("DELETE FROM settings WHERE key='tax_categories'")
        self._conn.commit()

    def seed(self):
        if not self.fetchone("SELECT id FROM users LIMIT 1"):
            h, salt = hash_password("admin123")
            self.execute(
                "INSERT INTO users (username, password_hash, salt, full_name, role) VALUES (?,?,?,?,?)",
                ("admin", h, salt, "Administrador", "admin"),
            )
        existing = {r["key"] for r in self.fetchall("SELECT key FROM settings")}
        for k, v in _DEFAULT_SETTINGS.items():
            if k not in existing:
                self.execute("INSERT INTO settings (key, value) VALUES (?,?)", (k, v))

        if not self.fetchone("SELECT id FROM categories LIMIT 1"):
            seed_categories = ["Café", "Chá", "Bebidas Frias", "Shakes", "Sobremesas", "Lanches"]
            for i, name in enumerate(seed_categories, 1):
                self.execute(
                    "INSERT INTO categories (name, sort_order) VALUES (?,?)", (name, i)
                )
            products = [
                ("Café Expresso", 250, 90, 1),
                ("Cappuccino", 350, 140, 1),
                ("Café com Leite", 380, 150, 1),
                ("Chocolate Quente", 400, 180, 1),
                ("Chá Karak", 150, 60, 2),
                ("Chá Verde", 200, 80, 2),
                ("Chá Gelado", 250, 100, 3),
                ("Café Gelado", 350, 150, 3),
                ("Milk Shake de Chocolate", 450, 200, 4),
                ("Milk Shake de Manga", 420, 180, 4),
                ("Fatia de Cheesecake", 550, 300, 5),
                ("Brownie", 450, 200, 5),
                ("Sanduíche", 400, 220, 6),
                ("Batata Frita", 300, 120, 6),
                ("Sanduíche de Frango", 550, 300, 6),
            ]
            for name, price, cost, cat in products:
                self.execute(
                    "INSERT INTO products (name, price, cost, category_id) VALUES (?,?,?,?)",
                    (name, price, cost, cat),
                )

        if not self.fetchone("SELECT id FROM staff LIMIT 1"):
            self.execute("INSERT INTO staff (name, role) VALUES (?,?)", ("Garçom 1", "Garçom"))
            self.execute("INSERT INTO staff (name, role) VALUES (?,?)", ("Garçom 2", "Garçom"))

        if not self.fetchone("SELECT id FROM tables LIMIT 1"):
            for i in range(1, 9):
                self.execute(
                    "INSERT INTO tables (table_no, seats) VALUES (?,?)", (str(i), 2 if i % 2 else 4)
                )

        if not self.fetchone("SELECT id FROM expense_categories LIMIT 1"):
            for name in ("Aluguel", "Contas (Água/Luz)", "Mercado", "Salários", "Diversos"):
                self.execute("INSERT INTO expense_categories (name) VALUES (?)", (name,))

        if not self.fetchone("SELECT id FROM payment_methods LIMIT 1"):
            for i, name in enumerate(("Dinheiro", "Cartão", "Pix"), 1):
                self.execute(
                    "INSERT INTO payment_methods (name, sort_order) VALUES (?,?)", (name, i)
                )

    def close(self):
        with self._lock:
            try:
                self._conn.close()
            except Exception:
                pass

    def backup(self):
        import datetime

        backup_dir = DB_PATH.parent / "backups"
        backup_dir.mkdir(exist_ok=True)
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        dest = backup_dir / f"openpos_backup_{stamp}.db"
        return self.backup_to(dest)

    def backup_to(self, dest):
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            cur = self._conn.cursor()
            cur.execute("VACUUM INTO ?", (str(dest),))
        return dest

    @staticmethod
    def _validate_backup(path: Path):
        required = {
            "users", "settings", "categories", "products", "tables", "staff",
            "orders", "order_items", "expenses", "expense_categories",
            "customers", "neighborhoods", "payment_methods",
            "accounts_payable", "accounts_receivable", "cash_sessions", "cash_moves",
            "chart_accounts", "suppliers",
        }
        conn = sqlite3.connect(str(path))
        try:
            conn.row_factory = sqlite3.Row
            tables = {r["name"] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            if not required.issubset(tables):
                raise ValueError(
                    "This file is not a valid Open POS backup (missing tables).")
            row = conn.execute("PRAGMA integrity_check").fetchone()
            if row and row["integrity_check"] != "ok":
                raise ValueError("Backup file failed the integrity check.")
        finally:
            conn.close()

    @classmethod
    def restore_from(cls, path: Path) -> "Database":
        path = Path(path)
        if not path.exists():
            raise ValueError("Backup file does not exist.")
        with cls._lock:
            cls._validate_backup(path)
            if cls._instance is not None:
                cls._instance.close()
            shutil.copyfile(path, DB_PATH)
            for suffix in ("-wal", "-shm"):
                extra = Path(str(DB_PATH) + suffix)
                if extra.exists():
                    try:
                        extra.unlink()
                    except OSError:
                        pass
            new = cls()
            new.init_schema()
            new.seed()
            cls._instance = new
            global db
            db = new
            rebind_services(new)
            return new

    @classmethod
    def reset_all(cls) -> "Database":
        with cls._lock:
            if cls._instance is not None:
                cls._instance.close()
            for p in (DB_PATH, Path(str(DB_PATH) + "-wal"), Path(str(DB_PATH) + "-shm")):
                if p.exists():
                    try:
                        p.unlink()
                    except OSError:
                        pass
            new = cls()
            new.init_schema()
            new.seed()
            cls._instance = new
            global db
            db = new
            rebind_services(new)
            return new


db = None


def get_db() -> Database:
    global db
    if db is None:
        db = Database.get()
    return db


def rebind_services(database: Database):
    """Re-point every service singleton's connection after a restore/reset."""
    from app.services import (
        auth_service, aux_service, expense_service, finance_service,
        order_service, product_service, report_service, settings_service,
        staff_service, table_service,
    )
    for mod in (auth_service, aux_service, expense_service, finance_service,
                order_service, product_service, report_service, settings_service,
                staff_service, table_service):
        singleton = getattr(mod, mod.__name__.rsplit(".", 1)[-1], None)
        if singleton is not None and hasattr(singleton, "_db"):
            singleton._db = database
    if hasattr(settings_service, "store_logo_path"):
        try:
            settings_service.store_logo_path()
        except Exception:
            pass

