"""Instância única e encaminhamento local de arquivos abertos pelo sistema."""

from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path

from PySide6.QtCore import QObject, Signal, QTimer
from PySide6.QtNetwork import QLocalServer, QLocalSocket

from core.paths import APP_ID
from core.file_transactions import file_lock

MAX_MESSAGE_BYTES = 256 * 1024
MAX_OPEN_FILES = 32


def _server_name() -> str:
    owner = hashlib.sha256(str(Path.home()).encode("utf-8")).hexdigest()[:12]
    return f"{APP_ID}-{owner}"


class ApplicationInstance(QObject):
    filesReceived = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.server = None
        self._clients = set()

    @staticmethod
    def forward_to_running(paths: list[str]) -> bool:
        if len(paths) > MAX_OPEN_FILES:
            return False
        socket = QLocalSocket()
        socket.connectToServer(_server_name())
        if not socket.waitForConnected(500):
            return False
        payload = json.dumps({"files": paths}, ensure_ascii=False).encode("utf-8") + b"\n"
        if len(payload) > MAX_MESSAGE_BYTES:
            socket.abort()
            return False
        socket.write(payload)
        if not socket.waitForBytesWritten(1000):
            return False
        socket.disconnectFromServer()
        return True

    def listen(self) -> bool:
        try:
            with file_lock(Path(tempfile.gettempdir()) / f"{_server_name()}.startup.lock"):
                return self._listen()
        except OSError:
            return False

    def _listen(self) -> bool:
        # Com UserAccessOption o Qt pode publicar por rename no Unix. Verificar
        # o servidor ANTES de listen evita substituir um endpoint ainda ativo.
        probe = QLocalSocket()
        probe.connectToServer(_server_name())
        if probe.waitForConnected(500):
            probe.abort()
            return False
        server = QLocalServer(self)
        server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        if not server.listen(_server_name()):
            probe = QLocalSocket()
            probe.connectToServer(_server_name())
            if probe.waitForConnected(500):
                probe.abort()
                return False
            QLocalServer.removeServer(_server_name())
            if not server.listen(_server_name()):
                return False
        server.newConnection.connect(self._accept_connections)
        self.server = server
        return True

    def close(self):
        if self.server is not None:
            self.server.close()
            self.server.deleteLater()
            self.server = None
        for socket in tuple(self._clients):
            socket.abort()
        self._clients.clear()

    def _accept_connections(self):
        while self.server and self.server.hasPendingConnections():
            socket = self.server.nextPendingConnection()
            if len(self._clients) >= 32:
                socket.abort()
                socket.deleteLater()
                continue
            timeout = QTimer(socket)
            timeout.setSingleShot(True)
            timeout.timeout.connect(socket.abort)
            timeout.start(5000)
            socket.setReadBufferSize(MAX_MESSAGE_BYTES + 1)
            self._clients.add(socket)
            # Não capturar o wrapper Python em lambdas: readyRead pode já estar
            # enfileirado quando o Qt destrói o socket após disconnected.
            socket.readyRead.connect(self._read_ready_client)
            socket.disconnected.connect(self._drop_disconnected_client)
            self._read_client(socket)

    def _read_ready_client(self):
        socket = self.sender()
        if socket is None or socket not in self._clients:
            return
        self._read_client(socket)

    def _drop_disconnected_client(self):
        socket = self.sender()
        if socket is not None:
            self._drop_client(socket)

    def _drop_client(self, socket):
        self._clients.discard(socket)
        try:
            socket.readyRead.disconnect(self._read_ready_client)
            socket.disconnected.disconnect(self._drop_disconnected_client)
            socket.deleteLater()
        except RuntimeError:
            # O Qt pode ter destruído o objeto antes de entregar o sinal Python.
            pass

    def _read_client(self, socket):
        try:
            if socket.bytesAvailable() > MAX_MESSAGE_BYTES:
                socket.abort()
                return
            lines = []
            while socket.canReadLine():
                lines.append(bytes(socket.readLine()).strip())
        except RuntimeError:
            # Um readyRead enfileirado pode chegar depois da destruição nativa.
            self._clients.discard(socket)
            return
        for raw in lines:
            try:
                message = json.loads(raw.decode("utf-8"))
                files = message.get("files", [])
                if (not isinstance(files, list) or len(files) > MAX_OPEN_FILES
                        or not all(isinstance(path, str) and len(path) <= 4096
                                   and "\0" not in path for path in files)):
                    continue
            except (UnicodeError, json.JSONDecodeError, AttributeError, RecursionError):
                continue
            self.filesReceived.emit(files)
