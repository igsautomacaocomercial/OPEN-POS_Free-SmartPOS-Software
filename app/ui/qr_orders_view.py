from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QMessageBox, QPushButton, QScrollArea,
    QVBoxLayout, QWidget,
)

from app.printing.printer_service import print_kot
from app.services.auth_service import auth_service
from app.services.order_service import order_service
from app.services.qr_order_service import qr_order_service
from app.ui.icons import make_icon
from app.utils.helpers import fmt_money


class QrOrdersView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build()
        self.refresh()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(10000)

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 22, 28, 22)
        root.setSpacing(14)

        head = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("Pedidos QR")
        title.setObjectName("PageTitle")
        sub = QLabel("Pedidos enviados pelo cardapio digital aguardando aprovacao.")
        sub.setObjectName("PageSubtitle")
        title_box.addWidget(title)
        title_box.addWidget(sub)
        head.addLayout(title_box)
        head.addStretch()
        refresh = QPushButton("Atualizar")
        refresh.setIcon(make_icon("refresh", "#4b5563", 24))
        refresh.clicked.connect(self.refresh)
        head.addWidget(refresh)
        root.addLayout(head)

        self.count = QLabel("0 pendentes")
        self.count.setObjectName("SectionHeader")
        root.addWidget(self.count)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.container = QWidget()
        self.list_layout = QVBoxLayout(self.container)
        self.list_layout.setContentsMargins(0, 0, 4, 0)
        self.list_layout.setSpacing(12)
        self.list_layout.addStretch()
        self.scroll.setWidget(self.container)
        root.addWidget(self.scroll, 1)

    def refresh(self):
        while self.list_layout.count() > 1:
            item = self.list_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        requests = qr_order_service.list_pending()
        self.count.setText(f"{len(requests)} pendente{'s' if len(requests) != 1 else ''}")
        if not requests:
            empty = QLabel("Nenhum pedido QR pendente.")
            empty.setProperty("muted", True)
            self.list_layout.insertWidget(0, empty)
            return
        for request in requests:
            self.list_layout.insertWidget(self.list_layout.count() - 1, self._request_card(request))

    def _request_card(self, request):
        frame = QFrame()
        frame.setProperty("card", True)
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(18, 16, 18, 16)
        lay.setSpacing(10)
        total = self._request_total(request["id"])
        title = QLabel(f"Mesa {request['table_no']} - Cliente: {request['customer_name']}")
        title.setObjectName("SectionHeader")
        lay.addWidget(title)
        meta = QLabel(f"Enviado em {request['created_at']}  |  Total: {fmt_money(total)}")
        meta.setProperty("muted", True)
        lay.addWidget(meta)
        for item in qr_order_service.items(request["id"]):
            lay.addWidget(QLabel(self._item_text(item)))
        actions = QHBoxLayout()
        actions.addStretch()
        reject = QPushButton("Rejeitar")
        reject.setProperty("danger", True)
        reject.clicked.connect(lambda _=False, rid=request["id"]: self._reject(rid))
        accept = QPushButton("Aceitar e Imprimir")
        accept.setProperty("primary", True)
        accept.clicked.connect(lambda _=False, rid=request["id"]: self._accept(rid))
        actions.addWidget(reject)
        actions.addWidget(accept)
        lay.addLayout(actions)
        return frame

    def _request_total(self, request_id):
        total = 0.0
        for item in qr_order_service.items(request_id):
            addons = qr_order_service.item_addons(item["id"])
            addon_total = sum(float(a["price"] or 0) * float(a["qty"] or 0) for a in addons)
            total += (float(item["price"] or 0) + addon_total) * float(item["qty"] or 0)
        return total

    def _item_text(self, item):
        parts = [f"{float(item['qty']):g}x {item['name']} - {fmt_money(item['price'])}"]
        addons = qr_order_service.item_addons(item["id"])
        if addons:
            parts.extend(f"+ {float(a['qty']):g}x {a['name']} ({fmt_money(a['price'])})" for a in addons)
        if item["instructions"]:
            parts.append(f"Obs: {item['instructions']}")
        return "\n".join(parts)

    def _accept(self, request_id):
        if QMessageBox.question(self, "Pedidos QR", "Aceitar pedido e imprimir KOT?") != QMessageBox.Yes:
            return
        try:
            request = qr_order_service.get(request_id)
            user = auth_service.current_user or {}
            order, item_ids = qr_order_service.accept(request_id, user.get("id"))
            items = [dict(i) for i in order_service.get_items(order["id"]) if i["id"] in item_ids]
            if items:
                order_for_print = dict(order)
                if request and request["customer_name"]:
                    order_for_print["customer_name"] = request["customer_name"]
                print_kot(order_for_print, items=items)
                order_service.mark_kot_printed(order["id"], items)
            QMessageBox.information(self, "Pedidos QR", "Pedido aceito e enviado para cozinha.")
        except Exception as exc:
            QMessageBox.critical(self, "Pedidos QR", str(exc))
        self.refresh()

    def _reject(self, request_id):
        if QMessageBox.question(self, "Pedidos QR", "Rejeitar este pedido?") != QMessageBox.Yes:
            return
        user = auth_service.current_user or {}
        qr_order_service.reject(request_id, user.get("id"))
        self.refresh()
