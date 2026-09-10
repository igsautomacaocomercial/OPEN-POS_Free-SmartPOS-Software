import datetime

from app.printing.escpos_builder import EscposBuilder, raster_bytes_from_png, _fit
from app.services.settings_service import settings_service
from app.utils.helpers import fmt_money, fmt_receipt_date, fmt_receipt_time, weekday_pt

BRANDING_LINE = "IGS Automacao Comercial"


class NoPrinterError(RuntimeError):
    pass


def list_printers() -> list:
    try:
        import win32print
    except ImportError:
        return []
    names = set()
    flags = getattr(win32print, "PRINTER_ENUM_LOCAL", 0) | getattr(
        win32print, "PRINTER_ENUM_CONNECTIONS", 0)
    for _, _, name, _ in win32print.EnumPrinters(flags):
        names.add(name)
    return sorted(names)


def _configured_printer() -> str | None:
    name = settings_service.get("printer_name", "").strip()
    if name:
        return name
    try:
        import win32print
        return win32print.GetDefaultPrinter()
    except Exception:
        return None


def _encoding() -> str:
    enc = settings_service.get("printer_encoding", "cp437").strip() or "cp437"
    return enc


def _cols() -> int:
    try:
        return max(16, min(64, int(settings_service.get("printer_cols", "42"))))
    except (TypeError, ValueError):
        return 42


def _cut_enabled() -> bool:
    return settings_service.get("printer_cut", "1") != "0"


def send_raw(data: bytes, printer: str | None = None) -> None:
    name = printer or _configured_printer()
    if not name:
        raise NoPrinterError(
            "Nenhuma impressora disponível. Conecte uma impressora POS e selecione-a "
            "em Configurações -> Impressão."
        )
    try:
        import win32print
    except ImportError:
        raise NoPrinterError("win32print não está disponível neste sistema.") from None
    available = list_printers()
    if available and name not in available:
        raise NoPrinterError(
            f"A impressora '{name}' não está conectada/disponível. Verifique se está ligada, "
            "depois selecione-a em Configurações -> Impressão."
        )
    try:
        hprinter = win32print.OpenPrinter(name)
    except Exception as e:
        raise NoPrinterError(f"Não foi possível abrir a impressora '{name}': {e}") from e
    try:
        win32print.StartDocPrinter(hprinter, 1, ("Receipt", None, "RAW"))
        try:
            win32print.StartPagePrinter(hprinter)
            win32print.WritePrinter(hprinter, data)
            win32print.EndPagePrinter(hprinter)
        finally:
            win32print.EndDocPrinter(hprinter)
    finally:
        win32print.ClosePrinter(hprinter)


def check_printer_connected(printer: str | None = None) -> str:
    """Return the printer name that would be used, or raise NoPrinterError if no
    POS printer is connected/available. Performs no printing."""
    name = printer or _configured_printer()
    if not name:
        raise NoPrinterError(
            "Nenhuma impressora POS conectada.\n\n"
            "Conecte uma impressora térmica/recibos a este computador, "
            "ligue-a e selecione-a em Configurações -> Impressão."
        )
    try:
        import win32print
    except ImportError:
        raise NoPrinterError(
            "Este sistema não consegue acessar a impressora. Verifique se a "
            "impressora POS está conectada e este app roda no Windows."
        ) from None
    available = list_printers()
    if available and name not in available:
        raise NoPrinterError(
            f"A impressora '{name}' não está conectada.\n\n"
            "Verifique se a impressora está ligada e conectada a este "
            "computador e selecione-a em Configurações -> Impressão."
        )
    return name


def print_or_error(data: bytes, parent=None) -> bool:
    """Print `data` if a POS printer is connected; otherwise show an error popup.
    Returns True on success, False (and shows a popup) if no printer."""
    from PySide6.QtWidgets import QMessageBox

    try:
        check_printer_connected()
        send_raw(data)
        return True
    except NoPrinterError as e:
        QMessageBox.critical(parent, "Printer Not Connected", str(e))
        return False
    except Exception as e:
        QMessageBox.critical(parent, "Print Error", str(e))
        return False



def _as_dict(row):
    return dict(row) if hasattr(row, "keys") else row


def _branding(b: EscposBuilder):
    b.left(BRANDING_LINE)


def _store_header(b: EscposBuilder, show_contact=True):
    settings = settings_service
    if settings.get("receipt_show_logo", "1") == "1":
        logo = settings.store_logo_path()
        if logo:
            try:
                data = raster_bytes_from_png(logo)
                if data:
                    b.raw(data).blank(1)
            except Exception:
                pass
    b.center(settings.get("store_name", "Open POS"), bold=True)
    if show_contact:
        for key in ("store_email", "store_phone", "store_address"):
            val = settings.get(key, "").strip()
            if val:
                b.center(val)
    b.rule()


def _items_for(order):
    from app.services.order_service import order_service
    items = []
    for item in order_service.get_items(order["id"]):
        row = dict(item)
        row["addons"] = [dict(a) for a in order_service.get_item_addons(item["id"])]
        items.append(row)
    return items


def _info_lines(order, cashier_label=True, show_day=True, show_waiter=True, show_rider=False):
    created = str(order["created_at"])
    try:
        dt = datetime.datetime.strptime(created, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        dt = datetime.datetime.now()
    lines = [("Pedido Nº", str(order["order_number"]))]
    if order.get("table_no"):
        lines.append(("Mesa", f"{order['table_no']}   Lugares: {order.get('seats', '-')}"))
    if show_waiter and order.get("waiter_name"):
        label = "Atendente" if order.get("order_type") == "delivery" else "Garçom"
        lines.append((label, order["waiter_name"]))
    if show_rider and order.get("rider_name"):
        lines.append(("Entregador", order["rider_name"]))
    if cashier_label and order.get("cashier_name"):
        lines.append(("Caixa", order["cashier_name"]))
    date_str = fmt_receipt_date(dt)
    if show_day:
        date_str += f"  ({weekday_pt(dt)})"
    lines.append(("Data", date_str))
    lines.append(("Hora", fmt_receipt_time(dt)))
    return lines


def _order_type_label(order):
    return {"dine-in": "NO LOCAL", "takeaway": "PARA VIAGEM", "delivery": "DELIVERY"}.get(
        order.get("order_type", "dine-in"), "DINE-IN"
    )


def _items_rows(order, show_price=True, items=None):
    from app.services.order_service import order_service
    source = [dict(i) for i in items] if items is not None else _items_for(order)
    rows = []
    for it in source:
        addons = it.get("addons") or [dict(a) for a in order_service.get_item_addons(it["id"])]
        addons_total = sum(float(a["price"] or 0) * float(a["qty"] or 0) for a in addons)
        rows.append({"name": it["name"], "qty": it["qty"], "price": (float(it["price"] or 0) + addons_total) if show_price else ""})
    return rows


def _summary_rows(order):
    currency = settings_service.get("currency", "R$")
    sub = float(order["subtotal"] or 0)
    disc = float(order["discount"] or 0)
    tax = float(order["tax"] or 0)
    charge = float(order.get("service_charge") or 0)
    total = float(order["total"] or 0)
    rows = [("Subtotal", fmt_money(sub, currency), False)]
    if disc > 0:
        rows.append(("Desconto", f"- {fmt_money(disc, currency)}", False))
    if tax > 0:
        rows.append((settings_service.get("tax_name", "Imposto"), fmt_money(tax, currency), False))
    if charge > 0:
        label = "Taxa de Entrega" if order.get("order_type") == "delivery" else "Taxa Para Viagem"
        rows.append((label, fmt_money(charge, currency), False))
    rows.append(("TOTAL", fmt_money(total, currency), True))
    return rows


def _new_builder() -> EscposBuilder:
    return EscposBuilder(cols=_cols(), encoding=_encoding())


def _kot_type_label(order) -> str:
    return {
        "dine-in": "MESA",
        "takeaway": "RETIRADA",
        "delivery": "DELIVERY",
    }.get(order.get("order_type", "dine-in"), str(order.get("order_type", "MESA")).upper())


def _kot_item_lines(items, cols: int) -> list[str]:
    from app.services.order_service import order_service
    qty_w = 3
    gap = 2
    name_w = max(16, cols - qty_w - gap)
    indent = " " * (qty_w + gap)
    lines = []
    for it in items:
        name = str(it.get("name", "")).strip().upper()
        action = str(it.get("kot_action") or "ADICIONAR").upper()
        qty = it.get("qty", 1)
        try:
            qty_s = f"{float(qty):g}"
        except (TypeError, ValueError):
            qty_s = str(qty)
        chunks = _fit(name, name_w)
        if action == "CANCELAR":
            lines.append("*** CANCELAR ITEM ***")
        elif action == "ALTERAR OBS":
            lines.append("*** ALTERAR OBSERVAÇÃO ***")
        for idx, chunk in enumerate(chunks):
            if idx == 0:
                lines.append(f"{qty_s.rjust(qty_w)}{' ' * gap}{chunk}")
            else:
                lines.append(f"{indent}{chunk}")
        instr = str(it.get("instructions") or "").strip()
        if instr:
            lines.append(f"{indent}>>> {instr.upper()} <<<")
        addons = it.get("addons") or [dict(a) for a in order_service.get_item_addons(it["id"])]
        for addon in addons:
            try:
                addon_qty = f"{float(addon.get('qty') or 1):g}"
            except (TypeError, ValueError):
                addon_qty = str(addon.get("qty") or 1)
            lines.append(f"{indent}+ {addon_qty}X {str(addon.get('name') or '').upper()}")
        if action in ("CANCELAR", "ALTERAR OBS"):
            lines.append("-" * cols)
    return lines


def _kot_text(order, items=None, title="KOT") -> str:
    order = _as_dict(order)
    items = [dict(i) for i in (items if items is not None else _items_for(order))]
    if not items:
        raise ValueError("Não há novos itens para imprimir.")

    cols = _cols()
    store = settings_service.get("store_name", "Open POS").strip() or "Open POS"
    created = str(order.get("created_at") or "")
    if " " in created:
        date_part, time_part = created.split(" ", 1)
    else:
        date_part, time_part = created, ""

    lines = [
        store.center(cols),
        str(title).center(cols),
        "",
        f"PEDIDO {order.get('order_number', '-') }".center(cols),
    ]
    if order.get("table_no"):
        mesa = f"MESA {str(order['table_no']).zfill(2)}"
        lines.append(mesa.center(cols))
    lines.append(f"TIPO: {_kot_type_label(order)}".center(cols))
    if date_part or time_part:
        lines.append(f"{date_part} - {time_part}".center(cols))
    if order.get("waiter_name"):
        label = "ATENDENTE" if order.get("order_type") == "delivery" else "GARÇOM"
        lines.append(f"{label}: {str(order['waiter_name']).upper()}".center(cols))
    if order.get("customer_name"):
        lines.append(f"CLIENTE: {str(order['customer_name']).upper()}".center(cols))
    lines.append("=" * cols)
    lines.append("QTD  PRODUTO")
    lines.append("=" * cols)
    lines.extend(_kot_item_lines(items, cols))
    lines.append("=" * cols)
    order_instr = str(order.get("instructions") or "").strip()
    lines.append("OBS:")
    lines.append(order_instr.upper() if order_instr else "SEM OBSERVAÇÕES")
    lines.append("=" * cols)
    lines.append("IGS Automacao Comercial".center(cols))
    lines.append("")
    lines.append("")
    return "\n".join(lines)


def _bill_text(order, title="CONTA", include_payment=False) -> str:
    order = _as_dict(order)
    cols = _cols()
    currency = settings_service.get("currency", "R$")
    store = settings_service.get("store_name", "Open POS").strip() or "Open POS"
    created = str(order.get("created_at") or "")
    if " " in created:
        date_part, time_part = created.split(" ", 1)
    else:
        date_part, time_part = created, ""

    def line(label, value):
        label = str(label)
        value = str(value)
        gap = max(2, cols - len(label) - len(value))
        return label + ("." * gap) + value

    def item_lines(order_items):
        qty_w = 3
        gap = 2
        name_w = max(14, cols - qty_w - gap - 10)
        price_w = 9
        indent = " " * (qty_w + gap)
        out = ["QTD  PRODUTO".ljust(qty_w + gap + name_w)]
        out.append("-" * cols)
        for it in order_items:
            name = str(it.get("name", "")).strip().upper()
            qty = it.get("qty", 1)
            try:
                qty_s = f"{float(qty):g}"
            except (TypeError, ValueError):
                qty_s = str(qty)
            addons = it.get("addons") or []
            addons_total = sum(float(a.get("price") or 0) * float(a.get("qty") or 0) for a in addons)
            unit_price = float(it.get("price") or 0) + addons_total
            price_s = fmt_money(unit_price, currency)
            chunks = _fit(name, name_w)
            for i, chunk in enumerate(chunks):
                if i == 0:
                    out.append(f"{qty_s.rjust(qty_w)}{' ' * gap}{chunk.ljust(name_w)}{price_s.rjust(price_w)}")
                else:
                    out.append(f"{indent}{chunk}")
            instr = str(it.get("instructions") or "").strip()
            if instr:
                out.append(f"{indent}>>> {instr.upper()} <<<")
            for addon in addons:
                try:
                    addon_qty = f"{float(addon.get('qty') or 1):g}"
                except (TypeError, ValueError):
                    addon_qty = str(addon.get("qty") or 1)
                addon_text = f"+ {addon_qty}X {str(addon.get('name') or '').upper()}"
                addon_price = fmt_money(float(addon.get("price") or 0), currency)
                out.append(f"{indent}{addon_text.ljust(name_w)}{addon_price.rjust(price_w)}")
        return out

    items = _items_for(order)
    subtotal = float(order.get("subtotal") or 0)
    discount = float(order.get("discount") or 0)
    tax = float(order.get("tax") or 0)
    charge = float(order.get("service_charge") or 0)
    total = float(order.get("total") or 0)

    lines = [
        store.center(cols),
        title.center(cols),
        "",
        f"PEDIDO {order.get('order_number', '-') }".center(cols),
    ]
    if order.get("table_no"):
        mesa = f"MESA {str(order['table_no']).zfill(2)}"
        if order.get("seats") is not None:
            mesa += f"  LUGARES {order.get('seats')}"
        lines.append(mesa.center(cols))
    lines.append(f"TIPO: {_order_type_label(order)}".center(cols))
    if date_part or time_part:
        lines.append(f"{date_part} - {time_part}".center(cols))
    if order.get("cashier_name"):
        lines.append(f"CAIXA: {order['cashier_name']}".center(cols))
    if order.get("waiter_name"):
        label = "ATENDENTE" if order.get("order_type") == "delivery" else "GARÇOM"
        lines.append(f"{label}: {order['waiter_name']}".center(cols))
    if order.get("customer_name"):
        lines.append(f"CLIENTE: {order['customer_name']}".center(cols))
    lines.append("=" * cols)
    lines.extend(item_lines(items))
    lines.append("=" * cols)
    if include_payment and order.get("payment_method"):
        lines.append(line("PAGAMENTO", str(order["payment_method"]).upper()))
    if include_payment and order.get("payment_details"):
        for ln in str(order["payment_details"]).split("\n"):
            if ln.strip():
                lines.append(ln.strip())
    lines.append(line("SUBTOTAL", fmt_money(subtotal, currency)))
    if discount > 0:
        lines.append(line("DESCONTO", fmt_money(discount, currency)))
    if charge > 0:
        lines.append(line("ACRÉSCIMO", fmt_money(charge, currency)))
    if tax > 0:
        lines.append(line(settings_service.get("tax_name", "IMPOSTO"), fmt_money(tax, currency)))
    lines.append("=" * cols)
    lines.append(line("TOTAL", fmt_money(total, currency)))
    lines.append("=" * cols)
    footer = settings_service.get("receipt_footer", "Obrigado pela preferência!").strip()
    lines.append(footer.center(cols))
    lines.append("Sistema desenvolvido por".center(cols))
    lines.append("IGS Automacao Comercial".center(cols))
    lines.append("")
    lines.append("")
    return "\n".join(lines)


def print_kot(order, items=None, title="KOT") -> bytes:
    b = _new_builder()
    text = _kot_text(order, items=items, title=title)
    try:
        payload = text.encode(_encoding(), errors="replace")
    except LookupError:
        payload = text.encode("cp437", errors="replace")
    data = b.raw(payload).build(cut=_cut_enabled())
    send_raw(data)
    return data


def print_request_bill(order) -> bytes:
    b = _new_builder()
    text = _bill_text(order, title="CONTA", include_payment=False)
    try:
        payload = text.encode(_encoding(), errors="replace")
    except LookupError:
        payload = text.encode("cp437", errors="replace")
    data = b.raw(payload).build(cut=_cut_enabled())
    send_raw(data)
    return data


def print_rider_bill(order) -> bytes:
    order = _as_dict(order)
    b = _new_builder()
    b.center("CÓPIA DO ENTREGADOR", bold=True, double=True)
    b.center("PEDIDO DE DELIVERY", bold=True)
    b.blank()
    b.kv("Pedido Nº", str(order["order_number"]))
    if order.get("rider_name"):
        b.kv("Entregador", order["rider_name"])
    b.rule()
    b.kv("Cliente", order.get("customer_name") or "-")
    if order.get("customer_phone"):
        b.kv("Telefone", order["customer_phone"])
    if order.get("customer_address"):
        b.left("Endereço:", bold=True)
        b.left(order["customer_address"])
    if order.get("payment_method"):
        b.kv("Pagamento", order["payment_method"])
    if order.get("change_needed"):
        b.kv("Troco", fmt_money(order.get("change_amount") or 0, settings_service.get("currency", "R$")))
    b.rule()
    b.items(_items_rows(order, show_price=True))
    b.rule()
    b.center("Entregue o quanto antes!", bold=True)
    _branding(b)
    data = b.build(cut=_cut_enabled())
    send_raw(data)
    return data


def print_final_bill(order) -> bytes:
    b = _new_builder()
    text = _bill_text(order, title="CONTA FINAL", include_payment=True)
    try:
        payload = text.encode(_encoding(), errors="replace")
    except LookupError:
        payload = text.encode("cp437", errors="replace")
    data = b.raw(payload).build(cut=_cut_enabled())
    send_raw(data)
    return data


def test_print() -> bytes:
    settings = settings_service
    b = _new_builder()
    _store_header(b, show_contact=True)
    b.center("TESTE DE IMPRESSÃO", bold=True, double=True)
    b.blank()
    b.kv("Loja", settings.get("store_name", "Open POS"))
    b.kv("Moeda", settings.get("currency", "R$"))
    b.kv("Data", fmt_receipt_date(datetime.datetime.now()))
    b.kv("Hora", fmt_receipt_time(datetime.datetime.now()))
    b.rule()
    b.items([{"name": "Item de Teste 1", "qty": 2, "price": 50},
             {"name": "Item de Teste 2", "qty": 1, "price": 100}])
    b.rule()
    b.summary([("Subtotal", fmt_money(200, settings.get("currency", "R$")), False),
               ("TOTAL", fmt_money(200, settings.get("currency", "R$")), True)])
    b.blank()
    b.center("Impressora conectada OK", bold=True)
    data = b.build(cut=_cut_enabled())
    send_raw(data)
    return data
