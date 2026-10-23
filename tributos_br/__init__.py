"""Cálculo dos tributos de uma NF-e de mercadoria: IPI, ICMS (próprio, FCP, DIFAL, ST, benefícios), PIS/COFINS e IBS/CBS."""

from .calculo import calcular
from .modelos import Beneficio, Item, Nota, Participante, Regime, ResultadoItem, ResultadoNota, Tratamento, Tributo
from .tabelas import sugerir as sugerir_beneficios

__all__ = [
    "Beneficio",
    "Item",
    "Nota",
    "Participante",
    "Regime",
    "ResultadoItem",
    "ResultadoNota",
    "Tratamento",
    "Tributo",
    "calcular",
    "sugerir_beneficios",
]
__version__ = "0.1.0"
