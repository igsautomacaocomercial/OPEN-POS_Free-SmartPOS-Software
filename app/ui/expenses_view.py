import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDateEdit, QDialog, QDoubleSpinBox, QFormLayout, QHBoxLayout,
    QInputDialog, QLabel, QLineEdit, QMessageBox,
    QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from app.services.auth_service import auth_service
from app.services.expense_service import expense_service
from app.services.finance_service import finance_service
from app.services.settings_service import settings_service
from app.ui.keys import bind_table_keys
from app.utils.helpers import fmt_money


class ExpenseDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Adicionar Despesa")
        self.setFixedWidth(420)
        form = QFormLayout(self)
        form.setSpacing(12)

        self.desc = QLineEdit()
        self.desc.setPlaceholderText("Para que isso foi?")
        self.amount = QDoubleSpinBox()
        self.amount.setRange(0, 100_000_000)
        self.amount.setDecimals(2)
        self.amount.setPrefix(settings_service.get("currency", "R$") + " ")
        self.date = QDateEdit()
        self.date.setCalendarPopup(True)
        self.date.setDate(datetime.date.today())

        form.addRow("Descrição", self.desc)
        form.addRow("Valor", self.amount)
        form.addRow("Data", self.date)

        btns = QHBoxLayout()
        save = QPushButton("Salvar")
        save.setProperty("primary", True)
        save.clicked.connect(self._save)
        cancel = QPushButton("Cancelar")
        cancel.clicked.connect(self.reject)
        btns.addWidget(cancel)
        btns.addWidget(save)
        form.addRow(btns)

    def _save(self):
        if self.amount.value() <= 0:
            QMessageBox.warning(self, "Validação", "Informe um valor válido.")
            return
        self.accept()



class ExpensesView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build()
        self.refresh()

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 22, 28, 22)
        outer.setSpacing(14)

        head = QHBoxLayout()
        t = QVBoxLayout()
        title = QLabel("Despesas")
        title.setObjectName("PageTitle")
        sub = QLabel("Acompanhe seus gastos diários")
        sub.setObjectName("PageSubtitle")
        t.addWidget(title)
        t.addWidget(sub)
        head.addLayout(t)
        head.addStretch()
        self.summary_lbl = QLabel("")
        self.summary_lbl.setStyleSheet("font-size: 16px; font-weight: 800; color: #ef4444;")
        head.addWidget(self.summary_lbl)
        outer.addLayout(head)

        btns = QHBoxLayout()
        btns.setSpacing(10)
        add = QPushButton("+  Adicionar Despesa")
        add.setProperty("primary", True)
        add.clicked.connect(self._add_expense)
        btns.addWidget(add)
        btns.addStretch()
        outer.addLayout(btns)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Data", "Descrição", "Valor"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.horizontalHeader().setStretchLastSection(True)
        outer.addWidget(self.table, 1)

        del_btn = QPushButton("Excluir Selecionado")
        del_btn.setProperty("danger", True)
        del_btn.clicked.connect(self._delete)
        self.del_btn = del_btn
        outer.addWidget(del_btn, alignment=Qt.AlignRight)

        self._apply_role_restrictions()

        bind_table_keys(self.table, on_delete=self._delete)

    def _apply_role_restrictions(self):
        role = (auth_service.current_user or {}).get("role")
        if role == "cashier":
            self.del_btn.setVisible(False)

        self.refresh()

    def refresh(self):
        start = datetime.date.today().replace(day=1).isoformat()
        end = datetime.date.today().isoformat()
        expenses = expense_service.list()
        self.table.setRowCount(len(expenses))
        currency = settings_service.get("currency", "R$")
        for i, e in enumerate(expenses):
            self.table.setItem(i, 0, QTableWidgetItem(e["expense_date"]))
            self.table.setItem(i, 1, QTableWidgetItem(e["description"] or ""))
            self.table.setItem(i, 2, QTableWidgetItem(fmt_money(e["amount"], currency)))
        self.table.resizeColumnsToContents()
        self.table.setColumnWidth(1, 300)
        monthly = expense_service.total_between(start, end)
        self.summary_lbl.setText(f"Este Mês: {fmt_money(monthly, currency)}")

    def _add_expense(self):
        dlg = ExpenseDialog(self)
        if dlg.exec():
            expense_service.add(None, dlg.desc.text().strip(),
                                dlg.amount.value(),
                                dlg.date.date().toString("yyyy-MM-dd"))
            finance_service.record_expense(dlg.amount.value(), dlg.desc.text().strip() or "Despesa")
            self.refresh()

    def _delete(self):
        if (auth_service.current_user or {}).get("role") == "cashier":
            return
        row = self.table.currentRow()
        if row < 0:
            return
        expense = expense_service.list()[row]
        if QMessageBox.question(self, "Excluir", "Excluir esta despesa?") == QMessageBox.Yes:
            expense_service.delete(expense["id"])
            self.refresh()


