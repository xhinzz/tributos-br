"""Prints do README (docs/img/*.svg), gerados do cálculo de verdade. Requer rich.

python scripts/gerar_imagens.py
"""

import io
from datetime import date
from pathlib import Path

from rich.console import Console
from rich.table import Table

from tributos_br import Item, Nota, Participante, calcular

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
    st = Nota(Participante("MG"), Participante("SP"), [Item("25221000", "1000", cest="1000100")], data=HOJE)
    beneficio = Nota(
        Participante("SP"), Participante("BA"), [Item("84378010", "1000", beneficio="conv52_91_anexo_i")], data=HOJE
    )
    _salvar("consumidor_final.svg", _tabela("Indústria de SP vende notebook a consumidor final no RJ", consumidor))
    _salvar(
        "st_e_beneficio.svg",
        _tabela("MG -> SP com ST: MVA de 49% ajustada para 59,9024%", st),
        _tabela("SP -> BA com o Conv. 52/91: carga de 5,14%", beneficio),
    )
    print(f"imagens em {DESTINO}")


if __name__ == "__main__":
    main()
