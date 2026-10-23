"""IBS e CBS da Reforma Tributária (EC 132/2023, LC 214/2025)."""

from __future__ import annotations

from decimal import Decimal

from .modelos import ZERO, Item, Nota, Regime, Tributo, centavos, pct

# ano: (CBS, IBS estadual, IBS municipal)
_ALIQUOTAS = {
    2026: (Decimal("0.9"), Decimal("0.1"), ZERO),
}


# NT 2025.002-RTC: tributação integral
CST, CLASSIFICACAO = "000", "000001"
# entram na dedução da base (LC 214/2025, art. 12, §2º, V; NT 2025.002, regra UB16-10)
DEDUZIDOS = ("ICMS", "FCP", "DIFAL", "FCP_DIFAL", "PIS", "COFINS")


def calcular(nota: Nota, item: Item, tributos: dict[str, Tributo]) -> dict[str, Tributo] | None:
    ano = nota.data.year
    if ano < 2026:
        return None
    if nota.emitente.regime == Regime.SIMPLES and ano == 2026:
        return None  # LC 214/2025, art. 348, III, "c"
    if ano not in _ALIQUOTAS:
        raise LookupError(f"alíquotas de IBS/CBS de {ano} ainda não estão na biblioteca")
    cbs, ibs_uf, ibs_mun = _ALIQUOTAS[ano]
    # o IPI fica fora (art. 12, §2º, II): valor_operacao já não o inclui
    base = item.valor_operacao - sum((tributos[n].valor for n in DEDUZIDOS if n in tributos), ZERO)
    fundamento = f"LC 214/2025 (arts. 343 e 346, alíquotas de {ano}); base do art. 12"
    extras = {"cclass_trib": CLASSIFICACAO}
    return {
        "CBS": Tributo(base, cbs, centavos(base * pct(cbs)), CST, fundamento, dict(extras)),
        "IBS_UF": Tributo(base, ibs_uf, centavos(base * pct(ibs_uf)), CST, fundamento, dict(extras)),
        "IBS_MUN": Tributo(base, ibs_mun, centavos(base * pct(ibs_mun)), CST, fundamento, dict(extras)),
    }
