import hashlib
import os
import secrets
from datetime import datetime


def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    salt = salt or secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000)
    return dk.hex(), salt


def verify_password(password: str, salt: str, password_hash: str) -> bool:
    dk, _ = hash_password(password, salt)
    return secrets.compare_digest(dk, password_hash)


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


_PT_DAYS = {
    "Monday": "Segunda-feira", "Tuesday": "Terça-feira", "Wednesday": "Quarta-feira",
    "Thursday": "Quinta-feira", "Friday": "Sexta-feira", "Saturday": "Sábado",
    "Sunday": "Domingo",
}
_PT_MONTHS = {
    "January": "janeiro", "February": "fevereiro", "March": "março",
    "April": "abril", "May": "maio", "June": "junho", "July": "julho",
    "August": "agosto", "September": "setembro", "October": "outubro",
    "November": "novembro", "December": "dezembro",
}
_PT_MONTHS_SHORT = {
    "Jan": "jan", "Feb": "fev", "Mar": "mar", "Apr": "abr", "May": "mai",
    "Jun": "jun", "Jul": "jul", "Aug": "ago", "Sep": "set", "Oct": "out",
    "Nov": "nov", "Dec": "dez",
}


def _br_number(value: float) -> str:
    txt = f"{abs(value):,.2f}"
    return txt.replace(",", "X").replace(".", ",").replace("X", ".")


def fmt_money(value: float, currency: str = "R$") -> str:
    try:
        value = float(value or 0)
    except (TypeError, ValueError):
        value = 0.0
    sign = "-" if value < 0 else ""
    return f"{sign}{currency} {_br_number(value)}"


def fmt_date(iso: str) -> str:
    try:
        return datetime.strptime(iso, "%Y-%m-%d").strftime("%d/%m/%Y")
    except Exception:
        return iso or ""


def fmt_datetime(iso: str) -> str:
    try:
        return datetime.strptime(iso, "%Y-%m-%d %H:%M:%S").strftime("%d/%m/%Y %H:%M")
    except Exception:
        return iso or ""


def fmt_date_long(dt) -> str:
    try:
        day = _PT_DAYS.get(dt.strftime("%A"), dt.strftime("%A"))
        month = _PT_MONTHS.get(dt.strftime("%B"), dt.strftime("%B"))
        return f"{day}, {dt.day:02d} de {month} de {dt.year}"
    except Exception:
        return dt.strftime("%d/%m/%Y")


def day_name(iso: str) -> str:
    try:
        d = datetime.strptime(iso, "%Y-%m-%d")
    except Exception:
        return ""
    return _PT_DAYS.get(d.strftime("%A"), d.strftime("%A"))


def fmt_day_label(dt) -> str:
    return f"{dt.day:02d} {month_abbr_pt(dt)}"


def month_abbr_pt(dt) -> str:
    return _PT_MONTHS_SHORT.get(dt.strftime("%b"), dt.strftime("%b"))


def weekday_pt(dt) -> str:
    return _PT_DAYS.get(dt.strftime("%A"), dt.strftime("%A"))


def fmt_receipt_date(dt) -> str:
    return f"{dt.day:02d}/{month_abbr_pt(dt)}/{dt.year}"


def fmt_receipt_time(dt) -> str:
    return dt.strftime("%H:%M")


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)
    return path