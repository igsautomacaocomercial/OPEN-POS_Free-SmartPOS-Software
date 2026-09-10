import shutil
import uuid
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFormLayout, QFrame, QHBoxLayout, QInputDialog,
    QFileDialog, QLabel, QLineEdit, QMessageBox, QPushButton, QTableWidget,
    QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget,
)

from PySide6.QtGui import QColor, QPixmap

from app.config import PRODUCT_IMAGES_DIR
from app.services.product_service import product_service
from app.services.settings_service import settings_service
from app.ui.icons import make_icon
from app.ui.keys import bind_table_keys


class ProductDialog(QDialog):
    def __init__(self, parent=None, product=None, categories=None):
        super().__init__(parent)
        self.product = product
        self.setWindowTitle("Editar Produto" if product else "Adicionar Produto")
        self.setMinimumWidth(560)
        self.setMinimumHeight(520)
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        tabs = QTabWidget()
        root.addWidget(tabs, 1)

        data_tab = QWidget()
        data_lay = QVBoxLayout(data_tab)
        data_lay.setContentsMargins(10, 12, 10, 10)
        data_lay.setSpacing(12)
        data_card = QFrame()
        data_card.setProperty("card", True)
        form = QFormLayout(data_card)
        form.setContentsMargins(18, 16, 18, 16)
        form.setSpacing(12)

        self.name = QLineEdit()
        self.cat = QComboBox()
        self.cat.addItem("— Nenhuma —", None)
        for c in categories or []:
            self.cat.addItem(c["name"], c["id"])
        self.price = QDoubleSpinBox()
        self.price.setRange(0, 1_000_000)
        self.price.setDecimals(2)
        self.price.setPrefix(settings_service.get("currency", "R$") + " ")
        self.price.setStyleSheet("QDoubleSpinBox { background: #fff4e0; border: 1.5px solid #f2c66d; border-radius: 9px; padding: 8px 11px; }")
        self.cost = QDoubleSpinBox()
        self.cost.setRange(0, 1_000_000)
        self.cost.setDecimals(2)
        self.cost.setPrefix(settings_service.get("currency", "R$") + " ")
        self.margin = QDoubleSpinBox()
        self.margin.setRange(0, 10000)
        self.margin.setDecimals(1)
        self.margin.setSuffix("  %")
        self.margin.setValue(0)
        self.margin.setStyleSheet("QDoubleSpinBox { background: #e8f7ec; border: 1.5px solid #82d5a3; border-radius: 9px; padding: 8px 11px; }")
        self._updating = False
        self.margin.valueChanged.connect(self._margin_changed)
        self.price.valueChanged.connect(self._from_price)
        self.cost.valueChanged.connect(self._from_price)
        self.allow_addons = QCheckBox("Usar adicionais/opcionais neste produto")
        self.image_path = product["image_path"] if product else ""
        self.image_label = QLabel(self.image_path or "Sem foto")
        self.image_label.setProperty("muted", True)
        img_row = QHBoxLayout()
        choose_img = QPushButton("Escolher Foto")
        choose_img.clicked.connect(self._choose_image)
        remove_img = QPushButton("Remover")
        remove_img.clicked.connect(self._remove_image)
        img_row.addWidget(self.image_label, 1)
        img_row.addWidget(choose_img)
        img_row.addWidget(remove_img)

        form.addRow("Nome", self.name)
        form.addRow("Categoria", self.cat)
        form.addRow("Preco", self.price)
        form.addRow("Custo", self.cost)
        form.addRow("Margem %", self.margin)
        form.addRow("Adicionais", self.allow_addons)
        data_lay.addWidget(data_card)
        data_lay.addStretch()
        tabs.addTab(data_tab, "Dados do Produto")

        photo_tab = QWidget()
        photo_lay = QVBoxLayout(photo_tab)
        photo_lay.setContentsMargins(10, 12, 10, 10)
        photo_lay.setSpacing(12)
        photo_card = QFrame()
        photo_card.setProperty("card", True)
        p_lay = QVBoxLayout(photo_card)
        p_lay.setContentsMargins(18, 16, 18, 16)
        p_lay.setSpacing(12)
        hint = QLabel("Esta foto aparece no cardapio digital do cliente.")
        hint.setProperty("muted", True)
        p_lay.addWidget(hint)
        self.photo_preview = QLabel("Sem foto")
        self.photo_preview.setAlignment(Qt.AlignCenter)
        self.photo_preview.setMinimumHeight(260)
        self.photo_preview.setStyleSheet(
            "QLabel { background: #fff7ed; border: 2px dashed #fdba74; border-radius: 18px; color: #9a3412; font-weight: 800; }"
        )
        p_lay.addWidget(self.photo_preview, 1)
        p_lay.addLayout(img_row)
        photo_lay.addWidget(photo_card, 1)
        tabs.addTab(photo_tab, "Foto / Cardapio Digital")

        btns = QHBoxLayout()
        btns.addStretch()
        save = QPushButton("Salvar")
        save.setProperty("primary", True)
        save.clicked.connect(self.accept)
        cancel = QPushButton("Cancelar")
        cancel.clicked.connect(self.reject)
        btns.addWidget(cancel)
        btns.addWidget(save)
        root.addLayout(btns)

        if product:
            self.name.setText(product["name"])
            idx = self.cat.findData(product["category_id"])
            if idx >= 0:
                self.cat.setCurrentIndex(idx)
            self.price.setValue(product["price"])
            self.cost.setValue(product["cost"])
            self.allow_addons.setChecked(bool(product["allow_addons"]))
        self._update_photo_preview()

    def _choose_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Escolher Foto do Produto", "", "Imagens (*.png *.jpg *.jpeg *.webp *.bmp)"
        )
        if not path:
            return
        src = Path(path)
        ext = src.suffix.lower() if src.suffix else ".jpg"
        if ext not in (".png", ".jpg", ".jpeg", ".webp", ".bmp"):
            QMessageBox.warning(self, "Foto", "Formato de imagem invalido.")
            return
        filename = f"{uuid.uuid4().hex}{ext}"
        dest = PRODUCT_IMAGES_DIR / filename
        shutil.copy2(src, dest)
        self.image_path = filename
        self.image_label.setText(filename)
        self._update_photo_preview()

    def _remove_image(self):
        self.image_path = ""
        self.image_label.setText("Sem foto")
        self._update_photo_preview()

    def _update_photo_preview(self):
        if not self.image_path:
            self.photo_preview.setPixmap(QPixmap())
            self.photo_preview.setText("Sem foto")
            return
        path = PRODUCT_IMAGES_DIR / self.image_path
        pix = QPixmap(str(path))
        if pix.isNull():
            self.photo_preview.setPixmap(QPixmap())
            self.photo_preview.setText("Foto nao encontrada")
            return
        self.photo_preview.setText("")
        self.photo_preview.setPixmap(
            pix.scaled(500, 260, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        )

    def _from_price(self, value=None):
        if self._updating:
            return
        cost = self.cost.value()
        price = self.price.value()
        self._updating = True
        self.margin.setValue(round((price - cost) / cost * 100.0, 1) if cost > 0 else 0.0)
        self._updating = False

    def _margin_changed(self, value):
        if self._updating:
            return
        cost = self.cost.value()
        self._updating = True
        self.price.setValue(round(cost * (1 + value / 100.0), 2))
        self._updating = False

    def values(self):
        return {
            "name": self.name.text().strip(),
            "category_id": self.cat.currentData(),
            "price": self.price.value(),
            "cost": self.cost.value(),
            "allow_addons": self.allow_addons.isChecked(),
            "image_path": self.image_path,
        }


class ProductsView(QWidget):
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
        title = QLabel("Produtos")
        title.setObjectName("PageTitle")
        sub = QLabel("Gerencie itens do menu e categorias")
        sub.setObjectName("PageSubtitle")
        t.addWidget(title)
        t.addWidget(sub)
        head.addLayout(t)
        head.addStretch()
        add = QPushButton("+  Adicionar Produto")
        add.setProperty("primary", True)
        add.clicked.connect(self._add_product)
        head.addWidget(add)
        outer.addLayout(head)

        body = QHBoxLayout()
        body.setSpacing(14)

        # categories panel
        cat_card = QFrame()
        cat_card.setProperty("card", True)
        cat_card.setMinimumWidth(360)
        cv = QVBoxLayout(cat_card)
        cv.setContentsMargins(12, 12, 12, 12)
        cv.setSpacing(8)
        cv.addWidget(QLabel("Categorias"))
        self.cat_list = QTableWidget(0, 1)
        self.cat_list.setHorizontalHeaderLabels(["Nome"])
        self.cat_list.horizontalHeader().setStretchLastSection(True)
        self.cat_list.verticalHeader().setVisible(False)
        self.cat_list.setShowGrid(False)
        self.cat_list.setEditTriggers(QTableWidget.NoEditTriggers)
        self.cat_list.itemClicked.connect(self._on_category_clicked)
        cv.addWidget(self.cat_list, 1)
        cat_btns = QHBoxLayout()
        b_add = QPushButton("Adicionar")
        b_add.setToolTip("Criar uma nova categoria")
        b_add.clicked.connect(self._add_category)
        b_edit = QPushButton("Renomear")
        b_edit.setToolTip("Renomear a categoria selecionada")
        b_edit.clicked.connect(self._rename_category)
        b_del = QPushButton("Excluir")
        b_del.setToolTip("Excluir a categoria selecionada (so se nao tiver produtos)")
        b_del.clicked.connect(self._delete_category)
        b_del.setProperty("danger", True)
        cat_btns.addWidget(b_add)
        cat_btns.addWidget(b_edit)
        cat_btns.addWidget(b_del)
        cv.addLayout(cat_btns)
        body.addWidget(cat_card)

        # products panel
        prod_card = QFrame()
        prod_card.setProperty("card", True)
        pv = QVBoxLayout(prod_card)
        pv.setContentsMargins(14, 12, 14, 12)
        pv.setSpacing(10)
        search_row = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("  Buscar produtos...")
        self.search.addAction(make_icon("search", "#9ca3af", 24), QLineEdit.LeadingPosition)
        self.search.textChanged.connect(self.refresh)
        search_row.addWidget(self.search)
        self.cat_filter = QComboBox()
        self.cat_filter.addItem("Todas as Categorias", None)
        self.cat_filter.currentIndexChanged.connect(lambda _: self.refresh())
        search_row.addWidget(self.cat_filter)
        pv.addLayout(search_row)

        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(["ID", "Nome", "Categoria", "Preco", "Custo", "Margem %", "Adicionais", "Foto"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.horizontalHeader().setStretchLastSection(True)
        pv.addWidget(self.table, 1)

        row_btns = QHBoxLayout()
        b_edit = QPushButton("Editar")
        b_edit.clicked.connect(self._edit_product)
        b_del = QPushButton("Excluir")
        b_del.setProperty("danger", True)
        b_del.clicked.connect(self._delete_product)
        row_btns.addStretch()
        row_btns.addWidget(b_edit)
        row_btns.addWidget(b_del)
        pv.addLayout(row_btns)
        body.addWidget(prod_card, 1)

        outer.addLayout(body, 1)

        bind_table_keys(self.table, on_enter=self._edit_product, on_delete=self._delete_product)
        bind_table_keys(self.cat_list, on_enter=self._rename_category, on_delete=self._delete_category)

    def refresh(self):
        cats = product_service.list_categories()
        self.cat_filter.blockSignals(True)
        cur = self.cat_filter.currentData()
        self.cat_filter.clear()
        self.cat_filter.addItem("Todas as Categorias", None)
        for c in cats:
            self.cat_filter.addItem(c["name"], c["id"])
        idx = self.cat_filter.findData(cur)
        if idx >= 0:
            self.cat_filter.setCurrentIndex(idx)
        self.cat_filter.blockSignals(False)

        self.cat_list.setRowCount(len(cats))
        for i, c in enumerate(cats):
            self.cat_list.setItem(i, 0, QTableWidgetItem(c["name"]))
        self.cat_list.resizeRowsToContents()

        cat_id = self.cat_filter.currentData()
        products = product_service.list_active("", None)
        if cat_id:
            products = [p for p in products if p["category_id"] == cat_id]
        s = self.search.text().strip().lower()
        if s:
            products = [p for p in products if s in p["name"].lower()]

        self.table.setRowCount(len(products))
        for i, p in enumerate(products):
            self.table.setItem(i, 0, QTableWidgetItem(str(p["id"])))
            self.table.setItem(i, 1, QTableWidgetItem(p["name"]))
            self.table.setItem(i, 2, QTableWidgetItem(p["category_name"] or "—"))
            _pi = QTableWidgetItem(f"{p['price']:,.2f}")
            _pi.setBackground(QColor("#fff4e0"))
            self.table.setItem(i, 3, _pi)
            self.table.setItem(i, 4, QTableWidgetItem(f"{p['cost']:,.2f}"))
            margin = 0.0
            if p["cost"]:
                margin = (p["price"] - p["cost"]) / p["cost"] * 100.0
            _mi = QTableWidgetItem(f"{margin:,.1f}%")
            if margin > 0:
                _mi.setBackground(QColor("#e8f7ec"))
            self.table.setItem(i, 5, _mi)
            self.table.setItem(i, 6, QTableWidgetItem("Sim" if p["allow_addons"] else "Nao"))
            self.table.setItem(i, 7, QTableWidgetItem("Sim" if p["image_path"] else "Nao"))
        self.table.resizeColumnsToContents()
        self.table.setColumnWidth(1, 240)

    def _on_category_clicked(self, item):
        cats = product_service.list_categories()
        row = item.row()
        if row < 0 or row >= len(cats):
            return
        cat_id = cats[row]["id"]
        if self.cat_filter.currentData() == cat_id:
            self.cat_filter.setCurrentIndex(0)
        else:
            idx = self.cat_filter.findData(cat_id)
            if idx >= 0:
                self.cat_filter.setCurrentIndex(idx)
        self.refresh()

    def _selected_id(self):
        row = self.table.currentRow()
        if row < 0:
            return None
        return int(self.table.item(row, 0).text())

    def _add_product(self):
        dlg = ProductDialog(self, categories=product_service.list_categories())
        if dlg.exec():
            v = dlg.values()
            if not v["name"]:
                QMessageBox.warning(self, "Validacao", "O nome e obrigatorio.")
                return
            product_service.add(v["name"], v["price"], v["cost"], v["category_id"], v["allow_addons"], v["image_path"])
            self.refresh()

    def _edit_product(self):
        pid = self._selected_id()
        if not pid:
            return
        p = product_service.get(pid)
        dlg = ProductDialog(self, product=p, categories=product_service.list_categories())
        if dlg.exec():
            v = dlg.values()
            product_service.update(pid, v["name"], v["price"], v["cost"], v["category_id"], True, v["allow_addons"], v["image_path"])
            self.refresh()

    def _delete_product(self):
        pid = self._selected_id()
        if not pid:
            return
        if QMessageBox.question(self, "Excluir", "Excluir este produto?") == QMessageBox.Yes:
            product_service.delete(pid)
            self.refresh()

    def _add_category(self):
        name, ok = QInputDialog.getText(self, "Adicionar Categoria", "Nome da categoria:")
        if ok and name.strip():
            product_service.add_category(name.strip())
            self.refresh()

    def _rename_category(self):
        row = self.cat_list.currentRow()
        if row < 0:
            return
        c = product_service.list_categories()[row]
        name, ok = QInputDialog.getText(self, "Renomear Categoria", "Nome da categoria:", text=c["name"])
        if ok and name.strip():
            product_service.update_category(c["id"], name.strip())
            self.refresh()

    def _delete_category(self):
        row = self.cat_list.currentRow()
        if row < 0:
            return
        c = product_service.list_categories()[row]
        try:
            product_service.delete_category(c["id"])
            self.refresh()
        except ValueError as e:
            QMessageBox.warning(self, "Não é Possível Excluir", str(e))
