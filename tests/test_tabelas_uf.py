from datetime import date, timedelta
from decimal import Decimal
from itertools import pairwise

import pytest

from tributos_br import tabelas
from tributos_br.modelos import UFS


@pytest.mark.parametrize("uf", sorted(UFS))
def test_uma_linha_vigente_por_dia_desde_2025(uf):
    linhas = sorted((x for x in tabelas._ufs() if x["uf"] == uf), key=lambda x: x["vigencia_inicio"])
    assert linhas, uf
    for anterior, seguinte in pairwise(linhas):
        # sem buraco nem sobreposição entre vigências
        assert date.fromisoformat(anterior["vigencia_fim"]) + timedelta(days=1) == date.fromisoformat(
            seguinte["vigencia_inicio"]
        )
    assert date.fromisoformat(linhas[0]["vigencia_inicio"]) <= date(2025, 1, 1)
    assert not linhas[-1]["vigencia_fim"]
    for linha in linhas:
        assert linha["difal_base"] in ("unica", "dupla", "por_dentro")
        assert linha["difal_conferido"] in ("sim", "nao")
        assert Decimal(17) <= Decimal(linha["aliquota_interna"]) <= Decimal(23)
        assert linha["fonte"]


@pytest.mark.parametrize(
    "uf,data,aliquota",
    [
        ("AL", date(2026, 3, 31), Decimal(19)),
        ("AL", date(2026, 4, 1), Decimal("20.5")),
        ("MA", date(2025, 2, 23), Decimal(23)),
        ("PI", date(2025, 4, 1), Decimal("22.5")),
        ("RN", date(2025, 3, 19), Decimal(18)),
        ("RN", date(2025, 3, 20), Decimal(20)),
        ("SP", date(2026, 10, 23), Decimal(18)),
    ],
)
def test_mudancas_de_aliquota(uf, data, aliquota):
    assert tabelas.dados_uf(uf, data).aliquota_interna == aliquota


def test_fcp_geral():
    hoje = date(2026, 10, 23)
    assert {uf: tabelas.dados_uf(uf, hoje).fcp for uf in UFS if tabelas.dados_uf(uf, hoje).fcp} == {
        "AL": 1,
        "RJ": 2,
        "SE": 1,
    }


def test_data_fora_da_tabela():
    with pytest.raises(LookupError):
        tabelas.dados_uf("SP", date(2020, 1, 1))
