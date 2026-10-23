"""Prints do README (docs/img/*.svg), gerados do cálculo de verdade. Requer rich.

python scripts/gerar_imagens.py
"""

import io
import sys
from datetime import date
from pathlib import Path

from rich.console import Console
from rich.table import Table

from tributos_br import Item, Nota, Participante, auditar, calcular

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tests.nfe import item, nfe

DESTINO = Path(__file__).resolve().parent.parent / "docs" / "img"
HOJE = date(2026, 10, 23)


def _br(valor) -> str:
    return f"{valor:,.2f}".translate(str.maketrans(",.", ".,"))


def _pct(valor) -> str:
    return f"{valor}".replace(".", ",") + "%"


def _tabela(titulo: str, nota: Nota) -> Table:
    tabela = Table(title=titulo, title_justify="left", header_style="bold cyan", border_style="grey50")
    for coluna, alinhamento in (
        ("tributo", "left"),
        ("base", "right"),
        ("alíq.", "right"),
        ("valor", "right"),
        ("CST", "center"),
        ("fundamento", "left"),
    ):
        tabela.add_column(coluna, justify=alinhamento, overflow="fold")
    resultado = calcular(nota)
    for nome, t in resultado.itens[0].tributos.items():
        tabela.add_row(
            nome,
            _br(t.base),
            _pct(t.aliquota),
            f"[bold]{_br(t.valor)}[/]",
            t.cst or "-",
            t.fundamento,
            style="yellow" if "conferir" in t.extras else None,
        )
    tabela.caption = f"valor da nota: {_br(resultado.valor_nota)}"
    tabela.caption_justify = "right"
    return tabela


def _auditoria() -> Table:
    # interestadual a 18% em vez de 12%, DIFAL esquecido e CBS que não fecha
    icms = {"ICMS00": {"orig": 0, "CST": "00", "modBC": 3, "vBC": "1000.00", "pICMS": "18.00", "vICMS": "180.00"}}
    ibscbs = {
        "CST": "000",
        "cClassTrib": "000001",
        "gIBSCBS": {
            "vBC": "744.15",
            "gIBSUF": {"pIBSUF": "0.1000", "vIBSUF": "0.74"},
            "gIBSMun": {"pIBSMun": "0.0000", "vIBSMun": "0.00"},
            "vIBS": "0.74",
            "gCBS": {"pCBS": "0.9000", "vCBS": "7.10"},
        },
    }
    relatorio = auditar(nfe(item(icms=icms, ibscbs=ibscbs), uf_dest="RJ", ind_ie_dest=9, ind_final=1))
    tabela = Table(
        title="Auditoria de uma NF-e de SP para consumidor final no RJ",
        title_justify="left",
        header_style="bold cyan",
        border_style="grey50",
    )
    for coluna in ("tipo", "item", "campo", "na nota", "esperado", "por quê"):
        tabela.add_column(coluna, overflow="fold")
    cores = {"conta": "red", "regra": "magenta", "aviso": "yellow"}
    for a in relatorio.achados:
        tabela.add_row(
            f"[{cores[a.tipo]}]{a.tipo}[/]",
            str(a.item or "-"),
            a.campo,
            _br(a.nota) if a.nota is not None else "ausente",
            _br(a.esperado) if a.esperado else "-",
            a.detalhe[:90],
        )
    return tabela


def _salvar(nome: str, *tabelas: Table):
    console = Console(record=True, width=150, file=io.StringIO())
    for tabela in tabelas:
        console.print(tabela)
        console.print()
    console.save_svg(str(DESTINO / nome), title="tributos-br")


def main():
    DESTINO.mkdir(parents=True, exist_ok=True)
    consumidor = Nota(
        Participante("SP", "real", industria=True),
        Participante("RJ", contribuinte_icms=False),
        [Item("84713012", "1000")],
        data=HOJE,
    )
    st = Nota(Participante("MG"), Participante("RJ"), [Item("38151210", "1000", cest="0100100")], data=HOJE)
    beneficio = Nota(
        Participante("SP"), Participante("BA"), [Item("84378010", "1000", beneficio="conv52_91_anexo_i")], data=HOJE
    )
    _salvar("consumidor_final.svg", _tabela("Indústria de SP vende notebook a consumidor final no RJ", consumidor))
    _salvar(
        "st_e_beneficio.svg",
        _tabela("Autopeça de MG para o RJ: Prot. 41/08, MVA de 71,78% ajustada para 88,958%", st),
        _tabela("SP -> BA com o Conv. 52/91: carga de 5,14%", beneficio),
    )
    _salvar("auditoria.svg", _auditoria())
    print(f"imagens em {DESTINO}")


if __name__ == "__main__":
    main()
