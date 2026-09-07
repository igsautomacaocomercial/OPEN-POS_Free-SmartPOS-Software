import csv
import datetime
import html
from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QTextDocument
from PySide6.QtPrintSupport import QPrinter
from PySide6.QtWidgets import (
    QComboBox, QDateEdit, QFileDialog, QFrame, QHBoxLayout, QLabel, QMessageBox,
    QPushButton, QScrollArea, QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout,
    QWidget,
)

from app.services.expense_service import expense_service
from app.services.finance_service import finance_service
from app.services.report_service import report_service
from app.services.settings_service import settings_service
from app.ui.charts import PALETTE, BarChart, HBarChart, LineChart, PieChart
from app.ui.icons import icon_pixmap, make_icon
from app.utils.crash_guard import get_logger
from app.utils.helpers import fmt_money

log = get_logger()

TYPE_LABELS = {"dine-in": "No Local", "takeaway": "Para Viagem", "delivery": "Delivery"}

PRESETS = ["Hoje", "Ontem", "Esta Semana", "Este Mês", "Mês Passado", "Personalizado"]


def _preset_range(preset):
    today = datetime.date.today()
    if preset == "Hoje":
        return today.isoformat(), today.isoformat()
    if preset == "Ontem":
        d = today - datetime.timedelta(days=1)
        return d.isoformat(), d.isoformat()
    if preset == "Esta Semana":
        start = today - datetime.timedelta(days=today.weekday())
        return start.isoformat(), today.isoformat()
    if preset == "Este Mês":
        start = today.replace(day=1)
        return start.isoformat(), today.isoformat()
    if preset == "Mês Passado":
        first = today.replace(day=1)
        last_month = first - datetime.timedelta(days=1)
        start = last_month.replace(day=1)
        return start.isoformat(), last_month.isoformat()
    return today.isoformat(), today.isoformat()


def _stat_card(icon_name, label, color):
    card = QFrame()
    card.setProperty("card", True)
    card.setMinimumHeight(116)
    lay = QHBoxLayout(card)
    lay.setContentsMargins(18, 18, 18, 18)
    lay.setSpacing(16)
    icon_lbl = QLabel()
    icon_lbl.setPixmap(icon_pixmap(icon_name, color, 24))
    icon_lbl.setStyleSheet(f"background: {color}22; border-radius: 12px;")
    icon_lbl.setAlignment(Qt.AlignCenter)
    icon_lbl.setFixedSize(48, 48)
    lay.addWidget(icon_lbl)
    txt = QVBoxLayout()
    txt.setSpacing(2)
    val = QLabel("0")
    val.setObjectName("StatValue")
    txt.addWidget(val)
    lbl = QLabel(label)
    lbl.setObjectName("StatLabel")
    txt.addWidget(lbl)
    lay.addLayout(txt, 1)
    lay.addStretch()
    card._value_lbl = val
    return card


class ReportsView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._ready = False
        self._build()
        self._ready = True
        self.refresh()

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 22, 28, 22)
        outer.setSpacing(14)

        head = QHBoxLayout()
        t = QVBoxLayout()
        title = QLabel("Relatórios")
        title.setObjectName("PageTitle")
        sub = QLabel("Vendas, lucro & prejuízo e desempenho da equipe")
        sub.setObjectName("PageSubtitle")
        t.addWidget(title)
        t.addWidget(sub)
        head.addLayout(t)
        head.addStretch()
        outer.addLayout(head)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollArea > QWidget > QWidget { background: transparent; }"
        )
        scroll.viewport().setAutoFillBackground(False)
        content = QWidget()
        body = QVBoxLayout(content)
        body.setContentsMargins(0, 0, 8, 16)
        body.setSpacing(16)

        self._build_filters(body)

        cards = QHBoxLayout()
        cards.setSpacing(12)
        self.c_revenue = _stat_card("coins", "Receita", "#10b981")
        self.c_cost = _stat_card("box", "Custo dos Produtos", "#f59e0b")
        self.c_gross = _stat_card("chart", "Lucro Bruto", "#ea580c")
        self.c_net = _stat_card("wallet", "Lucro / Prejuízo Líquido", "#ef4444")
        for c in (self.c_revenue, self.c_cost, self.c_gross, self.c_net):
            cards.addWidget(c)
        body.addLayout(cards)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_sales_tab(), "Vendas")
        self.tabs.addTab(self._build_pnl_tab(), "Lucro & Prejuízo")
        self.tabs.addTab(self._build_products_tab(), "Produtos")
        self.tabs.addTab(self._build_staff_tab(), "Desempenho da Equipe")
        self.tabs.addTab(self._build_expenses_tab(), "Despesas")
        self.tabs.addTab(self._build_payments_tab(), "Pagamentos")
        self.tabs.addTab(self._build_cash_report_tab(), "Caixa")
        self.tabs.addTab(self._build_payables_report_tab(), "Contas a Pagar")
        self.tabs.addTab(self._build_receivables_report_tab(), "Contas a Receber")
        body.addWidget(self.tabs, 1)

        body.addStretch(1)
        scroll.setWidget(content)
        outer.addWidget(scroll, 1)

    # ---------------- Filter bar ----------------
    def _build_filters(self, outer):
        card = QFrame()
        card.setProperty("card", True)
        row = QHBoxLayout(card)
        row.setContentsMargins(16, 12, 16, 12)
        row.setSpacing(10)

        self.preset = QComboBox()
        self.preset.addItems(PRESETS)
        self.preset.currentIndexChanged.connect(self._preset_changed)
        row.addWidget(self.preset)

        self.date_from = QDateEdit()
        self.date_from.setCalendarPopup(True)
        self.date_from.setFixedWidth(120)
        self.date_from.setDate(datetime.date.today())
        self.date_to = QDateEdit()
        self.date_to.setCalendarPopup(True)
        self.date_to.setFixedWidth(120)
        self.date_to.setDate(datetime.date.today())
        row.addWidget(self.date_from)
        arrow = QLabel("→")
        arrow.setStyleSheet("color: #6b7280; font-size: 14px;")
        arrow.setAlignment(Qt.AlignCenter)
        row.addWidget(arrow)
        row.addWidget(self.date_to)

        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setStyleSheet("color: #e5e7eb;")
        row.addWidget(sep)

        self.filter_type = QComboBox()
        self.filter_type.addItem("Todos os Tipos", None)
        for k in ("dine-in", "takeaway", "delivery"):
            self.filter_type.addItem(TYPE_LABELS[k], k)
        row.addWidget(self.filter_type)

        self.filter_pay = QComboBox()
        self.filter_pay.addItem("Todos os Pagamentos", None)
        row.addWidget(self.filter_pay)

        self.filter_waiter = QComboBox()
        self.filter_waiter.addItem("Todos os Garçons", None)
        row.addWidget(self.filter_waiter)

        run = QPushButton("   Executar")
        run.setProperty("primary", True)
        run.setIcon(make_icon("refresh", "#ffffff", 24))
        run.setIconSize(QSize(18, 18))
        run.clicked.connect(self.refresh)
        row.addWidget(run)

        export = QPushButton("Exportar CSV")
        export.setIcon(make_icon("download", "#4b5563", 24))
        export.setIconSize(QSize(16, 16))
        export.clicked.connect(self._export_csv)
        row.addWidget(export)
        excel = QPushButton("Exportar Excel")
        excel.setIcon(make_icon("download", "#4b5563", 24))
        excel.setIconSize(QSize(16, 16))
        excel.clicked.connect(self._export_excel)
        row.addWidget(excel)
        pdf = QPushButton("Exportar PDF")
        pdf.setIcon(make_icon("download", "#4b5563", 24))
        pdf.setIconSize(QSize(16, 16))
        pdf.clicked.connect(self._export_pdf)
        row.addWidget(pdf)
        row.addStretch()

        for combo in (self.filter_type, self.filter_pay, self.filter_waiter):
            combo.currentIndexChanged.connect(self._filters_changed)

        for m in report_service.list_payment_methods():
            self.filter_pay.addItem(m, m)
        for w in report_service.list_waiters():
            self.filter_waiter.addItem(w["name"], w["id"])

        outer.addWidget(card)

    def _preset_changed(self, idx):
        preset = self.preset.currentText()
        custom = preset == "Personalizado"
        self.date_from.setEnabled(custom)
        self.date_to.setEnabled(custom)
        if not custom:
            s, e = _preset_range(preset)
            self.date_from.setDate(datetime.date.fromisoformat(s))
            self.date_to.setDate(datetime.date.fromisoformat(e))
            if self._ready:
                self.refresh()

    def _filters_changed(self, _=None):
        if self._ready:
            self.refresh()

    def _filters(self):
        f = {}
        if self.filter_type.currentData():
            f["order_type"] = self.filter_type.currentData()
        if self.filter_pay.currentData():
            f["payment_method"] = self.filter_pay.currentData()
        if self.filter_waiter.currentData():
            f["waiter_id"] = self.filter_waiter.currentData()
        return f

    # ---------------- Chart / table cards ----------------
    def _chart_card(self, title, chart):
        card = QFrame()
        card.setProperty("card", True)
        v = QVBoxLayout(card)
        v.setContentsMargins(16, 14, 16, 12)
        lbl = QLabel(title)
        lbl.setObjectName("CardTitle")
        v.addWidget(lbl)
        v.addWidget(chart)
        return card

    def _table_card(self, title, table):
        card = QFrame()
        card.setProperty("card", True)
        v = QVBoxLayout(card)
        v.setContentsMargins(16, 14, 16, 12)
        lbl = QLabel(title)
        lbl.setObjectName("CardTitle")
        v.addWidget(lbl)
        v.addWidget(table)
        return card

    @staticmethod
    def _make_table(columns, stretch_last=True):
        table = QTableWidget(0, len(columns))
        table.setHorizontalHeaderLabels(columns)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setSelectionMode(QTableWidget.SingleSelection)
        table.setMinimumHeight(220)
        if stretch_last:
            table.horizontalHeader().setStretchLastSection(True)
        return table

    # ---------------- Tabs ----------------
    def _build_sales_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 8, 0, 0)
        top = QHBoxLayout()
        self.sales_trend = LineChart()
        self.sales_types = PieChart()
        top.addWidget(self._chart_card("Tendência Diária de Vendas", self.sales_trend), 3)
        top.addWidget(self._chart_card("Vendas por Tipo de Pedido", self.sales_types), 2)
        lay.addLayout(top)

        self.sales_table = self._make_table(
            ["Pedido", "Tipo", "Mesa", "Garçom", "Subtotal", "Desconto", "Imposto", "Total"])
        lay.addWidget(self.sales_table, 1)
        return w

    def _build_pnl_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 8, 0, 0)
        top = QHBoxLayout()
        scard = QFrame()
        scard.setProperty("card", True)
        sv = QVBoxLayout(scard)
        sv.setContentsMargins(24, 16, 24, 16)
        stitle = QLabel("Demonstrativo de Lucro & Prejuízo")
        stitle.setObjectName("CardTitle")
        sv.addWidget(stitle)
        self.pnl_lbl = QLabel("")
        self.pnl_lbl.setTextFormat(Qt.RichText)
        sv.addWidget(self.pnl_lbl, 1)
        top.addWidget(scard, 3)

        self.pnl_chart = BarChart()
        top.addWidget(self._chart_card("Vendas vs Custo vs Despesas", self.pnl_chart), 2)
        lay.addLayout(top)

        bot = QHBoxLayout()
        self.expense_pie = PieChart()
        self.expense_cat_table = self._make_table(["Categoria", "Valor"], stretch_last=False)
        bot.addWidget(self._chart_card("Despesas por Categoria", self.expense_pie), 2)
        bot.addWidget(self._table_card("Resumo de Despesas", self.expense_cat_table), 3)
        lay.addLayout(bot)
        return w

    def _build_products_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 8, 0, 0)
        top = QHBoxLayout()
        self.product_bar = HBarChart()
        self.category_pie = PieChart()
        top.addWidget(self._chart_card("Produtos Mais Vendidos por Qtd.", self.product_bar), 3)
        top.addWidget(self._chart_card("Receita por Categoria", self.category_pie), 2)
        lay.addLayout(top)
        self.product_table = self._make_table(["Produto", "Qtd. Vendida", "Receita", "Participação %"])
        lay.addWidget(self.product_table, 1)
        return w

    def _build_staff_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 8, 0, 0)
        top = QHBoxLayout()
        self.waiter_bar = HBarChart()
        self.rider_bar = HBarChart()
        top.addWidget(self._chart_card("Receita dos Garçons", self.waiter_bar), 3)
        top.addWidget(self._chart_card("Entregas dos Entregadores", self.rider_bar), 2)
        lay.addLayout(top)

        bot = QHBoxLayout()
        self.waiter_table = self._make_table(["Garçom", "Pedidos", "Itens", "Receita", "Ticket Médio"])
        self.rider_table = self._make_table(["Entregador", "Entregas", "Receita", "Ticket Médio"])
        bot.addWidget(self._table_card("Garçons", self.waiter_table), 1)
        bot.addWidget(self._table_card("Entregadores", self.rider_table), 1)
        lay.addLayout(bot)
        return w

    def _build_expenses_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 8, 0, 0)
        top = QHBoxLayout()
        self.expense_detail_pie = PieChart()
        self.expense_detail_table = self._make_table(["Data", "Categoria", "Descrição", "Valor"])
        top.addWidget(self._chart_card("Despesas por Categoria", self.expense_detail_pie), 2)
        top.addWidget(self._table_card("Detalhes das Despesas", self.expense_detail_table), 3)
        lay.addLayout(top)
        return w

    def _build_payments_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 8, 0, 0)
        top = QHBoxLayout()
        self.pay_pie = PieChart()
        self.pay_table = self._make_table(["Forma de Pagamento", "Pedidos", "Valor", "Participação %"])
        top.addWidget(self._chart_card("Detalhamento por Forma de Pagamento", self.pay_pie), 2)
        top.addWidget(self._table_card("Detalhes dos Pagamentos", self.pay_table), 3)
        lay.addLayout(top)
        return w

    def _build_cash_report_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 8, 0, 0)
        top = QHBoxLayout()
        self.cash_report_summary = QLabel("Selecione o período e clique em Executar.")
        self.cash_report_summary.setObjectName("CardTitle")
        self.cash_report_summary.setTextFormat(Qt.RichText)
        top.addWidget(self.cash_report_summary, 1)
        lay.addLayout(top)
        self.cash_sessions_table = self._make_table(
            ["Abertura", "Fechamento", "Abertura", "Entradas", "Saídas", "Esperado", "Fechado", "Status"])
        self.cash_moves_table = self._make_table(["Data/Hora", "Tipo", "Motivo", "Valor"])
        lay.addWidget(self._table_card("Sessões de Caixa", self.cash_sessions_table), 1)
        lay.addWidget(self._table_card("Movimentos de Caixa", self.cash_moves_table), 1)
        return w

    def _build_payables_report_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 8, 0, 0)
        self.payables_report_summary = QLabel("Selecione o período e clique em Executar.")
        self.payables_report_summary.setObjectName("CardTitle")
        self.payables_report_summary.setTextFormat(Qt.RichText)
        lay.addWidget(self.payables_report_summary)
        self.payables_report_table = self._make_table(
            ["Vencimento", "Conta", "Descrição", "Valor", "Status", "Paga em"])
        lay.addWidget(self.payables_report_table, 1)
        return w

    def _build_receivables_report_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 8, 0, 0)
        self.receivables_report_summary = QLabel("Selecione o período e clique em Executar.")
        self.receivables_report_summary.setObjectName("CardTitle")
        self.receivables_report_summary.setTextFormat(Qt.RichText)
        lay.addWidget(self.receivables_report_summary)
        self.receivables_report_table = self._make_table(
            ["Vencimento", "Conta", "Descrição", "Valor", "Status", "Recebida em"])
        lay.addWidget(self.receivables_report_table, 1)
        return w

    # ---------------- Refresh ----------------
    def refresh(self):
        try:
            self._refresh()
        except Exception:
            log.exception("Reports refresh failed")
            self.c_revenue._value_lbl.setText("—")
            self.c_cost._value_lbl.setText("—")
            self.c_gross._value_lbl.setText("—")
            self.c_net._value_lbl.setText("—")

    def _refresh(self):
        start = self.date_from.date().toString("yyyy-MM-dd")
        end = self.date_to.date().toString("yyyy-MM-dd")
        currency = settings_service.get("currency", "R$")
        flt = self._filters()

        pl = report_service.profit_loss(start, end, **flt)
        self.c_revenue._value_lbl.setText(fmt_money(pl["total"], currency))
        self.c_cost._value_lbl.setText(fmt_money(pl["cost"], currency))
        self.c_gross._value_lbl.setText(fmt_money(pl["gross_profit"], currency))
        self.c_net._value_lbl.setText(fmt_money(pl["net_profit"], currency))
        self.c_net._value_lbl.setStyleSheet(
            "color: %s; font-size: 26px; font-weight: 800;" %
            ("#10b981" if pl["net_profit"] >= 0 else "#ef4444")
        )
        self.c_gross._value_lbl.setStyleSheet("color: #ea580c; font-size: 26px; font-weight: 800;")

        self._refresh_sales(pl, currency, start, end, flt)
        self._refresh_pnl(pl, currency, start, end)
        self._refresh_products(start, end, currency, flt)
        self._refresh_staff(start, end, currency, flt)
        self._refresh_expenses(start, end, currency)
        self._refresh_payments(start, end, currency, flt)
        self._refresh_cash_report(start, end, currency)
        self._refresh_payables_report(start, end, currency)
        self._refresh_receivables_report(start, end, currency)

    def _refresh_sales(self, pl, currency, start, end, flt):
        series = report_service.daily_series_between(start, end, **flt)
        self.sales_trend.set_data([{"label": d["label"], "value": d["total"]} for d in series])

        types = report_service.order_type_breakdown(start, end, **flt)
        self.sales_types.set_data([
            {"label": TYPE_LABELS.get(r["order_type"], r["order_type"]),
             "value": r["total"],
             "color": PALETTE[i % len(PALETTE)]}
            for i, r in enumerate(types)
        ])

        rows = pl["rows"]
        self.sales_table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            self.sales_table.setItem(i, 0, QTableWidgetItem(f"#{r['order_number']}"))
            self.sales_table.setItem(i, 1, QTableWidgetItem(TYPE_LABELS.get(r["order_type"], r["order_type"])))
            self.sales_table.setItem(i, 2, QTableWidgetItem(r["table_no"] or "—"))
            self.sales_table.setItem(i, 3, QTableWidgetItem(r["waiter_name"] or "—"))
            self.sales_table.setItem(i, 4, QTableWidgetItem(fmt_money(r["subtotal"], currency)))
            self.sales_table.setItem(i, 5, QTableWidgetItem(fmt_money(r["discount"], currency)))
            self.sales_table.setItem(i, 6, QTableWidgetItem(fmt_money(r["tax"], currency)))
            self.sales_table.setItem(i, 7, QTableWidgetItem(fmt_money(r["total"], currency)))
        self.sales_table.resizeColumnsToContents()

    def _build_statement_html(self, pl, currency):
        def m(v):
            return fmt_money(v, currency)

        def row(label, value, extra=""):
            return (f'<tr><td style="padding:5px 20px 5px 0; color:#6b7280;{extra}">{label}</td>'
                    f'<td style="padding:5px 0; text-align:right; color:#111827;{extra}">{value}</td></tr>')

        sep = '<tr><td colspan="2" style="border-bottom:1px solid #e5e7eb;"></td></tr>'
        html = ['<table style="border-collapse:collapse; width:100%; font-size:14px;">']
        html.append(row("Vendas Brutas", m(pl["subtotal"])))
        html.append(row("Menos: Descontos", f"- {m(pl['discount'])}"))
        html.append(row("Mais: Taxas de Serviço", f"+ {m(pl['service_charge'])}"))
        html.append(row("Vendas Líquidas", m(pl["net_sales"]), "font-weight:700;"))
        html.append(row("Imposto sobre Vendas", m(pl["tax"])))
        html.append(row("Total Recebido", m(pl["total"]), "font-weight:700;"))
        html.append(sep)
        html.append(row("Menos: Custo dos Produtos Vendidos", f"- {m(pl['cost'])}"))
        html.append(row("Lucro Bruto", m(pl["gross_profit"]), "font-weight:800; color:#ea580c;"))
        html.append(sep)
        html.append(row("Menos: Despesas Operacionais", f"- {m(pl['expenses'])}"))
        html.append(sep)
        if pl["net_profit"] >= 0:
            html.append(row("LUCRO LÍQUIDO", m(pl["net_profit"]), "font-weight:800; font-size:16px; color:#10b981;"))
        else:
            html.append(row("PREJUÍZO LÍQUIDO", f"({m(abs(pl['net_profit']))})", "font-weight:800; font-size:16px; color:#ef4444;"))
        html.append("</table>")
        return "".join(html)

    def _refresh_pnl(self, pl, currency, start, end):
        self.pnl_lbl.setText(self._build_statement_html(pl, currency))
        self.pnl_chart.set_data([
            {"label": "Vendas", "value": pl["net_sales"], "color": "#ea580c"},
            {"label": "Custo", "value": pl["cost"], "color": "#f59e0b"},
            {"label": "Despesas", "value": pl["expenses"], "color": "#ef4444"},
            {"label": "Lucro Líquido", "value": max(pl["net_profit"], 0), "color": "#10b981"},
        ])

        cats = expense_service.by_category_between(start, end)
        self.expense_pie.set_data([
            {"label": r["name"], "value": r["total"], "color": PALETTE[i % len(PALETTE)]}
            for i, r in enumerate(cats)
        ])
        self.expense_cat_table.setRowCount(len(cats))
        for i, r in enumerate(cats):
            self.expense_cat_table.setItem(i, 0, QTableWidgetItem(r["name"]))
            self.expense_cat_table.setItem(i, 1, QTableWidgetItem(fmt_money(r["total"], currency)))
        self.expense_cat_table.resizeColumnsToContents()

    def _refresh_products(self, start, end, currency, flt):
        rank = report_service.product_rank(start, end, limit=10, **flt)
        total_rev = sum(r["revenue"] for r in rank) or 1
        self.product_bar.set_data([
            {"label": r["name"][:22], "value": r["qty"],
             "color": PALETTE[i % len(PALETTE)]}
            for i, r in enumerate(rank)
        ])
        self.product_table.setRowCount(len(rank))
        for i, r in enumerate(rank):
            self.product_table.setItem(i, 0, QTableWidgetItem(r["name"]))
            self.product_table.setItem(i, 1, QTableWidgetItem(str(r["qty"])))
            self.product_table.setItem(i, 2, QTableWidgetItem(fmt_money(r["revenue"], currency)))
            self.product_table.setItem(i, 3, QTableWidgetItem(f"{r['revenue'] / total_rev * 100:.1f}%"))
        self.product_table.resizeColumnsToContents()

        cats = report_service.category_sales(start, end, **flt)
        self.category_pie.set_data([
            {"label": r["category"], "value": r["revenue"], "color": PALETTE[i % len(PALETTE)]}
            for i, r in enumerate(cats)
        ])

    def _refresh_staff(self, start, end, currency, flt):
        waiters = report_service.staff_performance(start, end, "Garçom", **flt)
        self.waiter_bar.set_data([
            {"label": r["name"][:20], "value": r["revenue"],
             "color": PALETTE[i % len(PALETTE)]}
            for i, r in enumerate(waiters)
        ])
        self.waiter_table.setRowCount(len(waiters))
        for i, r in enumerate(waiters):
            self.waiter_table.setItem(i, 0, QTableWidgetItem(r["name"]))
            self.waiter_table.setItem(i, 1, QTableWidgetItem(str(r["orders"])))
            self.waiter_table.setItem(i, 2, QTableWidgetItem(str(r["items"])))
            self.waiter_table.setItem(i, 3, QTableWidgetItem(fmt_money(r["revenue"], currency)))
            self.waiter_table.setItem(i, 4, QTableWidgetItem(fmt_money(r["avg_ticket"], currency)))
        self.waiter_table.resizeColumnsToContents()

        riders = report_service.staff_performance(start, end, "Entregador")
        self.rider_bar.set_data([
            {"label": r["name"][:20], "value": r["orders"],
             "color": PALETTE[i % len(PALETTE)]}
            for i, r in enumerate(riders)
        ])
        self.rider_table.setRowCount(len(riders))
        for i, r in enumerate(riders):
            self.rider_table.setItem(i, 0, QTableWidgetItem(r["name"]))
            self.rider_table.setItem(i, 1, QTableWidgetItem(str(r["orders"])))
            self.rider_table.setItem(i, 2, QTableWidgetItem(fmt_money(r["revenue"], currency)))
            self.rider_table.setItem(i, 3, QTableWidgetItem(fmt_money(r["avg_ticket"], currency)))
        self.rider_table.resizeColumnsToContents()

    def _refresh_expenses(self, start, end, currency):
        cats = expense_service.by_category_between(start, end)
        self.expense_detail_pie.set_data([
            {"label": r["name"], "value": r["total"], "color": PALETTE[i % len(PALETTE)]}
            for i, r in enumerate(cats)
        ])
        rows = expense_service.list(start, end)
        self.expense_detail_table.setRowCount(len(rows))
        for i, e in enumerate(rows):
            self.expense_detail_table.setItem(i, 0, QTableWidgetItem(e["expense_date"]))
            self.expense_detail_table.setItem(i, 1, QTableWidgetItem(e["category_name"] or "—"))
            self.expense_detail_table.setItem(i, 2, QTableWidgetItem(e["description"] or ""))
            self.expense_detail_table.setItem(i, 3, QTableWidgetItem(fmt_money(e["amount"], currency)))
        self.expense_detail_table.resizeColumnsToContents()
        self.expense_detail_table.setColumnWidth(2, 300)

    def _refresh_payments(self, start, end, currency, flt):
        pays = report_service.payment_breakdown(start, end, **flt)
        total = sum(r["total"] for r in pays) or 1
        self.pay_pie.set_data([
            {"label": r["method"], "value": r["total"], "color": PALETTE[i % len(PALETTE)]}
            for i, r in enumerate(pays)
        ])
        self.pay_table.setRowCount(len(pays))
        for i, r in enumerate(pays):
            self.pay_table.setItem(i, 0, QTableWidgetItem(r["method"]))
            self.pay_table.setItem(i, 1, QTableWidgetItem(str(r["c"])))
            self.pay_table.setItem(i, 2, QTableWidgetItem(fmt_money(r["total"], currency)))
            self.pay_table.setItem(i, 3, QTableWidgetItem(f"{r['total'] / total * 100:.1f}%"))
        self.pay_table.resizeColumnsToContents()

    def _refresh_cash_report(self, start, end, currency):
        sessions = finance_service.sessions_between(start, end)
        moves = finance_service.movements_between(start, end)
        total_in = sum(float(m["amount"]) for m in moves if m["kind"] == "entrada")
        total_out = sum(float(m["amount"]) for m in moves if m["kind"] == "saida")
        summary = (f"<b>Sessões:</b> {len(sessions)} &nbsp;·&nbsp; "
                   f"<b>Entradas:</b> {fmt_money(total_in, currency)} &nbsp;·&nbsp; "
                   f"<b>Saídas:</b> {fmt_money(total_out, currency)} &nbsp;·&nbsp; "
                   f"<b>Líquido:</b> {fmt_money(total_in - total_out, currency)}")
        self.cash_report_summary.setText(summary)

        self.cash_sessions_table.setRowCount(len(sessions))
        for i, s in enumerate(sessions):
            ssum = finance_service.summary(s["id"])
            expected = float(s["opening_amount"] or 0) + ssum["liquido"]
            self.cash_sessions_table.setItem(i, 0, QTableWidgetItem(s["opened_at"] or "—"))
            self.cash_sessions_table.setItem(i, 1, QTableWidgetItem(s.get("closed_at") or "—"))
            self.cash_sessions_table.setItem(i, 2, QTableWidgetItem(fmt_money(s["opening_amount"], currency)))
            self.cash_sessions_table.setItem(i, 3, QTableWidgetItem(fmt_money(ssum["entrada"], currency)))
            self.cash_sessions_table.setItem(i, 4, QTableWidgetItem(fmt_money(ssum["saida"], currency)))
            self.cash_sessions_table.setItem(i, 5, QTableWidgetItem(fmt_money(expected, currency)))
            self.cash_sessions_table.setItem(i, 6, QTableWidgetItem(fmt_money(s.get("closing_amount") or 0, currency)))
            self.cash_sessions_table.setItem(i, 7, QTableWidgetItem(
                "Fechado" if s["status"] == "closed" else "Aberto"))
        self.cash_sessions_table.resizeColumnsToContents()

        self.cash_moves_table.setRowCount(len(moves))
        for i, m in enumerate(moves):
            self.cash_moves_table.setItem(i, 0, QTableWidgetItem(m["created_at"]))
            self.cash_moves_table.setItem(i, 1, QTableWidgetItem(
                "Entrada" if m["kind"] == "entrada" else "Saída"))
            self.cash_moves_table.setItem(i, 2, QTableWidgetItem(m["reason"] or ""))
            self.cash_moves_table.setItem(i, 3, QTableWidgetItem(fmt_money(m["amount"], currency)))
        self.cash_moves_table.resizeColumnsToContents()

    def _refresh_payables_report(self, start, end, currency):
        rows = finance_service.payables_between(start, end)
        pend_total = sum(float(r["amount"]) for r in rows if r["status"] == "pending")
        paid_total = sum(float(r["amount"]) for r in rows if r["status"] == "paid")
        self.payables_report_summary.setText(
            f"<b>{len(rows)}</b> contas no período &nbsp;·&nbsp; "
            f"<b>A pagar:</b> {fmt_money(pend_total, currency)} &nbsp;·&nbsp; "
            f"<b>Pagas:</b> {fmt_money(paid_total, currency)}")
        self.payables_report_table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            self.payables_report_table.setItem(i, 0, QTableWidgetItem(r["due_date"] or "—"))
            self.payables_report_table.setItem(i, 1, QTableWidgetItem(r["account_name"] or "—"))
            self.payables_report_table.setItem(i, 2, QTableWidgetItem(r["description"]))
            self.payables_report_table.setItem(i, 3, QTableWidgetItem(fmt_money(r["amount"], currency)))
            self.payables_report_table.setItem(i, 4, QTableWidgetItem(
                "Paga" if r["status"] == "paid" else "Pendente"))
            self.payables_report_table.setItem(i, 5, QTableWidgetItem(r["paid_at"] or "—"))
        self.payables_report_table.resizeColumnsToContents()

    def _refresh_receivables_report(self, start, end, currency):
        rows = finance_service.receivables_between(start, end)
        pend_total = sum(float(r["amount"]) for r in rows if r["status"] == "pending")
        paid_total = sum(float(r["amount"]) for r in rows if r["status"] == "paid")
        self.receivables_report_summary.setText(
            f"<b>{len(rows)}</b> contas no período &nbsp;·&nbsp; "
            f"<b>A receber:</b> {fmt_money(pend_total, currency)} &nbsp;·&nbsp; "
            f"<b>Recebidas:</b> {fmt_money(paid_total, currency)}")
        self.receivables_report_table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            self.receivables_report_table.setItem(i, 0, QTableWidgetItem(r["due_date"] or "—"))
            self.receivables_report_table.setItem(i, 1, QTableWidgetItem(r["account_name"] or "—"))
            self.receivables_report_table.setItem(i, 2, QTableWidgetItem(r["description"]))
            self.receivables_report_table.setItem(i, 3, QTableWidgetItem(fmt_money(r["amount"], currency)))
            self.receivables_report_table.setItem(i, 4, QTableWidgetItem(
                "Recebida" if r["status"] == "paid" else "Pendente"))
            self.receivables_report_table.setItem(i, 5, QTableWidgetItem(r["paid_at"] or "—"))
        self.receivables_report_table.resizeColumnsToContents()

    # ---------------- Export ----------------
    _TAB_TITLES = ["Vendas", "Lucro_e_Prejuizo", "Produtos", "Equipe", "Despesas", "Pagamentos",
                   "Caixa", "Contas_a_Pagar", "Contas_a_Receber"]

    def _export_data(self):
        start = self.date_from.date().toString("yyyy-MM-dd")
        end = self.date_to.date().toString("yyyy-MM-dd")
        flt = self._filters()
        tab = self.tabs.currentIndex()
        name = f"{self._TAB_TITLES[tab]}_{start}_a_{end}"
        rows, headers = [], []

        if tab == 0:
            rows = report_service.sales_between(start, end, **flt)
            headers = ["Pedido", "Tipo", "Mesa", "Garçom", "Subtotal", "Desconto", "Imposto", "Total", "Pagamento", "Data"]
            data = [[r["order_number"], TYPE_LABELS.get(r["order_type"], r["order_type"]), r["table_no"], r["waiter_name"],
                     r["subtotal"], r["discount"], r["tax"], r["total"], r["payment_method"], r["created_at"]]
                    for r in rows]
        elif tab == 1:
            pl = report_service.profit_loss(start, end, **flt)
            headers = ["Item", "Valor"]
            data = [
                ["Vendas Brutas", pl["subtotal"]], ["Descontos", pl["discount"]],
                ["Taxas de Serviço", pl["service_charge"]], ["Vendas Líquidas", pl["net_sales"]],
                ["Imposto sobre Vendas", pl["tax"]], ["Total Recebido", pl["total"]],
                ["Custo dos Produtos", pl["cost"]], ["Lucro Bruto", pl["gross_profit"]],
                ["Despesas Operacionais", pl["expenses"]], ["Lucro Líquido", pl["net_profit"]],
            ]
        elif tab == 2:
            rows = report_service.product_rank(start, end, limit=100, **flt)
            headers = ["Produto", "Qtd. Vendida", "Receita"]
            data = [[r["name"], r["qty"], r["revenue"]] for r in rows]
        elif tab == 3:
            waiters = report_service.staff_performance(start, end, "Garçom", **flt)
            riders = report_service.staff_performance(start, end, "Entregador")
            headers = ["Nome", "Papel", "Pedidos", "Receita"]
            data = ([[r["name"], "Garçom", r["orders"], r["revenue"]] for r in waiters]
                    + [[r["name"], "Entregador", r["orders"], r["revenue"]] for r in riders])
        elif tab == 4:
            rows = expense_service.list(start, end)
            headers = ["Data", "Categoria", "Descrição", "Valor"]
            data = [[r["expense_date"], r["category_name"], r["description"], r["amount"]] for r in rows]
        else:
            if tab == 5:
                rows = report_service.payment_breakdown(start, end, **flt)
                headers = ["Forma de Pagamento", "Pedidos", "Valor"]
                data = [[r["method"], r["c"], r["total"]] for r in rows]
            elif tab == 6:
                sessions = finance_service.sessions_between(start, end)
                moves = finance_service.movements_between(start, end)
                headers = ["Data", "Tipo", "Descrição", "Valor"]
                data = []
                for m in moves:
                    data.append([m["created_at"], "Entrada" if m["kind"] == "entrada" else "Saída",
                                 m["reason"] or "", m["amount"]])
                for s in sessions:
                    ssum = finance_service.summary(s["id"])
                    expected = float(s["opening_amount"] or 0) + ssum["liquido"]
                    data.append([s["opened_at"], "Sessão",
                                 f"Abertura R$ {s['opening_amount']} · Esperado R$ {expected:.2f}",
                                 expected])
            elif tab == 7:
                rows = finance_service.payables_between(start, end)
                headers = ["Vencimento", "Conta", "Descrição", "Valor", "Status", "Paga em"]
                data = [[r["due_date"], r["account_name"], r["description"], r["amount"],
                         "Paga" if r["status"] == "paid" else "Pendente", r["paid_at"]] for r in rows]
            else:
                rows = finance_service.receivables_between(start, end)
                headers = ["Vencimento", "Conta", "Descrição", "Valor", "Status", "Recebida em"]
                data = [[r["due_date"], r["account_name"], r["description"], r["amount"],
                         "Recebida" if r["status"] == "paid" else "Pendente", r["paid_at"]] for r in rows]
        return name, headers, data

    def _export_csv(self):
        name, headers, data = self._export_data()
        path, _ = QFileDialog.getSaveFileName(
            self, "Exportar Relatório", f"{name}.csv", "CSV (*.csv)")
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(headers)
            w.writerows(data)
        QMessageBox.information(self, "Exportado", f"Salvo em:\n{path}")

    def _export_excel(self):
        name, headers, data = self._export_data()
        path, _ = QFileDialog.getSaveFileName(
            self, "Exportar Excel", f"{name}.xlsx", "Excel (*.xlsx)")
        if not path:
            return
        from openpyxl import Workbook
        wb = Workbook()
        ws = wb.active
        ws.title = name[:31]
        ws.append(headers)
        for row in data:
            ws.append(row)
        try:
            wb.save(path)
        except Exception as e:
            QMessageBox.critical(self, "Erro ao Exportar", str(e))
            return
        QMessageBox.information(self, "Exportado", f"Salvo em:\n{path}")

    def _export_pdf(self):
        name, headers, data = self._export_data()
        path, _ = QFileDialog.getSaveFileName(
            self, "Exportar PDF", f"{name}.pdf", "PDF (*.pdf)")
        if not path:
            return
        biz = settings_service.get("business_name", "Open POS")
        thead = "".join(
            f"<th style='padding:6px; text-align:left; border-bottom:2px solid #ea580c;"
            f" color:#111827;'>{html.escape(str(h))}</th>" for h in headers)
        tbody = "".join(
            "<tr>" + "".join(
                f"<td style='padding:5px 6px; border-bottom:1px solid #e5e7eb; color:#374151;'>{html.escape(str(c))}</td>"
                for c in row) + "</tr>" for row in data)
        doc = QTextDocument()
        doc.setHtml(
            f"<div style='font-family: Arial, sans-serif;'>"
            f"<h1 style='color:#ea580c; margin:0;'>Relatório de {biz}</h1>"
            f"<h2 style='color:#6b7280; margin-top:4px; font-weight:400;'>Exportado em "
            f"{datetime.date.today().isoformat()} · {name}</h2>"
            f"<table style='border-collapse:collapse; width:100%; font-size:12px;'>"
            f"<thead><tr>{thead}</tr></thead><tbody>{tbody}</tbody></table></div>"
        )
        pr = QPrinter(QPrinter.HighResolution)
        pr.setOutputFormat(QPrinter.PdfFormat)
        pr.setOutputFileName(path)
        try:
            doc.print_(pr)
        except Exception as e:
            QMessageBox.critical(self, "Erro ao Exportar", str(e))
            return
        QMessageBox.information(self, "Exportado", f"Salvo em:\n{path}")
