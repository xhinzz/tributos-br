"""NCMs dos Anexos I e II da Lei 10.485/2002 (autopeças monofásicas), do texto compilado do Planalto.

    python scripts/atualizar_monofasicos.py [L10485compilado.htm]

Saída: tributos_br/dados/listas/lei10485_anexo_i.csv e _anexo_ii.csv. O Anexo I é tabela de duas colunas lida
em ordem; o Anexo II é texto numerado, cada item com o NCM e a destinação que o condiciona.
"""

import csv
import re
import sys
import urllib.request
from pathlib import Path

URL = "https://www.planalto.gov.br/ccivil_03/leis/2002/L10485compilado.htm"
LISTAS = Path(__file__).resolve().parent.parent / "tributos_br" / "dados" / "listas"
# a lei cita a TIPI de 2012: códigos desdobrados ou absorvidos na NCM 2022 (desdobramento mantém o regime,
# SC Cosit 62/2018)
CORRELACAO_2022 = {"85071000": "850710", "84139100": "841391", "90303921": "90303990"}
CODIGO = re.compile(r"\b(\d{2}\.\d{2}|\d{4}(?:\.\d{1,2}){0,2})((?:\s+Ex\s+\d{2}(?:\s+e\s+\d{2})?)?)")


def _texto(html: bytes) -> str:
    texto = re.sub(r"<[^>]+>", " ", html.decode("cp1252"))
    return re.sub(r"\s+", " ", texto.replace("&nbsp;", " "))


def anexo_i(texto: str) -> list[list[str]]:
    trecho = texto[texto.index("ANEXO I CÓDIGO") : texto.index("ANEXO II 1.")]
    trecho = re.sub(r"\([^)]*\)", "", trecho)  # notas de redação no meio da tabela
    saida = []
    for codigo, ex in CODIGO.findall(trecho):
        codigo = codigo.replace(".", "")
        nota = f"código {codigo} da TIPI 2012, correlacionado com a NCM 2022" if codigo in CORRELACAO_2022 else ""
        saida.append([CORRELACAO_2022.get(codigo, codigo), ex.strip(), nota])
    return saida


def anexo_ii(texto: str) -> list[list[str]]:
    trecho = texto[texto.index("ANEXO II 1.") :]
    itens = re.findall(r"(\d{1,2})\. (.+?;|.+?\.)(?= \d{1,2}\. | \*|$)", trecho[len("ANEXO II ") :])
    saida = []
    for numero, descricao in itens[:15]:
        # o NCM do item é o primeiro "código X" ou "posição X"; os demais são a destinação
        codigo = re.search(r"(?:código|posição) (\d{2}\.\d{2}|\d{4}(?:\.\d{1,2}){0,2})", descricao)
        saida.append([numero, codigo[1].replace(".", ""), descricao.rstrip(";.")])
    return saida


def _gravar(nome: str, cabecalho, linhas):
    with (LISTAS / nome).open("w", encoding="utf-8", newline="") as f:
        escritor = csv.writer(f, lineterminator="\n")
        escritor.writerow(cabecalho)
        escritor.writerows(linhas)
    print(f"{nome}: {len(linhas)} linhas")


def main():
    if len(sys.argv) > 1:
        html = Path(sys.argv[1]).read_bytes()
    else:
        with urllib.request.urlopen(
            urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0"}), timeout=60
        ) as r:
            html = r.read()
    texto = _texto(html)
    _gravar("lei10485_anexo_i.csv", ["ncm", "ex", "nota"], anexo_i(texto))
    _gravar("lei10485_anexo_ii.csv", ["item", "ncm", "descricao"], anexo_ii(texto))


if __name__ == "__main__":
    main()
