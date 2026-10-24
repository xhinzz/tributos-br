"""GitHub Action: audita os XMLs de NF-e de um pull request e comenta o resultado no PR.

Usa a API REST do GitHub com o GITHUB_TOKEN do job: lista os arquivos do PR, cria ou atualiza um único comentário
(marcado) e escreve o mesmo relatório no resumo do job. Sem dependência além da própria tributos-br.
"""

from __future__ import annotations

import fnmatch
import json
import os
import sys
import urllib.request
from pathlib import Path

from tributos_br.auditoria import auditar

MARCA = "<!-- tributos-br:auditoria -->"
ICONE = {"conta": "🔴", "regra": "🟣", "aviso": "🟡"}


def _api(metodo: str, caminho: str, corpo: dict | None = None):
    pedido = urllib.request.Request(
        f"{os.environ.get('GITHUB_API_URL', 'https://api.github.com')}{caminho}",
        data=json.dumps(corpo).encode() if corpo is not None else None,
        method=metodo,
        headers={
            "Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(pedido, timeout=30) as resposta:
        dados = resposta.read()
    return json.loads(dados) if dados else None


def arquivos_do_pr(api, repo: str, numero: int, padrao: str) -> list[str]:
    nomes, pagina = [], 1
    while lote := api("GET", f"/repos/{repo}/pulls/{numero}/files?per_page=100&page={pagina}"):
        nomes += [a["filename"] for a in lote if a["status"] != "removed" and fnmatch.fnmatch(a["filename"], padrao)]
        pagina += 1
    return nomes


def relatorio(resultados: dict[str, object]) -> str:
    linhas = [MARCA, "### Auditoria fiscal das NF-e (tributos-br)", ""]
    if not resultados:
        return "\n".join([*linhas, "Nenhum XML de NF-e alterado neste PR."])
    for nome, r in resultados.items():
        if isinstance(r, Exception):
            linhas += [f"**`{nome}`**: não deu para auditar ({r})", ""]
            continue
        situacao = "✅ sem divergência" if r.ok else "❌ divergências"
        linhas += [f"**`{nome}`** — {situacao}", ""]
        if r.achados:
            linhas += ["| | item | campo | na nota | esperado | por quê |", "|---|---|---|---|---|---|"]
            for a in r.achados:
                detalhe = a.detalhe.replace("|", "/")[:140]
                linhas.append(
                    f"| {ICONE[a.tipo]} {a.tipo} | {a.item or '-'} | `{a.campo}` | {a.nota if a.nota is not None else 'ausente'} "
                    f"| {a.esperado if a.esperado is not None else '-'} | {detalhe} |"
                )
            linhas.append("")
    return "\n".join(linhas)


def publicar(api, repo: str, numero: int, texto: str):
    """Um comentário só por PR: atualiza o marcado em vez de empilhar a cada push."""
    pagina = 1
    while lote := api("GET", f"/repos/{repo}/issues/{numero}/comments?per_page=100&page={pagina}"):
        for comentario in lote:
            if MARCA in (comentario.get("body") or ""):
                api("PATCH", f"/repos/{repo}/issues/comments/{comentario['id']}", {"body": texto})
                return
        pagina += 1
    api("POST", f"/repos/{repo}/issues/{numero}/comments", {"body": texto})


def main(api=_api) -> int:
    evento = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))
    repo, numero = os.environ["GITHUB_REPOSITORY"], evento["pull_request"]["number"]
    padrao, regime = os.environ.get("ENTRADA_ARQUIVOS") or "*.xml", os.environ.get("ENTRADA_REGIME") or None
    resultados: dict[str, object] = {}
    for nome in arquivos_do_pr(api, repo, numero, padrao):
        try:
            resultados[nome] = auditar(Path(nome), regime=regime)
        except Exception as erro:  # XML quebrado ou que não é NF-e não derruba os outros
            resultados[nome] = erro
    texto = relatorio(resultados)
    if resumo := os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(resumo, "a", encoding="utf-8") as f:
            f.write(texto + "\n")
    if os.environ.get("ENTRADA_COMENTAR", "true") == "true":
        publicar(api, repo, numero, texto)
    falhou = any(not getattr(r, "ok", False) for r in resultados.values())
    return 1 if falhou and os.environ.get("ENTRADA_FALHAR", "true") == "true" else 0


if __name__ == "__main__":
    sys.exit(main())
