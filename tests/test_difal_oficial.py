"""Exemplos numéricos publicados pelas próprias SEFAZ, reproduzidos pela tabela de métodos."""

from datetime import date
from decimal import Decimal as D

import pytest

from tributos_br import Item, Nota, Participante, calcular

HOJE = date(2026, 10, 23)


def difal(uf_origem, uf_destino, valor, data=HOJE, **item):
    nota = Nota(
        Participante(uf_origem),
        Participante(uf_destino, contribuinte_icms=False),
        [Item("84713012", valor, **item)],
        data=data,
    )
    return calcular(nota).itens[0].tributos


@pytest.mark.parametrize(
    "caso,origem,destino,valor,data,base,esperado",
    [
        # NE SEFAZ-CE 01/2024: 1.000 sem imposto / 0,80 = 1.250 × 13%
        ("CE", "SP", "CE", "1075.27", HOJE, D(1250), D("162.50")),
        # Parecer GEOT-GO 77/2024: 10.000 sem ICMS / 0,81 = 12.345,68 × 12%
        ("GO", "SP", "GO", "10752.69", HOJE, D("12345.68"), D("1481.48")),
        # NT 058/2026 MT, quadro 2: valor da nota × (17% − 7%)
        ("MT", "SP", "MT", "1000", HOJE, D(1000), D(100)),
        # NT 001/2024 MT, revogada em 12/08/2026: 930 / 0,83 × 10%
        ("MT antes", "SP", "MT", "1000", date(2026, 8, 11), D("1120.48"), D("112.05")),
        # PR: única até 06/01/2025, por dentro desde o Dec. 8.527/2025
        ("PR antes", "SP", "PR", "1000", date(2025, 1, 6), D(1000), D(75)),
        ("PR", "SP", "PR", "1000", date(2025, 1, 7), D("1093.17"), D("81.99")),
    ],
)
def test_exemplos_oficiais(caso, origem, destino, valor, data, base, esperado):
    t = difal(origem, destino, valor, data)["DIFAL"]
    assert (t.base, t.valor) == (base, esperado), caso
    assert "conferir" not in t.extras


def test_alagoas_comunicado_sre_21_2015():
    # BC 1.000; 20,5% + 1% de FECOEP; interestadual 7%: 135,00 + 10,00
    t = difal("SP", "AL", "1000")
    assert (t["DIFAL"].valor, t["FCP_DIFAL"].valor) == (D(135), D(10))


def test_tocantins_consulta_65_2021():
    # 1.000 de GO (12%) para TO, interna de 18% na época: (1.000 − 120) / 0,82 = 1.073,17 × 18% − 120
    t = difal("GO", "TO", "1000", aliquota_icms=D(18))["DIFAL"]
    assert (t.base, t.valor) == (D("1073.17"), D("73.17"))


@pytest.mark.parametrize("uf", ["AP", "BA", "MA", "MS", "SP"])
def test_ufs_sem_confirmacao_avisam(uf):
    origem = "RJ" if uf == "SP" else "SP"
    assert "conferir" in difal(origem, uf, "1000")["DIFAL"].extras
