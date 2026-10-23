"""IPI pela TIPI. Só industrial ou equiparado, fora do Simples, destaca."""

from __future__ import annotations

from . import tabelas
from .modelos import ZERO, Item, Nota, Regime, Tributo, centavos, pct


def calcular(nota: Nota, item: Item) -> Tributo | None:
    emit = nota.emitente
    if not emit.industria:
        return None
    if emit.regime == Regime.SIMPLES:
        return Tributo(ZERO, ZERO, ZERO, "99", "IPI recolhido no DAS, sem destaque (LC 123/2006, art. 13)")
    if item.aliquota_ipi is not None:
        aliquota, fundamento = item.aliquota_ipi, "alíquota de IPI informada"
    elif nota.data.year >= 2027:
        # ZFM continua tributada: informe aliquota_ipi
        return Tributo(ZERO, ZERO, ZERO, "51", "IPI reduzido a zero desde 2027 (EC 132/2023, ADCT art. 126, III, a)")
    else:
        try:
            aliquota = tabelas.aliquota_tipi(item.ncm, item.ex_tipi)
        except KeyError:
            raise LookupError(
                f"NCM {item.ncm} (EX {item.ex_tipi or '-'}) não está na TIPI; confira ou informe aliquota_ipi"
            ) from None
        if aliquota is None:
            return Tributo(ZERO, ZERO, ZERO, "53", f"NCM {item.ncm} 'NT' na TIPI (não tributado)")
        fundamento = f"TIPI (Decreto 11.158/2022), NCM {item.ncm}" + (f" EX {item.ex_tipi}" if item.ex_tipi else "")
    if aliquota == 0:
        return Tributo(ZERO, ZERO, ZERO, "51", f"{fundamento}: alíquota zero")
    # RIPI, art. 190
    base = item.valor_operacao
    return Tributo(base, aliquota, centavos(base * pct(aliquota)), "50", fundamento)
