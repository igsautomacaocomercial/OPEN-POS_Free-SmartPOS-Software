import shutil
import socket
import uuid

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout, QFrame, QHBoxLayout,
    QInputDialog, QLabel, QLineEdit, QMessageBox, QPushButton, QScrollArea, QSpinBox,
    QTabWidget, QVBoxLayout, QWidget,
)

from app.config import LOGOS_DIR
from app.database.db import get_db
from app.printing.printer_service import list_printers, test_print
from app.services.settings_service import settings_service
from app.ui.icons import make_icon



class SettingsView(QWidget):
    data_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build()

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 22, 28, 22)
        outer.setSpacing(14)
        title = QLabel("Configurações")
        title.setObjectName("PageTitle")
        outer.addWidget(title)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_store_tab(), "Loja")
        self.tabs.addTab(self._build_tax_tab(), "Taxas e Recibo")
        self.tabs.addTab(self._build_service_tab(), "Atendimento")
        self.tabs.addTab(self._build_printing_tab(), "Impressão")
        self.tabs.addTab(self._build_backup_tab(), "Backup / Restaurar")
        outer.addWidget(self.tabs, 1)

    # ---------------- Store ----------------
    def _build_store_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setSpacing(14)

        card = QFrame()
        card.setProperty("card", True)
        form = QFormLayout(card)
        form.setContentsMargins(20, 18, 20, 18)
        form.setSpacing(12)
        self.s_name = QLineEdit()
        self.s_email = QLineEdit()
        self.s_phone = QLineEdit()
        self.s_address = QLineEdit()
        self.s_currency = QComboBox()
        self.s_currency.addItems(["R$", "$", "€", "£", "AED", "SAR"])
        form.addRow("Nome da Loja", self.s_name)
        form.addRow("Email", self.s_email)
        form.addRow("Telefone", self.s_phone)
        form.addRow("Endereço", self.s_address)
        form.addRow("Moeda", self.s_currency)
        lay.addWidget(card)

        logo_card = QFrame()
        logo_card.setProperty("card", True)
        lv = QVBoxLayout(logo_card)
        lv.setContentsMargins(20, 18, 20, 18)
        lv.setSpacing(8)
        lv.addWidget(QLabel("Logo da Loja"))
        self.logo_lbl = QLabel("Nenhum logo enviado")
        self.logo_lbl.setProperty("muted", True)
        lv.addWidget(self.logo_lbl)
        btn_row = QHBoxLayout()
        upload = QPushButton("Enviar Logo")
        upload.clicked.connect(self._upload_logo)
        remove = QPushButton("Remover")
        remove.clicked.connect(self._remove_logo)
        btn_row.addWidget(upload)
        btn_row.addWidget(remove)
        btn_row.addStretch()
        lv.addLayout(btn_row)
        lay.addWidget(logo_card)

        save = QPushButton("Salvar Configurações da Loja")
        save.setProperty("primary", True)
        save.clicked.connect(self._save_store)
        lay.addWidget(save, alignment=Qt.AlignRight)
        lay.addStretch()
        return w

    def _upload_logo(self):
        path, _ = QFileDialog.getOpenFileName(self, "Selecionar Logo", "",
                                              "Images (*.png *.jpg *.jpeg *.bmp)")
        if not path:
            return
        ext = path.rsplit(".", 1)[-1]
        fname = f"logo_{uuid.uuid4().hex[:8]}.{ext}"
        shutil.copy(path, LOGOS_DIR / fname)
        settings_service.set("store_logo", fname)
        self.logo_lbl.setText(f"✓ {fname}")
        QMessageBox.information(self, "Salvo", "Logo enviado. Reinicie o aplicativo para aplicar em todos os lugares.")

    def _remove_logo(self):
        settings_service.set("store_logo", "")
        self.logo_lbl.setText("Nenhum logo enviado")

    def _save_store(self):
        settings_service.set_many({
            "store_name": self.s_name.text().strip(),
            "store_email": self.s_email.text().strip(),
            "store_phone": self.s_phone.text().strip(),
            "store_address": self.s_address.text().strip(),
            "currency": self.s_currency.currentText(),
        })
        QMessageBox.information(self, "Salvo", "Configurações da loja salvas.")

    # ---------------- Tax Management ----------------
    def _build_tax_tab(self):
        w = QWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        inner = QWidget()
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(4, 4, 8, 8)
        lay.setSpacing(14)

        tax = QFrame()
        tax.setProperty("card", True)
        tf = QFormLayout(tax)
        tf.setContentsMargins(20, 18, 20, 18)
        tf.setSpacing(12)
        self.delivery_charge = QDoubleSpinBox()
        self.delivery_charge.setRange(0, 100000)
        self.delivery_charge.setDecimals(2)
        self.delivery_charge.setPrefix(settings_service.get("currency", "R$") + " ")
        self.takeaway_charge = QDoubleSpinBox()
        self.takeaway_charge.setRange(0, 100000)
        self.takeaway_charge.setDecimals(2)
        self.takeaway_charge.setPrefix(settings_service.get("currency", "R$") + " ")
        tf.addRow("Taxa de Entrega (por pedido)", self.delivery_charge)
        tf.addRow("Taxa Para Viagem (por pedido)", self.takeaway_charge)
        lay.addWidget(tax)


        rec = QFrame()
        rec.setProperty("card", True)
        rf = QVBoxLayout(rec)
        rf.setContentsMargins(20, 18, 20, 18)
        rf.setSpacing(10)
        rf.addWidget(QLabel("Personalização do Recibo"))
        self.rec_footer = QLineEdit()
        self.rec_footer.setPlaceholderText("Mensagem do rodapé do recibo...")
        rf.addWidget(self.rec_footer)
        self.rec_show_logo = QCheckBox("Mostrar logo no recibo")
        self.rec_show_address = QCheckBox("Mostrar endereço no recibo")
        rf.addWidget(self.rec_show_logo)
        rf.addWidget(self.rec_show_address)
        lay.addWidget(rec)

        save = QPushButton("Salvar Configurações de Taxas & Recibo")
        save.setProperty("primary", True)
        save.clicked.connect(self._save_receipt)
        lay.addWidget(save, alignment=Qt.AlignRight)
        lay.addStretch()
        scroll.setWidget(inner)
        wlay = QVBoxLayout(w)
        wlay.setContentsMargins(0, 0, 0, 0)
        wlay.addWidget(scroll)
        return w

    def _save_receipt(self):
        settings_service.set_many({
            "delivery_charge": str(self.delivery_charge.value()),
            "takeaway_charge": str(self.takeaway_charge.value()),
            "tax_name": "Imposto",
            "tax_rate": "0",
            "tax_dinein": "0",
            "tax_takeaway": "0",
            "tax_delivery": "0",
            "receipt_footer": self.rec_footer.text().strip(),
            "receipt_show_logo": "1" if self.rec_show_logo.isChecked() else "0",
            "receipt_show_address": "1" if self.rec_show_address.isChecked() else "0",
        })
        QMessageBox.information(self, "Salvo", "Configurações de taxas & recibo salvas.")

    # ---------------- Service ----------------
    def _build_service_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setSpacing(14)

        card = QFrame()
        card.setProperty("card", True)
        cv = QVBoxLayout(card)
        cv.setContentsMargins(20, 18, 20, 18)
        cv.setSpacing(10)

        title = QLabel("Mesas e Atendimento")
        title.setStyleSheet("font-weight: 800; font-size: 15px;")
        cv.addWidget(title)

        hint = QLabel(
            "Quando ativado, o sistema pede a seleção de um garçom ativo antes de lançar itens em mesas sem garçom."
        )
        hint.setProperty("muted", True)
        hint.setWordWrap(True)
        cv.addWidget(hint)

        self.require_waiter_before_items = QCheckBox("Solicitar garçom antes de lançar itens na mesa")
        cv.addWidget(self.require_waiter_before_items)

        api_title = QLabel("App do Garçom na Rede Local")
        api_title.setStyleSheet("font-weight: 800; font-size: 15px; margin-top: 12px;")
        cv.addWidget(api_title)

        api_hint = QLabel(
            "Ative para acessar o app do garçom pelo celular na mesma rede. O IP é detectado automaticamente."
        )
        api_hint.setProperty("muted", True)
        api_hint.setWordWrap(True)
        cv.addWidget(api_hint)

        self.local_api_enabled = QCheckBox("Ativar API local / app do garçom")
        cv.addWidget(self.local_api_enabled)

        api_form = QFormLayout()
        self.local_api_host = QLineEdit()
        self.local_api_host.setText("0.0.0.0")
        self.local_api_host.setReadOnly(True)
        self.local_api_port = QSpinBox()
        self.local_api_port.setRange(1024, 65535)
        self.local_api_port.setValue(8080)
        self.local_api_port.valueChanged.connect(self._update_local_api_url)
        self.local_api_url = QLabel()
        self.local_api_url.setProperty("muted", True)
        self.local_api_url.setTextInteractionFlags(Qt.TextSelectableByMouse)
        refresh_ip = QPushButton("Atualizar IP")
        refresh_ip.clicked.connect(self._update_local_api_url)
        api_form.addRow("Escutar em", self.local_api_host)
        api_form.addRow("Porta", self.local_api_port)
        api_form.addRow("Link do celular", self.local_api_url)
        api_form.addRow("", refresh_ip)
        cv.addLayout(api_form)

        lay.addWidget(card)

        save = QPushButton("Salvar Configurações de Atendimento")
        save.setProperty("primary", True)
        save.clicked.connect(self._save_service)
        lay.addWidget(save, alignment=Qt.AlignRight)
        lay.addStretch()
        return w

    def _save_service(self):
        settings_service.set(
            "require_waiter_before_items",
            "1" if self.require_waiter_before_items.isChecked() else "0",
        )
        settings_service.set_many({
            "local_api_enabled": "1" if self.local_api_enabled.isChecked() else "0",
            "local_api_host": "0.0.0.0",
            "local_api_port": str(self.local_api_port.value()),
        })
        try:
            from app.api.runtime import local_api_runtime
            if self.local_api_enabled.isChecked():
                started = local_api_runtime.start("0.0.0.0", self.local_api_port.value())
                if not started:
                    detail = local_api_runtime.last_error or "Verifique dependências e porta."
                    QMessageBox.warning(self, "API local", f"Não foi possível iniciar a API local.\n\nDetalhe: {detail}")
            else:
                local_api_runtime.stop()
        except Exception as exc:
            QMessageBox.warning(self, "API local", f"Não foi possível aplicar a configuração da API local.\n\nDetalhe: {exc}")
        QMessageBox.information(self, "Salvo", "Configurações de atendimento salvas.")

    def _local_ip(self):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("8.8.8.8", 80))
                return s.getsockname()[0]
        except Exception:
            try:
                return socket.gethostbyname(socket.gethostname())
            except Exception:
                return "IP_DO_PC"

    def _update_local_api_url(self):
        self.local_api_url.setText(f"http://{self._local_ip()}:{self.local_api_port.value()}/garcom")

    # ---------------- Printing ----------------
    def _build_printing_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setSpacing(14)

        card = QFrame()
        card.setProperty("card", True)
        form = QFormLayout(card)
        form.setContentsMargins(20, 18, 20, 18)
        form.setSpacing(12)

        self.p_printer = QComboBox()
        self.p_printer.setMinimumWidth(340)
        form.addRow("Impressora POS", self.p_printer)
        self.p_printer.setToolTip(
            "Selecione a impressora de recibos. 'Padrão do Sistema' usa a impressora padrão do Windows.")

        row = QHBoxLayout()
        refresh = QPushButton("Atualizar Lista")
        refresh.clicked.connect(self._refresh_printers)
        row.addWidget(refresh)
        row.addStretch()
        form.addRow("", row)

        self.p_encoding = QComboBox()
        self.p_encoding.addItems(["cp437", "cp850", "utf-8", "cp1252"])
        form.addRow("Codificação de Caracteres", self.p_encoding)

        self.p_cols = QSpinBox()
        self.p_cols.setRange(24, 48)
        self.p_cols.setValue(42)
        self.p_cols.setSuffix("  caracteres")
        form.addRow("Largura do Papel (carac.)", self.p_cols)
        hint = QLabel("42 = térmica 80mm, 32 = térmica 58mm.")
        hint.setProperty("muted", True)
        form.addRow("", hint)

        self.p_cut = QComboBox()
        self.p_cut.addItem("Cortar papel após o recibo", "1")
        self.p_cut.addItem("Não cortar (deixar papel sem corte)", "0")
        form.addRow("Após Impressão", self.p_cut)
        lay.addWidget(card)

        test_card = QFrame()
        test_card.setProperty("card", True)
        tv = QVBoxLayout(test_card)
        tv.setContentsMargins(20, 18, 20, 18)
        tv.setSpacing(8)
        tv.addWidget(QLabel("Testar Impressora"))
        test_hint = QLabel("Imprime um recibo de teste curto na impressora selecionada.")
        test_hint.setProperty("muted", True)
        tv.addWidget(test_hint)
        self.btn_test = QPushButton("   Imprimir Recibo de Teste")
        self.btn_test.setIcon(make_icon("print", "#ffffff", 24))
        self.btn_test.setIconSize(QSize(18, 18))
        self.btn_test.setProperty("primary", True)
        self.btn_test.clicked.connect(self._test_print)
        tv.addWidget(self.btn_test, alignment=Qt.AlignLeft)
        lay.addWidget(test_card)

        save = QPushButton("Salvar Configurações de Impressão")
        save.setProperty("primary", True)
        save.clicked.connect(self._save_printing)
        lay.addWidget(save, alignment=Qt.AlignRight)
        lay.addStretch()
        return w

    def _refresh_printers(self):
        self._populate_printers(keep=settings_service.get("printer_name", "").strip())

    def _populate_printers(self, keep=""):
        self.p_printer.clear()
        self.p_printer.addItem("Padrão do Sistema", "")
        for name in list_printers():
            self.p_printer.addItem(name, name)
        idx = self.p_printer.findData(keep)
        self.p_printer.setCurrentIndex(idx if idx >= 0 else 0)

    def _save_printing(self):
        settings_service.set_many({
            "printer_name": self.p_printer.currentData() or "",
            "printer_encoding": self.p_encoding.currentText(),
            "printer_cols": str(self.p_cols.value()),
            "printer_cut": self.p_cut.currentData(),
        })
        QMessageBox.information(self, "Salvo", "Configurações de impressão salvas.")

    def _test_print(self):
        self._save_printing()
        try:
            test_print()
            QMessageBox.information(self, "Impressão de Teste", "Recibo de teste enviado para a impressora.")
        except Exception as e:
            QMessageBox.critical(self, "Erro de Impressão", str(e))

    # ---------------- Backup / Restore ----------------
    def _build_backup_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setSpacing(14)

        download = QFrame()
        download.setProperty("card", True)
        dv = QVBoxLayout(download)
        dv.setContentsMargins(20, 18, 20, 18)
        dv.setSpacing(8)
        dv.addWidget(QLabel("Backup dos Dados"))
        d_hint = QLabel("Crie um arquivo de backup de todos os seus dados (pedidos, produtos, equipe, configurações).")
        d_hint.setProperty("muted", True)
        d_hint.setWordWrap(True)
        dv.addWidget(d_hint)
        b_download = QPushButton("   Baixar Backup")
        b_download.setIcon(make_icon("download", "#ffffff", 24))
        b_download.setIconSize(QSize(18, 18))
        b_download.setProperty("primary", True)
        b_download.clicked.connect(self._download_backup)
        dv.addWidget(b_download, alignment=Qt.AlignLeft)
        lay.addWidget(download)

        restore = QFrame()
        restore.setProperty("card", True)
        rv = QVBoxLayout(restore)
        rv.setContentsMargins(20, 18, 20, 18)
        rv.setSpacing(8)
        rv.addWidget(QLabel("Restaurar Backup"))
        r_hint = QLabel("Substitua os dados atuais por um arquivo de backup salvo anteriormente. "
                        "Você será desconectado e precisará entrar novamente.")
        r_hint.setProperty("muted", True)
        r_hint.setWordWrap(True)
        rv.addWidget(r_hint)
        b_apply = QPushButton("   Aplicar Arquivo de Backup")
        b_apply.setIcon(make_icon("refresh", "#ffffff", 24))
        b_apply.setIconSize(QSize(18, 18))
        b_apply.setProperty("primary", True)
        b_apply.clicked.connect(self._apply_backup)
        rv.addWidget(b_apply, alignment=Qt.AlignLeft)
        lay.addWidget(restore)

        reset = QFrame()
        reset.setProperty("card", True)
        xv = QVBoxLayout(reset)
        xv.setContentsMargins(20, 18, 20, 18)
        xv.setSpacing(8)
        xv.addWidget(QLabel("Limpar Todos os Dados"))
        x_hint = QLabel("Exclua PERMANENTEMENTE todos os pedidos, produtos, equipe, mesas e configurações. "
                        "O aplicativo será redefinido para os padrões de fábrica. Isso não pode ser desfeito.")
        x_hint.setProperty("muted", True)
        x_hint.setWordWrap(True)
        xv.addWidget(x_hint)
        b_clear = QPushButton("   Limpar Todos os Dados")
        b_clear.setIcon(make_icon("trash", "#ffffff", 24))
        b_clear.setIconSize(QSize(18, 18))
        b_clear.setProperty("danger", True)
        b_clear.clicked.connect(self._clear_data)
        xv.addWidget(b_clear, alignment=Qt.AlignLeft)
        lay.addWidget(reset)

        auto = QFrame()
        auto.setProperty("card", True)
        av = QVBoxLayout(auto)
        av.setContentsMargins(20, 18, 20, 18)
        av.setSpacing(8)
        av.addWidget(QLabel("Backup Automático"))
        a_hint = QLabel("Crie um backup automaticamente ao abrir o aplicativo, "
                        "se o último for mais antigo que o intervalo escolhido.")
        a_hint.setProperty("muted", True)
        a_hint.setWordWrap(True)
        av.addWidget(a_hint)
        cfg = QHBoxLayout()
        cfg.setSpacing(10)
        self.ab_enabled = QCheckBox("Ativar backup automático")
        self.ab_enabled.setChecked(settings_service.get("auto_backup", "0") == "1")
        cfg.addWidget(self.ab_enabled)
        cfg.addWidget(QLabel("se mais antigo que"))
        self.ab_hours = QSpinBox()
        self.ab_hours.setRange(1, 168)
        self.ab_hours.setValue(int(settings_service.get_float("auto_backup_hours", 24) or 24))
        self.ab_hours.setSuffix(" h")
        cfg.addWidget(self.ab_hours)
        cfg.addStretch()
        av.addLayout(cfg)
        b_auto = QPushButton("   Salvar Configuração")
        b_auto.setIcon(make_icon("check", "#ffffff", 24))
        b_auto.setIconSize(QSize(18, 18))
        b_auto.setProperty("primary", True)
        b_auto.clicked.connect(self._save_auto_backup)
        av.addWidget(b_auto, alignment=Qt.AlignLeft)
        lay.addWidget(auto)

        lay.addStretch()
        return w

    def _save_auto_backup(self):
        settings_service.set("auto_backup", "1" if self.ab_enabled.isChecked() else "0")
        settings_service.set("auto_backup_hours", str(self.ab_hours.value()))
        from app.database.db import get_db
        try:
            get_db().backup()
        except Exception as e:
            QMessageBox.critical(self, "Falha no Backup", str(e))
        QMessageBox.information(
            self, "Backup Automático",
            "Preferência salva. Um backup também foi criado agora.")

    def _download_backup(self):
        import datetime
        from app.config import DATA_DIR

        default = DATA_DIR / f"openpos_backup_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        path, _ = QFileDialog.getSaveFileName(
            self, "Salvar Backup", str(default), "SQLite Database (*.db);;Todos os Arquivos (*)")
        if not path:
            return
        try:
            get_db().backup_to(path)
            QMessageBox.information(
                self, "Backup Criado",
                f"Backup salvo com sucesso.\n\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Falha no Backup", str(e))

    def _apply_backup(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Selecionar Arquivo de Backup", "", "SQLite Database (*.db);;Todos os Arquivos (*)")
        if not path:
            return
        resp = QMessageBox.warning(
            self, "Restaurar Backup",
            "Isso substituirá TODOS os dados atuais pelo arquivo de backup.\n\n"
            "Continuar?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if resp != QMessageBox.Yes:
            return
        try:
            from app.database.db import Database
            Database.restore_from(path)
        except Exception as e:
            QMessageBox.critical(self, "Falha na Restauração", str(e))
            return
        QMessageBox.information(
            self, "Restaurado",
            "Backup restaurado com sucesso. Você será desconectado.")
        self.data_changed.emit()

    def _clear_data(self):
        resp = QMessageBox.warning(
            self, "Limpar Todos os Dados",
            "Isso excluirá PERMANENTEMENTE todos os pedidos, produtos, equipe, mesas "
            "e configurações.\n\n"
            "Digite CLEAR para confirmar.",
            QMessageBox.Ok | QMessageBox.Cancel, QMessageBox.Cancel)
        if resp != QMessageBox.Ok:
            return
        text, ok = QInputDialog.getText(self, "Confirmar Limpeza", "Digite CLEAR para confirmar:")
        if not ok or text.strip().upper() != "CLEAR":
            QMessageBox.information(self, "Cancelado", "Limpeza de dados cancelada.")
            return
        try:
            from app.database.db import Database
            Database.reset_all()
        except Exception as e:
            QMessageBox.critical(self, "Falha na Limpeza", str(e))
            return
        QMessageBox.information(
            self, "Dados Limpos",
            "Todos os dados foram limpos. O aplicativo foi redefinido para os padrões "
            "de fábrica (admin / admin123). Você será desconectado.")
        self.data_changed.emit()

    # ---------------- load/save ----------------
    def reload(self):
        s = settings_service
        self.s_name.setText(s.get("store_name"))
        self.s_email.setText(s.get("store_email"))
        self.s_phone.setText(s.get("store_phone"))
        self.s_address.setText(s.get("store_address"))
        idx = self.s_currency.findText(s.get("currency", "R$"))
        if idx >= 0:
            self.s_currency.setCurrentIndex(idx)
        logo = s.get("store_logo", "")
        self.logo_lbl.setText(f"✓ {logo}" if logo else "Nenhum logo enviado")
        self.delivery_charge.setValue(s.get_float("delivery_charge", 0))
        self.takeaway_charge.setValue(s.get_float("takeaway_charge", 0))
        self.rec_footer.setText(s.get("receipt_footer"))
        self.rec_show_logo.setChecked(s.get("receipt_show_logo", "1") == "1")
        self.rec_show_address.setChecked(s.get("receipt_show_address", "1") == "1")
        self.require_waiter_before_items.setChecked(s.get("require_waiter_before_items", "0") == "1")
        self.local_api_enabled.setChecked(s.get("local_api_enabled", "0") == "1")
        self.local_api_host.setText("0.0.0.0")
        try:
            self.local_api_port.setValue(int(s.get("local_api_port", "8080")))
        except (TypeError, ValueError):
            self.local_api_port.setValue(8080)
        self._update_local_api_url()
        self._populate_printers(keep=s.get("printer_name", "").strip())
        enc = s.get("printer_encoding", "cp437")
        eidx = self.p_encoding.findText(enc)
        self.p_encoding.setCurrentIndex(eidx if eidx >= 0 else 0)
        try:
            self.p_cols.setValue(int(s.get("printer_cols", "42")))
        except (TypeError, ValueError):
            self.p_cols.setValue(42)
        cut = s.get("printer_cut", "1")
        cidx = self.p_cut.findData(cut)
        self.p_cut.setCurrentIndex(cidx if cidx >= 0 else 0)
