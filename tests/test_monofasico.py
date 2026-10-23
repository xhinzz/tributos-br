"""PIS/COFINS monofásico (Leis 10.147/2000, 10.485/2002 e 13.097/2015) e a extinção em 2027."""

from datetime import date
from decimal import Decimal as D

import pytest

from tributos_br import Item, Nota, Participante, calcular, pis_cofins, tabelas

HOJE = date(2026, 10, 23)
FABRICANTE, COMERCIO = Participante("SP", industria=True), Participante("SP")


def pis_cofins_de(emitente, ncm, destinatario=None, **item):
    item.setdefault("aliquota_ipi", D(0))
    nota = Nota(emitente, destinatario or Participante("SP"), [Item(ncm, 1000, **item)], data=HOJE)
    t = calcular(nota).itens[0].tributos
    return t["PIS"], t["COFINS"]


def test_medicamento_na_revenda_alíquota_zero():
    pis, cofins = pis_cofins_de(COMERCIO, "30049099")
    assert (pis.cst, pis.valor, cofins.cst, cofins.valor) == ("04", 0, "04", 0)
    assert "Lei 10.147/2000" in pis.fundamento


def test_medicamento_no_fabricante_concentra():
    pis, cofins = pis_cofins_de(FABRICANTE, "30049099")
    # base 1000 − 180 de ICMS = 820; 2,1% e 9,9%
    assert (pis.cst, pis.valor, cofins.valor) == ("02", D("17.22"), D("81.18"))


def test_excecao_da_lei_volta_ao_regime_comum():
    pis, _ = pis_cofins_de(COMERCIO, "30039056")  # 3003, exceto 3003.90.56
    assert (pis.cst, pis.aliquota) == ("01", D("1.65"))


def test_veiculo_com_base_reduzida():
    pis, cofins = pis_cofins_de(FABRICANTE, "87019100")
    # 820 × (1 − 48,1%) = 425,58; 2% e 9,6%
    assert pis.base == D("425.58") and pis.extras["reducao_base"] == D("48.1")
    assert (pis.valor, cofins.valor) == (D("8.51"), D("40.86"))


def test_automovel_sem_reducao_e_caminhao_avisa():
    pis, cofins = pis_cofins_de(FABRICANTE, "87032100")
    assert (pis.base, pis.valor, cofins.valor) == (D(820), D("16.40"), D("78.72"))
    assert "30,2%" in pis_cofins_de(FABRICANTE, "87042110")[0].extras["conferir"]


def test_autopeca_do_anexo_i():
    pis, cofins = pis_cofins_de(FABRICANTE, "87089990")  # 87.08 no Anexo I
    assert (pis.valor, cofins.valor) == (D("18.86"), D("88.56"))  # 820 × 2,3% e 10,8%
    assert "fabricante de veículos" in pis.extras["conferir"]
    assert pis_cofins_de(COMERCIO, "87089990")[0].cst == "04"


def test_autopeca_restrita_a_ex():
    assert "só o Ex 03 e 05" in pis_cofins_de(FABRICANTE, "40169990")[0].extras["conferir"]


def test_autopeca_do_anexo_ii_avisa_a_destinacao():
    assert "destinação" in pis_cofins_de(FABRICANTE, "84122110")[0].extras["conferir"]


def test_pneu_na_revenda():
    assert pis_cofins_de(COMERCIO, "40111000")[0].cst == "04"


def test_bebida_fria_tributa_atacado_e_reduz_para_consumidor_final():
    pis, cofins = pis_cofins_de(FABRICANTE, "22030000")
    assert (pis.cst, pis.valor, cofins.valor) == ("02", D("19.02"), D("87.58"))  # 820 × 2,32% e 10,68%
    atacado, _ = pis_cofins_de(COMERCIO, "22030000")
    assert (atacado.cst, atacado.aliquota) == ("02", D("2.32")) and "varejista" in atacado.extras["conferir"]
    # art. 25, §1º: 2,32% × (1 − 19,82%) = 1,8602%; 10,68% × (1 − 20,03%) = 8,5408%
    pis, cofins = pis_cofins_de(FABRICANTE, "22030000", Participante("SP", contribuinte_icms=False))
    assert (pis.aliquota, cofins.aliquota) == (D("1.8602"), D("8.5408"))
    assert (pis.valor, cofins.valor) == (D("15.25"), D("70.03"))


def test_varejista_de_bebida_informa_aliquota_zero():
    pis, _ = pis_cofins_de(COMERCIO, "22030000", pis_cofins="aliquota_zero")
    assert (pis.cst, pis.valor) == ("06", 0)


def test_simples_continua_no_das():
    assert pis_cofins_de(Participante("SP", "simples"), "30049099")[0].cst == "49"


def test_pis_cofins_extintos_em_2027():
    nota = Nota(COMERCIO, Participante("SP"), [Item("84713012", 1000)], data=date(2027, 1, 1))
    assert pis_cofins.calcular(nota, nota.itens[0], D(180)) == {}


def test_monofasico_termina_com_o_pis_em_2026():
    assert tabelas.monofasico("30049099", date(2026, 12, 31)) is not None
    assert tabelas.monofasico("30049099", date(2027, 1, 1)) is None


def test_todo_ncm_das_tabelas_existe_na_tipi_vigente():
    # a lei cita a TIPI de 2012; código que sumiu da NCM tem que ter sido correlacionado
    tipi = {ncm for ncm, _ in tabelas._tipi()}
    codigos = [linha["ncm"] for linha in tabelas._monofasicos() if not linha["ncm"].startswith("@")]
    codigos += list(tabelas._ex_da_lista("lei10485_anexo_i")) + list(tabelas._ex_da_lista("lei10485_anexo_ii"))
    sumidos = [c for c in codigos if not any(n.startswith(c) for n in tipi)]
    assert sumidos == []


@pytest.mark.parametrize("anexo,quantidade", [("lei10485_anexo_i", 51), ("lei10485_anexo_ii", 15)])
def test_anexos_da_lei_10485_completos(anexo, quantidade):
    assert len(tabelas._ex_da_lista(anexo)) == quantidade
