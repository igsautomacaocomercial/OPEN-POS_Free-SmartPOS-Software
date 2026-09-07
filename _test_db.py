import sys
sys.path.insert(0, ".")
from app.config import DB_PATH
from app.database.db import get_db

print("DB path:", DB_PATH)
db = get_db()
tables = [r["name"] for r in db.fetchall(
    "SELECT name FROM sqlite_master WHERE type='table'")]
print("Tables:", sorted(tables))
if "users" in tables:
    users = db.fetchall("SELECT username, role FROM users")
    print("Users:", users)