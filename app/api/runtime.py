import threading

from app.services.settings_service import settings_service
from app.utils.crash_guard import get_logger

log = get_logger()


class LocalApiRuntime:
    def __init__(self):
        self._server = None
        self._thread = None
        self._host = None
        self._port = None
        self.last_error = ""
        self._lock = threading.RLock()

    def start_from_settings(self):
        if settings_service.get("local_api_enabled", "0") != "1":
            return False
        host = settings_service.get("local_api_host", "0.0.0.0").strip() or "0.0.0.0"
        try:
            port = int(settings_service.get("local_api_port", "8080"))
        except (TypeError, ValueError):
            port = 8080
        return self.start(host, port)

    def start(self, host="0.0.0.0", port=8080):
        port = int(port)
        self.last_error = ""
        with self._lock:
            if self._thread and self._thread.is_alive():
                if self._host == host and self._port == port:
                    return True
                self.stop()

            with self._lock:
                return self._start_locked(host, port)

    def _start_locked(self, host, port):
        try:
            import uvicorn
            from app.api.server import create_app
        except Exception as exc:
            self.last_error = str(exc)
            log.exception("Falha ao importar dependencias da API local")
            return False

        config = uvicorn.Config(
            create_app(),
            host=host,
            port=port,
            log_level="warning",
            access_log=False,
            log_config=None,
        )
        self._server = uvicorn.Server(config)
        self._thread = threading.Thread(target=self._run, args=(self._server,), daemon=True, name="openpos-local-api")
        self._host = host
        self._port = port
        self._thread.start()
        log.info("API local iniciando em http://%s:%s", host, port)
        return True

    def _run(self, server):
        try:
            server.run()
        except Exception as exc:
            self.last_error = str(exc)
            log.exception("API local encerrada com erro")

    def stop(self):
        with self._lock:
            thread = self._thread
            if self._server:
                self._server.should_exit = True
            self._server = None
            self._thread = None
            self._host = None
            self._port = None
        if thread and thread.is_alive():
            thread.join(timeout=2)


local_api_runtime = LocalApiRuntime()
