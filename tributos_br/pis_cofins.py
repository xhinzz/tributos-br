"""PIS/COFINS pelo regime do emitente."""

from __future__ import annotations

from decimal import Decimal

from .modelos import ZERO, Item, Nota, Regime, Tributo, centavos, pct

# grupo PISNT/COFINSNT
_SEM_INCIDENCIA = {
    "monofasico": ("04", "revenda de produto monofásico, alíquota zero (tributado no fabricante ou importador)"),
    "aliquota_zero": ("06", "alíquota zero"),
    "isenta": ("07", "isenta"),
    "suspensao": ("09", "suspensão"),
}

_ALIQUOTAS = {
    Regime.REAL: (Decimal("1.65"), Decimal("7.6"), "não cumulativo (Leis 10.637/2002 e 10.833/2003)"),
    Regime.PRESUMIDO: (Decimal("0.65"), Decimal(3), "cumulativo (Lei 9.718/1998)"),
}


def calcular(nota: Nota, item: Item, valor_icms: Decimal) -> dict[str, Tributo]:
    regime = nota.emitente.regime
    if regime == Regime.SIMPLES:
        nada = "recolhido no DAS (LC 123/2006, art. 13)"
        return {"PIS": Tributo(ZERO, ZERO, ZERO, "49", nada), "COFINS": Tributo(ZERO, ZERO, ZERO, "49", nada)}
    if item.pis_cofins:
        cst, motivo = _SEM_INCIDENCIA[item.pis_cofins]
        return {"PIS": Tributo(ZERO, ZERO, ZERO, cst, motivo), "COFINS": Tributo(ZERO, ZERO, ZERO, cst, motivo)}
    pis, cofins, fundamento = _ALIQUOTAS[regime]
    base = item.valor_operacao - valor_icms
    fundamento += "; base sem o ICMS (STF, Tema 69)"
    return {
        "PIS": Tributo(base, pis, centavos(base * pct(pis)), "01", fundamento),
        "COFINS": Tributo(base, cofins, centavos(base * pct(cofins)), "01", fundamento),
    }
