from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QComboBox, QDialog, QFrame, QHBoxLayout, QInputDialog, QLabel, QMessageBox,
    QPushButton, QVBoxLayout, QWidget,
)

from app.printing.printer_service import (
    print_final_bill, print_kot, print_request_bill,
)
from app.services.aux_service import payment_service
from app.services.auth_service import auth_service
from app.services.order_service import order_service
from app.services.settings_service import settings_service
from app.services.staff_service import staff_service
from app.services.table_service import table_service
from app.utils.helpers import fmt_money
from app.ui.cart_panel import CartPanel
from app.ui.icons import make_icon

STATUS_LABEL = {"free": "LIVRE", "occupied": "OCUPADA", "request_bill": "PEDINDO CONTA"}


class TablePopup(QDialog):
    def __init__(self, table, parent=None):
        super().__init__(parent)
        self.table = dict(table) if hasattr(table, "keys") else table
        self.order = None
        self.setWindowTitle(f"Mesa {table['table_no']}")
        self.resize(1080, 640)
        self.setModal(True)
        self._build()
        self._init_order()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(12)

        head = QHBoxLayout()
        title = QLabel(f"Mesa {self.table['table_no']}  ·  {self.table['seats']} lugares")
        title.setStyleSheet("font-size: 20px; font-weight: 800; color: #111827;")
        head.addWidget(title)
        status = QLabel()
        status.setStyleSheet("font-weight: 800; font-size: 12px; padding: 5px 14px; border-radius: 12px;")
        st = self.table["status"]
        status.setText(STATUS_LABEL.get(st, st.upper()))
        bg = {"free": "#10b981", "occupied": "#ef4444", "request_bill": "#f59e0b"}.get(st, "#6b7280")
        status.setStyleSheet(f"background: {bg}22; color: {bg}; font-weight: 800; padding: 4px 12px; border-radius: 12px;")
        head.addWidget(status)
        head.addStretch()
        head.addWidget(QLabel("Garçom:"))

        self.waiter = QComboBox()
        self.waiter.setMinimumWidth(180)
        self.waiters = staff_service.list_waiters()
        self.waiter.addItem("— Selecionar Garçom —", None)
        for w in self.waiters:
            self.waiter.addItem(w["name"], w["id"])
        self.waiter.currentIndexChanged.connect(self._waiter_changed)
        head.addWidget(self.waiter)
        root.addLayout(head)

        self.cart = CartPanel()
        self.cart.grid.product_clicked.connect(self._add_product)
        self.cart.load_categories()
        root.addWidget(self.cart, 1)

        actions = QHBoxLayout()
        actions.setSpacing(10)

        self.btn_kot = QPushButton("   Imprimir KOT")
        self.btn_kot.setProperty("warning", True)
        self.btn_kot.setIcon(make_icon("print", "#ffffff", 24))
        self.btn_kot.setIconSize(QSize(18, 18))
        self.btn_kot.clicked.connect(self._do_kot)

        self.btn_request = QPushButton("   Pedir Conta")
        self.btn_request.setProperty("primary", True)
        self.btn_request.setIcon(make_icon("note", "#ffffff", 24))
        self.btn_request.setIconSize(QSize(18, 18))
        self.btn_request.clicked.connect(self._do_request_bill)

        self.pay_label = QLabel("Pagamento:")
        self.btn_save = QPushButton("   Salvar")
        self.btn_save.setIcon(make_icon("check", "#4b5563", 24))
        self.btn_save.setIconSize(QSize(18, 18))
        self.btn_save.setToolTip("Salva o pedido e mantém a mesa aberta para o cliente continuar consumindo.")
        self.btn_save.clicked.connect(self._do_save)
        self.btn_save.setEnabled(False)
        self.payment = QComboBox()
        names = payment_service.list_active_names()
        if not names:
            names = ["Dinheiro", "Cartão", "Pix"]
        self.payment.addItems(names)
        idx = self.payment.findText("Dinheiro")
        if idx >= 0:
            self.payment.setCurrentIndex(idx)

        self.btn_final = QPushButton("   Conta Final & Fechar")
        self.btn_final.setProperty("success", True)
        self.btn_final.setIcon(make_icon("check", "#ffffff", 24))
        self.btn_final.setIconSize(QSize(18, 18))
        self.btn_final.clicked.connect(self._do_final_bill)

        self.btn_close = QPushButton("Fechar Mesa (Sem Pagamento)")
        self.btn_close.setToolTip("Fecha sem registrar pagamento (conta final não é impressa).")
        self.btn_close.setEnabled(False)
        self.btn_close.clicked.connect(self._do_manual_close)

        self.btn_transfer = QPushButton("Transferir Mesa")
        self.btn_transfer.setToolTip("Move o pedido para outra mesa livre.")
        self.btn_transfer.setEnabled(False)
        self.btn_transfer.clicked.connect(self._transfer_table)
        self.btn_merge = QPushButton("Juntar Contas")
        self.btn_merge.setToolTip("Move os itens de outra mesa para esta (mesa de origem é liberada).")
        self.btn_merge.setEnabled(False)
        self.btn_merge.clicked.connect(self._merge_table)
        actions.addWidget(self.btn_kot)
        actions.addWidget(self.btn_request)
        actions.addWidget(self.btn_transfer)
        actions.addWidget(self.btn_merge)
        actions.addWidget(self.btn_save)
        actions.addStretch()
        actions.addWidget(self.pay_label)
        actions.addWidget(self.payment)
        actions.addWidget(self.btn_final)
        actions.addWidget(self.btn_close)
        root.addLayout(actions)

    def _init_order(self):
        if self.table["status"] != "free":
            order = order_service.get_open_order_for_table(self.table["id"])
            if order:
                self.order = order
                idx = self.waiter.findData(order["waiter_id"])
                if idx >= 0:
                    self.waiter.setCurrentIndex(idx)
                self.cart.load_order(order["id"])
                self.btn_final.setEnabled(True)
                self.btn_request.setEnabled(True)
                self.btn_kot.setEnabled(True)
                self.btn_save.setEnabled(True)
                self.btn_close.setEnabled(True)
                self.btn_transfer.setEnabled(True)
                self.btn_merge.setEnabled(True)
                return
        # free table -> create order when first product added
        self.order = None
        self.btn_final.setEnabled(False)
        self.btn_request.setEnabled(False)
        self.btn_kot.setEnabled(False)
        self.btn_save.setEnabled(False)
        self.btn_close.setEnabled(False)
        self.btn_transfer.setEnabled(False)
        self.btn_merge.setEnabled(False)

    def _ensure_order(self):
        if self.order is None:
            self.order = order_service.create_order(
                table_id=self.table["id"],
                waiter_id=self.waiter.currentData(),
                cashier_id=auth_service.current_user["id"],
                order_type="dine-in",
                instructions=self.cart.note.text().strip(),
            )
            table_service.set_status(self.table["id"], "occupied", self.order["id"])
            self.table["status"] = "occupied"
            self.cart.load_order(self.order["id"])
            self.btn_final.setEnabled(True)
            self.btn_request.setEnabled(True)
            self.btn_kot.setEnabled(True)
            self.btn_save.setEnabled(True)
            self.btn_close.setEnabled(True)
            self.btn_transfer.setEnabled(True)
            self.btn_merge.setEnabled(True)
        return self.order

    def _add_product(self, product_id):
        order = self._ensure_order()
        order_service.add_item(order["id"], product_id=product_id, qty=1)
        self.cart.refresh()

    def _waiter_changed(self, idx):
        if self.order is not None:
            order_service.set_waiter(self.order["id"], self.waiter.currentData())

    def _do_kot(self):
        order = self._ensure_order()
        if not order_service.get_items(order["id"]):
            QMessageBox.information(self, "Pedido Vazio", "Adicione itens antes de imprimir o KOT.")
            return
        try:
            print_kot(order)
        except Exception as e:
            QMessageBox.critical(self, "Erro de Impressão", str(e))

    def _do_request_bill(self):
        order = self._ensure_order()
        if not order_service.get_items(order["id"]):
            QMessageBox.information(self, "Pedido Vazio", "Adicione itens antes de pedir a conta.")
            return
        order_service.request_bill(order["id"])
        self.table["status"] = "request_bill"
        try:
            print_request_bill(order_service.get(order["id"]))
        except Exception as e:
            QMessageBox.critical(self, "Erro de Impressão", str(e))
        self.accept()

    def _do_save(self):
        if self.order is None:
            self.accept()
            return
        order_service.set_order_instructions(self.order["id"], self.cart.note.text().strip())
        self.accept()

    def _transfer_table(self):
        if self.order is None:
            return
        free = [t for t in table_service.list_all() if t["status"] == "free"]
        free = [t for t in free if t["id"] != self.table["id"]]
        if not free:
            QMessageBox.information(self, "Transferir Mesa", "Não há mesas livres para transferir.")
            return
        names = [t["table_no"] for t in free]
        name, ok = QInputDialog.getItem(self, "Transferir Mesa",
                                        "Para qual mesa livre?", names, 0, False)
        if not ok or not name:
            return
        dest = next(t for t in free if t["table_no"] == name)
        try:
            order_service.transfer_order(self.order["id"], dest["id"])
        except ValueError as e:
            QMessageBox.warning(self, "Transferir Mesa", str(e))
            return
        self.table["id"] = dest["id"]
        self.table["table_no"] = dest["table_no"]
        self.setWindowTitle(f"Mesa {dest['table_no']}")
        QMessageBox.information(self, "Transferir Mesa",
                                f"Pedido movido para a mesa {dest['table_no']}.")

    def _merge_table(self):
        if self.order is None:
            return
        others = [t for t in table_service.list_all() if t["status"] != "free"]
        others = [t for t in others if t["id"] != self.table["id"]]
        if not others:
            QMessageBox.information(self, "Juntar Contas", "Nenhuma outra mesa com pedido aberto.")
            return
        names = [t["table_no"] for t in others]
        name, ok = QInputDialog.getItem(self, "Juntar Contas",
                                        "Unir a conta de qual mesa nesta?", names, 0, False)
        if not ok or not name:
            return
        src = next(t for t in others if t["table_no"] == name)
        src_order = order_service.get_open_order_for_table(src["id"])
        if not src_order:
            QMessageBox.information(self, "Juntar Contas", "A mesa selecionada não tem pedido aberto.")
            return
        resp = QMessageBox.question(
            self, "Juntar Contas",
            f"Mover os itens da mesa {name} para esta mesa "
            f"({self.table['table_no']})? A mesa {name} será liberada.",
        )
        if resp != QMessageBox.Yes:
            return
        try:
            order_service.merge_orders(src_order["id"], self.order["id"])
        except ValueError as e:
            QMessageBox.warning(self, "Juntar Contas", str(e))
            return
        self.cart.refresh()
        QMessageBox.information(self, "Juntar Contas", "Contas unidas com sucesso.")

    def _do_final_bill(self):
        order = self._ensure_order()
        if not order_service.get_items(order["id"]):
            QMessageBox.information(self, "Pedido Vazio", "Adicione itens antes da conta final.")
            return
        method = self.payment.currentText()
        if method == "Dinheiro":
            cur = settings_service.get("currency", "R$")
            total = float(self.order["total"])
            received, ok1 = QInputDialog.getDouble(
                self, "Pagamento em Dinheiro",
                f"Total da conta: {fmt_money(total, cur)}\n\nValor recebido do cliente:",
                total, total, 100000000, 2,
            )
            if not ok1:
                return
            troco = round(received - total, 2)
            QMessageBox.information(
                self, "Troco",
                f"Valor recebido: {fmt_money(received, cur)}\n"
                f"Total da conta: {fmt_money(total, cur)}\n"
                f"Troco a devolver: {fmt_money(troco, cur)}",
            )
        resp = QMessageBox.question(
            self, "Confirmar Pagamento",
            f"Fechar esta conta e imprimir a conta final?\n\nTotal: {self.cart.t_total.text()}\nPagamento: {method}",
        )
        if resp != QMessageBox.Yes:
            return
        order_service.finalize(order["id"], method)
        self.table["status"] = "free"
        try:
            print_final_bill(order_service.get(order["id"]))
        except Exception as e:
            QMessageBox.critical(self, "Erro de Impressão", str(e))
        self.accept()

    def _do_manual_close(self):
        if self.order is not None and order_service.get_items(self.order["id"]):
            resp = QMessageBox.question(
                self, "Fechar Mesa",
                "A mesa tem itens, mas nenhum pagamento será registrado. Fechar mesmo assim?",
            )
            if resp != QMessageBox.Yes:
                return
            order_service.manual_close(self.order["id"])
        else:
            self.order = None
            table_service.set_status(self.table["id"], "free", None)
        self.accept()
