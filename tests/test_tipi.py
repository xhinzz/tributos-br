from decimal import Decimal

import pytest

from tributos_br import tabelas


@pytest.mark.parametrize(
    "ncm,ex,esperado",
    [
        ("84713012", "", Decimal(15)),  # notebook
        ("30049099", "", Decimal(0)),  # medicamento
        ("87032100", "", Decimal("5.27")),
        ("22030000", "", Decimal("3.9")),  # cerveja de malte
    ],
)
def test_aliquotas(ncm, ex, esperado):
    assert tabelas.aliquota_tipi(ncm, ex) == esperado


def test_nao_tributado():
    assert tabelas.aliquota_tipi("01012100") is None


def test_ncm_inexistente():
    with pytest.raises(KeyError):
        tabelas.aliquota_tipi("99999999")


def test_tabela_sem_notacao_cientifica_nem_ruido_de_float():
    for (ncm, _), aliquota in tabelas._tipi().items():
        assert len(ncm) == 8 and ncm.isdigit()
        assert aliquota == "NT" or Decimal(aliquota) == round(Decimal(aliquota), 2)
        assert "E" not in aliquota
