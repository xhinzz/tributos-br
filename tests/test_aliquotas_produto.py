"""Alíquota interna própria do produto (RICMS de cada UF), com o FCP que só vale para consumidor final."""

from datetime import date
from decimal import Decimal as D

import pytest

from tributos_br import Item, Nota, Participante, calcular, tabelas

HOJE = date(2026, 10, 23)


def icms(emit, dest, ncm, final=False):
    destinatario = Participante(dest, contribuinte_icms=not final)
    t = calcular(Nota(Participante(emit), destinatario, [Item(ncm, 1000)], data=HOJE)).itens[0].tributos
    return t


def test_cerveja_em_sp_com_fecoep_so_para_consumidor_final():
    revenda = icms("SP", "SP", "22030000")
    assert (revenda["ICMS"].aliquota, revenda["ICMS"].valor) == (D(20), D(200)) and "FCP" not in revenda
    final = icms("SP", "SP", "22030000", final=True)
    assert (final["ICMS"].valor, final["FCP"].aliquota, final["FCP"].valor) == (D(200), D(2), D(20))
    assert "art. 54-A" in final["ICMS"].fundamento


def test_fumo_em_sp_30_mais_2():
    t = icms("SP", "SP", "24022000", final=True)
    assert (t["ICMS"].aliquota, t["FCP"].aliquota) == (D(30), D(2))


@pytest.mark.parametrize(
    "ncm,aliquota",
    [
        ("94036000", D(12)),  # móveis de madeira
        ("94012000", D(18)),  # assentos de veículos: exceção do inciso XIII
        ("33049910", D(25)),  # cosmético
        ("33051000", D(18)),  # xampu: fora dos 25%
        ("87114000", D(25)),  # moto acima de 250 cm³
        ("84713012", D(18)),  # sem alíquota própria: modal
    ],
)
def test_aliquotas_de_sp(ncm, aliquota):
    assert icms("SP", "SP", ncm)["ICMS"].aliquota == aliquota


def test_condicao_que_o_ncm_nao_decide_avisa():
    assert "§1º" in icms("SP", "SP", "72142000")["ICMS"].extras["conferir"]


def test_difal_usa_a_aliquota_do_produto_no_destino():
    # cosmético de MG para consumidor final em SP: 25% em SP; 1000 × 25% − 120 = 130
    t = icms("MG", "SP", "33049910", final=True)["DIFAL"]
    assert (t.aliquota, t.valor) == (D(25), D(130))


def test_perfume_em_mg_com_fem_ate_2026():
    final = icms("MG", "MG", "33049910", final=True)
    assert (final["ICMS"].aliquota, final["FCP"].aliquota) == (D(25), D(2))
    assert "FCP" not in icms("MG", "MG", "33049910")
    depois = tabelas.aliquota_produto("MG", "33049910", date(2027, 1, 1), final=True)
    assert (depois.aliquota, depois.fcp) == (D(25), None)


def test_xampu_em_mg_sem_fem():
    t = icms("MG", "MG", "33051000", final=True)
    assert t["ICMS"].aliquota == 25 and "FCP" not in t


def test_tabela_sem_codigo_que_sumiu_da_ncm():
    tipi = {ncm for ncm, _ in tabelas._tipi()}
    for linha in tabelas._aliquotas_produto():
        for codigo in filter(None, linha["ncm"].split("|") + linha["excecoes"].split("|")):
            assert any(n.startswith(codigo) for n in tipi), (linha["uf"], codigo)
        assert linha["destinatario"] in ("", "final", "nao_final")


@pytest.mark.parametrize(
    "ncm,revenda,final",
    [
        ("33049910", (D(25), None), (D(23), D(2))),  # perfume e cosmético: art. 14, III, f e §9º, VI
        ("22030000", (D(29), None), (D(27), D(2))),  # cerveja
        ("24022000", (D(29), None), (D(27), D(2))),  # cigarro: a linha de 2402 vence a de tabacaria (24)
        ("22011000", (D("19.5"), None), (D("17.5"), D(2))),  # água mineral: modal fora do consumidor final
        ("22021000", (D(20), None), (D(18), D(2))),  # refrigerante
    ],
)
def test_pr_muda_a_aliquota_para_consumidor_final(ncm, revenda, final):
    def par(t):
        return t["ICMS"].aliquota, t["FCP"].aliquota if "FCP" in t else None

    assert par(icms("PR", "PR", ncm)) == revenda
    assert par(icms("PR", "PR", ncm, final=True)) == final


def test_pr_maquina_industrial_a_12_mas_nao_a_parte():
    assert icms("PR", "PR", "84186910")["ICMS"].aliquota == 12
    assert icms("PR", "PR", "84189900")["ICMS"].aliquota == D("19.5")  # "Partes" da 84.18, pela TIPI


def test_rj_perfume_com_fecp_geral_e_aviso_da_carga():
    t = icms("RJ", "RJ", "33030010")
    assert (t["ICMS"].aliquota, t["FCP"].aliquota) == (D(25), D(2))
    assert "Dec. 45.607/2016" in t["ICMS"].extras["conferir"]


def test_difal_para_consumidor_final_no_pr_usa_a_aliquota_do_paragrafo_9():
    t = icms("SP", "PR", "33049910", final=True)
    assert (t["DIFAL"].aliquota, t["FCP_DIFAL"].aliquota) == (D(23), D(2))
