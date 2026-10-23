"""CEST (Conv. 142/18, Anexos II a XXVI) e NCMs do Conv. 52/91 (Anexos I e II), direto do HTML do CONFAZ.

    python scripts/atualizar_convenios.py [pasta_com_os_html]

Não existe CSV oficial, e o HTML compilado mistura a redação vigente com as antigas (ver _vigentes).
"""

import csv
import re
import sys
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

CONFAZ = "https://www.confaz.fazenda.gov.br/legislacao/convenios/"
DADOS = Path(__file__).resolve().parent.parent / "tributos_br" / "dados"
NCM = re.compile(r"\b\d{4}(?:\.\d{1,2}(?:\.\d{1,2})?)?\b")


class _Tabelas(HTMLParser):
    """Tabelas de primeiro nível e o texto antes delas, onde fica o título do anexo."""

    def __init__(self):
        super().__init__()
        self.tabelas, self._texto, self._linha, self._celula, self._nivel = [], [], None, None, 0

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self._nivel += 1
            if self._nivel == 1:
                self.tabelas.append({"titulo": " ".join(self._texto[-12:]), "linhas": []})
        elif self._nivel == 1 and tag == "tr":
            self._linha = []
        elif self._nivel == 1 and tag in ("td", "th"):
            self._celula = []

    def handle_endtag(self, tag):
        if tag == "table":
            self._nivel -= 1
        elif self._nivel == 1 and tag in ("td", "th") and self._celula is not None and self._linha is not None:
            self._linha.append(re.sub(r"\s+", " ", " ".join(self._celula)).strip())
            self._celula = None
        elif self._nivel == 1 and tag == "tr" and self._linha is not None:
            self.tabelas[-1]["linhas"].append(self._linha)
            self._linha = None

    def handle_data(self, data):
        if self._celula is not None:
            self._celula.append(data)
        elif self._nivel == 0 and data.strip():
            self._texto.append(re.sub(r"\s+", " ", data.strip()))


def _html(nome: str, pasta: Path | None) -> str:
    if pasta:
        return (pasta / f"{nome.split('/')[-1]}.html").read_text(encoding="utf-8")
    pedido = urllib.request.Request(CONFAZ + nome, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(pedido, timeout=60) as resposta:
        return resposta.read().decode("utf-8")


def _item(texto: str) -> tuple[int, ...] | None:
    numeros = re.findall(r"\d+", texto.split()[0]) if texto.strip() else []
    return tuple(int(n) for n in numeros) or None


def _vigentes(linhas):
    """A vigente vem antes das antigas, que repetem o número do item: só passa item maior que o último."""
    ultimo = ()
    for linha in linhas:
        if len(linha) == 1 or not any(linha[1:]):
            continue
        item = _item(linha[0])
        if item is None or item <= ultimo:
            continue
        ultimo = item
        if "REVOGAD" not in " ".join(linha).upper():
            yield linha


def _ncms(texto: str) -> list[str]:
    return [n.replace(".", "") for n in NCM.findall(texto)]


def cest(html: str) -> list[list[str]]:
    p = _Tabelas()
    p.feed(html)
    saida = []
    for tabela in p.tabelas:
        anexo = re.findall(r"ANEXO ([IVXL]+)\s+(.+?)(?= ANEXO |$)", tabela["titulo"])
        if (
            not anexo
            or anexo[-1][0] in ("I", "XXVII")
            or not tabela["linhas"]
            or tabela["linhas"][0][:2] != ["ITEM", "CEST"]
        ):
            continue
        segmento = anexo[-1][1].strip()
        for linha in _vigentes(tabela["linhas"][1:]):
            if len(linha) < 4 or not re.fullmatch(r"\d{2}\.\d{3}\.\d{2}", linha[1]):
                continue
            for ncm in _ncms(linha[2]):
                saida.append([linha[1].replace(".", ""), ncm, segmento, linha[3]])
    return saida


def conv52(html: str) -> dict[str, list[list[str]]]:
    p = _Tabelas()
    p.feed(html)
    anexos = {}
    for tabela in p.tabelas:
        anexo = re.findall(r"ANEXO (I{1,2})\b", tabela["titulo"])
        # a primeira de cada anexo é a vigente; as outras são o anexo inteiro em redação antiga
        if not anexo or anexo[-1] in anexos or tabela["linhas"][0][:3] != ["ITEM", "DESCRIÇÃO", "NCM/SH"]:
            continue
        anexos[anexo[-1]] = [
            [linha[0], ncm, linha[1]]
            for linha in _vigentes(tabela["linhas"][1:])
            if len(linha) >= 3
            for ncm in _ncms(linha[2])
        ]
    return anexos


def _gravar(caminho: Path, cabecalho, linhas):
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with caminho.open("w", encoding="utf-8", newline="") as f:
        escritor = csv.writer(f, lineterminator="\n")
        escritor.writerow(cabecalho)
        escritor.writerows(linhas)
    print(f"{caminho.relative_to(DADOS)}: {len(linhas)} linhas")


def main():
    pasta = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    _gravar(DADOS / "cest.csv", ["cest", "ncm", "segmento", "descricao"], cest(_html("2018/CV142_18", pasta)))
    anexos = conv52(_html("1991/CV052_91", pasta))
    for anexo, linhas in anexos.items():
        _gravar(DADOS / "listas" / f"conv52_91_anexo_{anexo.lower()}.csv", ["item", "ncm", "descricao"], linhas)


if __name__ == "__main__":
    main()
