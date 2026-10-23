"""Orquestra o cálculo item a item: IPI primeiro (entra na base do ICMS e da ST), depois ICMS, PIS/COFINS e IBS/CBS."""

from __future__ import annotations

from . import ibs_cbs, icms, ipi, pis_cofins
from .modelos import ZERO, Nota, ResultadoItem, ResultadoNota


def calcular(nota: Nota) -> ResultadoNota:
    resultados = []
    for item in nota.itens:
        tributos = {}
        if (t_ipi := ipi.calcular(nota, item)) is not None:
            tributos["IPI"] = t_ipi
        valor_ipi = t_ipi.valor if t_ipi else ZERO
        tributos |= icms.calcular(nota, item, valor_ipi)
        valor_icms = tributos["ICMS"].valor
        tributos |= pis_cofins.calcular(nota, item, valor_icms)
        if (t_ibs := ibs_cbs.calcular(nota, item, tributos)) is not None:
            tributos |= t_ibs
        resultados.append(ResultadoItem(item, tributos))
    return ResultadoNota(resultados)
