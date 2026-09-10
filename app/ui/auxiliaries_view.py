from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFrame, QHBoxLayout, QInputDialog,
    QLabel, QLineEdit, QMessageBox, QPushButton, QSpinBox, QTabWidget,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from app.services.aux_service import (
    customer_service, neighborhood_service, payment_service, supplier_service,
)
from app.services.addon_service import addon_service
from app.services.auth_service import auth_service
from app.services.brasil_api import brazil_api_service, only_digits, format_cep, format_cnpj
from app.services.chart_account_service import chart_account_service
from app.services.order_service import order_service
from app.services.product_service import product_service
from app.services.staff_service import staff_service
from app.services.settings_service import settings_service
from app.services.table_service import table_service
from app.ui.icons import make_icon
from app.ui.keys import bind_table_keys
from app.utils.helpers import fmt_money

ROLE_OPTIONS = {"admin": "Administrador", "manager": "Gerente", "cashier": "Caixa"}
AUX_PAGE_SIZE = 50
STATUS_ORDER = {"open": "Em aberto", "request_bill": "Pedindo conta", "paid": "Pago", "closed": "Fechado"}
TIPO_ORDER = {"dine-in": "Mesa", "takeaway": "Balcão", "delivery": "Entrega"}


class AuxiliariesView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build()

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 22, 28, 22)
        outer.setSpacing(14)
        title = QLabel("Auxiliares")
        title.setObjectName("PageTitle")
        outer.addWidget(title)
        sub = QLabel("Cadastros de apoio: Mesas, Clientes, Fornecedores, Bairros, Entregadores, "
                     "Formas de Pagamento, Plano de Contas, Categorias, Adicionais, Equipe e Usuarios.")
        sub.setObjectName("PageSubtitle")
        outer.addWidget(sub)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_tables_tab(), "Mesas")
        self.tabs.addTab(self._build_customers_tab(), "Clientes")
        self.tabs.addTab(self._build_suppliers_tab(), "Fornecedores")
        self.tabs.addTab(self._build_neighborhoods_tab(), "Bairros")
        self.tabs.addTab(self._build_riders_tab(), "Entregadores")
        self.tabs.addTab(self._build_payments_tab(), "Formas de Pagamento")
        self.tabs.addTab(self._build_chart_tab(), "Plano de Contas")
        self.tabs.addTab(self._build_categories_tab(), "Categorias")
        self.tabs.addTab(self._build_addons_tab(), "Adicionais")
        self.tabs.addTab(self._build_staff_tab(), "Equipe")
        self.tabs.addTab(self._build_users_tab(), "Usuários")
        outer.addWidget(self.tabs, 1)

    # ---------------- Tables ----------------
    def _build_tables_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setSpacing(10)
        form_row = QHBoxLayout()
        form_row.addWidget(QLabel("Nº da Mesa:"))
        self.t_no = QLineEdit()
        self.t_no.setFixedWidth(120)
        form_row.addWidget(self.t_no)
        form_row.addWidget(QLabel("Lugares:"))
        self.t_seats = QSpinBox()
        self.t_seats.setRange(1, 30)
        self.t_seats.setValue(2)
        self.t_seats.setFixedWidth(80)
        form_row.addWidget(self.t_seats)
        add = QPushButton("+  Adicionar Mesa")
        add.setProperty("primary", True)
        add.clicked.connect(self._add_table)
        form_row.addWidget(add)
        form_row.addStretch()
        lay.addLayout(form_row)

        self.tables_table = QTableWidget(0, 4)
        self.tables_table.setHorizontalHeaderLabels(["ID", "Nº da Mesa", "Lugares", "Status"])
        self.tables_table.verticalHeader().setVisible(False)
        self.tables_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tables_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.tables_table.setSelectionMode(QTableWidget.SingleSelection)
        self.tables_table.horizontalHeader().setStretchLastSection(True)
        lay.addWidget(self.tables_table, 1)

        row_btns = QHBoxLayout()
        edit = QPushButton("Editar")
        edit.clicked.connect(self._edit_table)
        delete = QPushButton("Excluir")
        delete.setProperty("danger", True)
        delete.clicked.connect(self._delete_table)
        row_btns.addStretch()
        row_btns.addWidget(edit)
        row_btns.addWidget(delete)
        lay.addLayout(row_btns)
        self.refresh_tables()
        bind_table_keys(self.tables_table, on_enter=self._edit_table, on_delete=self._delete_table)
        return w

    def refresh_tables(self):
        tables = table_service.list_all()
        self.tables_table.setRowCount(len(tables))
        for i, t in enumerate(tables):
            self.tables_table.setItem(i, 0, QTableWidgetItem(str(t["id"])))
            self.tables_table.setItem(i, 1, QTableWidgetItem(t["table_no"]))
            self.tables_table.setItem(i, 2, QTableWidgetItem(str(t["seats"])))
            self.tables_table.setItem(i, 3, QTableWidgetItem(
                {"free": "Livre", "occupied": "Ocupada", "request_bill": "Pedindo Conta"}
                .get(t["status"], t["status"])))
        self.tables_table.resizeColumnsToContents()

    def _selected_table(self):
        row = self.tables_table.currentRow()
        if row < 0:
            return None
        tables = table_service.list_all()
        return tables[row]

    def _add_table(self):
        no = self.t_no.text().strip()
        if not no:
            return
        try:
            table_service.add(no, self.t_seats.value())
            self.t_no.clear()
            self.refresh_tables()
        except ValueError as e:
            QMessageBox.warning(self, "Erro", str(e))

    def _edit_table(self):
        t = self._selected_table()
        if not t:
            return
        no, ok1 = QInputDialog.getText(self, "Editar Mesa", "Nº da Mesa:", text=t["table_no"])
        if not ok1:
            return
        seats, ok2 = QInputDialog.getInt(self, "Editar Mesa", "Lugares:", value=t["seats"], minValue=1, maxValue=30)
        if not ok2:
            return
        try:
            table_service.update(t["id"], no.strip(), seats)
            self.refresh_tables()
        except ValueError as e:
            QMessageBox.warning(self, "Erro", str(e))

    def _delete_table(self):
        t = self._selected_table()
        if not t:
            return
        try:
            table_service.delete(t["id"])
            self.refresh_tables()
        except ValueError as e:
            QMessageBox.warning(self, "Não é Possível Excluir", str(e))

    # ---------------- Customers ----------------
    def _style_aux_table(self, table):
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setSelectionMode(QTableWidget.SingleSelection)
        table.horizontalHeader().setStretchLastSection(True)

    def _build_customers_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setSpacing(10)

        search_row = QHBoxLayout()
        search_row.addWidget(QLabel("Buscar:"))
        self.c_search = QLineEdit()
        self.c_search.setPlaceholderText("Nome, telefone, documento ou e-mail...")
        self.c_search.setMaximumWidth(300)
        self.c_search.textChanged.connect(self._customers_reload)
        search_row.addWidget(self.c_search)
        self.c_show_inactive = QCheckBox("Mostrar inativos")
        self.c_show_inactive.toggled.connect(self._customers_reload)
        search_row.addWidget(self.c_show_inactive)
        search_row.addStretch()
        self.c_prev = QPushButton("◀  Anterior")
        self.c_info = QLabel("Página 1 de 1")
        self.c_next = QPushButton("Próxima  ▶")
        self.c_prev.clicked.connect(self._cust_page_back)
        self.c_next.clicked.connect(self._cust_page_next)
        search_row.addWidget(self.c_prev)
        search_row.addWidget(self.c_info)
        search_row.addWidget(self.c_next)
        lay.addLayout(search_row)

        self.customers_table = QTableWidget(0, 8)
        self.customers_table.setHorizontalHeaderLabels(
            ["Código", "Nome", "Telefone", "Documento", "E-mail", "Cidade/UF", "Bairro", "Ativo"])
        self._style_aux_table(self.customers_table)
        self.customers_table.doubleClicked.connect(self._customer_ficha)
        lay.addWidget(self.customers_table, 1)

        self._cust_page = 1
        self._cust_rows = []
        btn_row = QHBoxLayout()
        novo = QPushButton("+  Novo")
        novo.setProperty("primary", True)
        novo.clicked.connect(self._customer_novo)
        edit = QPushButton("Editar")
        edit.clicked.connect(self._customer_editar)
        inativar = QPushButton("Inativar")
        inativar.clicked.connect(self._customer_inativar)
        delete = QPushButton("Excluir")
        delete.setProperty("danger", True)
        delete.clicked.connect(self._delete_customer)
        ficha = QPushButton("Ficha & Histórico")
        ficha.clicked.connect(self._customer_ficha)
        btn_row.addWidget(novo)
        btn_row.addWidget(edit)
        btn_row.addWidget(inativar)
        btn_row.addStretch()
        btn_row.addWidget(ficha)
        btn_row.addWidget(delete)
        lay.addLayout(btn_row)
        self.refresh_customers()
        bind_table_keys(self.customers_table, on_enter=self._customer_editar,
                        on_delete=self._delete_customer)
        return w

    def refresh_customers(self):
        term = getattr(self, "c_search", None)
        term = term.text().strip() if term else ""
        show_inactive = getattr(self, "c_show_inactive", None)
        include_inactive = bool(show_inactive and show_inactive.isChecked())
        rows = customer_service.search(term, include_inactive=include_inactive)
        self._cust_rows = rows
        total = len(rows)
        pages = max(1, (total + AUX_PAGE_SIZE - 1) // AUX_PAGE_SIZE) if total else 1
        page = getattr(self, "_cust_page", 1)
        if page > pages:
            page = pages
        self._cust_page = page
        start = (page - 1) * AUX_PAGE_SIZE
        page_rows = rows[start:start + AUX_PAGE_SIZE]
        self.customers_table.setRowCount(len(page_rows))
        for i, c in enumerate(page_rows):
            self.customers_table.setItem(i, 0, QTableWidgetItem(str(c["id"])))
            self.customers_table.setItem(i, 1, QTableWidgetItem(c["name"]))
            self.customers_table.setItem(i, 2, QTableWidgetItem(c["phone"] or ""))
            self.customers_table.setItem(i, 3, QTableWidgetItem(c["document"] or ""))
            self.customers_table.setItem(i, 4, QTableWidgetItem(c["email"] or ""))
            uf = f"{c['city']}/{c['state']}".strip("/ ")
            self.customers_table.setItem(i, 5, QTableWidgetItem(uf))
            self.customers_table.setItem(i, 6, QTableWidgetItem(c["neighborhood"] or ""))
            self.customers_table.setItem(i, 7, QTableWidgetItem("Sim" if c["is_active"] else "Não"))
        self.customers_table.resizeColumnsToContents()
        self.c_prev.setEnabled(page > 1)
        self.c_next.setEnabled(page < pages)
        self.c_info.setText(f"Página {page} de {pages}  ({total} clientes)")

    def _customers_reload(self):
        self._cust_page = 1
        self.refresh_customers()

    def _cust_page_back(self):
        if self._cust_page > 1:
            self._cust_page -= 1
            self.refresh_customers()

    def _cust_page_next(self):
        total = len(self._cust_rows)
        pages = max(1, (total + AUX_PAGE_SIZE - 1) // AUX_PAGE_SIZE) if total else 1
        if self._cust_page < pages:
            self._cust_page += 1
            self.refresh_customers()

    def _selected_customer(self):
        row = self.customers_table.currentRow()
        if row < 0:
            return None
        start = (self._cust_page - 1) * AUX_PAGE_SIZE + row
        if start >= len(self._cust_rows):
            return None
        return self._cust_rows[start]

    def _customer_novo(self):
        self._customer_form(None)

    def _customer_editar(self):
        c = self._selected_customer()
        if not c:
            return
        self._customer_form(c)

    def _lookup_customer_doc(self):
        doc = only_digits(self.c_doc.text())
        if len(doc) == 14:
            data = brazil_api_service.fetch_cnpj(self.c_doc.text())
            if not data:
                QMessageBox.warning(self, "Busca CNPJ", "Não foi possível consultar o CNPJ.")
                return
            self.c_name.setText(data["name"])
            self.c_doc.setText(data["document"])
            self.c_address.setText(data["address"])
            self.c_neighborhood.setCurrentText(data["neighborhood"])
            self.c_city.setText(data["city"])
            self.c_state.setText(data["state"])
            self.c_cep.setText(data["cep"])
            if not self.c_phone.text():
                self.c_phone.setText(data["phone"])
            if not self.c_email.text():
                self.c_email.setText(data["email"])
        elif len(doc) == 11:
            QMessageBox.information(self, "CPF", "CPF identificado (não buscado na Receita).")
        elif doc:
            QMessageBox.warning(self, "Documento", "Digite um CNPJ (14 dígitos) ou CPF (11 dígitos).")

    def _c_bairro_sync(self, text):
        if not hasattr(self, "c_bairro_taxa"):
            return
        fee = None
        combo = self.c_neighborhood
        for i in range(combo.count()):
            n = combo.itemData(i)
            if n and n["name"] == text.strip():
                fee = n["delivery_fee"]
                break
        self.c_bairro_taxa.setText(
            f"Taxa: {fmt_money(fee or 0, settings_service.get('currency', 'R$'))}" if fee is not None else "")

    def _lookup_customer_cep(self):
        cep = only_digits(self.c_cep.text())
        if len(cep) != 8:
            return
        data = brazil_api_service.fetch_cep(self.c_cep.text())
        if not data:
            QMessageBox.warning(self, "Busca CEP", "Não foi possível consultar o CEP.")
            return
        self.c_cep.setText(data["cep"])
        self.c_address.setText(data["address"])
        self.c_neighborhood.setCurrentText(data["neighborhood"])
        self.c_city.setText(data["city"])
        self.c_state.setText(data["state"])

    def _customer_form(self, c):
        from PySide6.QtWidgets import QDialog, QFormLayout
        dlg = QDialog(self)
        dlg.setWindowTitle("Novo Cliente" if not c else f"Editar Cliente #{c['id']}")
        dlg.setMinimumWidth(520)
        form = QFormLayout(dlg)
        form.setSpacing(9)

        codigo = QLabel("automático" if not c else str(c["id"]))
        codigo.setStyleSheet("font-weight: 800; color: #ea580c;")
        name = QLineEdit(c["name"] or "" if c else "")
        doc = QLineEdit(c["document"] or "" if c else "")
        doc.setPlaceholderText("CNPJ / CPF")
        phone = QLineEdit(c["phone"] or "" if c else "")
        email = QLineEdit(c["email"] or "" if c else "")
        cep = QLineEdit(c["cep"] or "" if c else "")
        cep.setPlaceholderText("00000-000")
        self.c_doc, self.c_phone = doc, phone
        self.c_email, self.c_cep = email, cep
        address = QLineEdit(c["address"] or "" if c else "")
        neighborhood = QComboBox()
        neighborhood.setEditable(True)
        neighborhood.setInsertPolicy(QComboBox.NoInsert)
        neighborhood.addItem("— Bairro —")
        for n in neighborhood_service.list_all():
            neighborhood.addItem(n["name"])
            neighborhood.setItemData(neighborhood.count() - 1, n)
        self.c_bairro_taxa = QLabel("")
        self.c_bairro_taxa.setProperty("muted", True)
        self.c_neighborhood = neighborhood
        neighborhood.currentTextChanged.connect(self._c_bairro_sync)
        if c and c["neighborhood"]:
            neighborhood.setCurrentText(c["neighborhood"])
        city = QLineEdit(c["city"] or "" if c else "")
        state = QLineEdit(c["state"] or "" if c else "")
        state.setMaxLength(2)
        notes = QLineEdit(c["notes"] or "" if c else "")
        self.c_name, self.c_address = name, address
        self.c_city = city
        self.c_state = state

        buscar = QPushButton("Buscar na Receita")
        buscar.clicked.connect(self._lookup_customer_doc)
        doc_row = QHBoxLayout()
        doc_row.addWidget(doc)
        doc_row.addWidget(buscar)
        cep_row = QHBoxLayout()
        bcep = QPushButton("Buscar CEP")
        bcep.clicked.connect(self._lookup_customer_cep)
        cep_row.addWidget(cep)
        cep_row.addWidget(bcep)

        form.addRow("Código", codigo)
        form.addRow("Nome", name)
        form.addRow("Documento", doc_row)
        form.addRow("Telefone", phone)
        form.addRow("E-mail", email)
        form.addRow("CEP", cep_row)
        form.addRow("Endereço", address)
        bairro_row = QHBoxLayout()
        bairro_row.addWidget(neighborhood, 1)
        bairro_row.addWidget(self.c_bairro_taxa)
        form.addRow("Bairro", bairro_row)
        form.addRow("Cidade", city)
        form.addRow("UF", state)
        form.addRow("Observações", notes)

        bts = QHBoxLayout()
        save = QPushButton("Salvar")
        save.setProperty("primary", True)
        cancel = QPushButton("Cancelar")
        cancel.clicked.connect(dlg.reject)
        bts.addWidget(cancel)
        bts.addStretch()
        bts.addWidget(save)

        def on_save():
            if not name.text().strip():
                QMessageBox.warning(dlg, "Validação", "Informe o nome do cliente.")
                return
            dlg.accept()
        save.clicked.connect(on_save)
        form.addRow(bts)
        name.setFocus()
        if not dlg.exec():
            return
        entity = "PJ" if len(only_digits(doc.text())) == 14 else "PF"
        if not c:
            customer_service.add(name.text().strip(), phone.text().strip(), address.text().strip(),
                                 notes.text().strip(), doc.text().strip(), cep.text().strip(),
                                 email.text().strip(), entity, city.text().strip(),
                                 state.text().strip(), neighborhood.currentText().strip())
        else:
            customer_service.update(c["id"], name.text().strip(), phone.text().strip(),
                                    address.text().strip(), notes.text().strip(), doc.text().strip(),
                                    cep.text().strip(), email.text().strip(), entity,
                                    city.text().strip(), state.text().strip(),
                                    neighborhood.currentText().strip())
        self._customers_reload()

    def _customer_inativar(self):
        c = self._selected_customer()
        if not c:
            return
        acao = "Inativar" if c["is_active"] else "Reativar"
        if QMessageBox.question(self, acao, f"{acao} o cliente {c['name']}?") == QMessageBox.Yes:
            customer_service.set_active(c["id"], not c["is_active"])
            self.refresh_customers()

    def _customer_ficha(self):
        c = self._selected_customer()
        if not c:
            return
        from PySide6.QtWidgets import QDialog, QFormLayout
        dlg = QDialog(self)
        dlg.setWindowTitle(f"Ficha do Cliente · {c['name']}")
        dlg.resize(860, 560)
        outer = QVBoxLayout(dlg)
        tabs = QTabWidget()

        dados = QWidget()
        dl = QVBoxLayout(dados)
        form = QFormLayout()
        for label, value in [
            ("Código", str(c["id"])),
            ("Nome", c["name"]),
            ("Telefone", c["phone"] or "—"),
            ("Documento", c["document"] or "—"),
            ("E-mail", c["email"] or "—"),
            ("CEP", c["cep"] or "—"),
            ("Endereço", c["address"] or "—"),
            ("Bairro", c["neighborhood"] or "—"),
            ("Cidade/UF", f"{c['city']}/{c['state']}".strip("/ ") or "—"),
            ("Observações", c["notes"] or "—"),
            ("Situação", "Ativo" if c["is_active"] else "Inativo"),
            ("Cadastrado em", c["created_at"] or "—"),
        ]:
            v = QLabel(str(value))
            v.setTextInteractionFlags(Qt.TextSelectableByMouse)
            form.addRow(label + ":", v)
        dl.addLayout(form)
        dl.addStretch()
        tabs.addTab(dados, "Dados do Cliente")

        hist = QWidget()
        hl = QVBoxLayout(hist)
        hist_table = QTableWidget(0, 7)
        hist_table.setHorizontalHeaderLabels(
            ["Nº Pedido", "Data", "Tipo", "Mesa", "Status", "Pagamento", "Total"])
        self._style_aux_table(hist_table)
        hist_table.horizontalHeader().setStretchLastSection(True)
        orders = order_service.list_by_customer(c["id"])
        hist_table.setRowCount(len(orders))
        for i, o in enumerate(orders):
            hist_table.setItem(i, 0, QTableWidgetItem(o["order_number"] or ""))
            hist_table.setItem(i, 1, QTableWidgetItem(o["created_at"] or ""))
            hist_table.setItem(i, 2, QTableWidgetItem(TIPO_ORDER.get(o["order_type"], o["order_type"])))
            hist_table.setItem(i, 3, QTableWidgetItem(o["table_no"] or "—"))
            hist_table.setItem(i, 4, QTableWidgetItem(STATUS_ORDER.get(o["status"], o["status"])))
            hist_table.setItem(i, 5, QTableWidgetItem(o["payment_method"] or ""))
            hist_table.setItem(i, 6, QTableWidgetItem(f"{float(o['total'] or 0):.2f}"))
        hist_table.resizeColumnsToContents()
        hl.addWidget(hist_table, 1)
        total_gasto = sum(float(o["total"] or 0) for o in orders if o["status"] == "paid")
        resumo = QLabel(
            f"{len(orders)} pedido(s) · Total em vendas pagas: {settings_service.get('currency', 'R$')} {total_gasto:.2f}")
        resumo.setObjectName("CardTitle")
        hl.addWidget(resumo)
        tabs.addTab(hist, "Histórico de Pedidos")

        outer.addWidget(tabs, 1)
        bts = QHBoxLayout()
        fechar = QPushButton("Fechar")
        fechar.setProperty("primary", True)
        fechar.clicked.connect(dlg.accept)
        bts.addStretch()
        bts.addWidget(fechar)
        outer.addLayout(bts)
        dlg.exec()

    def _delete_customer(self):
        c = self._selected_customer()
        if not c:
            return
        if QMessageBox.question(self, "Excluir", f"Excluir o cliente {c['name']}?") == QMessageBox.Yes:
            customer_service.delete(c["id"])
            self._customers_reload()

    # ---------------- Suppliers ----------------
    def _build_suppliers_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setSpacing(10)

        search_row = QHBoxLayout()
        search_row.addWidget(QLabel("Buscar:"))
        self.s_search = QLineEdit()
        self.s_search.setPlaceholderText("Nome, telefone, CNPJ ou e-mail...")
        self.s_search.setMaximumWidth(300)
        self.s_search.textChanged.connect(self._suppliers_reload)
        search_row.addWidget(self.s_search)
        self.s_show_inactive = QCheckBox("Mostrar inativos")
        self.s_show_inactive.toggled.connect(self._suppliers_reload)
        search_row.addWidget(self.s_show_inactive)
        search_row.addStretch()
        self.s_prev = QPushButton("◀  Anterior")
        self.s_info = QLabel("Página 1 de 1")
        self.s_next = QPushButton("Próxima  ▶")
        self.s_prev.clicked.connect(self._supp_page_back)
        self.s_next.clicked.connect(self._supp_page_next)
        search_row.addWidget(self.s_prev)
        search_row.addWidget(self.s_info)
        search_row.addWidget(self.s_next)
        lay.addLayout(search_row)

        self.suppliers_table = QTableWidget(0, 8)
        self.suppliers_table.setHorizontalHeaderLabels(
            ["Código", "Nome", "Telefone", "CNPJ", "E-mail", "Cidade/UF", "Bairro", "Ativo"])
        self._style_aux_table(self.suppliers_table)
        lay.addWidget(self.suppliers_table, 1)

        self._supp_page = 1
        self._supp_rows = []
        btn_row = QHBoxLayout()
        novo = QPushButton("+  Novo")
        novo.setProperty("primary", True)
        novo.clicked.connect(self._supplier_novo)
        edit = QPushButton("Editar")
        edit.clicked.connect(self._supplier_editar)
        inativar = QPushButton("Inativar")
        inativar.clicked.connect(self._supplier_inativar)
        delete = QPushButton("Excluir")
        delete.setProperty("danger", True)
        delete.clicked.connect(self._delete_supplier)
        btn_row.addWidget(novo)
        btn_row.addWidget(edit)
        btn_row.addWidget(inativar)
        btn_row.addStretch()
        btn_row.addWidget(delete)
        lay.addLayout(btn_row)
        self.refresh_suppliers()
        bind_table_keys(self.suppliers_table, on_enter=self._supplier_editar,
                        on_delete=self._delete_supplier)
        return w

    def refresh_suppliers(self):
        term = getattr(self, "s_search", None)
        term = term.text().strip() if term else ""
        show_inactive = getattr(self, "s_show_inactive", None)
        include_inactive = bool(show_inactive and show_inactive.isChecked())
        rows = supplier_service.search(term, include_inactive=include_inactive)
        self._supp_rows = rows
        total = len(rows)
        pages = max(1, (total + AUX_PAGE_SIZE - 1) // AUX_PAGE_SIZE) if total else 1
        page = getattr(self, "_supp_page", 1)
        if page > pages:
            page = pages
        self._supp_page = page
        start = (page - 1) * AUX_PAGE_SIZE
        page_rows = rows[start:start + AUX_PAGE_SIZE]
        self.suppliers_table.setRowCount(len(page_rows))
        for i, s in enumerate(page_rows):
            self.suppliers_table.setItem(i, 0, QTableWidgetItem(str(s["id"])))
            self.suppliers_table.setItem(i, 1, QTableWidgetItem(s["name"]))
            self.suppliers_table.setItem(i, 2, QTableWidgetItem(s["phone"] or ""))
            self.suppliers_table.setItem(i, 3, QTableWidgetItem(s["document"] or ""))
            self.suppliers_table.setItem(i, 4, QTableWidgetItem(s["email"] or ""))
            uf = f"{s['city']}/{s['state']}".strip("/ ")
            self.suppliers_table.setItem(i, 5, QTableWidgetItem(uf))
            self.suppliers_table.setItem(i, 6, QTableWidgetItem(s["neighborhood"] or ""))
            self.suppliers_table.setItem(i, 7, QTableWidgetItem("Sim" if s["is_active"] else "Não"))
        self.suppliers_table.resizeColumnsToContents()
        self.s_prev.setEnabled(page > 1)
        self.s_next.setEnabled(page < pages)
        self.s_info.setText(f"Página {page} de {pages}  ({total} fornecedores)")

    def _suppliers_reload(self):
        self._supp_page = 1
        self.refresh_suppliers()

    def _supp_page_back(self):
        if self._supp_page > 1:
            self._supp_page -= 1
            self.refresh_suppliers()

    def _supp_page_next(self):
        total = len(self._supp_rows)
        pages = max(1, (total + AUX_PAGE_SIZE - 1) // AUX_PAGE_SIZE) if total else 1
        if self._supp_page < pages:
            self._supp_page += 1
            self.refresh_suppliers()

    def _selected_supplier(self):
        row = self.suppliers_table.currentRow()
        if row < 0:
            return None
        start = (self._supp_page - 1) * AUX_PAGE_SIZE + row
        if start >= len(self._supp_rows):
            return None
        return self._supp_rows[start]

    def _supplier_novo(self):
        self._supplier_form(None)

    def _supplier_editar(self):
        s = self._selected_supplier()
        if not s:
            return
        self._supplier_form(s)

    def _lookup_supplier_doc(self):
        doc = only_digits(self.s_doc.text())
        if len(doc) == 14:
            data = brazil_api_service.fetch_cnpj(self.s_doc.text())
            if not data:
                QMessageBox.warning(self, "Busca CNPJ", "Não foi possível consultar o CNPJ.")
                return
            self.s_name.setText(data["name"])
            self.s_doc.setText(data["document"])
            self.s_address.setText(data["address"])
            self.s_neighborhood.setText(data["neighborhood"])
            self.s_city.setText(data["city"])
            self.s_state.setText(data["state"])
            self.s_cep.setText(data["cep"])
            if not self.s_phone.text():
                self.s_phone.setText(data["phone"])
            if not self.s_email.text():
                self.s_email.setText(data["email"])
        elif doc:
            QMessageBox.warning(self, "CNPJ", "Digite um CNPJ com 14 dígitos.")

    def _lookup_supplier_cep(self):
        cep = only_digits(self.s_cep.text())
        if len(cep) != 8:
            return
        data = brazil_api_service.fetch_cep(self.s_cep.text())
        if not data:
            QMessageBox.warning(self, "Busca CEP", "Não foi possível consultar o CEP.")
            return
        self.s_cep.setText(data["cep"])
        self.s_address.setText(data["address"])
        self.s_neighborhood.setText(data["neighborhood"])
        self.s_city.setText(data["city"])
        self.s_state.setText(data["state"])

    def _supplier_form(self, s):
        from PySide6.QtWidgets import QDialog, QFormLayout
        dlg = QDialog(self)
        dlg.setWindowTitle("Novo Fornecedor" if not s else f"Editar Fornecedor #{s['id']}")
        dlg.setMinimumWidth(520)
        form = QFormLayout(dlg)
        form.setSpacing(9)

        codigo = QLabel("automático" if not s else str(s["id"]))
        codigo.setStyleSheet("font-weight: 800; color: #ea580c;")
        name = QLineEdit(s["name"] or "" if s else "")
        doc = QLineEdit(s["document"] or "" if s else "")
        doc.setPlaceholderText("CNPJ")
        phone = QLineEdit(s["phone"] or "" if s else "")
        email = QLineEdit(s["email"] or "" if s else "")
        cep = QLineEdit(s["cep"] or "" if s else "")
        cep.setPlaceholderText("00000-000")
        self.s_doc, self.s_phone = doc, phone
        self.s_email, self.s_cep = email, cep
        address = QLineEdit(s["address"] or "" if s else "")
        neighborhood = QLineEdit(s["neighborhood"] or "" if s else "")
        city = QLineEdit(s["city"] or "" if s else "")
        state = QLineEdit(s["state"] or "" if s else "")
        state.setMaxLength(2)
        notes = QLineEdit(s["notes"] or "" if s else "")
        self.s_name, self.s_address = name, address
        self.s_neighborhood, self.s_city = neighborhood, city
        self.s_state = state

        buscar = QPushButton("Buscar na Receita")
        buscar.clicked.connect(self._lookup_supplier_doc)
        doc_row = QHBoxLayout()
        doc_row.addWidget(doc)
        doc_row.addWidget(buscar)
        cep_row = QHBoxLayout()
        bcep = QPushButton("Buscar CEP")
        bcep.clicked.connect(self._lookup_supplier_cep)
        cep_row.addWidget(cep)
        cep_row.addWidget(bcep)

        form.addRow("Código", codigo)
        form.addRow("Nome", name)
        form.addRow("CNPJ", doc_row)
        form.addRow("Telefone", phone)
        form.addRow("E-mail", email)
        form.addRow("CEP", cep_row)
        form.addRow("Endereço", address)
        form.addRow("Bairro", neighborhood)
        form.addRow("Cidade", city)
        form.addRow("UF", state)
        form.addRow("Observações", notes)

        bts = QHBoxLayout()
        save = QPushButton("Salvar")
        save.setProperty("primary", True)
        cancel = QPushButton("Cancelar")
        cancel.clicked.connect(dlg.reject)
        bts.addWidget(cancel)
        bts.addStretch()
        bts.addWidget(save)

        def on_save():
            if not name.text().strip():
                QMessageBox.warning(dlg, "Validação", "Informe o nome do fornecedor.")
                return
            dlg.accept()
        save.clicked.connect(on_save)
        form.addRow(bts)
        name.setFocus()
        if not dlg.exec():
            return
        if not s:
            supplier_service.add(name.text().strip(), phone.text().strip(), doc.text().strip(),
                                 cep.text().strip(), email.text().strip(), address.text().strip(),
                                 city.text().strip(), state.text().strip(), neighborhood.text().strip())
        else:
            supplier_service.update(s["id"], name.text().strip(), phone.text().strip(),
                                    doc.text().strip(), cep.text().strip(), email.text().strip(),
                                    address.text().strip(), city.text().strip(), state.text().strip(),
                                    neighborhood.text().strip(), notes.text().strip(),
                                    bool(s["is_active"]))
        self._suppliers_reload()

    def _supplier_inativar(self):
        s = self._selected_supplier()
        if not s:
            return
        acao = "Inativar" if s["is_active"] else "Reativar"
        if QMessageBox.question(self, acao, f"{acao} o fornecedor {s['name']}?") == QMessageBox.Yes:
            supplier_service.update(s["id"], s["name"], s["phone"], s["document"], s["cep"],
                                    s["email"], s["address"], s["city"], s["state"],
                                    s["neighborhood"], s["notes"], not s["is_active"])
            self.refresh_suppliers()

    def _delete_supplier(self):
        s = self._selected_supplier()
        if not s:
            return
        if QMessageBox.question(self, "Excluir", f"Excluir o fornecedor {s['name']}?") == QMessageBox.Yes:
            supplier_service.delete(s["id"])
            self._suppliers_reload()

    # ---------------- Neighborhoods ----------------
    def _build_neighborhoods_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setSpacing(10)
        form_row = QHBoxLayout()
        form_row.addWidget(QLabel("Nome:"))
        self.n_name = QLineEdit()
        self.n_name.setFixedWidth(180)
        form_row.addWidget(self.n_name)
        form_row.addWidget(QLabel("Taxa de Entrega:"))
        self.n_fee = QDoubleSpinBox()
        self.n_fee.setRange(0, 100000)
        self.n_fee.setDecimals(2)
        self.n_fee.setPrefix(settings_service.get("currency", "R$") + " ")
        self.n_fee.setFixedWidth(110)
        form_row.addWidget(self.n_fee)
        add = QPushButton("+  Adicionar Bairro")
        add.setProperty("primary", True)
        add.clicked.connect(self._add_neighborhood)
        form_row.addWidget(add)
        form_row.addStretch()
        lay.addLayout(form_row)

        self.neighborhoods_table = QTableWidget(0, 4)
        self.neighborhoods_table.setHorizontalHeaderLabels(["ID", "Nome", "Taxa de Entrega", "Ativo"])
        self.neighborhoods_table.verticalHeader().setVisible(False)
        self.neighborhoods_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.neighborhoods_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.neighborhoods_table.setSelectionMode(QTableWidget.SingleSelection)
        self.neighborhoods_table.horizontalHeader().setStretchLastSection(True)
        lay.addWidget(self.neighborhoods_table, 1)

        row_btns = QHBoxLayout()
        edit = QPushButton("Editar")
        edit.clicked.connect(self._edit_neighborhood)
        toggle = QPushButton("Ativar / Desativar")
        toggle.clicked.connect(self._toggle_neighborhood)
        delete = QPushButton("Excluir")
        delete.setProperty("danger", True)
        delete.clicked.connect(self._delete_neighborhood)
        row_btns.addStretch()
        row_btns.addWidget(edit)
        row_btns.addWidget(toggle)
        row_btns.addWidget(delete)
        lay.addLayout(row_btns)
        self.refresh_neighborhoods()
        bind_table_keys(self.neighborhoods_table, on_enter=self._edit_neighborhood, on_delete=self._delete_neighborhood)
        return w

    def refresh_neighborhoods(self):
        neighborhoods = neighborhood_service.list_all()
        self.neighborhoods_table.setRowCount(len(neighborhoods))
        for i, n in enumerate(neighborhoods):
            self.neighborhoods_table.setItem(i, 0, QTableWidgetItem(str(n["id"])))
            self.neighborhoods_table.setItem(i, 1, QTableWidgetItem(n["name"]))
            self.neighborhoods_table.setItem(i, 2, QTableWidgetItem(f"{n['delivery_fee']:g}"))
            self.neighborhoods_table.setItem(i, 3, QTableWidgetItem("Sim" if n["is_active"] else "Não"))
        self.neighborhoods_table.resizeColumnsToContents()

    def _selected_neighborhood(self):
        row = self.neighborhoods_table.currentRow()
        if row < 0:
            return None
        neighborhoods = neighborhood_service.list_all()
        if row >= len(neighborhoods):
            return None
        return neighborhoods[row]

    def _add_neighborhood(self):
        name = self.n_name.text().strip()
        if not name:
            return
        neighborhood_service.add(name, self.n_fee.value())
        self.n_name.clear()
        self.n_fee.setValue(0)
        self.refresh_neighborhoods()

    def _edit_neighborhood(self):
        n = self._selected_neighborhood()
        if not n:
            return
        from PySide6.QtWidgets import QDialog, QFormLayout
        currency = settings_service.get("currency", "R$")
        dlg = QDialog(self)
        dlg.setWindowTitle(f"Editar Bairro · {n['name']}")
        form = QFormLayout(dlg)
        name = QLineEdit(n["name"])
        fee = QDoubleSpinBox()
        fee.setRange(0, 100000)
        fee.setDecimals(2)
        fee.setPrefix(currency + " ")
        fee.setValue(float(n["delivery_fee"] or 0))
        active = QCheckBox("Bairro ativo (aparece no balcão/entrega)")
        active.setChecked(bool(n["is_active"]))
        form.addRow("Nome", name)
        form.addRow("Taxa de Entrega", fee)
        form.addRow("", active)
        bts = QHBoxLayout()
        save = QPushButton("Salvar")
        save.setProperty("primary", True)
        cancel = QPushButton("Cancelar")
        cancel.clicked.connect(dlg.reject)
        bts.addWidget(cancel)
        bts.addStretch()
        bts.addWidget(save)
        form.addRow(bts)
        name.setFocus()
        name.selectAll()

        def on_save():
            if not name.text().strip():
                QMessageBox.warning(dlg, "Validação", "Informe o nome do bairro.")
                return
            dlg.accept()
        save.clicked.connect(on_save)
        if not dlg.exec():
            return
        neighborhood_service.update(
            n["id"], name.text().strip(), fee.value(), active.isChecked())
        self.refresh_neighborhoods()

    def _toggle_neighborhood(self):
        n = self._selected_neighborhood()
        if not n:
            return
        neighborhood_service.update(n["id"], n["name"], n["delivery_fee"], not n["is_active"])
        self.refresh_neighborhoods()

    def _delete_neighborhood(self):
        n = self._selected_neighborhood()
        if not n:
            return
        if QMessageBox.question(self, "Excluir", f"Excluir o bairro {n['name']}?") == QMessageBox.Yes:
            neighborhood_service.delete(n["id"])
            self.refresh_neighborhoods()

    # ---------------- Riders (Entregadores = Motoqueiros) ----------------
    def _build_riders_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setSpacing(10)
        form_row = QHBoxLayout()
        form_row.addWidget(QLabel("Nome:"))
        self.r_name = QLineEdit()
        self.r_name.setFixedWidth(180)
        form_row.addWidget(self.r_name)
        form_row.addWidget(QLabel("Telefone:"))
        self.r_phone = QLineEdit()
        self.r_phone.setFixedWidth(150)
        form_row.addWidget(self.r_phone)
        hint = QLabel("Entregadores são os motoqueiros que fazem as entregas.")
        hint.setProperty("muted", True)
        form_row.addWidget(hint)
        add = QPushButton("+  Adicionar Entregador")
        add.setProperty("primary", True)
        add.clicked.connect(self._add_rider)
        form_row.addWidget(add)
        form_row.addStretch()
        lay.addLayout(form_row)

        self.riders_table = QTableWidget(0, 4)
        self.riders_table.setHorizontalHeaderLabels(["ID", "Nome", "Papel", "Telefone"])
        self.riders_table.verticalHeader().setVisible(False)
        self.riders_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.riders_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.riders_table.setSelectionMode(QTableWidget.SingleSelection)
        self.riders_table.horizontalHeader().setStretchLastSection(True)
        lay.addWidget(self.riders_table, 1)

        row_btns = QHBoxLayout()
        edit = QPushButton("Editar")
        edit.clicked.connect(self._edit_rider)
        delete = QPushButton("Excluir")
        delete.setProperty("danger", True)
        delete.clicked.connect(self._delete_rider)
        row_btns.addStretch()
        row_btns.addWidget(edit)
        row_btns.addWidget(delete)
        lay.addLayout(row_btns)
        self.refresh_riders()
        bind_table_keys(self.riders_table, on_enter=self._edit_rider, on_delete=self._delete_rider)
        return w

    def refresh_riders(self):
        riders = staff_service.list_riders()
        self.riders_table.setRowCount(len(riders))
        for i, s in enumerate(riders):
            self.riders_table.setItem(i, 0, QTableWidgetItem(str(s["id"])))
            self.riders_table.setItem(i, 1, QTableWidgetItem(s["name"]))
            self.riders_table.setItem(i, 2, QTableWidgetItem("Entregador"))
            self.riders_table.setItem(i, 3, QTableWidgetItem(s["phone"] or ""))
        self.riders_table.resizeColumnsToContents()

    def _selected_rider(self):
        row = self.riders_table.currentRow()
        if row < 0:
            return None
        riders = staff_service.list_riders()
        if row >= len(riders):
            return None
        return riders[row]

    def _add_rider(self):
        name = self.r_name.text().strip()
        if not name:
            return
        staff_service.add(name, "Entregador", self.r_phone.text().strip())
        self.r_name.clear()
        self.r_phone.clear()
        self.refresh_riders()

    def _edit_rider(self):
        s = self._selected_rider()
        if not s:
            return
        name, ok1 = QInputDialog.getText(self, "Editar Entregador", "Nome:", text=s["name"])
        if not ok1:
            return
        phone, ok2 = QInputDialog.getText(self, "Editar Entregador", "Telefone:", text=s["phone"] or "")
        if not ok2:
            return
        staff_service.update(s["id"], name.strip(), "Entregador", phone.strip(), True)
        self.refresh_riders()

    def _delete_rider(self):
        s = self._selected_rider()
        if not s:
            return
        if QMessageBox.question(self, "Excluir", f"Excluir o entregador {s['name']}?") == QMessageBox.Yes:
            staff_service.delete(s["id"])
            self.refresh_riders()

    # ---------------- Payment Methods ----------------
    def _build_payments_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setSpacing(10)
        form_row = QHBoxLayout()
        form_row.addWidget(QLabel("Nome:"))
        self.p_name = QLineEdit()
        self.p_name.setFixedWidth(180)
        self.p_name.setPlaceholderText("Ex.: Pix, Cartão, Dinheiro...")
        form_row.addWidget(self.p_name)
        add = QPushButton("+  Adicionar Forma de Pagamento")
        add.setProperty("primary", True)
        add.clicked.connect(self._add_payment)
        form_row.addWidget(add)
        form_row.addStretch()
        lay.addLayout(form_row)

        self.payments_table = QTableWidget(0, 3)
        self.payments_table.setHorizontalHeaderLabels(["ID", "Nome", "Ativo"])
        self.payments_table.verticalHeader().setVisible(False)
        self.payments_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.payments_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.payments_table.setSelectionMode(QTableWidget.SingleSelection)
        self.payments_table.horizontalHeader().setStretchLastSection(True)
        lay.addWidget(self.payments_table, 1)

        row_btns = QHBoxLayout()
        edit = QPushButton("Editar")
        edit.clicked.connect(self._edit_payment)
        toggle = QPushButton("Ativar / Desativar")
        toggle.clicked.connect(self._toggle_payment)
        delete = QPushButton("Excluir")
        delete.setProperty("danger", True)
        delete.clicked.connect(self._delete_payment)
        row_btns.addStretch()
        row_btns.addWidget(edit)
        row_btns.addWidget(toggle)
        row_btns.addWidget(delete)
        lay.addLayout(row_btns)
        self.refresh_payments()
        bind_table_keys(self.payments_table, on_enter=self._edit_payment, on_delete=self._delete_payment)
        return w

    def refresh_payments(self):
        methods = payment_service.list_all()
        self.payments_table.setRowCount(len(methods))
        for i, m in enumerate(methods):
            self.payments_table.setItem(i, 0, QTableWidgetItem(str(m["id"])))
            self.payments_table.setItem(i, 1, QTableWidgetItem(m["name"]))
            self.payments_table.setItem(i, 2, QTableWidgetItem("Sim" if m["is_active"] else "Não"))
        self.payments_table.resizeColumnsToContents()

    def _selected_payment(self):
        row = self.payments_table.currentRow()
        if row < 0:
            return None
        methods = payment_service.list_all()
        if row >= len(methods):
            return None
        return methods[row]

    def _add_payment(self):
        name = self.p_name.text().strip()
        if not name:
            return
        payment_service.add(name)
        self.p_name.clear()
        self.refresh_payments()

    def _edit_payment(self):
        m = self._selected_payment()
        if not m:
            return
        name, ok = QInputDialog.getText(self, "Editar Forma de Pagamento", "Nome:", text=m["name"])
        if ok and name.strip():
            payment_service.update(m["id"], name.strip(), bool(m["is_active"]))
            self.refresh_payments()

    def _toggle_payment(self):
        m = self._selected_payment()
        if not m:
            return
        payment_service.update(m["id"], m["name"], not m["is_active"])
        self.refresh_payments()

    def _delete_payment(self):
        m = self._selected_payment()
        if not m:
            return
        try:
            payment_service.delete(m["id"])
            self.refresh_payments()
        except ValueError as e:
            QMessageBox.warning(self, "Não é Possível Excluir", str(e))

    # ---------------- Plano de Contas ----------------
    def _build_chart_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setSpacing(10)
        form_row = QHBoxLayout()
        form_row.addWidget(QLabel("Código:"))
        self.ac_code = QLineEdit()
        self.ac_code.setFixedWidth(90)
        self.ac_code.setPlaceholderText("Ex.: 1.1")
        form_row.addWidget(self.ac_code)
        form_row.addWidget(QLabel("Nome:"))
        self.ac_name = QLineEdit()
        self.ac_name.setFixedWidth(200)
        self.ac_name.setPlaceholderText("Ex.: Vendas de Café")
        form_row.addWidget(self.ac_name)
        self.ac_type = QComboBox()
        self.ac_type.addItem("Entrada (Receita)", "entrada")
        self.ac_type.addItem("Saída (Despesa)", "saida")
        form_row.addWidget(self.ac_type)
        add = QPushButton("+  Adicionar Conta")
        add.setProperty("primary", True)
        add.clicked.connect(self._add_chart)
        form_row.addWidget(add)
        form_row.addStretch()
        lay.addLayout(form_row)

        self.chart_table = QTableWidget(0, 4)
        self.chart_table.setHorizontalHeaderLabels(["Código", "Nome", "Tipo", "Ativo"])
        self.chart_table.verticalHeader().setVisible(False)
        self.chart_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.chart_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.chart_table.setSelectionMode(QTableWidget.SingleSelection)
        self.chart_table.horizontalHeader().setStretchLastSection(True)
        lay.addWidget(self.chart_table, 1)

        row_btns = QHBoxLayout()
        edit = QPushButton("Editar")
        edit.clicked.connect(self._edit_chart)
        toggle = QPushButton("Ativar / Desativar")
        toggle.clicked.connect(self._toggle_chart)
        delete = QPushButton("Excluir")
        delete.setProperty("danger", True)
        delete.clicked.connect(self._delete_chart)
        row_btns.addStretch()
        row_btns.addWidget(edit)
        row_btns.addWidget(toggle)
        row_btns.addWidget(delete)
        lay.addLayout(row_btns)
        self.refresh_chart()
        bind_table_keys(self.chart_table, on_enter=self._edit_chart, on_delete=self._delete_chart)
        return w

    def refresh_chart(self):
        tipo_lbl = {"entrada": "Entrada", "saida": "Saída"}
        rows = chart_account_service.list_all()
        self.chart_table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            self.chart_table.setItem(i, 0, QTableWidgetItem(r["code"] or "—"))
            self.chart_table.setItem(i, 1, QTableWidgetItem(r["name"]))
            self.chart_table.setItem(i, 2, QTableWidgetItem(tipo_lbl.get(r["type"], r["type"])))
            self.chart_table.setItem(i, 3, QTableWidgetItem("Sim" if r["is_active"] else "Não"))
        self.chart_table.resizeColumnsToContents()

    def _selected_chart(self):
        row = self.chart_table.currentRow()
        if row < 0:
            return None
        rows = chart_account_service.list_all()
        if row >= len(rows):
            return None
        return rows[row]

    def _add_chart(self):
        name = self.ac_name.text().strip()
        if not name:
            QMessageBox.information(self, "Plano de Contas", "Informe o nome da conta.")
            return
        try:
            chart_account_service.add(name, self.ac_code.text().strip(), self.ac_type.currentData())
        except ValueError as e:
            QMessageBox.warning(self, "Validação", str(e))
            return
        self.ac_name.clear()
        self.ac_code.clear()
        self.refresh_chart()

    def _edit_chart(self):
        c = self._selected_chart()
        if not c:
            return
        name, ok = QInputDialog.getText(self, "Editar Conta", "Nome:", text=c["name"])
        if ok and name.strip():
            code, ok2 = QInputDialog.getText(self, "Editar Conta", "Código:", text=c["code"])
            if ok2:
                type_lbl = ["Entrada (Receita)", "Saída (Despesa)"]
                inicio = 0 if c["type"] == "entrada" else 1
                tipo, ok3 = QInputDialog.getItem(self, "Editar Conta", "Tipo:", type_lbl, inicio, False)
                if ok3:
                    tkey = "entrada" if tipo.startswith("Entrada") else "saida"
                    chart_account_service.update(c["id"], name.strip(), code.strip(), tkey, bool(c["is_active"]))
                    self.refresh_chart()

    def _toggle_chart(self):
        c = self._selected_chart()
        if not c:
            return
        chart_account_service.update(c["id"], c["name"], c["code"], c["type"], not c["is_active"])
        self.refresh_chart()

    def _delete_chart(self):
        c = self._selected_chart()
        if not c:
            return
        try:
            chart_account_service.delete(c["id"])
            self.refresh_chart()
        except ValueError as e:
            QMessageBox.warning(self, "Não é Possível Excluir", str(e))

    # ---------------- Categories ----------------
    def _build_categories_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setSpacing(10)
        form_row = QHBoxLayout()
        form_row.addWidget(QLabel("Nome:"))
        self.cat_name = QLineEdit()
        self.cat_name.setFixedWidth(200)
        form_row.addWidget(self.cat_name)
        add = QPushButton("+  Adicionar Categoria")
        add.setProperty("primary", True)
        add.clicked.connect(self._add_category)
        form_row.addWidget(add)
        form_row.addStretch()
        lay.addLayout(form_row)

        self.categories_table = QTableWidget(0, 2)
        self.categories_table.setHorizontalHeaderLabels(["ID", "Nome"])
        self.categories_table.verticalHeader().setVisible(False)
        self.categories_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.categories_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.categories_table.setSelectionMode(QTableWidget.SingleSelection)
        self.categories_table.horizontalHeader().setStretchLastSection(True)
        lay.addWidget(self.categories_table, 1)

        row_btns = QHBoxLayout()
        edit = QPushButton("Editar")
        edit.clicked.connect(self._edit_category)
        delete = QPushButton("Excluir")
        delete.setProperty("danger", True)
        delete.clicked.connect(self._delete_category)
        row_btns.addStretch()
        row_btns.addWidget(edit)
        row_btns.addWidget(delete)
        lay.addLayout(row_btns)
        self.refresh_categories()
        bind_table_keys(self.categories_table, on_enter=self._edit_category, on_delete=self._delete_category)
        return w

    def refresh_categories(self):
        cats = product_service.list_categories()
        self.categories_table.setRowCount(len(cats))
        for i, c in enumerate(cats):
            self.categories_table.setItem(i, 0, QTableWidgetItem(str(c["id"])))
            self.categories_table.setItem(i, 1, QTableWidgetItem(c["name"]))
        self.categories_table.resizeColumnsToContents()

    def _selected_category(self):
        row = self.categories_table.currentRow()
        if row < 0:
            return None
        cats = product_service.list_categories()
        if row >= len(cats):
            return None
        return cats[row]

    def _add_category(self):
        name = self.cat_name.text().strip()
        if not name:
            return
        product_service.add_category(name)
        self.cat_name.clear()
        self.refresh_categories()

    def _edit_category(self):
        c = self._selected_category()
        if not c:
            return
        name, ok = QInputDialog.getText(self, "Editar Categoria", "Nome:", text=c["name"])
        if ok and name.strip():
            product_service.update_category(c["id"], name.strip())
            self.refresh_categories()

    def _delete_category(self):
        c = self._selected_category()
        if not c:
            return
        try:
            product_service.delete_category(c["id"])
            self.refresh_categories()
        except ValueError as e:
            QMessageBox.warning(self, "Não é Possível Excluir", str(e))

    # ---------------- Add-ons ----------------
    def _build_addons_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setSpacing(10)
        form_row = QHBoxLayout()
        form_row.addWidget(QLabel("Nome:"))
        self.addon_name = QLineEdit()
        self.addon_name.setFixedWidth(220)
        self.addon_name.setPlaceholderText("Ex.: Ovo, Bacon, Queijo")
        form_row.addWidget(self.addon_name)
        form_row.addWidget(QLabel("Preco:"))
        self.addon_price = QDoubleSpinBox()
        self.addon_price.setRange(0, 100000)
        self.addon_price.setDecimals(2)
        self.addon_price.setPrefix(settings_service.get("currency", "R$") + " ")
        self.addon_price.setFixedWidth(130)
        form_row.addWidget(self.addon_price)
        add = QPushButton("+  Adicionar")
        add.setProperty("primary", True)
        add.clicked.connect(self._add_addon)
        form_row.addWidget(add)
        form_row.addStretch()
        lay.addLayout(form_row)

        self.addons_table = QTableWidget(0, 4)
        self.addons_table.setHorizontalHeaderLabels(["ID", "Nome", "Preco", "Ativo"])
        self._style_aux_table(self.addons_table)
        lay.addWidget(self.addons_table, 1)

        row_btns = QHBoxLayout()
        edit = QPushButton("Editar")
        edit.clicked.connect(self._edit_addon)
        toggle = QPushButton("Ativar / Desativar")
        toggle.clicked.connect(self._toggle_addon)
        delete = QPushButton("Excluir")
        delete.setProperty("danger", True)
        delete.clicked.connect(self._delete_addon)
        row_btns.addStretch()
        row_btns.addWidget(edit)
        row_btns.addWidget(toggle)
        row_btns.addWidget(delete)
        lay.addLayout(row_btns)
        self.refresh_addons()
        bind_table_keys(self.addons_table, on_enter=self._edit_addon, on_delete=self._delete_addon)
        return w

    def refresh_addons(self):
        rows = addon_service.list_all()
        self.addons_table.setRowCount(len(rows))
        currency = settings_service.get("currency", "R$")
        for i, addon in enumerate(rows):
            self.addons_table.setItem(i, 0, QTableWidgetItem(str(addon["id"])))
            self.addons_table.setItem(i, 1, QTableWidgetItem(addon["name"]))
            self.addons_table.setItem(i, 2, QTableWidgetItem(fmt_money(addon["price"], currency)))
            self.addons_table.setItem(i, 3, QTableWidgetItem("Sim" if addon["is_active"] else "Nao"))
        self.addons_table.resizeColumnsToContents()

    def _selected_addon(self):
        row = self.addons_table.currentRow()
        if row < 0:
            return None
        rows = addon_service.list_all()
        if row >= len(rows):
            return None
        return rows[row]

    def _add_addon(self):
        try:
            addon_service.add(self.addon_name.text().strip(), self.addon_price.value())
        except ValueError as e:
            QMessageBox.warning(self, "Adicionais", str(e))
            return
        self.addon_name.clear()
        self.addon_price.setValue(0)
        self.refresh_addons()

    def _edit_addon(self):
        addon = self._selected_addon()
        if not addon:
            return
        name, ok = QInputDialog.getText(self, "Editar Adicional", "Nome:", text=addon["name"])
        if not ok or not name.strip():
            return
        price, ok2 = QInputDialog.getDouble(
            self, "Editar Adicional", "Preco:", value=float(addon["price"] or 0), minValue=0, maxValue=100000, decimals=2)
        if not ok2:
            return
        addon_service.update(addon["id"], name.strip(), price, bool(addon["is_active"]), addon["sort_order"])
        self.refresh_addons()

    def _toggle_addon(self):
        addon = self._selected_addon()
        if not addon:
            return
        addon_service.update(addon["id"], addon["name"], addon["price"], not addon["is_active"], addon["sort_order"])
        self.refresh_addons()

    def _delete_addon(self):
        addon = self._selected_addon()
        if not addon:
            return
        try:
            addon_service.delete(addon["id"])
            self.refresh_addons()
        except ValueError as e:
            QMessageBox.warning(self, "Nao e Possivel Excluir", str(e))

    # ---------------- Staff ----------------
    def _build_staff_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setSpacing(10)
        form_row = QHBoxLayout()
        form_row.addWidget(QLabel("Nome:"))
        self.st_name = QLineEdit()
        self.st_name.setFixedWidth(160)
        form_row.addWidget(self.st_name)
        form_row.addWidget(QLabel("Papel:"))
        self.st_role = QComboBox()
        self.st_role.addItems(["Garçom", "Chefe de Sala", "Auxiliar", "Entregador"])
        form_row.addWidget(self.st_role)
        form_row.addWidget(QLabel("Telefone:"))
        self.st_phone = QLineEdit()
        self.st_phone.setFixedWidth(140)
        form_row.addWidget(self.st_phone)
        add = QPushButton("+  Adicionar Funcionário")
        add.setProperty("primary", True)
        add.clicked.connect(self._add_staff)
        form_row.addWidget(add)
        form_row.addStretch()
        lay.addLayout(form_row)

        self.staff_table = QTableWidget(0, 4)
        self.staff_table.setHorizontalHeaderLabels(["ID", "Nome", "Papel", "Telefone"])
        self.staff_table.verticalHeader().setVisible(False)
        self.staff_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.staff_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.staff_table.setSelectionMode(QTableWidget.SingleSelection)
        self.staff_table.horizontalHeader().setStretchLastSection(True)
        lay.addWidget(self.staff_table, 1)

        row_btns = QHBoxLayout()
        edit = QPushButton("Editar")
        edit.clicked.connect(self._edit_staff)
        delete = QPushButton("Excluir")
        delete.setProperty("danger", True)
        delete.clicked.connect(self._delete_staff)
        row_btns.addStretch()
        row_btns.addWidget(edit)
        row_btns.addWidget(delete)
        lay.addLayout(row_btns)
        self.refresh_staff()
        bind_table_keys(self.staff_table, on_enter=self._edit_staff, on_delete=self._delete_staff)
        return w

    def refresh_staff(self):
        staff = staff_service.list_all()
        self.staff_table.setRowCount(len(staff))
        for i, s in enumerate(staff):
            self.staff_table.setItem(i, 0, QTableWidgetItem(str(s["id"])))
            self.staff_table.setItem(i, 1, QTableWidgetItem(s["name"]))
            self.staff_table.setItem(i, 2, QTableWidgetItem(s["role"]))
            self.staff_table.setItem(i, 3, QTableWidgetItem(s["phone"] or ""))
        self.staff_table.resizeColumnsToContents()

    def _add_staff(self):
        if not self.st_name.text().strip():
            return
        staff_service.add(self.st_name.text().strip(), self.st_role.currentText(), self.st_phone.text().strip())
        self.st_name.clear()
        self.st_phone.clear()
        self.refresh_staff()

    def _edit_staff(self):
        row = self.staff_table.currentRow()
        if row < 0:
            return
        s = staff_service.list_all()[row]
        name, ok = QInputDialog.getText(self, "Editar Funcionário", "Nome:", text=s["name"])
        if not ok:
            return
        staff_service.update(s["id"], name.strip(), s["role"], s["phone"] or "", True)
        self.refresh_staff()

    def _delete_staff(self):
        row = self.staff_table.currentRow()
        if row < 0:
            return
        s = staff_service.list_all()[row]
        if QMessageBox.question(self, "Excluir", f"Excluir o funcionário {s['name']}?") == QMessageBox.Yes:
            staff_service.delete(s["id"])
            self.refresh_staff()

    # ---------------- Users ----------------
    def _build_users_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setSpacing(10)
        form_row = QHBoxLayout()
        form_row.addWidget(QLabel("Usuário:"))
        self.u_user = QLineEdit()
        self.u_user.setFixedWidth(130)
        form_row.addWidget(self.u_user)
        form_row.addWidget(QLabel("Senha:"))
        self.u_pass = QLineEdit()
        self.u_pass.setFixedWidth(130)
        self.u_pass.setEchoMode(QLineEdit.Password)
        form_row.addWidget(self.u_pass)
        form_row.addWidget(QLabel("Nome:"))
        self.u_name = QLineEdit()
        self.u_name.setFixedWidth(150)
        form_row.addWidget(self.u_name)
        form_row.addWidget(QLabel("Papel:"))
        self.u_role = QComboBox()
        self.u_role.addItems(list(ROLE_OPTIONS.values()))
        form_row.addWidget(self.u_role)
        add = QPushButton("+  Adicionar Usuário")
        add.setProperty("primary", True)
        add.clicked.connect(self._add_user)
        form_row.addWidget(add)
        form_row.addStretch()
        lay.addLayout(form_row)

        self.users_table = QTableWidget(0, 5)
        self.users_table.setHorizontalHeaderLabels(["ID", "Usuário", "Nome Completo", "Papel", "Ativo"])
        self.users_table.verticalHeader().setVisible(False)
        self.users_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.users_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.users_table.setSelectionMode(QTableWidget.SingleSelection)
        self.users_table.horizontalHeader().setStretchLastSection(True)
        lay.addWidget(self.users_table, 1)

        row_btns = QHBoxLayout()
        reset = QPushButton("Redefinir Senha")
        reset.clicked.connect(self._reset_password)
        toggle = QPushButton("Ativar / Desativar")
        toggle.clicked.connect(self._toggle_user)
        delete = QPushButton("Excluir")
        delete.setProperty("danger", True)
        delete.clicked.connect(self._delete_user)
        row_btns.addStretch()
        row_btns.addWidget(reset)
        row_btns.addWidget(toggle)
        row_btns.addWidget(delete)
        lay.addLayout(row_btns)
        self.refresh_users()
        bind_table_keys(self.users_table, on_delete=self._delete_user)
        return w

    def refresh_users(self):
        users = auth_service.list_users()
        self.users_table.setRowCount(len(users))
        for i, u in enumerate(users):
            self.users_table.setItem(i, 0, QTableWidgetItem(str(u["id"])))
            self.users_table.setItem(i, 1, QTableWidgetItem(u["username"]))
            self.users_table.setItem(i, 2, QTableWidgetItem(u["full_name"]))
            self.users_table.setItem(i, 3, QTableWidgetItem(ROLE_OPTIONS.get(u["role"], u["role"])))
            self.users_table.setItem(i, 4, QTableWidgetItem("Sim" if u["is_active"] else "Não"))
        self.users_table.resizeColumnsToContents()

    def _selected_user(self):
        row = self.users_table.currentRow()
        if row < 0:
            return None
        users = auth_service.list_users()
        if row >= len(users):
            return None
        return users[row]

    def _add_user(self):
        u = self.u_user.text().strip()
        p = self.u_pass.text()
        n = self.u_name.text().strip()
        if not u or not p:
            QMessageBox.warning(self, "Validação", "Usuário e senha são obrigatórios.")
            return
        try:
            auth_service.add_user(u, p, n or u, list(ROLE_OPTIONS)[self.u_role.currentIndex()])
            self.u_user.clear()
            self.u_pass.clear()
            self.u_name.clear()
            self.refresh_users()
        except ValueError as e:
            QMessageBox.warning(self, "Erro", str(e))

    def _reset_password(self):
        u = self._selected_user()
        if not u:
            return
        p, ok = QInputDialog.getText(self, "Redefinir Senha", "Nova senha:",
                                     echo=QLineEdit.Password)
        if ok and p:
            auth_service.set_password(u["id"], p)
            QMessageBox.information(self, "Concluído", "Senha atualizada.")

    def _toggle_user(self):
        u = self._selected_user()
        if not u:
            return
        if u["role"] == "admin" and u["id"] == auth_service.current_user["id"]:
            QMessageBox.warning(self, "Aviso", "Você não pode desativar sua própria conta.")
            return
        auth_service.update_user(u["id"], u["full_name"], u["role"], not u["is_active"])
        self.refresh_users()

    def _delete_user(self):
        u = self._selected_user()
        if not u:
            return
        if u["role"] == "admin":
            QMessageBox.warning(self, "Aviso", "Contas de administrador não podem ser excluídas.")
            return
        if QMessageBox.question(self, "Excluir", f"Excluir o usuário {u['username']}?") == QMessageBox.Yes:
            auth_service.delete_user(u["id"])
            self.refresh_users()

    # ---------------- refresh ----------------
    def refresh(self):
        self.reload()

    def reload(self):
        self.refresh_tables()
        self.refresh_customers()
        self.refresh_suppliers()
        self.refresh_neighborhoods()
        self.refresh_riders()
        self.refresh_payments()
        self.refresh_categories()
        self.refresh_staff()
        self.refresh_users()
