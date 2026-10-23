import pytest

from tributos_br import cnpj


@pytest.mark.parametrize(
    "numero",
    [
        "11.222.333/0001-81",
        "00.000.000/0001-91",  # Banco do Brasil
        "12.ABC.345/01DE-35",  # exemplo oficial do CNPJ alfanumérico (Receita Federal)
        "12abc34501de35",
    ],
)
def test_validos(numero):
    assert cnpj.valido(numero)


@pytest.mark.parametrize(
    "numero", ["11.222.333/0001-82", "11111111111111", "1122233300018", "12.ABC.345/01DE-3A", "", "AB.CDE.FGH/IJKL-MN"]
)
def test_invalidos(numero):
    assert not cnpj.valido(numero)


def test_participante_recusa_cnpj_invalido_sem_rede():
    with pytest.raises(ValueError, match="CNPJ inválido"):
        cnpj.participante("11.222.333/0001-82")
