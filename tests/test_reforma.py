"""IBS/CBS por cClassTrib (IT 2025.002) e anexos da LC 214/2025."""

from datetime import date
from decimal import Decimal as D

import pytest

from tributos_br import Item, Nota, Participante, calcular, sugerir_cclass_trib, tabelas

HOJE = date(2026, 10, 23)
ARROZ = "10063021"  # Anexo I: cesta básica, redução de 100%
MEL = "04090000"  # Anexo VII, item 3: redução de 60%
NOTEBOOK = "84713012"


def ibs_cbs(ncm, cclass, **item):
    nota = Nota(Participante("SP"), Participante("SP"), [Item(ncm, 1000, cclass_trib=cclass, **item)], data=HOJE)
    return calcular(nota).itens[0].tributos


def test_cesta_basica_reducao_a_zero():
    t = ibs_cbs(ARROZ, "200003")
    assert {n: (t[n].cst, t[n].valor) for n in ("CBS", "IBS_UF", "IBS_MUN")} == {
        "CBS": ("200", 0),
        "IBS_UF": ("200", 0),
        "IBS_MUN": ("200", 0),
    }
    assert t["CBS"].extras["aliquota_efetiva"] == 0 and "conferir" not in t["CBS"].extras


def test_alimento_com_reducao_de_60():
    t = ibs_cbs(MEL, "200034")
    # base 1000 − 180 − 13,53 − 62,32 = 744,15; CBS 0,9% × 40% = 0,36%; IBS 0,1% × 40% = 0,04%
    assert t["CBS"].base == D("744.15")
    assert (t["CBS"].extras["aliquota_efetiva"], t["CBS"].valor) == (D("0.3600"), D("2.68"))
    assert (t["IBS_UF"].extras["aliquota_efetiva"], t["IBS_UF"].valor) == (D("0.0400"), D("0.30"))
    assert t["CBS"].cst == "200" and t["CBS"].extras["reducao_aliquota"] == 60


def test_ncm_fora_do_anexo_avisa():
    t = ibs_cbs(NOTEBOOK, "200034")
    assert "Anexo 7" in t["CBS"].extras["conferir"]


def test_sem_aliquota_so_cst_e_classificacao():
    t = ibs_cbs(NOTEBOOK, "410004")  # exportação
    assert (t["CBS"].cst, t["CBS"].base, t["CBS"].valor) == ("410", 0, 0)


@pytest.mark.parametrize(
    "codigo,erro",
    [
        ("999999", "não existe"),
        ("011002", "não é usado em NF-e"),
        ("620001", "ainda não é calculado"),
        ("515001", "ainda não é calculado"),
    ],
)
def test_classificacoes_recusadas(codigo, erro):
    with pytest.raises(ValueError, match=erro):
        ibs_cbs(NOTEBOOK, codigo)


def test_padrao_continua_tributacao_integral():
    t = ibs_cbs(NOTEBOOK, "000001")
    assert (t["CBS"].cst, t["CBS"].valor) == ("000", D("6.70"))
    assert "aliquota_efetiva" not in t["CBS"].extras


@pytest.mark.parametrize(
    "ncm,codigo",
    [
        (ARROZ, "200003"),
        (MEL, "200034"),
        ("04072100", "200014"),  # ovos, Anexo XV
        ("08051000", "200014"),  # laranja, posição 08.05
        ("03061400", "200034"),  # caranguejo: 0306.1 entra, 0306.11 e 0306.15 não
        ("31021010", "200038"),  # ureia, insumo agropecuário
        ("96190000", "200035"),  # fraldas
    ],
)
def test_sugestao_pelo_ncm_citado_na_lei(ncm, codigo):
    assert codigo in [c for c, _ in sugerir_cclass_trib(ncm, HOJE)]


def test_excecao_citada_na_lei_nao_entra():
    # Anexo VII, item 1: "0306.1 ..., exceto os produtos da subposição 0306.11"
    assert "200034" not in [c for c, _ in sugerir_cclass_trib("03061100", HOJE)]
    # Anexo XV, item 2: hortícolas das posições 07.01 a 07.10, "exceto os cogumelos e trufas ... 0709.5 e 0710.80.00"
    assert tabelas.no_anexo_lc214(15, "07096000") is True
    assert tabelas.no_anexo_lc214(15, "07095100") is False
    assert tabelas.no_anexo_lc214(15, "07108000") is False


def test_tabela_oficial_completa():
    assert len(tabelas._cclass()) == 173
    assert tabelas.cclass_trib("200003", HOJE).red_cbs == 100
