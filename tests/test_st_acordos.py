"""ST interestadual só entre signatárias do acordo do segmento (Conv. 142/18, cl. 2ª)."""

from datetime import date
from decimal import Decimal as D

import pytest

from tests.nfe import item, nfe
from tributos_br import Item, Nota, Participante, calcular, tabelas
from tributos_br.auditoria import auditar

HOJE = date(2026, 10, 23)
CATALISADOR, CIMENTO, ETANOL_ANIDRO = "38151210", "25232910", "22071010"


def st(origem, destino, ncm, cest, data=HOJE, **kw):
    nota = Nota(Participante(origem), Participante(destino), [Item(ncm, 1000, cest=cest, **kw)], data=data)
    return calcular(nota).itens[0].tributos.get("ICMS_ST")


def test_sp_saiu_das_autopecas_em_outubro_de_2026():
    # Prot. 93/26: SP fora do Prot. 41/08 desde 01/10/2026
    assert st("SP", "RJ", CATALISADOR, "0100100") is None
    assert st("SP", "RJ", CATALISADOR, "0100100", data=date(2026, 9, 30)) is not None


def test_destino_com_mva_propria_exige_mva():
    # §6º do Prot. 41/08: para a BA vale a MVA da legislação interna
    with pytest.raises(ValueError, match="informe a MVA"):
        st("MG", "BA", CATALISADOR, "0100100")
    assert st("MG", "BA", CATALISADOR, "0100100", mva=D(50)).extras["mva_original"] == 50


def test_cimento_mva_do_protocolo():
    t = st("MG", "BA", CIMENTO, "0500100")
    # 1,20 × (1 − 7%) / (1 − 20,5%) − 1 = 40,3774%; base 1403,77 × 20,5% = 287,77 − 70
    assert t.extras["mva_aplicada"] == D("40.3774")
    assert (t.base, t.valor) == (D("1403.77"), D("217.77"))


def test_agua_fora_para_sp_e_destino_pr_mas_refrigerante_nao():
    assert tabelas.acordo_st("0300300", "SP", "RJ", HOJE) is None  # Prot. 42/26
    assert tabelas.acordo_st("0300300", "RJ", "PR", HOJE) is None  # Prot. 3/25
    assert tabelas.acordo_st("0300300", "RJ", "BA", HOJE).codigo == "prot11_91"
    assert tabelas.acordo_st("0301000", "SP", "RJ", HOJE).codigo == "prot11_91"


def test_pneus_rs_sai_em_2027():
    assert tabelas.acordo_st("1600100", "RS", "PR", date(2026, 12, 31)).codigo == "conv102_17"
    assert tabelas.acordo_st("1600100", "RS", "PR", date(2027, 1, 1)) is None


def test_cest_excluido_do_acordo():
    assert tabelas.acordo_st("0101900", "MG", "RJ", HOJE) is None


def test_base_por_preco_recusa():
    with pytest.raises(ValueError, match="base por preço"):
        st("SP", "RJ", ETANOL_ANIDRO, "0600100")


def test_sem_acordo_e_mva_informada_avisa():
    t = st("SP", "RJ", CATALISADOR, "0100100", mva=D(40))
    assert "sem acordo" in t.extras["conferir"]


def test_auditoria_aponta_st_devida_e_ausente():
    icms = {"ICMS00": {"orig": 0, "CST": "00", "modBC": 3, "vBC": "1000.00", "pICMS": "12.00", "vICMS": "120.00"}}
    r = auditar(nfe(item(ncm=CATALISADOR, CEST="0100100", icms=icms, ibscbs=False), uf_emit="MG", uf_dest="RJ"))
    achado = next(a for a in r.achados if a.campo == "vICMSST")
    assert achado.tipo == "regra" and "Prot. ICMS 41/2008" in achado.detalhe


def test_auditoria_avisa_st_sem_acordo():
    icms = {
        "ICMS10": {
            "orig": 0,
            "CST": "10",
            "modBC": 3,
            "vBC": "1000.00",
            "pICMS": "12.00",
            "vICMS": "120.00",
            "modBCST": 4,
            "pMVAST": "40.00",
            "vBCST": "1400.00",
            "pICMSST": "20.00",
            "vICMSST": "160.00",
        }
    }
    r = auditar(
        nfe(item(ncm=CATALISADOR, CEST="0100100", icms=icms, ibscbs=False), uf_emit="SP", uf_dest="RJ", v_nf="1160.00")
    )
    assert any(a.campo == "vICMSST" and a.tipo == "aviso" for a in r.achados)


def test_tabela_de_acordos_bem_formada():
    for linha in tabelas._acordos():
        assert None not in linha
        assert linha["base"] in ("mva", "preco")
        assert all(len(uf) == 2 for uf in linha["ufs"].split("|"))
        assert all(r.split(":")[0] in ("cest", "uf", "destino") for r in filter(None, linha["excecoes"].split("|")))
