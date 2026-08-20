"""Canal de artefato (boleto PDF) e retenção dos artefatos de pagamento.

Nenhum dado real aparece aqui. O "PDF" é um cabeçalho válido seguido da palavra
EXEMPLOFICTICIO, e o Pix sintético é um BR Code montado no próprio teste. O que
se valida é estrutura, permissão e prazo — nunca valor.
"""

import json
import os
import time

import pytest
from fastapi.testclient import TestClient

from jarvis.api import app as api_module
from jarvis.services.artifact_store import ArtifactError, ArtifactStore
from jarvis.services.poco_node import PocoNodeService

FAKE_PDF = b"%PDF-1.4\nEXEMPLOFICTICIO boleto sintetico\n%%EOF\n"
SECRET = "segredo-de-teste"


# ------------------------------------------------------------------ guarda local


def test_store_only_accepts_a_real_pdf(tmp_path):
    store = ArtifactStore(tmp_path / "artifacts")

    with pytest.raises(ArtifactError) as html:
        # A tela de login do portal chega com 200 e disfarce de PDF.
        store.store(b"<html>login</html>", "application/pdf")
    assert html.value.status_code == 400

    with pytest.raises(ArtifactError) as mime:
        store.store(FAKE_PDF, "text/html")
    assert mime.value.status_code == 415

    with pytest.raises(ArtifactError) as empty:
        store.store(b"", "application/pdf")
    assert empty.value.status_code == 400


def test_store_enforces_a_hard_size_limit(tmp_path):
    store = ArtifactStore(tmp_path / "artifacts", max_bytes=2048)
    with pytest.raises(ArtifactError) as big:
        store.store(FAKE_PDF + b"x" * 4096, "application/pdf")
    assert big.value.status_code == 413
    assert store._files() == []


def test_identifier_is_opaque_and_the_filename_is_generated_here(tmp_path):
    store = ArtifactStore(tmp_path / "artifacts")
    meta = store.store(FAKE_PDF, "application/pdf; charset=binary", kind="boleto")

    assert len(meta.artifact_id) == 32
    path = store.resolve(meta.artifact_id)
    assert path.name == f"{meta.artifact_id}.pdf"
    assert path.read_bytes() == FAKE_PDF
    assert meta.mime == "application/pdf"


def test_no_path_ever_comes_from_outside(tmp_path):
    store = ArtifactStore(tmp_path / "artifacts")
    for hostile in ["../../etc/passwd", "..", "", "z" * 32, "0" * 31, "/etc/passwd", "0" * 33]:
        with pytest.raises(ArtifactError) as exc:
            store.resolve(hostile)
        assert exc.value.status_code == 404


def test_delivery_consumes_the_artifact(tmp_path):
    store = ArtifactStore(tmp_path / "artifacts")
    meta = store.store(FAKE_PDF, "application/pdf")
    path = store.resolve(meta.artifact_id)

    store.consume(meta.artifact_id)

    assert not path.exists()
    with pytest.raises(KeyError):
        store.resolve(meta.artifact_id)


def test_ttl_removes_the_file_without_anyone_asking(tmp_path):
    now = [1000.0]
    store = ArtifactStore(tmp_path / "artifacts", ttl_seconds=60, clock=lambda: now[0])
    meta = store.store(FAKE_PDF, "application/pdf")
    path = store.resolve(meta.artifact_id)

    now[0] += 61
    assert store.purge() >= 1

    assert not path.exists()
    with pytest.raises(KeyError):
        store.resolve(meta.artifact_id)


def test_boot_wipes_what_a_previous_run_left_behind(tmp_path):
    directory = tmp_path / "artifacts"
    first = ArtifactStore(directory)
    meta = first.store(FAKE_PDF, "application/pdf")
    leftover = directory / f"{meta.artifact_id}.pdf"
    assert leftover.exists()

    # O índice só existe em memória: depois do boot o arquivo é inalcançável, e
    # deixá-lo no disco seria exposição sem finalidade.
    second = ArtifactStore(directory)

    assert not leftover.exists()
    with pytest.raises(KeyError):
        second.resolve(meta.artifact_id)


def test_there_is_no_public_listing():
    for forbidden in ["list", "all", "items", "index"]:
        assert not hasattr(ArtifactStore, forbidden)


@pytest.mark.skipif(os.name != "posix", reason="modo POSIX só é observável no Pi")
def test_file_and_directory_are_private(tmp_path):
    store = ArtifactStore(tmp_path / "artifacts")
    meta = store.store(FAKE_PDF, "application/pdf")
    assert oct(store.resolve(meta.artifact_id).stat().st_mode)[-3:] == "600"
    assert oct(store.directory.stat().st_mode)[-3:] == "700"


# ------------------------------------------------------------------ canal HTTP


@pytest.fixture
def channel(tmp_path):
    poco = PocoNodeService(tmp_path / "poco.json", SECRET)
    store = ArtifactStore(tmp_path / "artifacts", max_bytes=8192, ttl_seconds=60)
    api_module.app.state.poco_service = poco
    api_module.app.state.artifact_store = store
    yield store
    api_module.app.state.poco_service = None
    api_module.app.state.artifact_store = None


def _signed_headers(body: bytes, path: str, mime: str = "application/pdf"):
    timestamp = str(int(time.time()))
    return {
        "X-Poco-Timestamp": timestamp,
        "X-Poco-Signature": PocoNodeService.signature(SECRET, timestamp, "POST", path, body),
        "X-Poco-Artifact-Mime": mime,
        "X-Poco-Artifact-Kind": "boleto",
        "Content-Type": "application/pdf",
    }


def _client(host: str = "127.0.0.1"):
    return TestClient(api_module.app, client=(host, 4242))


def test_upload_requires_the_same_hmac_as_the_rest_of_the_node(channel):
    path = "/api/poco/artifacts"
    with _client() as client:
        bad = client.post(
            path,
            content=FAKE_PDF,
            headers={
                "X-Poco-Timestamp": str(int(time.time())),
                "X-Poco-Signature": "0" * 64,
                "X-Poco-Artifact-Mime": "application/pdf",
            },
        )
        assert bad.status_code == 401
        assert channel._files() == []

        good = client.post(path, content=FAKE_PDF, headers=_signed_headers(FAKE_PDF, path))
        assert good.status_code == 200
        artifact_id = good.json()["artifact_id"]
        assert len(artifact_id) == 32
        assert good.json()["size_bytes"] == len(FAKE_PDF)


def test_upload_rejects_anything_that_is_not_a_pdf(channel):
    path = "/api/poco/artifacts"
    with _client() as client:
        wrong_mime = client.post(
            path, content=FAKE_PDF, headers=_signed_headers(FAKE_PDF, path, mime="image/png")
        )
        assert wrong_mime.status_code == 415

        html = b"<html>login</html>"
        disguised = client.post(path, content=html, headers=_signed_headers(html, path))
        assert disguised.status_code == 400
        assert channel._files() == []


def test_upload_refuses_oversize_before_reading_the_body(channel):
    path = "/api/poco/artifacts"
    oversize = FAKE_PDF + b"x" * 9000
    with _client() as client:
        response = client.post(path, content=oversize, headers=_signed_headers(oversize, path))
    assert response.status_code == 413
    assert channel._files() == []


def test_download_is_loopback_only_and_happens_once(channel):
    path = "/api/poco/artifacts"
    with _client() as client:
        artifact_id = client.post(
            path, content=FAKE_PDF, headers=_signed_headers(FAKE_PDF, path)
        ).json()["artifact_id"]

    with _client("192.168.1.55") as remote:
        assert remote.get(f"{path}/{artifact_id}").status_code == 403

    with _client() as client:
        served = client.get(f"{path}/{artifact_id}")
        assert served.status_code == 200
        assert served.headers["content-type"] == "application/pdf"
        assert served.content == FAKE_PDF
        # Entregue é entregue: a segunda tentativa não encontra mais nada.
        assert client.get(f"{path}/{artifact_id}").status_code == 404
    assert channel._files() == []


def test_download_never_accepts_a_path(channel):
    with _client() as client:
        assert client.get("/api/poco/artifacts/....%2F....%2Fetc%2Fpasswd").status_code == 404
        assert client.get("/api/poco/artifacts/" + "z" * 32).status_code == 404


def test_upload_stays_inside_the_lan(channel):
    path = "/api/poco/artifacts"
    with _client("8.8.8.8") as internet:
        response = internet.post(path, content=FAKE_PDF, headers=_signed_headers(FAKE_PDF, path))
    assert response.status_code == 403


# ------------------------------------------------------------------ retenção


def test_new_artifact_actions_are_allowed_and_nothing_else_is(tmp_path):
    service = PocoNodeService(tmp_path / "poco.json", SECRET)
    assert service.enqueue("get_equatorial_pix", {"property": "casa"}).action == "get_equatorial_pix"
    assert service.enqueue("get_equatorial_boleto", {"property": "casa"}).status == "queued"
    with pytest.raises(ValueError):
        service.enqueue("pay_equatorial_pix", {"property": "casa"})


def test_pix_payload_never_touches_the_queue_file(tmp_path):
    """O Pix copia e cola é ordem de pagamento; ele não pode existir no disco.

    A poda por prazo continua valendo para o resto, mas ela age depois. A fila é
    gravada no instante em que o resultado chega, então a única defesa real é
    filtrar na serialização.
    """
    path = tmp_path / "poco.json"
    service = PocoNodeService(path, SECRET)
    created = service.enqueue("get_equatorial_pix", {"property": "casa"})
    service.next_job()
    synthetic = "000201...EXEMPLOFICTICIO...6304ABCD"
    service.update_job(
        created.job_id,
        "completed",
        {"pix": synthetic, "reference": "08/2026", "amount": "R$ 1,00"},
    )

    # Em memória o consumidor legítimo ainda lê, dentro do timeout do job.
    assert service.get_job(created.job_id).result["pix"] == synthetic

    raw = path.read_text(encoding="utf-8")
    assert "EXEMPLOFICTICIO" not in raw
    assert json.loads(raw)["jobs"][0]["result"] is None
    assert json.loads(raw)["jobs"][0]["action"] == "get_equatorial_pix"

    # E o reinício não ressuscita o conteúdo.
    assert PocoNodeService(path, SECRET).get_job(created.job_id).result is None


def test_barcode_and_pix_are_stripped_from_any_persisted_result(tmp_path):
    path = tmp_path / "poco.json"
    service = PocoNodeService(path, SECRET)
    created = service.enqueue("refresh_equatorial_bills", {"property": "casa"})
    service.next_job()
    service.update_job(
        created.job_id,
        "completed",
        {"amount": "R$ 1,00", "reference": "08/2026", "barcode": "8" * 48, "pix": "000201EXEMPLOFICTICIO"},
    )

    stored = json.loads(path.read_text(encoding="utf-8"))["jobs"][0]["result"]
    assert stored == {"amount": "R$ 1,00", "reference": "08/2026"}
    assert service.get_job(created.job_id).result["barcode"] == "8" * 48


def test_artifact_metadata_may_persist_because_it_is_not_sensitive(tmp_path):
    path = tmp_path / "poco.json"
    service = PocoNodeService(path, SECRET)
    created = service.enqueue("get_equatorial_boleto", {"property": "casa"})
    service.next_job()
    service.update_job(
        created.job_id,
        "completed",
        {
            "provider": "equatorial",
            "property": "casa",
            "reference": "08/2026",
            "artifact_id": "0" * 32,
            "boleto_available": True,
        },
    )

    stored = json.loads(path.read_text(encoding="utf-8"))["jobs"][0]["result"]
    assert stored["artifact_id"] == "0" * 32
    assert stored["boleto_available"] is True


def test_pix_result_has_a_shorter_grace_than_the_rest(tmp_path):
    now = [1000.0]
    service = PocoNodeService(
        tmp_path / "poco.json",
        shared_secret=SECRET,
        result_grace_seconds=600,
        sensitive_result_grace_seconds=120,
        clock=lambda: now[0],
    )
    pix = service.enqueue("get_equatorial_pix", ttl_seconds=600)
    bills = service.enqueue("refresh_equatorial_bills", ttl_seconds=600)
    service.next_job()
    service.next_job()
    service.update_job(pix.job_id, "completed", {"pix": "000201EXEMPLOFICTICIO"})
    service.update_job(bills.job_id, "completed", {"amount": "R$ 1,00"})

    now[0] += 121
    service.next_job()  # a varredura roda junto com a entrega do próximo job

    assert service.get_job(pix.job_id).result is None
    assert service.get_job(bills.job_id).result is not None
