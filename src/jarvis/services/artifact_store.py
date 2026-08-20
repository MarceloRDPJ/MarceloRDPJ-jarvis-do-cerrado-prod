"""Canal de artefato binário do nó Android para o Pi.

Por que não colocar o PDF dentro do resultado do job: o resultado do job é
JSON, é persistido em ``poco_node.json`` e fica ao lado de um dashboard sem
autenticação documentada. Um boleto em base64 ali significaria a fatura oficial
do proprietário gravada em texto claro, sem prazo, num arquivo que o resto do
sistema lê por outros motivos.

Este módulo é o oposto disso:

* o conteúdo nunca entra em JSON, banco ou log;
* o nome do arquivo é gerado aqui dentro, nunca vem do portal;
* só ``application/pdf`` entra, e só se os bytes começarem com ``%PDF``;
* há limite rígido de tamanho, verificado antes de gravar;
* o arquivo nasce com permissão 600, dentro de um diretório 700;
* o identificador devolvido é opaco e é a única forma de alcançar o arquivo:
  não existe listagem, nem resolução por caminho;
* o TTL é curto, a leitura consome o artefato e o boot apaga o que sobrou.
"""

from __future__ import annotations

import os
import re
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class ArtifactError(ValueError):
    """Conteúdo recusado. A mensagem é segura para virar resposta HTTP."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


# Allowlist deliberadamente de um único item. O canal existe para o boleto
# oficial; qualquer outro tipo de arquivo vindo do telefone é recusado.
ALLOWED_MIMES = frozenset({"application/pdf"})

PDF_MAGIC = b"%PDF-"

_ARTIFACT_ID = re.compile(r"^[0-9a-f]{32}$")

# Só este formato de nome é reconhecido na varredura. Nada mais no diretório é
# tratado como artefato, e nada fora dele é alcançável.
_FILENAME = re.compile(r"^[0-9a-f]{32}\.pdf$")


@dataclass(frozen=True)
class ArtifactMeta:
    """Metadado não sensível. Fica só em memória, junto com o TTL."""

    artifact_id: str
    mime: str
    kind: str
    size_bytes: int
    created_at: float

    def public(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "mime": self.mime,
            "kind": self.kind,
            "size_bytes": self.size_bytes,
            "created_at": self.created_at,
        }


class ArtifactStore:
    """Guarda temporária de artefatos binários, endereçada por id opaco."""

    def __init__(
        self,
        directory: str | os.PathLike,
        max_bytes: int = 3 * 1024 * 1024,
        ttl_seconds: int = 300,
        clock=time.time,
    ):
        self.directory = Path(directory)
        self.max_bytes = max(1024, int(max_bytes))
        self.ttl_seconds = max(30, int(ttl_seconds))
        self.clock = clock
        self._lock = threading.RLock()
        self._items: dict[str, ArtifactMeta] = {}
        self._ensure_directory()
        # Boot: o índice vive em memória, então tudo que sobrou de uma execução
        # anterior é inalcançável por definição. Deixar o arquivo no disco só
        # aumentaria a janela de exposição.
        self.purge_all()

    # ------------------------------------------------------------------ escrita

    def store(self, data: bytes, mime: str, kind: str = "boleto") -> ArtifactMeta:
        """Valida e grava. Recusar é o caminho normal; não há correção de conteúdo."""
        normalized = self.normalize_mime(mime)
        if normalized not in ALLOWED_MIMES:
            raise ArtifactError("Tipo de artefato não permitido neste canal", 415)
        if not data:
            raise ArtifactError("Artefato vazio", 400)
        if len(data) > self.max_bytes:
            raise ArtifactError("Artefato acima do limite deste canal", 413)
        if not data.startswith(PDF_MAGIC):
            # HTML de tela de login chega com 200 e Content-Type mentiroso. Sem
            # esta checagem o proprietário receberia uma página de login com
            # nome de boleto.
            raise ArtifactError("O conteúdo não é um PDF", 400)

        artifact_id = uuid.uuid4().hex
        meta = ArtifactMeta(
            artifact_id=artifact_id,
            mime=normalized,
            kind=self._safe_kind(kind),
            size_bytes=len(data),
            created_at=self.clock(),
        )
        with self._lock:
            self.purge()
            self._ensure_directory()
            path = self._path(artifact_id)
            # O_BINARY existe só no Windows, e sem ele o \n do PDF viraria \r\n:
            # o arquivo entregue deixaria de ser byte a byte o que o portal emitiu.
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
            handle = os.open(path, flags, 0o600)
            try:
                os.write(handle, data)
            finally:
                os.close(handle)
            self._chmod(path, 0o600)
            self._items[artifact_id] = meta
        return meta

    # ------------------------------------------------------------------ leitura

    def resolve(self, artifact_id: str) -> Path:
        """Traduz id opaco em caminho. Nunca aceita caminho vindo de fora."""
        with self._lock:
            self.purge()
            meta = self._items.get(self._validate_id(artifact_id))
            if not meta:
                raise KeyError(artifact_id)
            path = self._path(meta.artifact_id)
            if not path.exists():
                self._items.pop(meta.artifact_id, None)
                raise KeyError(artifact_id)
            return path

    def describe(self, artifact_id: str) -> dict[str, Any]:
        with self._lock:
            meta = self._items.get(self._validate_id(artifact_id))
            if not meta:
                raise KeyError(artifact_id)
            return meta.public()

    # ------------------------------------------------------------------ limpeza

    def consume(self, artifact_id: str) -> None:
        """Apaga depois do envio. Entrega feita, artefato deixa de existir."""
        try:
            valid = self._validate_id(artifact_id)
        except ArtifactError:
            return
        with self._lock:
            self._items.pop(valid, None)
            self._unlink(self._path(valid))

    def purge(self, now: float | None = None) -> int:
        """Remove o que passou do TTL e qualquer arquivo órfão do diretório."""
        moment = self.clock() if now is None else now
        removed = 0
        with self._lock:
            for artifact_id, meta in list(self._items.items()):
                if moment - meta.created_at > self.ttl_seconds:
                    self._items.pop(artifact_id, None)
                    self._unlink(self._path(artifact_id))
                    removed += 1
            for path in self._files():
                if path.stem not in self._items:
                    self._unlink(path)
                    removed += 1
        return removed

    def purge_all(self) -> int:
        with self._lock:
            removed = 0
            for path in self._files():
                self._unlink(path)
                removed += 1
            self._items.clear()
            return removed

    # ------------------------------------------------------------------ internos

    @staticmethod
    def normalize_mime(mime: str | None) -> str:
        """``application/pdf; charset=binary`` continua sendo application/pdf."""
        return str(mime or "").split(";")[0].strip().lower()

    @staticmethod
    def _safe_kind(kind: str | None) -> str:
        cleaned = re.sub(r"[^a-z_]", "", str(kind or "").lower())
        return cleaned[:16] or "artifact"

    @staticmethod
    def _validate_id(artifact_id: str) -> str:
        value = str(artifact_id or "")
        if not _ARTIFACT_ID.match(value):
            # Corta travessia de caminho, curinga e id de outro formato antes de
            # qualquer contato com o sistema de arquivos.
            raise ArtifactError("Identificador de artefato inválido", 404)
        return value

    def _path(self, artifact_id: str) -> Path:
        return self.directory / f"{artifact_id}.pdf"

    def _files(self) -> list[Path]:
        if not self.directory.exists():
            return []
        try:
            return [item for item in self.directory.iterdir() if _FILENAME.match(item.name)]
        except OSError:
            return []

    def _ensure_directory(self) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        self._chmod(self.directory, 0o700)

    @staticmethod
    def _chmod(path: Path, mode: int) -> None:
        # Windows não implementa o modo POSIX inteiro; a garantia real é no Pi.
        try:
            os.chmod(path, mode)
        except OSError:
            pass

    @staticmethod
    def _unlink(path: Path) -> None:
        try:
            path.unlink()
        except OSError:
            pass
