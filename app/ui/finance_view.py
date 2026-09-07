import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QDateEdit, QDialog, QDoubleSpinBox, QFormLayout, QFrame, QHBoxLayout,
    QInputDialog, QLabel, QLineEdit, QMessageBox, QPushButton, QTabWidget,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from app.services.chart_account_service import chart_account_service
from app.services.finance_service import finance_service
from app.services.settings_service import settings_service
from app.ui.keys import bind_table_keys
from app.utils.helpers import fmt_money


class AccountDialog(QDialog):
    def __init__(self, parent=None, title="Conta"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setFixedWidth(420)
        form = QFormLayout(self)
        form.setSpacing(12)

        self.desc = QLineEdit()
        self.desc.setPlaceholderText("Descrição da conta...")
        self.account = QComboBox()
        self.account.addItem("— Sem Conta no Plano —", None)
        for a in chart_account_service.list_active():
            label = (a["code"] + " " + a["name"]).strip()
            self.account.addItem(label, a["id"])
        self.amount = QDoubleSpinBox()
        self.amount.setRange(0, 100_000_000)
        self.amount.setDecimals(2)
        self.amount.setPrefix(settings_service.get("currency", "R$") + " ")
        self.date = QDateEdit()
        self.date.setCalendarPopup(True)
        self.date.setDate(datetime.date.today())
        self.notes = QLineEdit()
        self.notes.setPlaceholderText("Observações (opcional)")

        form.addRow("Descrição", self.desc)
        form.addRow("Plano de Contas", self.account)
        form.addRow("Valor", self.amount)
        form.addRow("Vencimento", self.date)
        form.addRow("Observações", self.notes)

        btns = QHBoxLayout()
        save = QPushButton("Salvar")
        save.setProperty("primary", True)
        save.clicked.connect(self.accept)
        cancel = QPushButton("Cancelar")
        cancel.clicked.connect(self.reject)
        btns.addWidget(cancel)
        btns.addWidget(save)
        form.addRow(btns)

    def values(self):
        return {
            "description": self.desc.text().strip(),
            "account_id": self.account.currentData(),
            "amount": self.amount.value(),
            "due_date": self.date.date().toString("yyyy-MM-dd"),
            "notes": self.notes.text().strip(),
        }


class FinanceView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build()
        self.reload()

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 22, 28, 22)
        outer.setSpacing(14)

        title = QLabel("Financeiro")
        title.setObjectName("PageTitle")
        sub = QLabel("Caixa, contas a pagar e a receber")
        sub.setObjectName("PageSubtitle")
        outer.addWidget(title)
        outer.addWidget(sub)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_cash_tab(), "Caixa")
        self.tabs.addTab(self._build_payable_tab(), "Contas a Pagar")
        self.tabs.addTab(self._build_receivable_tab(), "Contas a Receber")
        outer.addWidget(self.tabs, 1)

    # ---------------- Aba Caixa ----------------
    def _build_cash_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setSpacing(14)

        top = QFrame()
        top.setProperty("card", True)
        tl = QVBoxLayout(top)
        tl.setContentsMargins(20, 16, 20, 16)
        tl.setSpacing(12)
        self.cash_status = QLabel("Carregando...")
        self.cash_status.setStyleSheet("font-size: 16px; font-weight: 800;")
        tl.addWidget(self.cash_status)
        btns = QHBoxLayout()
        self.b_open = QPushButton("Abrir Caixa")
        self.b_open.setProperty("primary", True)
        self.b_open.clicked.connect(self._open_cash)
        self.b_sangria = QPushButton("Sangria")
        self.b_sangria.clicked.connect(lambda: self._move("saida"))
        self.b_reforce = QPushButton("Reforço")
        self.b_reforce.clicked.connect(lambda: self._move("entrada"))
        self.b_close = QPushButton("Fechar Caixa")
        self.b_close.setProperty("danger", True)
        self.b_close.clicked.connect(self._close_cash)
        for b in (self.b_open, self.b_sangria, self.b_reforce, self.b_close):
            btns.addWidget(b)
        btns.addStretch()
        tl.addLayout(btns)
        lay.addWidget(top)

        sum_card = QFrame()
        sum_card.setProperty("card", True)
        sl = QHBoxLayout(sum_card)
        sl.setContentsMargins(20, 16, 20, 16)
        self.s_open = self._stat(sl, "Abertura", "#1f2937")
        self.s_in = self._stat(sl, "Entradas", "#16a34a")
        self.s_out = self._stat(sl, "Saídas", "#dc2626")
        self.s_net = self._stat(sl, "Esperado no Caixa", "#ea580c")
        lay.addWidget(sum_card)

        self.moves = QTableWidget(0, 4)
        self.moves.setHorizontalHeaderLabels(["Data/Hora", "Tipo", "Motivo", "Valor"])
        self.moves.verticalHeader().setVisible(False)
        self.moves.setEditTriggers(QTableWidget.NoEditTriggers)
        self.moves.setSelectionBehavior(QTableWidget.SelectRows)
        self.moves.setSelectionMode(QTableWidget.SingleSelection)
        self.moves.horizontalHeader().setStretchLastSection(True)
        lay.addWidget(self.moves, 1)
        lay.addLayout(self._cash_pager_bar())
        return w

    def _cash_pager_bar(self):
        bar = QHBoxLayout()
        prev = QPushButton("◀  Anterior")
        info = QLabel("Página 1 de 1")
        nxt = QPushButton("Próxima  ▶")
        self.cash_prev, self.cash_info, self.cash_next = prev, info, nxt
        prev.clicked.connect(self._cash_pager_back)
        nxt.clicked.connect(self._cash_pager_forward)
        bar.addStretch()
        bar.addWidget(prev)
        bar.addWidget(info)
        bar.addWidget(nxt)
        return bar

    def _stat(self, lay, label, color):
        box = QVBoxLayout()
        lbl = QLabel(label)
        lbl.setProperty("muted", True)
        val = QLabel("R$ 0,00")
        val.setStyleSheet(f"font-size: 18px; font-weight: 800; color: {color};")
        box.addWidget(lbl)
        box.addWidget(val)
        lay.addLayout(box)
        return val

    # ---------------- Aba Contas a Pagar ----------------
    def _build_payable_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setSpacing(12)
        row = QHBoxLayout()
        add = QPushButton("+  Adicionar Conta a Pagar")
        add.setProperty("primary", True)
        add.clicked.connect(self._add_payable)
        pay = QPushButton("Marcar como Paga")
        pay.clicked.connect(self._pay_bill)
        rm = QPushButton("Excluir")
        rm.setProperty("danger", True)
        rm.clicked.connect(self._delete_payable)
        row.addWidget(add)
        row.addWidget(pay)
        row.addWidget(rm)
        row.addStretch()
        row.addWidget(QLabel("Filtro:"))
        self.pay_status = QComboBox()
        self.pay_status.addItem("Todas", "all")
        self.pay_status.addItem("A Pagar", "pending")
        self.pay_status.addItem("Pagas", "paid")
        self.pay_status.addItem("Atrasadas", "overdue")
        self.pay_status.addItem("Em Dia", "ontime")
        self.pay_status.currentIndexChanged.connect(lambda _: self._pay_pager_go(1))
        row.addWidget(self.pay_status)
        lay.addLayout(row)
        self.pay_table = QTableWidget(0, 6)
        self.pay_table.setHorizontalHeaderLabels(
            ["Vencimento", "Conta", "Descrição", "Valor", "Status", "Paga em"])
        lay.addWidget(self.pay_table, 1)
        self._style_table(self.pay_table)
        lay.addLayout(self._pager_bar("pay"))
        bind_table_keys(self.pay_table, on_enter=self._pay_bill, on_delete=self._delete_payable)
        return w

    # ---------------- Aba Contas a Receber ----------------
    def _build_receivable_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setSpacing(12)
        row = QHBoxLayout()
        add = QPushButton("+  Adicionar Conta a Receber")
        add.setProperty("primary", True)
        add.clicked.connect(self._add_receivable)
        recv = QPushButton("Marcar como Recebida")
        recv.clicked.connect(self._receive_bill)
        rm = QPushButton("Excluir")
        rm.setProperty("danger", True)
        rm.clicked.connect(self._delete_receivable)
        row.addWidget(add)
        row.addWidget(recv)
        row.addWidget(rm)
        row.addStretch()
        row.addWidget(QLabel("Filtro:"))
        self.recv_status = QComboBox()
        self.recv_status.addItem("Todas", "all")
        self.recv_status.addItem("A Receber", "pending")
        self.recv_status.addItem("Recebidas", "paid")
        self.recv_status.addItem("Atrasadas", "overdue")
        self.recv_status.addItem("Em Dia", "ontime")
        self.recv_status.currentIndexChanged.connect(lambda _: self._recv_pager_go(1))
        row.addWidget(self.recv_status)
        lay.addLayout(row)
        self.recv_table = QTableWidget(0, 6)
        self.recv_table.setHorizontalHeaderLabels(
            ["Vencimento", "Conta", "Descrição", "Valor", "Status", "Recebida em"])
        lay.addWidget(self.recv_table, 1)
        self._style_table(self.recv_table)
        lay.addLayout(self._pager_bar("recv"))
        bind_table_keys(self.recv_table, on_enter=self._receive_bill, on_delete=self._delete_receivable)
        return w

    def _pager_bar(self, kind):
        bar = QHBoxLayout()
        prev = QPushButton("◀  Anterior")
        info = QLabel("Página 1 de 1")
        nxt = QPushButton("Próxima  ▶")
        if kind == "pay":
            self.pay_prev, self.pay_info, self.pay_next = prev, info, nxt
            prev.clicked.connect(self._pay_pager_back)
            nxt.clicked.connect(self._pay_pager_forward)
        else:
            self.recv_prev, self.recv_info, self.recv_next = prev, info, nxt
            prev.clicked.connect(self._recv_pager_back)
            nxt.clicked.connect(self._recv_pager_forward)
        bar.addStretch()
        bar.addWidget(prev)
        bar.addWidget(info)
        bar.addWidget(nxt)
        return bar

    def _style_table(self, table):
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setSelectionMode(QTableWidget.SingleSelection)
        table.horizontalHeader().setStretchLastSection(True)

    # ---------------- Ações do Caixa ----------------
    def _open_cash(self):
        if finance_service.current_session():
            QMessageBox.information(self, "Caixa", "O caixa já está aberto.")
            return
        cur = settings_service.get("currency", "R$")
        value, ok = QInputDialog.getDouble(
            self, "Abrir Caixa", "Valor inicial em espécie (R$):", 0, 0, 100_000_000, 2)
        if not ok:
            return
        try:
            finance_service.open_session(value)
        except ValueError as e:
            QMessageBox.warning(self, "Caixa", str(e))
        self.reload()

    def _move(self, kind):
        session = finance_service.current_session()
        if not session:
            QMessageBox.information(self, "Caixa", "Abra o caixa primeiro.")
            return
        label = "Sangria (saída)" if kind == "saida" else "Reforço (entrada)"
        cur = settings_service.get("currency", "R$")
        value, ok = QInputDialog.getDouble(self, label, "Valor:", 0, 0, 100_000_000, 2)
        if not ok:
            return
        reason, ok2 = QInputDialog.getText(self, label, "Motivo:")
        if not ok2:
            return
        finance_service.add_move(session["id"], kind, value, reason.strip() or label)
        self.reload()

    def _close_cash(self):
        session = finance_service.current_session()
        if not session:
            QMessageBox.information(self, "Caixa", "Não há caixa aberto.")
            return
        cur = settings_service.get("currency", "R$")
        s = finance_service.summary(session["id"])
        expected = session["opening_amount"] + s["liquido"]
        value, ok = QInputDialog.getDouble(
            self, "Fechar Caixa",
            f"Valor contado em caixa ({cur}):", expected, 0, 100_000_000, 2)
        if not ok:
            return
        note, ok2 = QInputDialog.getText(self, "Fechar Caixa", "Observação:")
        if not ok2:
            return
        finance_service.close_session(session["id"], value, note.strip())
        QMessageBox.information(
            self, "Fechar Caixa",
            f"Esperado: {fmt_money(expected, cur)}\nContado: {fmt_money(value, cur)}")
        self.reload()

    def _reload_cash(self):
        session = finance_service.current_session()
        cur = settings_service.get("currency", "R$")
        enabled = session is not None
        self.b_open.setEnabled(not enabled)
        self.b_sangria.setEnabled(enabled)
        self.b_reforce.setEnabled(enabled)
        self.b_close.setEnabled(enabled)
        if session:
            self.cash_status.setStyleSheet("font-size: 16px; font-weight: 800; color: #16a34a;")
            self.cash_status.setText(f"Caixa ABERTO desde {session['opened_at']}")
            s = finance_service.summary(session["id"])
            expected = session["opening_amount"] + s["liquido"]
            self.s_open.setText(fmt_money(session["opening_amount"], cur))
            self.s_in.setText(fmt_money(s["entrada"], cur))
            self.s_out.setText(fmt_money(s["saida"], cur))
            self.s_net.setText(fmt_money(expected, cur))
        else:
            self.cash_status.setStyleSheet("font-size: 16px; font-weight: 800; color: #6b7280;")
            self.cash_status.setText("Caixa FECHADO — clique em 'Abrir Caixa' para começar o dia")
            self.s_open.setText("R$ 0,00")
            self.s_in.setText("R$ 0,00")
            self.s_out.setText("R$ 0,00")
            self.s_net.setText("R$ 0,00")

        self.moves.setRowCount(0)
        self.cash_prev.setEnabled(False)
        self.cash_next.setEnabled(False)
        self.cash_info.setText("Página 1 de 1")
        if session:
            total = finance_service.count_movements(session["id"])
            pages = max(1, -(-total // self.PAGE_SIZE))
            page = min(self._cash_page, pages) if hasattr(self, "_cash_page") else 1
            self._cash_page = page
            moves = finance_service.movements_page(session["id"], page, self.PAGE_SIZE)
            self.moves.setRowCount(len(moves))
            for i, m in enumerate(moves):
                self.moves.setItem(i, 0, QTableWidgetItem(m["created_at"]))
                tipo = QTableWidgetItem("Entrada" if m["kind"] == "entrada" else "Saída")
                tipo.setForeground(Qt.green if m["kind"] == "entrada" else Qt.red)
                self.moves.setItem(i, 1, tipo)
                self.moves.setItem(i, 2, QTableWidgetItem(m["reason"]))
                self.moves.setItem(i, 3, QTableWidgetItem(fmt_money(m["amount"], cur)))
            self.moves.resizeColumnsToContents()
            self.moves.setColumnWidth(2, 320)
            self.cash_info.setText(f"Página {page} de {pages}  ({total} movimentos)")
            self.cash_prev.setEnabled(page > 1)
            self.cash_next.setEnabled(page < pages)

    def _cash_pager_back(self):
        if not hasattr(self, "_cash_page"):
            self._cash_page = 1
        self._cash_page = max(1, self._cash_page - 1)
        self._reload_cash()

    def _cash_pager_forward(self):
        if not hasattr(self, "_cash_page"):
            self._cash_page = 1
        self._cash_page += 1
        self._reload_cash()

    # ---------------- Ações Contas a Pagar ----------------
    def _add_payable(self):
        dlg = AccountDialog(self, "Adicionar Conta a Pagar")
        if dlg.exec():
            v = dlg.values()
            try:
                finance_service.add_payable(v["description"], v["amount"], v["due_date"],
                                              v["notes"], v["account_id"])
            except ValueError as e:
                QMessageBox.warning(self, "Validação", str(e))
                return
            self.reload()

    # ---------------- Paginação ----------------
    PAGE_SIZE = 50

    def _bills_page(self, kind):
        return getattr(self, f"_{kind}_page", 1)

    def _set_bills_page(self, kind, page):
        setattr(self, f"_{kind}_page", page)

    def _cur_status(self, kind):
        combo = getattr(self, f"{kind}_status")
        return combo.currentData() or "all"

    def _pay_pager_go(self, page):
        self._set_bills_page("pay", page)
        self._reload_payables()

    def _recv_pager_go(self, page):
        self._set_bills_page("recv", page)
        self._reload_receivables()

    def _pay_pager_back(self):
        self._pay_pager_go(max(1, self._bills_page("pay") - 1))

    def _pay_pager_forward(self):
        self._pay_pager_go(self._bills_page("pay") + 1)

    def _recv_pager_back(self):
        self._recv_pager_go(max(1, self._bills_page("recv") - 1))

    def _recv_pager_forward(self):
        self._recv_pager_go(self._bills_page("recv") + 1)

    def _reload_payables(self):
        page = self._bills_page("pay")
        status = self._cur_status("pay")
        total = finance_service.count_payables(status)
        pages = max(1, -(-total // self.PAGE_SIZE))
        page = min(page, pages)
        self._set_bills_page("pay", page)
        bills = finance_service.list_payables(status, page, self.PAGE_SIZE)
        self._pay_bills = bills
        self.pay_info.setText(f"Página {page} de {pages}  ({total} contas)")
        self.pay_prev.setEnabled(page > 1)
        self.pay_next.setEnabled(page < pages)
        self._fill_bills(self.pay_table, bills, "Paga em")

    def _reload_receivables(self):
        page = self._bills_page("recv")
        status = self._cur_status("recv")
        total = finance_service.count_receivables(status)
        pages = max(1, -(-total // self.PAGE_SIZE))
        page = min(page, pages)
        self._set_bills_page("recv", page)
        bills = finance_service.list_receivables(status, page, self.PAGE_SIZE)
        self._recv_bills = bills
        self.recv_info.setText(f"Página {page} de {pages}  ({total} contas)")
        self.recv_prev.setEnabled(page > 1)
        self.recv_next.setEnabled(page < pages)
        self._fill_bills(self.recv_table, bills, "Recebida em")

    def _fill_bills(self, table, bills, paid_label):
        cur = settings_service.get("currency", "R$")
        table.setRowCount(len(bills))
        for i, b in enumerate(bills):
            table.setItem(i, 0, QTableWidgetItem(b["due_date"] or "—"))
            table.setItem(i, 1, QTableWidgetItem(b["account_name"] or "—"))
            table.setItem(i, 2, QTableWidgetItem(b["description"]))
            table.setItem(i, 3, QTableWidgetItem(fmt_money(b["amount"], cur)))
            status_item = QTableWidgetItem("Paga" if b["status"] == "paid" else "Pendente")
            status_item.setForeground(Qt.green if b["status"] == "paid" else Qt.red)
            table.setItem(i, 4, status_item)
            table.setItem(i, 5, QTableWidgetItem(b["paid_at"] or "—"))
        table.resizeColumnsToContents()
        table.setColumnWidth(2, 320)

    def _pay_bill(self):
        row = self.pay_table.currentRow()
        if row < 0:
            return
        bills = self._pay_bills
        if row >= len(bills):
            return
        if bills[row]["status"] == "paid":
            return
        finance_service.pay_bill(bills[row]["id"])
        self._reload_payables()

    def _delete_payable(self):
        row = self.pay_table.currentRow()
        if row < 0:
            return
        bills = self._pay_bills
        if row >= len(bills):
            return
        if QMessageBox.question(self, "Excluir", "Excluir esta conta a pagar?") == QMessageBox.Yes:
            finance_service.delete_payable(bills[row]["id"])
            self._reload_payables()

    # ---------------- Ações Contas a Receber ----------------
    def _add_receivable(self):
        dlg = AccountDialog(self, "Adicionar Conta a Receber")
        if dlg.exec():
            v = dlg.values()
            try:
                finance_service.add_receivable(v["description"], v["amount"], v["due_date"],
                                                v["notes"], v["account_id"])
            except ValueError as e:
                QMessageBox.warning(self, "Validação", str(e))
                return
            self.reload()

    def _receive_bill(self):
        row = self.recv_table.currentRow()
        if row < 0:
            return
        bills = self._recv_bills
        if row >= len(bills):
            return
        if bills[row]["status"] == "paid":
            return
        finance_service.receive_bill(bills[row]["id"])
        self._reload_receivables()

    def _delete_receivable(self):
        row = self.recv_table.currentRow()
        if row < 0:
            return
        bills = self._recv_bills
        if row >= len(bills):
            return
        if QMessageBox.question(self, "Excluir", "Excluir esta conta a receber?") == QMessageBox.Yes:
            finance_service.delete_receivable(bills[row]["id"])
            self._reload_receivables()

    # ---------------- Geral ----------------
    def reload(self):
        self._reload_cash()
        self._reload_payables()
        self._reload_receivables()

    def refresh(self):
        self.reload()