from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QComboBox, QDialog, QFrame, QHBoxLayout, QLabel, QInputDialog, QLineEdit, QListWidget,
    QListWidgetItem, QMessageBox, QPushButton, QScrollArea, QTabWidget, QTableWidget,
    QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget,
)

from app.printing.printer_service import (
    print_final_bill, print_kot, print_request_bill, print_rider_bill,
)
from app.services.auth_service import auth_service
from app.services.aux_service import customer_service, neighborhood_service
from app.services.brasil_api import brazil_api_service, only_digits
from app.services.order_service import order_service
from app.services.aux_service import payment_service
from app.services.settings_service import settings_service
from app.services.staff_service import staff_service
from app.ui.cart_panel import CartPanel
from app.ui.icons import icon_pixmap, make_icon
from app.ui.keys import bind_table_keys
from app.utils.helpers import fmt_datetime, fmt_money

ORDER_TYPE_LABEL = {"takeaway": "Para Viagem", "delivery": "Entrega"}


def _as_dict(row):
    return dict(row) if hasattr(row, "keys") else row


class OrderDetailDialog(QDialog):
    def __init__(self, order, parent=None):
        super().__init__(parent)
        self.order = order
        self.setWindowTitle(f"Pedido #{order['order_number']}")
        self.resize(460, 560)
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(8)

        currency = settings_service.get("currency", "R$")

        head = QHBoxLayout()
        t = QLabel(f"Pedido #{order['order_number']}")
        t.setStyleSheet("font-size: 20px; font-weight: 800;")
        head.addWidget(t)
        head.addStretch()
        st = QLabel(ORDER_TYPE_LABEL.get(order["order_type"], order["order_type"]).upper())
        st.setStyleSheet("background: #eef2ff; color: #4f46e5; font-weight: 800; padding: 4px 12px; border-radius: 12px;")
        head.addWidget(st)
        root.addLayout(head)

        info = []
        info.append(f"Data:   {fmt_datetime(order['created_at'])}")
        if order.get("waiter_name"):
            label = "Atendente" if order.get("order_type") == "delivery" else "Garçom"
            info.append(f"{label}:   {order['waiter_name']}")
        if order.get("rider_name"):
            info.append(f"Motoqueiro:   {order['rider_name']}")
        if order.get("customer_name"):
            info.append(f"Cliente:   {order['customer_name']}")
        if order.get("customer_phone"):
            info.append(f"Telefone:   {order['customer_phone']}")
        if order.get("customer_address"):
            info.append(f"Endereço:   {order['customer_address']}")
        if order.get("payment_method"):
            info.append(f"Pagamento:   {order['payment_method']}")
        if order.get("payment_details"):
            for line in str(order["payment_details"]).split("\n"):
                if line.strip():
                    info.append(f"· {line.strip()}")
        if order.get("change_needed"):
            troco = fmt_money(order.get("change_amount") or 0, currency)
            info.append(f"Troco:   {troco}")
        il = QLabel("\n".join(info))
        il.setProperty("muted", True)
        root.addWidget(il)

        self.items = QTableWidget(0, 3)
        self.items.setHorizontalHeaderLabels(["Item", "Qtd", "Valor"])
        self.items.verticalHeader().setVisible(False)
        self.items.setEditTriggers(QTableWidget.NoEditTriggers)
        self.items.horizontalHeader().setStretchLastSection(True)
        root.addWidget(self.items, 1)
        self._fill_items()

        rows = []
        rows.append(f"Subtotal:   {fmt_money(order['subtotal'], currency)}")
        if order["discount"]:
            rows.append(f"Desconto:   - {fmt_money(order['discount'], currency)}")
        if order["tax"]:
            rows.append(f"{settings_service.get('tax_name','Imposto')}:   {fmt_money(order['tax'], currency)}")
        if order["service_charge"]:
            label = "Taxa de entrega" if order["order_type"] == "delivery" else "Taxa para viagem"
            rows.append(f"{label}:   {fmt_money(order['service_charge'], currency)}")
        rows.append(f"TOTAL:   {fmt_money(order['total'], currency)}")
        tl = QLabel("\n".join(rows))
        tl.setStyleSheet("font-weight: 700; font-size: 14px;")
        root.addWidget(tl)

        btns = QHBoxLayout()
        b_print = QPushButton("   Imprimir Conta")
        b_print.setProperty("primary", True)
        b_print.setIcon(make_icon("print", "#ffffff", 24))
        b_print.setIconSize(QSize(18, 18))
        b_print.clicked.connect(lambda: self._print(print_request_bill))
        btns.addWidget(b_print)
        if order["order_type"] == "delivery" and order.get("rider_name"):
            b_rider = QPushButton("   Cópia do Motoqueiro")
            b_rider.setIcon(make_icon("box", "#4b5563", 24))
            b_rider.setIconSize(QSize(18, 18))
            b_rider.clicked.connect(lambda: self._print(print_rider_bill))
            btns.addWidget(b_rider)
        btns.addStretch()
        close = QPushButton("Fechar")
        close.clicked.connect(self.accept)
        btns.addWidget(close)
        root.addLayout(btns)

    def _fill_items(self):
        items = order_service.get_items(self.order["id"])
        currency = settings_service.get("currency", "R$")
        self.items.setRowCount(len(items))
        for i, it in enumerate(items):
            self.items.setItem(i, 0, QTableWidgetItem(it["name"]))
            self.items.setItem(i, 1, QTableWidgetItem(str(it["qty"])))
            self.items.setItem(i, 2, QTableWidgetItem(fmt_money(it["price"] * it["qty"], currency)))
        self.items.resizeColumnsToContents()

    def _print(self, fn):
        try:
            fn(self.order)
        except Exception as e:
            QMessageBox.critical(self, "Erro de Impressão", str(e))


class QuickSalePage(QWidget):
    def __init__(self, order_type, parent=None):
        super().__init__(parent)
        self.order_type = order_type
        self.order_id = None
        self.payment_confirmed = False
        self.payment_selected = False
        self.payment_method = "Dinheiro"
        self.payment_change_needed = False
        self.payment_change_amount = 0.0
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 14, 20, 14)
        root.setSpacing(10)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_new(), "Novo Pedido")
        self.tabs.addTab(self._build_pending(), "Pendentes")
        self.tabs.addTab(self._build_completed(), "Concluídos")
        self.tabs.currentChanged.connect(lambda _: self._refresh_tab())
        root.addWidget(self.tabs)

    # ---------------- New Order ----------------
    def _build_new(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 12, 0, 8)
        lay.setSpacing(10)

        head = QFrame()
        head.setProperty("card", True)
        vh = QVBoxLayout(head)
        vh.setContentsMargins(16, 10, 16, 10)
        vh.setSpacing(8)

        row1 = QHBoxLayout()
        row1.setSpacing(10)

        if self.order_type == "delivery":
            section = QLabel("Cliente")
            section.setStyleSheet("font-weight: 800; color: #111827;")
            vh.addWidget(section)

            customer_row = QHBoxLayout()
            customer_row.setSpacing(10)
            self.phone = QLineEdit()
            self.phone.setPlaceholderText("Telefone do cliente")
            self.phone.setMinimumWidth(190)
            self.phone.setStyleSheet(
                "QLineEdit {"
                "background-color: #E0F7FA;"
                "border: 2px solid #0288D1;"
                "border-radius: 8px;"
                "padding: 8px 12px;"
                "font-size: 13px;"
                "font-weight: 700;"
                "color: #000000;"
                "}"
            )
            self.phone.editingFinished.connect(self._lookup_customer)
            self.customer = QLineEdit()
            self.customer.setPlaceholderText("Nome do cliente")
            self.customer.setMinimumWidth(180)
            self.btn_new_customer = QPushButton("+ Cadastrar Cliente")
            self.btn_new_customer.setProperty("warning", True)
            self.btn_new_customer.clicked.connect(self._register_customer)
            self.btn_edit_customer = QPushButton("   Editar Cliente")
            self.btn_edit_customer.setIcon(make_icon("pencil", "#4b5563", 24))
            self.btn_edit_customer.setIconSize(QSize(18, 18))
            self.btn_edit_customer.clicked.connect(self._edit_customer)
            customer_row.addWidget(self.phone)
            customer_row.addWidget(self.customer, 1)
            customer_row.addWidget(self.btn_new_customer)
            customer_row.addWidget(self.btn_edit_customer)
            vh.addLayout(customer_row)

            section = QLabel("Entrega")
            section.setStyleSheet("font-weight: 800; color: #111827;")
            vh.addWidget(section)

            delivery_row = QHBoxLayout()
            delivery_row.setSpacing(10)
            self.address = QLineEdit()
            self.address.setPlaceholderText("Endereço de entrega")
            self.address.setMinimumWidth(260)
            self.address_number = QLineEdit()
            self.address_number.setPlaceholderText("Nº")
            self.address_number.setMinimumWidth(70)
            self.address_complement = QLineEdit()
            self.address_complement.setPlaceholderText("Complemento")
            self.address_complement.setMinimumWidth(130)
            self.neighborhood = QComboBox()
            self.neighborhood.setMinimumWidth(150)
            self.neighborhood.addItem("— Bairro —", None)
            for nb in neighborhood_service.list_active():
                self.neighborhood.addItem(nb["name"], nb["id"])
            self.neighborhood.currentIndexChanged.connect(self._neighborhood_changed)
            delivery_row.addWidget(self.address, 2)
            delivery_row.addWidget(self.address_number)
            delivery_row.addWidget(self.address_complement, 1)
            delivery_row.addWidget(self.neighborhood)
            vh.addLayout(delivery_row)

            section = QLabel("Operação")
            section.setStyleSheet("font-weight: 800; color: #111827;")
            vh.addWidget(section)

        attendant_label = "Atendente:" if self.order_type == "delivery" else "Garçom:"
        row1.addWidget(QLabel(attendant_label))
        self.waiter = QComboBox()
        self.waiter.setMinimumWidth(150)
        self.waiter.addItem("— Selecionar —", None)
        for s in staff_service.list_waiters():
            self.waiter.addItem(s["name"], s["id"])
        self.waiter.currentIndexChanged.connect(self._waiter_changed)
        row1.addWidget(self.waiter)
        row1.addStretch()
        charge = settings_service.get_float(
            "delivery_charge" if self.order_type == "delivery" else "takeaway_charge", 0
        )
        self.charge_lbl = QLabel(
            f"Taxa: {fmt_money(charge, settings_service.get('currency','Rs'))}"
        )
        self.charge_lbl.setStyleSheet("font-weight: 700; color: #4f46e5;")
        row1.addWidget(self.charge_lbl)
        self.payment_status = QLabel("Pagamento: não definido")
        self.payment_status.setStyleSheet("font-weight: 700; color: #6b7280;")
        row1.addWidget(self.payment_status)
        vh.addLayout(row1)
        lay.addWidget(head)

        self.cart = CartPanel()
        self.cart.grid.product_clicked.connect(self._add_product)
        self.cart.load_categories()
        lay.addWidget(self.cart, 1)

        actions = QHBoxLayout()
        actions.setSpacing(10)
        self.btn_kot = QPushButton("   Imprimir KOT e Enviar para Pendentes")
        self.btn_kot.setProperty("warning", True)
        self.btn_kot.setIcon(make_icon("print", "#ffffff", 24))
        self.btn_kot.setIconSize(QSize(18, 18))
        self.btn_kot.clicked.connect(self._send_to_pending)
        self.btn_payment = QPushButton("   Forma de Pagamento")
        self.btn_payment.setIcon(make_icon("card", "#4f46e5", 24))
        self.btn_payment.setIconSize(QSize(18, 18))
        self.btn_payment.clicked.connect(self._select_payment_method)
        if self.order_type == "takeaway":
            self.btn_finalize_now = QPushButton("   Finalizar Venda")
            self.btn_finalize_now.setProperty("success", True)
            self.btn_finalize_now.setIcon(make_icon("check", "#ffffff", 24))
            self.btn_finalize_now.setIconSize(QSize(18, 18))
            self.btn_finalize_now.clicked.connect(self._finalize_now)
        self.btn_clear = QPushButton("   Limpar Pedido")
        self.btn_clear.setIcon(make_icon("trash", "#ef4444", 24))
        self.btn_clear.setIconSize(QSize(18, 18))
        self.btn_clear.clicked.connect(self._clear)
        actions.addWidget(self.btn_kot)
        actions.addWidget(self.btn_payment)
        if self.order_type == "takeaway":
            actions.addWidget(self.btn_finalize_now)
        actions.addStretch()
        actions.addWidget(self.btn_clear)
        lay.addLayout(actions)
        return w

    def _delivery_charge(self):
        if self.order_type != "delivery":
            return 0.0
        nid = self.neighborhood.currentData() if hasattr(self, "neighborhood") else None
        if nid is not None:
            nb = neighborhood_service.get(nid)
            if nb:
                return float(nb["delivery_fee"] or 0)
        return settings_service.get_float("delivery_charge", 0)

    def _delivery_address(self):
        parts = [self.address.text().strip()]
        if hasattr(self, "address_number") and self.address_number.text().strip():
            parts.append(self.address_number.text().strip())
        if hasattr(self, "address_complement") and self.address_complement.text().strip():
            parts.append(self.address_complement.text().strip())
        return ", ".join(p for p in parts if p)

    def _ensure_order(self):
        if self.order_type == "delivery" and not self._ensure_delivery_attendant():
            return None
        if self.order_id is not None:
            return self.order_id
        waiter_id = self.waiter.currentData()
        if waiter_id is None:
            label = "atendente" if self.order_type == "delivery" else "garçom"
            QMessageBox.warning(self, "Atendimento", f"Selecione um {label} primeiro.")
            return None
        rider_id = None
        customer_name = customer_phone = customer_address = ""
        if self.order_type == "delivery":
            customer_name = self.customer.text().strip()
            customer_phone = self.phone.text().strip()
            customer_address = self._delivery_address()
            if not customer_address:
                QMessageBox.warning(self, "Endereço Obrigatório", "Informe o endereço de entrega.")
                return None
        charge = self._delivery_charge() if self.order_type == "delivery" else settings_service.get_float("takeaway_charge", 0)
        order = order_service.create_order(
            order_type=self.order_type,
            cashier_id=auth_service.current_user["id"],
            waiter_id=waiter_id,
            rider_id=rider_id,
            customer_name=customer_name,
            customer_phone=customer_phone,
            customer_address=customer_address,
            service_charge=charge,
            payment_method=self.payment_method if self.order_type == "delivery" else "Dinheiro",
            change_needed=0,
            change_amount=0,
        )
        self.order_id = order["id"]
        self.cart.load_order(order["id"])
        self.payment_confirmed = False
        self.payment_selected = False
        return self.order_id

    def _sync_order_header(self):
        if self.order_id is None or self.order_type != "delivery":
            return
        order = order_service.get(self.order_id)
        order_service.set_customer_info(
            self.order_id,
            customer_id=order["customer_id"] if order else None,
            name=self.customer.text().strip(),
            phone=self.phone.text().strip(),
            address=self._delivery_address(),
        )
        order_service.set_service_charge(self.order_id, self._delivery_charge())

    def _add_product(self, product_id):
        oid = self._ensure_order()
        if oid is None:
            return
        order_service.add_item(oid, product_id=product_id, qty=1)
        self.cart.refresh()

    def _ensure_delivery_attendant(self):
        if self.order_type != "delivery" or self.waiter.currentData() is not None:
            return True
        attendant_id = self._select_attendant_touch()
        if attendant_id is None:
            return False
        idx = self.waiter.findData(attendant_id)
        if idx >= 0:
            self.waiter.setCurrentIndex(idx)
            if self.order_id is not None:
                order_service.set_waiter(self.order_id, attendant_id)
            return True
        QMessageBox.warning(self, "Atendente", "Não foi possível selecionar o atendente.")
        return False

    def _select_attendant_touch(self):
        attendants = staff_service.list_waiters()
        if not attendants:
            QMessageBox.information(self, "Atendente", "Nenhum atendente ativo cadastrado.")
            return None

        dlg = QDialog(self)
        dlg.setWindowTitle("Selecionar Atendente")
        dlg.setModal(True)
        dlg.resize(520, 420)
        selected = {"id": None}

        root = QVBoxLayout(dlg)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(12)

        title = QLabel("Selecione o atendente do delivery")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 18px; font-weight: 800; color: #111827;")
        root.addWidget(title)

        hint = QLabel("O item será lançado após a seleção.")
        hint.setAlignment(Qt.AlignCenter)
        hint.setProperty("muted", True)
        root.addWidget(hint)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        list_widget = QWidget()
        list_box = QVBoxLayout(list_widget)
        list_box.setSpacing(10)
        for attendant in attendants:
            btn = QPushButton(attendant["name"])
            btn.setMinimumHeight(54)
            btn.setStyleSheet("font-size: 16px; font-weight: 700; text-align: left; padding: 8px 16px;")
            btn.clicked.connect(lambda _=False, aid=attendant["id"]: self._accept_attendant_touch(dlg, selected, aid))
            list_box.addWidget(btn)
        list_box.addStretch()
        scroll.setWidget(list_widget)
        root.addWidget(scroll, 1)

        cancel = QPushButton("Cancelar")
        cancel.setMinimumHeight(42)
        cancel.clicked.connect(dlg.reject)
        root.addWidget(cancel, alignment=Qt.AlignRight)

        return selected["id"] if dlg.exec() else None

    def _accept_attendant_touch(self, dlg, selected, attendant_id):
        selected["id"] = attendant_id
        dlg.accept()

    def _waiter_changed(self, idx):
        if self.order_id is not None:
            order_service.set_waiter(self.order_id, self.waiter.currentData())

    def _neighborhood_changed(self, idx):
        fee = self._delivery_charge()
        self.charge_lbl.setText(f"Taxa: {fmt_money(fee, settings_service.get('currency', 'R$'))}")
        if self.order_id is not None:
            order_service.set_service_charge(self.order_id, fee)
            self.cart.refresh()

    def _sync_payment_button(self):
        if not hasattr(self, "btn_payment"):
            return
        if self.payment_selected:
            label = self.payment_method
            if self.payment_method == "Dinheiro" and self.payment_change_needed:
                label += f" · Troco {fmt_money(self.payment_change_amount, settings_service.get('currency', 'R$'))}"
            self.btn_payment.setText(f"   Pagamento: {label}")
            if hasattr(self, "payment_status"):
                self.payment_status.setText(f"Pagamento: {label}")
                self.payment_status.setStyleSheet("font-weight: 800; color: #10b981;")
        else:
            self.btn_payment.setText("   Forma de Pagamento")
            if hasattr(self, "payment_status"):
                self.payment_status.setText("Pagamento: não definido")
                self.payment_status.setStyleSheet("font-weight: 700; color: #6b7280;")

    def _select_payment_method(self):
        oid = self._ensure_order()
        if oid is None:
            return False
        methods = payment_service.list_active_names() or ["Dinheiro", "Pix", "Cartão de crédito", "Cartão de débito"]
        idx = methods.index(self.payment_method) if self.payment_method in methods else 0
        method, ok = QInputDialog.getItem(
            self,
            "Forma de Pagamento",
            "Selecione a forma de pagamento:",
            methods,
            idx,
            False,
        )
        if not ok or not method:
            return False
        change_needed = False
        change_amount = 0.0
        if method == "Dinheiro":
            resp = QMessageBox.question(
                self, "Troco", "Vai precisar de troco?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
            if resp == QMessageBox.Yes:
                cur = settings_service.get("currency", "R$")
                total = float(order_service.get(oid)["total"])
                received, ok2 = QInputDialog.getDouble(
                    self, "Troco",
                    f"Total da conta: {fmt_money(total, cur)}\n\nValor recebido:",
                    total, total, 100000000, 2,
                )
                if not ok2:
                    return False
                change_needed = True
                change_amount = round(received - total, 2)
        order_service.set_payment_details(
            oid, payment_method=method,
            change_needed=1 if change_needed else 0,
            change_amount=change_amount,
        )
        self.payment_method = method
        self.payment_selected = True
        self.payment_change_needed = change_needed
        self.payment_change_amount = change_amount
        self.payment_confirmed = True
        self._sync_payment_button()
        return True

    def _customer_form(self, customer=None):
        from PySide6.QtWidgets import QDialog, QFormLayout

        data = _as_dict(customer) if customer else {}
        dlg = QDialog(self)
        dlg.setWindowTitle("Novo Cliente" if not customer else f"Editar Cliente #{data['id']}")
        dlg.setMinimumWidth(520)
        form = QFormLayout(dlg)
        form.setSpacing(9)

        codigo = QLabel("automático" if not customer else str(data["id"]))
        codigo.setStyleSheet("font-weight: 800; color: #ea580c;")
        name = QLineEdit(data.get("name") or self.customer.text().strip())
        doc = QLineEdit(data.get("document") or "")
        doc.setPlaceholderText("CNPJ / CPF")
        phone = QLineEdit(data.get("phone") or self.phone.text().strip())
        email = QLineEdit(data.get("email") or "")
        cep = QLineEdit(data.get("cep") or "")
        cep.setPlaceholderText("00000-000")
        address = QLineEdit(data.get("address") or self.address.text().strip())
        address_number = QLineEdit("")
        address_number.setPlaceholderText("Nº")
        address_complement = QLineEdit("")
        address_complement.setPlaceholderText("Complemento")
        neighborhood = QComboBox()
        neighborhood.setEditable(True)
        neighborhood.setInsertPolicy(QComboBox.NoInsert)
        neighborhood.addItem("— Bairro —")
        for n in neighborhood_service.list_all():
            neighborhood.addItem(n["name"])
            neighborhood.setItemData(neighborhood.count() - 1, n)
        bairro_taxa = QLabel("")
        bairro_taxa.setProperty("muted", True)
        city = QLineEdit(data.get("city") or "")
        state = QLineEdit(data.get("state") or "")
        state.setMaxLength(2)
        notes = QLineEdit(data.get("notes") or "")

        def bairro_sync(text):
            fee = None
            for i in range(neighborhood.count()):
                n = neighborhood.itemData(i)
                if n and n["name"] == text.strip():
                    fee = n["delivery_fee"]
                    break
            bairro_taxa.setText(
                f"Taxa: {fmt_money(fee or 0, settings_service.get('currency', 'R$'))}" if fee is not None else ""
            )

        def lookup_doc():
            d = only_digits(doc.text())
            if len(d) == 14:
                found = brazil_api_service.fetch_cnpj(doc.text())
                if not found:
                    QMessageBox.warning(dlg, "Busca CNPJ", "Não foi possível consultar o CNPJ.")
                    return
                name.setText(found["name"])
                doc.setText(found["document"])
                address.setText(found["address"])
                neighborhood.setCurrentText(found["neighborhood"])
                city.setText(found["city"])
                state.setText(found["state"])
                cep.setText(found["cep"])
                if not phone.text():
                    phone.setText(found["phone"])
                if not email.text():
                    email.setText(found["email"])
            elif len(d) == 11:
                QMessageBox.information(dlg, "CPF", "CPF identificado (não buscado na Receita).")
            elif d:
                QMessageBox.warning(dlg, "Documento", "Digite um CNPJ (14 dígitos) ou CPF (11 dígitos).")

        def lookup_cep():
            z = only_digits(cep.text())
            if len(z) != 8:
                return
            found = brazil_api_service.fetch_cep(cep.text())
            if not found:
                QMessageBox.warning(dlg, "Busca CEP", "Não foi possível consultar o CEP.")
                return
            cep.setText(found["cep"])
            address.setText(found["address"])
            neighborhood.setCurrentText(found.get("neighborhood") or "— Bairro —")
            city.setText(found["city"])
            state.setText(found["state"])

        neighborhood.currentTextChanged.connect(bairro_sync)
        bairro_sync(neighborhood.currentText())
        doc_btn = QPushButton("Buscar na Receita")
        doc_btn.clicked.connect(lookup_doc)
        cep_btn = QPushButton("Buscar CEP")
        cep_btn.clicked.connect(lookup_cep)
        doc_row = QHBoxLayout()
        doc_row.addWidget(doc)
        doc_row.addWidget(doc_btn)
        cep_row = QHBoxLayout()
        cep_row.addWidget(cep)
        cep_row.addWidget(cep_btn)

        form.addRow("Código", codigo)
        form.addRow("Nome", name)
        form.addRow("Documento", doc_row)
        form.addRow("Telefone", phone)
        form.addRow("E-mail", email)
        form.addRow("CEP", cep_row)
        form.addRow("Endereço", address)
        form.addRow("Número", address_number)
        form.addRow("Complemento", address_complement)
        bairro_row = QHBoxLayout()
        bairro_row.addWidget(neighborhood, 1)
        bairro_row.addWidget(bairro_taxa)
        form.addRow("Bairro", bairro_row)
        form.addRow("Cidade", city)
        form.addRow("UF", state)
        form.addRow("Observações", notes)

        buttons = QHBoxLayout()
        cancel = QPushButton("Cancelar")
        cancel.clicked.connect(dlg.reject)
        save = QPushButton("Salvar")
        save.setProperty("primary", True)
        buttons.addWidget(cancel)
        buttons.addStretch()
        buttons.addWidget(save)
        form.addRow(buttons)

        def on_save():
            if not name.text().strip():
                QMessageBox.warning(dlg, "Validação", "Informe o nome do cliente.")
                return
            dlg.accept()

        save.clicked.connect(on_save)
        name.setFocus()
        if customer and data.get("neighborhood"):
            neighborhood.setCurrentText(data.get("neighborhood") or "— Bairro —")
        elif self.neighborhood.currentText().strip() and self.neighborhood.currentText().strip() != "— Bairro —":
            neighborhood.setCurrentText(self.neighborhood.currentText().strip())

        if not dlg.exec():
            return None

        entity = "PJ" if len(only_digits(doc.text())) == 14 else "PF"
        full_address = ", ".join(
            p for p in [address.text().strip(), address_number.text().strip(), address_complement.text().strip()] if p
        )
        existing = data if customer else customer_service.find_by_phone(only_digits(phone.text()), active_only=False)
        if existing:
            customer_service.update(
                existing["id"], name.text().strip(), phone.text().strip(), full_address,
                notes.text().strip(), doc.text().strip(), cep.text().strip(), email.text().strip(),
                entity, city.text().strip(), state.text().strip(), neighborhood.currentText().strip(),
                is_active=True,
            )
            customer_id = existing["id"]
        else:
            customer_service.add(
                name.text().strip(), phone.text().strip(), full_address, notes.text().strip(),
                doc.text().strip(), cep.text().strip(), email.text().strip(), entity,
                city.text().strip(), state.text().strip(), neighborhood.currentText().strip(),
            )
            created = customer_service.find_by_phone(only_digits(phone.text()), active_only=False)
            customer_id = created["id"] if created else None

        self.customer.setText(name.text().strip())
        self.phone.setText(phone.text().strip())
        self.address.setText(full_address)
        if hasattr(self, "address_number"):
            self.address_number.setText(address_number.text().strip())
        if hasattr(self, "address_complement"):
            self.address_complement.setText(address_complement.text().strip())
        if neighborhood.currentText().strip() and neighborhood.currentText().strip() != "— Bairro —":
            idx = self.neighborhood.findText(neighborhood.currentText().strip())
            if idx >= 0:
                self.neighborhood.setCurrentIndex(idx)
        if self.order_id is not None:
            order_service.set_customer_info(
                self.order_id,
                customer_id=customer_id,
                name=name.text().strip(),
                phone=phone.text().strip(),
                address=address.text().strip(),
            )
        return customer_id

    def _register_customer(self):
        self._customer_form(None)

    def _edit_customer(self):
        phone = only_digits(self.phone.text())
        if not phone:
            QMessageBox.information(self, "Editar Cliente", "Informe o telefone do cliente primeiro.")
            return
        customer = customer_service.find_by_phone(phone, active_only=False)
        if not customer:
            QMessageBox.information(self, "Editar Cliente", "Cliente não encontrado para este telefone.")
            return
        self._customer_form(customer)

    def _send_to_pending(self):
        oid = self._ensure_order()
        if oid is None:
            return
        if not order_service.get_items(oid):
            QMessageBox.information(self, "Pedido Vazio", "Adicione itens primeiro.")
            return
        self._sync_order_header()
        order = order_service.get(oid)
        if self.order_type == "delivery":
            if not self.payment_selected:
                if not self._select_payment_method():
                    return
            order = order_service.get(oid)
        try:
            items = order_service.get_pending_kot_items(order["id"])
            if not items:
                QMessageBox.information(self, "KOT", "Não há novos itens para imprimir.")
                return
            print_kot(order, items=items)
            order_service.mark_kot_printed(order["id"], items)
        except Exception as e:
            QMessageBox.critical(self, "Erro de Impressão", str(e))
            return
        # Start a fresh order for the next sale so multiple pending orders can coexist.
        self.order_id = None
        self.payment_confirmed = False
        self.payment_selected = False
        self.payment_method = "Dinheiro"
        self.payment_change_needed = False
        self.payment_change_amount = 0.0
        self._sync_payment_button()
        self.cart.load_order(None)
        self.tabs.setCurrentIndex(1)
        self._refresh_tab()

    def _finalize_now(self):
        oid = self._ensure_order()
        if oid is None:
            return
        if not order_service.get_items(oid):
            QMessageBox.information(self, "Pedido Vazio", "Adicione itens primeiro.")
            return
        if not self.payment_selected:
            if not self._select_payment_method():
                return
        order = _as_dict(order_service.get(oid))
        payment_method = order.get("payment_method") or self.payment_method or "Dinheiro"
        try:
            print_final_bill(order)
        except Exception as e:
            QMessageBox.critical(self, "Erro de Impressão", str(e))
            return
        order_service.finalize(oid, payment_method)
        self.order_id = None
        self.payment_confirmed = False
        self.payment_selected = False
        self.payment_method = "Dinheiro"
        self.payment_change_needed = False
        self.payment_change_amount = 0.0
        self._sync_payment_button()
        self.cart.load_order(None)
        self.cart.load_categories()
        self.tabs.setCurrentIndex(2)
        self._refresh_tab()

    def _clear(self):
        if self.order_id is not None:
            if order_service.get_items(self.order_id):
                resp = QMessageBox.question(
                    self, "Descartar Pedido", "Este pedido tem itens. Descartar?")
                if resp != QMessageBox.Yes:
                    return
            order_service.manual_close(self.order_id)
            self.order_id = None
            self.payment_confirmed = False
            self.payment_selected = False
            self.payment_method = "Dinheiro"
            self.payment_change_needed = False
            self.payment_change_amount = 0.0
            self._sync_payment_button()
        self.cart.load_order(None)
        self.cart.load_categories()

    # ---------------- Pending ----------------
    def _build_pending(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 10, 0, 8)
        self.pending_scroll = QScrollArea()
        self.pending_scroll.setWidgetResizable(True)
        self.pending_scroll.setFrameShape(QFrame.NoFrame)
        self.pending_container = QWidget()
        self.pending_layout = QVBoxLayout(self.pending_container)
        self.pending_layout.setContentsMargins(0, 0, 6, 0)
        self.pending_layout.setSpacing(10)
        self.pending_layout.addStretch()
        self.pending_scroll.setWidget(self.pending_container)
        lay.addWidget(self.pending_scroll)
        return w

    def _refresh_pending(self):
        for i in reversed(range(self.pending_layout.count())):
            it = self.pending_layout.itemAt(i)
            w = it.widget()
            if w:
                w.deleteLater()
        orders = order_service.list_by_type_and_status(self.order_type, ["open"])
        orders = [_as_dict(o) for o in orders if order_service.get_items(o["id"])]
        currency = settings_service.get("currency", "R$")
        if not orders:
            empty = QLabel("Nenhum pedido pendente.")
            empty.setProperty("muted", True)
            empty.setAlignment(Qt.AlignCenter)
            empty.setStyleSheet("font-size: 16px; padding: 40px;")
            self.pending_layout.insertWidget(0, empty)
            return
        for o in orders:
            self.pending_layout.insertWidget(
                self.pending_layout.count() - 1, self._pending_card(o, currency)
            )

    def _pending_card(self, order, currency):
        card = QFrame()
        card.setProperty("card", True)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(6)

        head = QHBoxLayout()
        no = QLabel(f"Pedido #{order['order_number']}")
        no.setStyleSheet("font-size: 16px; font-weight: 800;")
        head.addWidget(no)
        head.addSpacing(12)
        time = QLabel(fmt_datetime(order["created_at"]))
        time.setProperty("muted", True)
        head.addWidget(time)
        head.addStretch()
        total = QLabel(fmt_money(order["total"], currency))
        total.setStyleSheet("font-size: 17px; font-weight: 800; color: #4f46e5;")
        head.addWidget(total)
        lay.addLayout(head)

        line = QLabel(self._order_summary(order))
        line.setWordWrap(True)
        lay.addWidget(line)

        meta = QLabel(self._meta_line(order))
        meta.setProperty("muted", True)
        meta.setWordWrap(True)
        lay.addWidget(meta)

        btns = QHBoxLayout()
        btns.setSpacing(8)
        b_complete = QPushButton("   Concluir")
        b_complete.setProperty("success", True)
        b_complete.setIcon(make_icon("tick", "#ffffff", 24))
        b_complete.setIconSize(QSize(18, 18))
        b_complete.setCursor(Qt.PointingHandCursor)
        b_complete.clicked.connect(lambda _=False, oid=order["id"]: self._complete(oid))
        btns.addWidget(b_complete)
        btns.addStretch()
        b_reprint = QPushButton("   Reimprimir KOT")
        b_reprint.setIcon(make_icon("print", "#4b5563", 24))
        b_reprint.setIconSize(QSize(18, 18))
        b_reprint.setCursor(Qt.PointingHandCursor)
        b_reprint.clicked.connect(lambda _=False, oid=order["id"]: self._reprint_pending(oid))
        btns.addWidget(b_reprint)
        b_edit = QPushButton("   Editar")
        b_edit.setIcon(make_icon("pencil", "#4b5563", 24))
        b_edit.setIconSize(QSize(18, 18))
        b_edit.setCursor(Qt.PointingHandCursor)
        b_edit.clicked.connect(lambda _=False, oid=order["id"]: self._edit_pending(oid))
        b_cancel = QPushButton("   Cancelar")
        b_cancel.setProperty("danger", True)
        b_cancel.setIcon(make_icon("close", "#ffffff", 24))
        b_cancel.setIconSize(QSize(18, 18))
        b_cancel.setCursor(Qt.PointingHandCursor)
        b_cancel.clicked.connect(lambda _=False, oid=order["id"]: self._cancel_pending(oid))
        btns.addWidget(b_edit)
        btns.addWidget(b_cancel)
        lay.addLayout(btns)
        return card

    def _reprint_pending(self, order_id):
        order = _as_dict(order_service.get(order_id))
        if not order:
            return
        dlg = QDialog(self)
        dlg.setWindowTitle(f"Pré-visualização KOT #{order['order_number']}")
        dlg.resize(420, 760)
        dlg.setMinimumWidth(380)
        root = QVBoxLayout(dlg)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(10)

        title = QLabel("Prévia do cupom 80mm")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 18px; font-weight: 800; color: #111827;")
        root.addWidget(title)

        paper = QFrame()
        paper.setFixedWidth(340)
        paper.setStyleSheet(
            "QFrame { background: #ffffff; border: 1px solid #e5e7eb; border-radius: 8px; }"
        )
        paper_layout = QVBoxLayout(paper)
        paper_layout.setContentsMargins(12, 12, 12, 12)
        paper_layout.setSpacing(0)

        preview = QTextEdit()
        preview.setReadOnly(True)
        preview.setFrameShape(QFrame.NoFrame)
        preview.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        preview.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        preview.setLineWrapMode(QTextEdit.WidgetWidth)
        preview.setStyleSheet(
            "QTextEdit {"
            "font-family: Consolas, monospace;"
            "font-size: 10px;"
            "background: transparent;"
            "border: none;"
            "padding: 0px;"
            "margin: 0px;"
            "}"
        )
        preview.setText(self._kot_preview_text(order, title="KOT"))
        paper_layout.addWidget(preview)

        paper_wrap = QHBoxLayout()
        paper_wrap.addStretch()
        paper_wrap.addWidget(paper)
        paper_wrap.addStretch()
        root.addLayout(paper_wrap, 1)

        btns = QHBoxLayout()
        btns.addStretch()
        close = QPushButton("Fechar")
        close.clicked.connect(dlg.reject)
        print_btn = QPushButton("Imprimir")
        print_btn.setProperty("primary", True)
        print_btn.clicked.connect(lambda: self._print_kot_from_preview(order, dlg))
        btns.addWidget(close)
        btns.addWidget(print_btn)
        root.addLayout(btns)
        dlg.exec()

    def _print_kot_from_preview(self, order, dlg):
        try:
            print_kot(order)
            dlg.accept()
        except Exception as e:
            QMessageBox.critical(self, "Erro de Impressão", str(e))

    def _kot_preview_text(self, order, title="KOT"):
        order = _as_dict(order)
        items = [_as_dict(it) for it in order_service.get_items(order["id"])]
        width = 42
        created = str(order.get("created_at") or "")
        if " " in created:
            date_part, time_part = created.split(" ", 1)
        else:
            date_part, time_part = created, ""

        def kot_type_label(o):
            return {
                "dine-in": "MESA",
                "takeaway": "RETIRADA",
                "delivery": "DELIVERY",
            }.get(o.get("order_type", "dine-in"), str(o.get("order_type", "MESA")).upper())

        def item_lines(order_items):
            qty_w = 3
            gap = 2
            name_w = max(16, width - qty_w - gap)
            indent = " " * (qty_w + gap)
            out = []
            for it in order_items:
                name = str(it.get("name", "")).strip().upper()
                action = str(it.get("kot_action") or "ADICIONAR").upper()
                try:
                    qty_s = f"{float(it.get('qty', 1)):g}"
                except (TypeError, ValueError):
                    qty_s = str(it.get("qty", 1))
                if action == "CANCELAR":
                    out.append("*** CANCELAR ITEM ***")
                elif action == "ALTERAR OBS":
                    out.append("*** ALTERAR OBSERVAÇÃO ***")
                chunks = []
                cur = ""
                for word in name.split():
                    nxt = f"{cur} {word}".strip() if cur else word
                    if len(nxt) <= name_w:
                        cur = nxt
                    else:
                        if cur:
                            chunks.append(cur)
                        while len(word) > name_w:
                            chunks.append(word[:name_w])
                            word = word[name_w:]
                        cur = word
                if cur or not chunks:
                    chunks.append(cur)
                for i, chunk in enumerate(chunks):
                    if i == 0:
                        out.append(f"{qty_s.rjust(qty_w)}{' ' * gap}{chunk}")
                    else:
                        out.append(f"{indent}{chunk}")
                instr = str(it.get("instructions") or "").strip()
                if instr:
                    out.append(f"{indent}>>> {instr.upper()} <<<")
                if action in ("CANCELAR", "ALTERAR OBS"):
                    out.append("-" * width)
            return out

        lines = [
            settings_service.get("store_name", "Open POS").center(width),
            title.center(width),
            "",
            f"PEDIDO {order.get('order_number', '-') }".center(width),
        ]
        if order.get("table_no"):
            lines.append(f"MESA {str(order['table_no']).zfill(2)}".center(width))
        lines.append(f"TIPO: {kot_type_label(order)}".center(width))
        if date_part or time_part:
            lines.append(f"{date_part} - {time_part}".center(width))
        if order.get("waiter_name"):
            label = "ATENDENTE" if order.get("order_type") == "delivery" else "GARÇOM"
            lines.append(f"{label}: {str(order['waiter_name']).upper()}".center(width))
        lines.append("=" * width)
        lines.append("QTD  PRODUTO")
        lines.append("=" * width)
        lines.extend(item_lines(items))
        lines.append("=" * width)
        order_instr = str(order.get("instructions") or "").strip()
        lines.append("OBS:")
        lines.append(order_instr.upper() if order_instr else "SEM OBSERVAÇÕES")
        lines.append("=" * width)
        lines.append("IGS Automacao Comercial".center(width))
        lines.append("")
        lines.append("")
        return "\n".join(lines)

    def _order_summary(self, order):
        items = order_service.get_items(order["id"])
        return "  ·  ".join(f"{it['name']} x{it['qty']:g}" for it in items) or "—"

    def _meta_line(self, order):
        parts = []
        if order.get("waiter_name"):
            label = "Atendente" if order.get("order_type") == "delivery" else "Garçom"
            parts.append(f"{label}: {order['waiter_name']}")
        if order.get("rider_name"):
            parts.append(f"Motoqueiro: {order['rider_name']}")
        if order.get("payment_method"):
            parts.append(f"Pagamento: {order['payment_method']}")
        if order.get("change_needed"):
            parts.append(f"Troco: {fmt_money(order.get('change_amount') or 0, settings_service.get('currency', 'R$'))}")
        if order.get("customer_name"):
            parts.append(f"Cliente: {order['customer_name']}")
        if order.get("customer_phone"):
            parts.append(f"Telefone: {order['customer_phone']}")
        if order.get("customer_address"):
            parts.append(f"Endereço: {order['customer_address']}")
        return "   |   ".join(parts)

    def _complete(self, order_id):
        if self.order_type == "delivery" and not self._ensure_rider_for_delivery(order_id):
            return
        order = _as_dict(order_service.get(order_id))
        payment_method = order.get("payment_method") or (self.payment_method if self.order_type == "delivery" else "Dinheiro")
        if not payment_method:
            payment_method = "Dinheiro"
        change_amount = None
        if self.order_type == "delivery":
            order_for_print = dict(order)
            order_for_print["payment_method"] = payment_method
            if order.get("change_needed"):
                change_amount = float(order.get("change_amount") or 0)
            if change_amount is not None:
                order_for_print["change_amount"] = change_amount
        else:
            order_for_print = order
        try:
            if self.order_type == "delivery":
                print_rider_bill(order_for_print)
                print_final_bill(order_for_print)
            else:
                print_request_bill(order)
        except Exception as e:
            QMessageBox.critical(self, "Erro de Impressão", str(e))
            return
        order_service.finalize(order_id, payment_method)
        if self.order_id == order_id:
            self.order_id = None
            self.cart.load_order(None)
        self._refresh_tab()

    def _edit_pending(self, order_id):
        order = _as_dict(order_service.get(order_id))
        self.order_id = order_id
        self._load_head(order)
        self.cart.load_order(order_id)
        self.tabs.setCurrentIndex(0)

    def _cancel_pending(self, order_id):
        order = _as_dict(order_service.get(order_id))
        resp = QMessageBox.question(
            self, "Cancelar Pedido",
            f"Cancelar o pedido #{order['order_number']}? Esta ação não pode ser desfeita.")
        if resp != QMessageBox.Yes:
            return
        order_service.manual_close(order_id)
        if self.order_id == order_id:
            self.order_id = None
            self.cart.load_order(None)
        self._refresh_pending()

    def _load_head(self, order):
        idx = self.waiter.findData(order["waiter_id"])
        self.waiter.setCurrentIndex(max(0, idx))
        if self.order_type == "delivery":
            self.customer.setText(order["customer_name"] or "")
            self.phone.setText(order["customer_phone"] or "")
            self.address.setText(order["customer_address"] or "")
            self.payment_method = order.get("payment_method") or "Dinheiro"
            self.payment_selected = True
            self.payment_confirmed = True
            self.payment_change_needed = bool(order.get("change_needed"))
            self.payment_change_amount = float(order.get("change_amount") or 0)
            self._sync_payment_button()

    # ---------------- Completed ----------------
    def _build_completed(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 10, 0, 8)
        self.completed_list = QListWidget()
        self.completed_list.setFrameShape(QFrame.NoFrame)
        self.completed_list.itemClicked.connect(self._open_completed)
        lay.addWidget(self.completed_list)
        bind_table_keys(self.completed_list, on_enter=self._open_selected_completed)
        return w

    def _refresh_completed(self):
        self.completed_list.clear()
        orders = [_as_dict(o) for o in order_service.list_by_type_and_status(self.order_type, ["paid"])]
        currency = settings_service.get("currency", "R$")
        for o in orders:
            name = o.get("customer_name") or o.get("waiter_name") or ""
            txt = f"#{o['order_number']}   {fmt_datetime(o['created_at'])}   {name}   {fmt_money(o['total'], currency)}"
            item = QListWidgetItem(txt)
            item.setData(Qt.UserRole, o["id"])
            item.setIcon(icon_pixmap("note", "#6b7280", 16))
            self.completed_list.addItem(item)

    def _open_completed(self, item):
        oid = item.data(Qt.UserRole)
        order = _as_dict(order_service.get(oid))
        if order:
            dlg = OrderDetailDialog(order, self)
            dlg.exec()

    def _open_selected_completed(self):
        item = self.completed_list.currentItem()
        if item:
            self._open_completed(item)

    # ---------------- misc ----------------
    def _refresh_tab(self):
        idx = self.tabs.currentIndex()
        if idx == 0:
            pass
        elif idx == 1:
            self._refresh_pending()
        elif idx == 2:
            self._refresh_completed()

    def _lookup_customer(self):
        phone = self.phone.text().strip()
        if not phone:
            return
        normalized_phone = only_digits(phone)
        customer = customer_service.find_by_phone(normalized_phone)
        if not customer:
            if QMessageBox.question(
                self, "Cliente não encontrado",
                f"Este número ({phone}) não está cadastrado.\n\nDeseja cadastrá-lo agora?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes,
            ) == QMessageBox.Yes:
                self._register_customer()
            return
        if customer["name"] and not self.customer.text().strip():
            self.customer.setText(customer["name"])
        if customer["address"] and not self.address.text().strip():
            self.address.setText(customer["address"])
        if customer["neighborhood"]:
            idx = self.neighborhood.findText(customer["neighborhood"])
            if idx >= 0:
                self.neighborhood.setCurrentIndex(idx)
    def refresh(self):
        self._refresh_tab()

    def _ensure_rider_for_delivery(self, order_id):
        order = _as_dict(order_service.get(order_id))
        if order.get("rider_id"):
            return True
        riders = staff_service.list_riders()
        if not riders:
            QMessageBox.information(self, "Motoqueiro", "Nenhum motoqueiro ativo cadastrado.")
            return False
        names = [r["name"] for r in riders]
        name, ok = QInputDialog.getItem(
            self, "Motoqueiro", "Selecione o motoqueiro para concluir a entrega:", names, 0, False)
        if not ok or not name:
            return False
        rider = next(r for r in riders if r["name"] == name)
        order_service.set_rider(order_id, rider["id"])
        return True


class PosView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 22, 28, 22)
        outer.setSpacing(12)
        title = QLabel("Venda Rápida")
        title.setObjectName("PageTitle")
        outer.addWidget(title)
        sub = QLabel("Pedidos para viagem e entrega")
        sub.setObjectName("PageSubtitle")
        outer.addWidget(sub)

        self.tabs = QTabWidget()
        self.page_takeaway = QuickSalePage("takeaway")
        self.page_delivery = QuickSalePage("delivery")
        self.tabs.addTab(self.page_takeaway, "Para Viagem")
        self.tabs.addTab(self.page_delivery, "Entrega")
        outer.addWidget(self.tabs, 1)

    def refresh(self):
        self.page_takeaway._refresh_tab()
        self.page_delivery._refresh_tab()
