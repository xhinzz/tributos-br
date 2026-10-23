import pytest

from tributos_br.icms import aliquota_interestadual

SUL_SUDESTE_SEM_ES = ["MG", "PR", "RJ", "RS", "SC", "SP"]
NORTE_NORDESTE_CO_ES = [
    "AC",
    "AL",
    "AM",
    "AP",
    "BA",
    "CE",
    "DF",
    "ES",
    "GO",
    "MA",
    "MS",
    "MT",
    "PA",
    "PB",
    "PE",
    "PI",
    "RN",
    "RO",
    "RR",
    "SE",
    "TO",
]


@pytest.mark.parametrize("origem_uf", SUL_SUDESTE_SEM_ES)
@pytest.mark.parametrize("destino_uf", NORTE_NORDESTE_CO_ES)
def test_sete_por_cento(origem_uf, destino_uf):
    assert aliquota_interestadual(origem_uf, destino_uf, 0)[0] == 7


@pytest.mark.parametrize(
    "origem_uf,destino_uf",
    [("SP", "RJ"), ("MG", "SP"), ("RS", "PR"), ("BA", "SP"), ("ES", "SP"), ("ES", "BA"), ("GO", "MT"), ("AM", "PA")],
)
def test_doze_por_cento(origem_uf, destino_uf):
    assert aliquota_interestadual(origem_uf, destino_uf, 0)[0] == 12


@pytest.mark.parametrize("origem", [1, 2, 3, 8])
def test_importados_quatro_por_cento(origem):
    assert aliquota_interestadual("SP", "BA", origem)[0] == 4
    assert aliquota_interestadual("BA", "SP", origem)[0] == 4


@pytest.mark.parametrize("origem", [0, 4, 5, 6, 7])
def test_origens_fora_da_resolucao_13(origem):
    assert aliquota_interestadual("BA", "SP", origem)[0] == 12
