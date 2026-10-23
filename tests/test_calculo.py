"""Esperados calculados à mão; a conta está no comentário."""

import json
from datetime import date
from decimal import Decimal as D

import pytest

from tributos_br import Beneficio, Item, Nota, Participante, Regime, calcular, ipi
from tributos_br.__main__ import main

HOJE = date(2026, 10, 23)
NOTEBOOK = "84713012"  # IPI 15% na TIPI
CAL = "25221000"  # CEST 10.001.00, IVA-ST de SP 49%
MAQUINA = "84378010"  # Anexo I do Conv. 52/91


def nota(emit, dest, *itens, **kw):
    kw.setdefault("data", HOJE)
    return calcular(Nota(emit, dest, list(itens), **kw))


def tributos(resultado, i=0):
    return resultado.itens[i].tributos


def valores(resultado, i=0):
    return {nome: t.valor for nome, t in tributos(resultado, i).items()}


def test_venda_interna_lucro_real():
    r = nota(Participante("SP"), Participante("SP"), Item(NOTEBOOK, 1000))
    # ICMS 1000 × 18% = 180; PIS/COFINS sobre 1000 − 180 = 820; IBS/CBS sobre 820 − 13,53 − 62,32 = 744,15
    assert valores(r) == {
        "ICMS": D("180.00"),
        "PIS": D("13.53"),
        "COFINS": D("62.32"),
        "CBS": D("6.70"),
        "IBS_UF": D("0.74"),
        "IBS_MUN": D("0.00"),
    }
    assert tributos(r)["ICMS"].cst == "00"
    assert tributos(r)["PIS"].base == D(820)
    assert tributos(r)["CBS"].base == D("744.15")
    assert tributos(r)["CBS"].cst == "000" and tributos(r)["CBS"].extras["cclass_trib"] == "000001"
    # IBS/CBS não somam no total da nota em 2026 (NT 2025.002, regra VB01-10)
    assert r.valor_nota == D(1000)


def test_industria_para_revenda_interestadual_ipi_fora_da_base():
    r = nota(Participante("SP", industria=True), Participante("BA"), Item(NOTEBOOK, 1000))
    t = tributos(r)
    # IPI 15% = 150; entre contribuintes para revenda o IPI fica fora da base do ICMS: 1000 × 7% = 70
    assert (t["IPI"].valor, t["IPI"].cst) == (D(150), "50")
    assert (t["ICMS"].base, t["ICMS"].aliquota, t["ICMS"].valor) == (D(1000), D(7), D(70))
    # PIS 930 × 1,65% = 15,345 → 15,35; COFINS 930 × 7,6% = 70,68
    assert (t["PIS"].valor, t["COFINS"].valor) == (D("15.35"), D("70.68"))
    assert "DIFAL" not in t
    assert r.valor_nota == D(1150)


def test_industria_para_consumidor_final_ipi_na_base():
    r = nota(Participante("SP", industria=True), Participante("SP", contribuinte_icms=False), Item(NOTEBOOK, 1000))
    t = tributos(r)
    # base do ICMS 1000 + 150 de IPI = 1150 × 18% = 207; PIS/COFINS sobre 1000 − 207 = 793
    assert (t["ICMS"].base, t["ICMS"].valor) == (D(1150), D(207))
    assert (t["PIS"].valor, t["COFINS"].valor) == (D("13.08"), D("60.27"))
    # IBS/CBS: 1000 − 207 − 13,08 − 60,27 = 719,65 (o IPI não entra)
    assert t["CBS"].base == D("719.65") and t["CBS"].valor == D("6.48") and t["IBS_UF"].valor == D("0.72")


def test_difal_base_unica_com_fcp_rj():
    r = nota(Participante("SP", Regime.PRESUMIDO), Participante("RJ", contribuinte_icms=False), Item(NOTEBOOK, 1000))
    t = valores(r)
    # 12% de SP para RJ = 120; DIFAL 1000 × 20% − 120 = 80; FECP 1000 × 2% = 20
    assert (t["ICMS"], t["DIFAL"], t["FCP_DIFAL"]) == (D(120), D(80), D(20))
    # Presumido: PIS 880 × 0,65% = 5,72; COFINS 880 × 3% = 26,40
    assert (t["PIS"], t["COFINS"]) == (D("5.72"), D("26.40"))
    # IBS/CBS: 1000 − 120 − 80 − 20 − 5,72 − 26,40 = 747,88 (DIFAL e FCP saem da base)
    assert tributos(r)["CBS"].base == D("747.88")
    assert (t["CBS"], t["IBS_UF"]) == (D("6.73"), D("0.75"))
    assert tributos(r)["DIFAL"].extras["metodo"] == "unica"
    # o DIFAL não compõe o valor da nota
    assert r.valor_nota == D(1000)


@pytest.mark.parametrize(
    "metodo,base,difal",
    [
        ("unica", D(1000), D(130)),  # 1000 × (20% − 7%)
        ("dupla", D("1162.50"), D("162.50")),  # 930 / 0,8 = 1162,50; × 20% = 232,50 − 70
        ("por_dentro", D("1162.50"), D("151.13")),  # 1162,50 × 13% = 151,125
    ],
)
def test_tres_metodos_do_difal(metodo, base, difal):
    # PB: interna de 20%, sem FCP geral
    r = nota(Participante("SP"), Participante("PB", contribuinte_icms=False), Item(NOTEBOOK, 1000), metodo_difal=metodo)
    t = tributos(r)["DIFAL"]
    assert (t.base, t.valor) == (base, difal)
    assert "conferir" not in t.extras  # método informado pelo usuário


def test_difal_sem_metodo_conferido_avisa():
    r = nota(Participante("SP"), Participante("MS", contribuinte_icms=False), Item(NOTEBOOK, 1000))
    t = tributos(r)["DIFAL"]
    assert t.extras["metodo"] == "dupla"
    assert "conferir" in t.extras


def test_difal_dupla_bahia():
    r = nota(
        Participante("SP"), Participante("BA", contribuinte_icms=False), Item(NOTEBOOK, 1000), metodo_difal="dupla"
    )
    t = tributos(r)["DIFAL"]
    # 930 / (1 − 20,5%) = 1169,81; × 20,5% = 239,81 − 70 = 169,81
    assert (t.base, t.aliquota, t.valor) == (D("1169.81"), D("20.5"), D("169.81"))


def test_simples_nao_recolhe_difal():
    # STF, ADI 5.464
    r = nota(Participante("SP", Regime.SIMPLES), Participante("BA", contribuinte_icms=False), Item(NOTEBOOK, 1000))
    assert "DIFAL" not in tributos(r)


def test_importado_quatro_por_cento():
    r = nota(Participante("SP"), Participante("BA"), Item(NOTEBOOK, 1000, origem=1))
    assert tributos(r)["ICMS"].aliquota == 4 and tributos(r)["ICMS"].valor == D(40)


def test_fcp_proprio_na_operacao_interna():
    r = nota(Participante("RJ"), Participante("RJ"), Item(NOTEBOOK, 1000))
    assert valores(r)["ICMS"] == D(200) and valores(r)["FCP"] == D(20)


def test_frete_seguro_outras_e_desconto():
    item = Item(NOTEBOOK, 1000, frete=D(50), seguro=D(10), outras=D(5), desconto=D(65))
    r = nota(Participante("SP", industria=True), Participante("SP"), item)
    t = tributos(r)
    # valor da operação 1000 + 50 + 10 + 5 − 65 = 1000: base do IPI e do ICMS
    assert t["IPI"].base == D(1000) and t["ICMS"].base == D(1000)
    # vNF = 1000 − 65 + 50 + 10 + 5 + 150 de IPI
    assert r.valor_nota == D(1150)


def test_st_interna_com_mva_da_tabela():
    item = Item(CAL, 1000, cest="1000100", aliquota_ipi=D(10))
    r = nota(Participante("SP", industria=True), Participante("SP"), item)
    t = tributos(r)
    # ICMS próprio 1000 × 18% = 180 (IPI fora: revenda); ST (1000 + 100) × 1,49 = 1639 × 18% = 295,02 − 180
    assert t["ICMS"].cst == "10"
    assert (t["ICMS_ST"].base, t["ICMS_ST"].valor) == (D("1639.00"), D("115.02"))
    assert t["ICMS_ST"].extras["mva_aplicada"] == D(49)
    assert r.valor_nota == D("1215.02")


def test_st_interestadual_mva_ajustada():
    r = nota(Participante("MG"), Participante("SP"), Item(CAL, 1000, cest="1000100"))
    st = tributos(r)["ICMS_ST"]
    # MVA ajustada = 1,49 × (1 − 12%) / (1 − 18%) − 1 = 59,9024%; base 1599,02 × 18% = 287,82 − 120 de ICMS próprio
    assert st.extras["mva_aplicada"] == D("59.9024")
    assert (st.base, st.valor) == (D("1599.02"), D("167.82"))


def test_st_do_simples_sem_mva_ajustada_e_com_deducao_presumida():
    r = nota(Participante("MG", Regime.SIMPLES), Participante("SP"), Item(CAL, 1000, cest="1000100"))
    t = tributos(r)
    # Conv. 142/18, cl. 11ª, §1º: MVA original; cl. 13ª, §1º: deduz 12% × 1000 mesmo sem destaque
    assert t["ICMS"].cst == "202" and t["ICMS"].valor == 0
    assert t["ICMS_ST"].extras["mva_aplicada"] == D(49)
    assert t["ICMS_ST"].valor == D("148.20")  # 1490 × 18% = 268,20 − 120


def test_st_nao_se_aplica_a_consumidor_final():
    r = nota(Participante("SP"), Participante("SP", contribuinte_icms=False), Item(CAL, 1000, cest="1000100"))
    assert "ICMS_ST" not in tributos(r)
    with pytest.raises(ValueError, match="ST só cabe"):
        nota(Participante("SP"), Participante("SP", contribuinte_icms=False), Item(CAL, 1000, mva=D(40)))


def test_simples_csosn_e_credito():
    sem = nota(Participante("SP", Regime.SIMPLES), Participante("SP"), Item(NOTEBOOK, 1000))
    assert tributos(sem)["ICMS"].cst == "102"
    assert tributos(sem)["PIS"].cst == "49" and tributos(sem)["PIS"].valor == 0
    assert "CBS" not in tributos(sem)  # LC 214/2025, art. 348, III, c
    emit = Participante("SP", Regime.SIMPLES, aliquota_credito_sn=D("1.25"))
    com = nota(emit, Participante("SP"), Item(NOTEBOOK, 1000))
    assert tributos(com)["ICMS"].cst == "101" and tributos(com)["ICMS"].extras["valor_credito"] == D("12.50")
    # crédito só para quem está fora do Simples e revende
    assert tributos(nota(emit, Participante("SP", Regime.SIMPLES), Item(NOTEBOOK, 1000)))["ICMS"].cst == "102"


def test_conv52_91_reducao_interestadual():
    r = nota(Participante("SP"), Participante("BA"), Item(MAQUINA, 1000, beneficio="conv52_91_anexo_i"))
    icms = tributos(r)["ICMS"]
    # redução de 26,5714%: base 734,29 × 7% = 51,40 (carga de 5,14%)
    assert (icms.cst, icms.base, icms.valor) == ("20", D("734.29"), D("51.40"))
    assert icms.extras["valor_desonerado"] == D("18.60")


def test_conv52_91_difal_respeita_a_carga_interna_do_destino():
    # cl. 5ª: a carga total é a interna (8,80%). RJ: redução no destino de 1 − 8,8/20 = 56%
    r = nota(
        Participante("SP"),
        Participante("RJ", contribuinte_icms=False),
        Item(MAQUINA, 1000, beneficio="conv52_91_anexo_i"),
    )
    t = tributos(r)
    # origem: 12% com redução de 26,6667% = 88,00; destino: 440 × 20% = 88 − 88 = 0
    assert t["ICMS"].valor == D(88)
    assert (t["DIFAL"].base, t["DIFAL"].valor) == (D(440), D(0))
    assert t["DIFAL"].extras["reducao_base_destino"] == D(56)


def test_beneficio_recusado_com_motivo():
    with pytest.raises(ValueError, match="fora da lista"):
        nota(Participante("SP"), Participante("BA"), Item("87019100", 1000, beneficio="conv52_91_anexo_i"))


def test_isencao_manual_com_cbenef():
    b = Beneficio("isencao", cbenef="SP099999", fundamento="RICMS/SP, Anexo I")
    t = tributos(nota(Participante("SP"), Participante("SP"), Item(NOTEBOOK, 1000, beneficio=b)))["ICMS"]
    assert (t.cst, t.valor, t.extras["cbenef"], t.extras["valor_desonerado"]) == ("40", 0, "SP099999", D(180))


def test_diferimento_parcial():
    b = Beneficio("diferimento", percentual=D("33.33"))
    t = tributos(nota(Participante("SP"), Participante("SP"), Item(NOTEBOOK, 1000, beneficio=b)))["ICMS"]
    # vICMSOp 180; diferido 180 × 33,33% = 59,99; devido 120,01
    assert t.cst == "51"
    assert (t.extras["valor_operacao"], t.extras["valor_diferido"], t.valor) == (D(180), D("59.99"), D("120.01"))


def test_ipi_nao_tributado_e_aliquota_zero():
    nt = tributos(nota(Participante("SP", industria=True), Participante("SP"), Item("01012100", 1000)))["IPI"]
    assert (nt.cst, nt.valor) == ("53", 0)
    zero = tributos(nota(Participante("SP", industria=True), Participante("SP"), Item("30049099", 1000)))["IPI"]
    assert zero.cst == "51"


def test_ipi_zerado_a_partir_de_2027():
    n = Nota(Participante("SP", industria=True), Participante("SP"), [Item(NOTEBOOK, 1000)], data=date(2027, 1, 4))
    t = ipi.calcular(n, n.itens[0])
    assert (t.cst, t.valor) == ("51", 0) and "ADCT art. 126" in t.fundamento


def test_ano_sem_aliquota_de_ibs_cbs_publicada():
    with pytest.raises(LookupError, match="IBS/CBS de 2027"):
        nota(Participante("SP"), Participante("SP"), Item(NOTEBOOK, 1000), data=date(2027, 1, 4))


def test_ibs_cbs_fora_antes_de_2026():
    r = nota(Participante("SP"), Participante("SP"), Item(NOTEBOOK, 1000), data=date(2025, 12, 31))
    assert "CBS" not in tributos(r)


def test_totais_de_nota_com_dois_itens():
    r = nota(Participante("SP"), Participante("SP"), Item(NOTEBOOK, 1000), Item(NOTEBOOK, D("500.50")))
    # 180 + 90,09
    assert r.totais["ICMS"] == D("270.09")
    assert r.valor_nota == D("1500.50")


@pytest.mark.parametrize(
    "kwargs,erro",
    [
        ({"ncm": "8471", "valor": 1}, "NCM"),
        ({"ncm": NOTEBOOK, "valor": 1, "origem": 9}, "origem"),
        ({"ncm": NOTEBOOK, "valor": -1}, "negativo"),
        ({"ncm": NOTEBOOK, "valor": 10, "desconto": 11}, "desconto"),
    ],
)
def test_validacao_do_item(kwargs, erro):
    with pytest.raises(ValueError, match=erro):
        Item(**kwargs)


def test_validacao_participante_e_cest():
    with pytest.raises(ValueError, match="UF"):
        Participante("XX")
    with pytest.raises(ValueError, match="não pertence"):
        nota(Participante("SP"), Participante("SP"), Item(NOTEBOOK, 1000, cest="1000100"))


def test_float_nao_herda_erro_binario():
    assert Item(NOTEBOOK, 0.1).valor == D("0.1")


def test_linha_de_comando(tmp_path, capsys):
    arquivo = tmp_path / "nota.json"
    arquivo.write_text(
        json.dumps(
            {
                "data": "2026-10-23",
                "emitente": {"uf": "SP", "regime": "presumido"},
                "destinatario": {"uf": "RJ", "contribuinte_icms": False},
                "itens": [{"ncm": NOTEBOOK, "valor": "1000"}],
            }
        ),
        encoding="utf-8",
    )
    assert main([str(arquivo)]) == 0
    saida = json.loads(capsys.readouterr().out)
    assert saida["totais"]["DIFAL"] == "80.00"
    assert saida["itens"][0]["tributos"]["ICMS"]["aliquota"] == "12"


def test_linha_de_comando_erro(tmp_path, capsys):
    arquivo = tmp_path / "nota.json"
    arquivo.write_text(
        json.dumps({"emitente": {"uf": "SP"}, "destinatario": {"uf": "ZZ"}, "itens": []}), encoding="utf-8"
    )
    assert main([str(arquivo)]) == 1
    assert "UF inválida" in capsys.readouterr().err


@pytest.mark.parametrize(
    "motivo,cst", [("monofasico", "04"), ("aliquota_zero", "06"), ("isenta", "07"), ("suspensao", "09")]
)
def test_pis_cofins_sem_incidencia(motivo, cst):
    r = nota(Participante("SP"), Participante("SP"), Item(NOTEBOOK, 1000, pis_cofins=motivo))
    t = tributos(r)
    assert (t["PIS"].cst, t["PIS"].valor, t["COFINS"].cst, t["COFINS"].valor) == (cst, 0, cst, 0)
    # sem PIS/COFINS a deduzir, a base do IBS/CBS é 1000 − 180 de ICMS
    assert t["CBS"].base == D(820)


def test_pis_cofins_motivo_invalido():
    with pytest.raises(ValueError, match="pis_cofins"):
        Item(NOTEBOOK, 1, pis_cofins="imune")
