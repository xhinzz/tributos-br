"""GitHub Action de auditoria, com a API do GitHub simulada."""

import json
import sys
from pathlib import Path

import pytest

from tests.nfe import nfe

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "acao"))
import auditar_pr


class GitHubFalso:
    def __init__(self, arquivos, comentarios=()):
        self.arquivos, self.comentarios, self.chamadas = arquivos, list(comentarios), []

    def __call__(self, metodo, caminho, corpo=None):
        self.chamadas.append((metodo, caminho, corpo))
        pagina = int(caminho.rsplit("page=", 1)[1]) if "page=" in caminho else 1
        if caminho.startswith("/repos/dono/repo/pulls/7/files"):
            return self.arquivos[(pagina - 1) * 100 : pagina * 100]
        if caminho.startswith("/repos/dono/repo/issues/7/comments") and metodo == "GET":
            return self.comentarios if pagina == 1 else []
        return {}


@pytest.fixture
def pr(tmp_path, monkeypatch):
    evento = tmp_path / "evento.json"
    evento.write_text(json.dumps({"pull_request": {"number": 7}}), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(evento))
    monkeypatch.setenv("GITHUB_REPOSITORY", "dono/repo")
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(tmp_path / "resumo.md"))
    (tmp_path / "notas").mkdir()
    (tmp_path / "notas" / "certa.xml").write_text(nfe(), encoding="utf-8")
    (tmp_path / "notas" / "errada.xml").write_text(nfe(v_nf="999.00"), encoding="utf-8")
    return tmp_path


def _arquivos(*nomes, status="modified"):
    return [{"filename": n, "status": status} for n in nomes]


def test_comenta_e_falha_com_divergencia(pr):
    api = GitHubFalso(_arquivos("notas/certa.xml", "notas/errada.xml", "README.md"))
    assert auditar_pr.main(api) == 1
    metodo, caminho, corpo = api.chamadas[-1]
    assert (metodo, caminho) == ("POST", "/repos/dono/repo/issues/7/comments")
    assert "`notas/certa.xml`** — ✅" in corpo["body"] and "`notas/errada.xml`** — ❌" in corpo["body"]
    assert "`vNF`" in corpo["body"] and "README" not in corpo["body"]
    assert auditar_pr.MARCA in (pr / "resumo.md").read_text(encoding="utf-8")


def test_atualiza_o_comentario_em_vez_de_empilhar(pr):
    api = GitHubFalso(_arquivos("notas/certa.xml"), [{"id": 55, "body": f"{auditar_pr.MARCA}\nantigo"}])
    assert auditar_pr.main(api) == 0
    assert api.chamadas[-1][:2] == ("PATCH", "/repos/dono/repo/issues/comments/55")
    assert not any(m == "POST" for m, *_ in api.chamadas)


def test_pagina_os_arquivos_do_pr_e_ignora_removidos(pr):
    api = GitHubFalso(
        _arquivos(*[f"x{i}.txt" for i in range(100)])
        + _arquivos("notas/certa.xml")
        + _arquivos("velha.xml", status="removed")
    )
    assert auditar_pr.arquivos_do_pr(api, "dono/repo", 7, "**/*.xml") == ["notas/certa.xml"]


def test_xml_quebrado_nao_derruba_os_outros(pr, monkeypatch):
    (pr / "notas" / "quebrado.xml").write_text("<nada", encoding="utf-8")
    monkeypatch.setenv("ENTRADA_FALHAR", "false")
    api = GitHubFalso(_arquivos("notas/quebrado.xml", "notas/certa.xml"))
    assert auditar_pr.main(api) == 0
    corpo = api.chamadas[-1][2]["body"]
    assert "não deu para auditar" in corpo and "`notas/certa.xml`** — ✅" in corpo


def test_sem_xml_no_pr(pr, monkeypatch):
    monkeypatch.setenv("ENTRADA_COMENTAR", "false")
    api = GitHubFalso(_arquivos("README.md"))
    assert auditar_pr.main(api) == 0
    assert all(m == "GET" for m, *_ in api.chamadas)
    assert "Nenhum XML" in (pr / "resumo.md").read_text(encoding="utf-8")
