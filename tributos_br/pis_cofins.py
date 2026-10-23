"""PIS/COFINS pelo regime do emitente."""

from __future__ import annotations

from decimal import Decimal

from . import tabelas
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
    if nota.data.year >= 2027:
        return {}  # extintos pela EC 132/2023 (ADCT, art. 126, II): a CBS assume
    regime = nota.emitente.regime
    if regime == Regime.SIMPLES:
        nada = "recolhido no DAS (LC 123/2006, art. 13)"
        return {"PIS": Tributo(ZERO, ZERO, ZERO, "49", nada), "COFINS": Tributo(ZERO, ZERO, ZERO, "49", nada)}
    if item.pis_cofins:
        cst, motivo = _SEM_INCIDENCIA[item.pis_cofins]
        return {"PIS": Tributo(ZERO, ZERO, ZERO, cst, motivo), "COFINS": Tributo(ZERO, ZERO, ZERO, cst, motivo)}
    base = item.valor_operacao - valor_icms
    cst, extras = "01", {}
    if monofasico := tabelas.monofasico(item.ncm, nota.data):
        if monofasico.conferir:
            extras["conferir"] = monofasico.conferir
        if not nota.emitente.industria:
            if monofasico.cst_revenda == "04":
                motivo = f"{_SEM_INCIDENCIA['monofasico'][1]}; {monofasico.fundamento}"
                return {nome: Tributo(ZERO, ZERO, ZERO, "04", motivo, dict(extras)) for nome in ("PIS", "COFINS")}
            pis, cofins = monofasico.pis_revenda, monofasico.cofins_revenda
        else:
            # fabricante ou importador concentra a cadeia, em qualquer regime
            pis, cofins = monofasico.pis, monofasico.cofins
            if monofasico.reducao_base:
                base = centavos(base * (1 - pct(monofasico.reducao_base)))
                extras["reducao_base"] = monofasico.reducao_base
        if monofasico.reducao_final and nota.consumidor_final:
            pis, cofins = (
                (a * (1 - pct(r))).quantize(Decimal("0.0001"))
                for a, r in zip((pis, cofins), monofasico.reducao_final, strict=True)
            )
        cst, fundamento = "02", monofasico.fundamento
    else:
        pis, cofins, fundamento = _ALIQUOTAS[regime]
    fundamento += "; base sem o ICMS (STF, Tema 69)"
    return {
        "PIS": Tributo(base, pis, centavos(base * pct(pis)), cst, fundamento, dict(extras)),
        "COFINS": Tributo(base, cofins, centavos(base * pct(cofins)), cst, fundamento, dict(extras)),
    }
