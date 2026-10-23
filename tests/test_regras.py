"""Base de regras: benefícios (Conv. 100/97 e 52/91), CEST (Conv. 142/18) e MVA, conferidos contra o texto dos atos."""

from datetime import date
from decimal import Decimal

import pytest

from tributos_br import tabelas
from tributos_br.modelos import Tratamento

HOJE = date(2026, 10, 23)
MAQUINA = "84378010"  # Anexo I do Conv. 52/91 (máquinas para a indústria de moagem de grãos)
TRATOR = "87019100"  # fora dos anexos


def test_conv52_91_carga_5_14_de_sul_sudeste_para_nordeste():
    regra = tabelas.regra("conv52_91_anexo_i", MAQUINA, "SP", "BA", Decimal(7), HOJE)
    assert regra.tratamento == Tratamento.REDUCAO_BASE
    # 7% × (1 − 26,5714%) = 5,14%
    assert regra.percentual == Decimal("26.5714")
    assert (Decimal(7) * (1 - regra.percentual / 100)).quantize(Decimal("0.01")) == Decimal("5.14")


def test_conv52_91_carga_8_80_nas_demais_e_nas_internas():
    assert tabelas.regra("conv52_91_anexo_i", MAQUINA, "BA", "SP", Decimal(12), HOJE).percentual == Decimal("26.6667")
    interna = tabelas.regra("conv52_91_anexo_i", MAQUINA, "SP", "SP", Decimal(18), HOJE)
    assert (Decimal(18) * (1 - interna.percentual / 100)).quantize(Decimal("0.01")) == Decimal("8.80")


def test_conv52_91_anexo_ii_cargas():
    agricola = tabelas._lista("conv52_91_anexo_ii")[0]
    assert tabelas.regra("conv52_91_anexo_ii", agricola, "PR", "MT", Decimal(7), HOJE).percentual == Decimal("41.4286")
    assert tabelas.regra("conv52_91_anexo_ii", agricola, "MT", "PR", Decimal(12), HOJE).percentual == Decimal("41.6667")
    interna = tabelas.regra("conv52_91_anexo_ii", agricola, "PR", "PR", Decimal("19.5"), HOJE)
    assert (Decimal("19.5") * (1 - interna.percentual / 100)).quantize(Decimal("0.01")) == Decimal("5.60")


def test_conv52_91_recusa_ncm_fora_do_anexo():
    with pytest.raises(ValueError, match="fora da lista"):
        tabelas.regra("conv52_91_anexo_i", TRATOR, "SP", "BA", Decimal(7), HOJE)


def test_conv52_91_termina_em_2026():
    with pytest.raises(ValueError, match="vigência"):
        tabelas.regra("conv52_91_anexo_i", MAQUINA, "SP", "BA", Decimal(7), date(2027, 1, 1))


def test_conv52_91_sem_faixa_para_importado_a_4_por_cento():
    with pytest.raises(ValueError, match="alíquota"):
        tabelas.regra("conv52_91_anexo_i", MAQUINA, "SP", "BA", Decimal(4), HOJE)


def test_conv100_97_reducoes_interestaduais():
    assert tabelas.regra("conv100_97_cl1", "38089199", "MT", "GO", Decimal(12), HOJE).percentual == 60
    assert tabelas.regra("conv100_97_cl2", "23040010", "MT", "SP", Decimal(12), HOJE).percentual == 30
    with pytest.raises(ValueError, match="interestadual"):
        tabelas.regra("conv100_97_cl1", "38089199", "MT", "MT", Decimal(17), HOJE)


def test_conv100_97_fertilizante_carga_4_por_cento_em_qualquer_operacao():
    ureia = "31021010"
    assert tabelas.regra("conv100_97_cl3a", ureia, "SP", "MT", Decimal(7), HOJE).percentual == Decimal("42.8571")
    assert tabelas.regra("conv100_97_cl3a", ureia, "MT", "PR", Decimal(12), HOJE).percentual == Decimal("66.6667")
    assert tabelas.regra("conv100_97_cl3a", ureia, "MT", "MT", Decimal(17), HOJE).percentual == Decimal("76.4706")
    # a 4% a carga já é a do convênio: nada a reduzir
    assert tabelas.regra("conv100_97_cl3a", ureia, "SP", "MT", Decimal(4), HOJE).percentual == 0


def test_conv100_97_vale_ate_2027():
    tabelas.regra("conv100_97_cl1", "38089199", "MT", "GO", Decimal(12), date(2027, 12, 31))
    with pytest.raises(ValueError, match="vigência"):
        tabelas.regra("conv100_97_cl1", "38089199", "MT", "GO", Decimal(12), date(2028, 1, 1))


def test_beneficio_desconhecido():
    with pytest.raises(ValueError, match="desconhecido"):
        tabelas.regra("conv999", MAQUINA, "SP", "BA", Decimal(7), HOJE)


def test_sugerir_lista_so_o_que_pode_cobrir():
    sugestoes = tabelas.sugerir(MAQUINA, HOJE)
    assert sugestoes[0][::2] == ("conv52_91_anexo_i", "ncm")
    assert "conv52_91_anexo_ii" not in [c for c, _, _ in sugestoes]
    # convênio sem lista de NCM: cabe ao usuário conferir a descrição
    assert ("conv100_97_cl1", "descricao") in [(c, k) for c, _, k in sugestoes]
    assert "conv52_91_anexo_i" not in [c for c, _, _ in tabelas.sugerir(TRATOR, HOJE)]


def test_listas_do_conv52_91_tem_ncm_valido():
    for anexo in ("conv52_91_anexo_i", "conv52_91_anexo_ii"):
        ncms = tabelas._lista(anexo)
        assert len(ncms) > 40
        assert all(n.isdigit() and 4 <= len(n) <= 8 for n in ncms)


@pytest.mark.parametrize(
    "cest,ncm",
    [("1000100", "25221000"), ("2100100", "73211100"), ("0100100", "38151210"), ("1300100", "30049099")],
)
def test_cest_compativel(cest, ncm):
    tabelas.conferir_cest(cest, ncm)


def test_cest_incompativel_ou_inexistente():
    with pytest.raises(ValueError, match="não pertence"):
        tabelas.conferir_cest("2100100", "25221000")
    with pytest.raises(ValueError, match="não existe"):
        tabelas.conferir_cest("9999999", "25221000")


def test_tabela_cest_sem_redacao_antiga():
    cests = tabelas._cest()
    assert 1000 <= len(cests) <= 1100
    assert all(len(c) == 7 and c.isdigit() for c in cests)


@pytest.mark.parametrize(
    "cest,data,esperado",
    [
        ("1000100", date(2026, 10, 23), Decimal(49)),
        ("1000600", date(2026, 3, 31), Decimal(84)),
        ("1000600", date(2026, 4, 1), Decimal(72)),
        ("2100100", date(2026, 8, 1), Decimal(38)),
    ],
)
def test_mva_de_sp_por_vigencia(cest, data, esperado):
    ncm = tabelas._cest()[cest][0].ljust(8, "0")
    assert tabelas.mva("SP", ncm, cest, data)[0] == esperado


def test_mva_inexistente_fora_da_vigencia_ou_da_uf():
    assert tabelas.mva("SP", "73211100", "2100100", date(2026, 7, 31)) is None
    assert tabelas.mva("RJ", "25221000", "1000100", date(2026, 10, 23)) is None
