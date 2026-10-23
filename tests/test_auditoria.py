from decimal import Decimal as D

import pytest

from tests.nfe import item, nfe
from tributos_br.__main__ import main
from tributos_br.auditoria import auditar


def achados(relatorio, tipo=None):
    return {(a.campo, a.item): (a.nota, a.esperado) for a in relatorio.achados if tipo in (None, a.tipo)}


def test_nota_certa_nao_tem_achado():
    r = auditar(nfe())
    assert r.ok and r.achados == []
    assert r.chave == "35261011222333000181550010000000011000000010"


def test_consumidor_final_em_outra_uf_completa():
    # o exemplo do README: IPI na base, DIFAL e FCP do RJ, IBS/CBS sobre 667,27
    xml = nfe(
        item(
            icms={
                "ICMS00": {"orig": 0, "CST": "00", "modBC": 3, "vBC": "1150.00", "pICMS": "12.00", "vICMS": "138.00"}
            },
            ipi={"CST": "50", "vBC": "1000.00", "pIPI": "15.00", "vIPI": "150.00"},
            pis={"PISAliq": {"CST": "01", "vBC": "862.00", "pPIS": "1.65", "vPIS": "14.22"}},
            cofins={"COFINSAliq": {"CST": "01", "vBC": "862.00", "pCOFINS": "7.60", "vCOFINS": "65.51"}},
            difal={
                "vBCUFDest": "1150.00",
                "vBCFCPUFDest": "1150.00",
                "pFCPUFDest": "2.00",
                "pICMSUFDest": "20.00",
                "pICMSInter": "12.00",
                "pICMSInterPart": "100.00",
                "vFCPUFDest": "23.00",
                "vICMSUFDest": "92.00",
                "vICMSUFRemet": "0.00",
            },
            ibscbs={
                "CST": "000",
                "cClassTrib": "000001",
                "gIBSCBS": {
                    "vBC": "667.27",
                    "gIBSUF": {"pIBSUF": "0.1000", "vIBSUF": "0.67"},
                    "gIBSMun": {"pIBSMun": "0.0000", "vIBSMun": "0.00"},
                    "vIBS": "0.67",
                    "gCBS": {"pCBS": "0.9000", "vCBS": "6.01"},
                },
            },
        ),
        uf_dest="RJ",
        ind_ie_dest=9,
        ind_final=1,
        v_nf="1150.00",
    )
    r = auditar(xml)
    assert r.ok, r.como_dict()


def test_aliquota_interestadual_errada_e_difal_esquecido():
    xml = nfe(
        item(
            icms={
                "ICMS00": {"orig": 0, "CST": "00", "modBC": 3, "vBC": "1000.00", "pICMS": "18.00", "vICMS": "180.00"}
            },
        ),
        uf_dest="RJ",
        ind_ie_dest=9,
        ind_final=1,
    )
    r = auditar(xml)
    regras = achados(r, "regra")
    assert regras[("pICMS", 1)] == (D(18), D(12))
    assert regras[("vICMS", 1)] == (D(180), D(120))
    # 1000 × 20% − 120 = 80 e FECP de 2% = 20, os dois ausentes
    assert regras[("vICMSUFDest", 1)] == (None, D(80))
    assert regras[("vFCPUFDest", 1)] == (None, D(20))
    # PIS/COFINS fecham com o ICMS da nota: a causa já está no ICMS, não repete
    assert ("vPIS", 1) not in regras and ("vCOFINS", 1) not in regras
    assert not r.ok


def test_conta_que_nao_fecha():
    xml = nfe(
        item(
            icms={
                "ICMS00": {"orig": 0, "CST": "00", "modBC": 3, "vBC": "1000.00", "pICMS": "18.00", "vICMS": "181.00"}
            },
            ibscbs={
                "CST": "000",
                "cClassTrib": "000001",
                "gIBSCBS": {
                    "vBC": "744.15",
                    "gIBSUF": {"pIBSUF": "0.1000", "vIBSUF": "0.74"},
                    "gIBSMun": {"pIBSMun": "0.0000", "vIBSMun": "0.00"},
                    "vIBS": "0.74",
                    "gCBS": {"pCBS": "0.9000", "vCBS": "7.00"},
                },
            },
        )
    )
    contas = achados(auditar(xml), "conta")
    assert contas[("vICMS", 1)] == (D(181), D(180))
    assert contas[("vCBS", 1)] == (D(7), D("6.70"))
    # base do IBS/CBS pela UB16-10 com o vICMS da nota: 1000 − 181 − 13,53 − 62,32
    assert contas[("vBC (IBS/CBS)", 1)] == (D("744.15"), D("743.15"))


def test_aliquota_propria_do_produto_e_aviso_e_nao_contamina_o_resto():
    # alimento a 12% em SP: base do PIS 880, CBS sobre 880 − 14,52 − 66,88 = 798,60
    xml = nfe(
        item(
            ncm="19052090",
            icms={
                "ICMS00": {"orig": 0, "CST": "00", "modBC": 3, "vBC": "1000.00", "pICMS": "12.00", "vICMS": "120.00"}
            },
            pis={"PISAliq": {"CST": "01", "vBC": "880.00", "pPIS": "1.65", "vPIS": "14.52"}},
            cofins={"COFINSAliq": {"CST": "01", "vBC": "880.00", "pCOFINS": "7.60", "vCOFINS": "66.88"}},
            ibscbs={
                "CST": "000",
                "cClassTrib": "000001",
                "gIBSCBS": {
                    "vBC": "798.60",
                    "gIBSUF": {"pIBSUF": "0.1000", "vIBSUF": "0.80"},
                    "gIBSMun": {"pIBSMun": "0.0000", "vIBSMun": "0.00"},
                    "vIBS": "0.80",
                    "gCBS": {"pCBS": "0.9000", "vCBS": "7.19"},
                },
            },
        )
    )
    r = auditar(xml)
    assert r.ok, r.como_dict()
    assert achados(r, "aviso") == {("alíquota interna", 1): (D(12), D(18))}


def test_icms_na_base_do_pis_e_aviso():
    xml = nfe(
        item(
            pis={"PISAliq": {"CST": "01", "vBC": "1000.00", "pPIS": "1.65", "vPIS": "16.50"}},
            cofins={"COFINSAliq": {"CST": "01", "vBC": "1000.00", "pCOFINS": "7.60", "vCOFINS": "76.00"}},
            ibscbs={
                "CST": "000",
                "cClassTrib": "000001",
                "gIBSCBS": {
                    "vBC": "727.50",
                    "gIBSUF": {"pIBSUF": "0.1000", "vIBSUF": "0.73"},
                    "gIBSMun": {"pIBSMun": "0.0000", "vIBSMun": "0.00"},
                    "vIBS": "0.73",
                    "gCBS": {"pCBS": "0.9000", "vCBS": "6.55"},
                },
            },
        )
    )
    r = auditar(xml)
    assert r.ok, r.como_dict()
    assert set(achados(r, "aviso")) == {("vBC (PIS)", 1), ("vBC (COFINS)", 1)}


def test_st_que_nao_fecha_e_cst_sem_st():
    icms = {
        "ICMS10": {
            "orig": 0,
            "CST": "10",
            "modBC": 3,
            "vBC": "1000.00",
            "pICMS": "18.00",
            "vICMS": "180.00",
            "modBCST": 4,
            "pMVAST": "49.00",
            "vBCST": "1490.00",
            "pICMSST": "18.00",
            "vICMSST": "90.00",
        }
    }
    r = auditar(nfe(item(ncm="25221000", CEST="1000100", icms=icms), v_nf="1090.00"))
    contas = achados(r, "conta")
    # 1490 × 18% = 268,20 − 180
    assert contas[("vICMSST", 1)] == (D(90), D("88.20"))
    assert ("vBCST", 1) not in contas


def test_cest_incompativel():
    r = auditar(nfe(item(CEST="1000100")))
    assert ("CEST", 1) in achados(r, "regra")


def test_simples_csosn():
    icms = {"ICMSSN102": {"orig": 0, "CSOSN": "102"}}
    pis = {"PISOutr": {"CST": "49", "vBC": "0.00", "pPIS": "0.00", "vPIS": "0.00"}}
    cofins = {"COFINSOutr": {"CST": "49", "vBC": "0.00", "pCOFINS": "0.00", "vCOFINS": "0.00"}}
    r = auditar(nfe(item(icms=icms, pis=pis, cofins=cofins, ibscbs=False), crt=1))
    assert r.ok, r.como_dict()


def test_simples_com_credito_e_pis_com_base_preenchida():
    # como sai de ERP de verdade: CSOSN 101 com pCredSN e vBC preenchido no PISOutr com alíquota zero
    icms = {"ICMSSN101": {"orig": 0, "CSOSN": "101", "pCredSN": "1.25", "vCredICMSSN": "12.50"}}
    pis = {"PISOutr": {"CST": "49", "vBC": "1000.00", "pPIS": "0.00", "vPIS": "0.00"}}
    cofins = {"COFINSOutr": {"CST": "49", "vBC": "1000.00", "pCOFINS": "0.00", "vCOFINS": "0.00"}}
    r = auditar(nfe(item(icms=icms, pis=pis, cofins=cofins, ibscbs=False), crt=1))
    assert r.ok and r.achados == [], r.como_dict()


def test_xml_sem_namespace_e_sem_nfeproc():
    # exportação comum de ERP: só o <infNFe>, sem o namespace do portal
    xml = nfe().split("<NFe>")[1].split("</NFe>")[0].replace(' xmlns="http://www.portalfiscal.inf.br/nfe"', "")
    assert auditar(xml).ok


def test_devolucao_so_confere_a_conta():
    xml = nfe(v_nf="999.00").replace("<indFinal>", "<finNFe>4</finNFe><indFinal>")
    r = auditar(xml)
    assert r.ok and [a.campo for a in r.achados] == ["finNFe"]


def test_regime_normal_sem_grupo_ibscbs():
    r = auditar(nfe(item(ibscbs=False)))
    assert ("IBSCBS", 1) in achados(r, "regra")


def test_reducao_da_nota_e_aceita_e_conferida():
    icms = {
        "ICMS20": {
            "orig": 0,
            "CST": "20",
            "modBC": 3,
            "pRedBC": "26.5714",
            "vBC": "734.29",
            "pICMS": "7.00",
            "vICMS": "51.40",
        }
    }
    pis = {"PISAliq": {"CST": "01", "vBC": "948.60", "pPIS": "1.65", "vPIS": "15.65"}}
    cofins = {"COFINSAliq": {"CST": "01", "vBC": "948.60", "pCOFINS": "7.60", "vCOFINS": "72.09"}}
    ibscbs = {
        "CST": "000",
        "cClassTrib": "000001",
        "gIBSCBS": {
            "vBC": "860.86",
            "gIBSUF": {"pIBSUF": "0.1000", "vIBSUF": "0.86"},
            "gIBSMun": {"pIBSMun": "0.0000", "vIBSMun": "0.00"},
            "vIBS": "0.86",
            "gCBS": {"pCBS": "0.9000", "vCBS": "7.75"},
        },
    }
    r = auditar(nfe(item(ncm="84378010", icms=icms, pis=pis, cofins=cofins, ibscbs=ibscbs), uf_dest="BA"))
    assert r.ok, r.como_dict()


def test_vnf_errado():
    assert achados(auditar(nfe(v_nf="1100.00")), "regra")[("vNF", None)] == (D(1100), D(1000))


def test_xml_que_nao_e_nfe():
    with pytest.raises(ValueError, match="infNFe"):
        auditar("<cte/>")


def test_linha_de_comando(tmp_path, capsys):
    certa, errada = tmp_path / "certa.xml", tmp_path / "errada.xml"
    certa.write_text(nfe(), encoding="utf-8")
    errada.write_text(nfe(v_nf="999.00"), encoding="utf-8")
    assert main([str(certa)]) == 0
    assert main([str(errada)]) == 3
    assert '"campo": "vNF"' in capsys.readouterr().out


def test_csosn_101_com_credito_zerado():
    # achado numa nota real: 101 "com permissão de crédito" e pCredSN 0,00
    icms = {"ICMSSN101": {"orig": 0, "CSOSN": "101", "pCredSN": "0.00", "vCredICMSSN": "0.00"}}
    pis = {"PISOutr": {"CST": "99", "vBC": "1000.00", "pPIS": "0.000", "vPIS": "0.00"}}
    cofins = {"COFINSOutr": {"CST": "99", "vBC": "1000.00", "pCOFINS": "0.000", "vCOFINS": "0.00"}}
    r = auditar(nfe(item(icms=icms, pis=pis, cofins=cofins, ibscbs=False), crt=1))
    (achado,) = r.achados
    assert (achado.campo, achado.nota, achado.esperado) == ("CSOSN", "101", "102")
    assert "art. 23, §4º" in achado.detalhe
