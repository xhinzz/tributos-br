"""IBS/CBS (EC 132/2023, LC 214/2025)."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from . import tabelas
from .modelos import ZERO, Item, Nota, Regime, Tributo, centavos, pct

# ano: (CBS, IBS UF, IBS município)
_ALIQUOTAS = {
    2026: (Decimal("0.9"), Decimal("0.1"), ZERO),
}

# saem da base: LC 214, art. 12, §2º, V; NT 2025.002, UB16-10
DEDUZIDOS = ("ICMS", "FCP", "DIFAL", "FCP_DIFAL", "PIS", "COFINS")


def _efetiva(aliquota: Decimal, reducao: Decimal) -> Decimal:
    # NT 2025.002, UB28-10: 4 casas, arredondando a última
    return (aliquota * (1 - pct(reducao))).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def calcular(nota: Nota, item: Item, tributos: dict[str, Tributo]) -> dict[str, Tributo] | None:
    ano = nota.data.year
    if ano < 2026:
        return None
    if nota.emitente.regime == Regime.SIMPLES and ano == 2026:
        return None  # art. 348, III, c
    if ano not in _ALIQUOTAS:
        raise LookupError(f"alíquotas de IBS/CBS de {ano} ainda não estão na biblioteca")
    classe = tabelas.cclass_trib(item.cclass_trib, nota.data)
    extras: dict = {"cclass_trib": classe.codigo}
    if classe.anexo and not tabelas.no_anexo_lc214(classe.anexo, item.ncm):
        extras["conferir"] = f"NCM {item.ncm} fora da lista do Anexo {classe.anexo} da LC 214"
    fundamento = f"{classe.fundamento}; {classe.nome}"

    if classe.tipo == "Sem alíquota":
        # sem grupo gIBSCBS: só CST e cClassTrib
        return {
            nome: Tributo(ZERO, ZERO, ZERO, classe.cst, fundamento, dict(extras))
            for nome in ("CBS", "IBS_UF", "IBS_MUN")
        }
    if classe.tipo != "Padrão" or classe.cst in ("510", "515"):
        raise ValueError(f"cClassTrib {classe.codigo} ({classe.tipo}, CST {classe.cst}) ainda não é calculado aqui")

    # art. 12, §2º, II: sem IPI, que valor_operacao já não tem
    base = item.valor_operacao - sum((tributos[n].valor for n in DEDUZIDOS if n in tributos), ZERO)
    fundamento += f"; alíquotas de {ano} (arts. 343 e 346)"
    cbs, ibs_uf, ibs_mun = _ALIQUOTAS[ano]
    resultado = {}
    for nome, aliquota, reducao in (
        ("CBS", cbs, classe.red_cbs),
        ("IBS_UF", ibs_uf, classe.red_ibs),
        ("IBS_MUN", ibs_mun, classe.red_ibs),
    ):
        efetiva = _efetiva(aliquota, reducao)
        extra = dict(extras)
        if reducao:
            extra |= {"reducao_aliquota": reducao, "aliquota_efetiva": efetiva}
        resultado[nome] = Tributo(base, aliquota, centavos(base * pct(efetiva)), classe.cst, fundamento, extra)
    return resultado
