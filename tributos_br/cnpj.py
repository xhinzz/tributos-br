"""Validação de CNPJ (numérico e alfanumérico, IN RFB 2.229/2024) e preenchimento do participante pela BrasilAPI."""

from __future__ import annotations

import json
import re
import urllib.request

from .modelos import Participante, Regime

_PESOS = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]


def limpar(cnpj: str) -> str:
    return re.sub(r"[./\s-]", "", cnpj).upper()


def _dv(base: str) -> str:
    # cada caractere vale o código ASCII menos 48: dígitos ficam iguais, 'A' vale 17
    soma = sum((ord(c) - 48) * p for c, p in zip(base, _PESOS[-len(base) :], strict=True))
    resto = soma % 11
    return "0" if resto < 2 else str(11 - resto)


def valido(cnpj: str) -> bool:
    cnpj = limpar(cnpj)
    if not re.fullmatch(r"[0-9A-Z]{12}[0-9]{2}", cnpj) or len(set(cnpj)) == 1:
        return False
    primeiro = _dv(cnpj[:12])
    return cnpj[12:] == primeiro + _dv(cnpj[:12] + primeiro)


def participante(
    cnpj: str,
    *,
    contribuinte_icms: bool = True,
    industria: bool = False,
    regime: Regime | str | None = None,
    timeout: float = 15,
) -> Participante:
    """Monta o participante a partir do cadastro público do CNPJ.

    O cadastro informa a UF e a opção pelo Simples, mas não se a empresa é Lucro Real ou Presumido, nem a
    inscrição estadual: fora do Simples, o regime precisa ser informado.
    """
    cnpj = limpar(cnpj)
    if not valido(cnpj):
        raise ValueError(f"CNPJ inválido: {cnpj}")
    with urllib.request.urlopen(f"https://brasilapi.com.br/api/cnpj/v1/{cnpj}", timeout=timeout) as resposta:
        dados = json.load(resposta)
    if dados.get("opcao_pelo_simples"):
        regime = Regime.SIMPLES
    elif regime is None:
        raise ValueError(f"{cnpj} não é do Simples: informe regime='real' ou 'presumido'")
    return Participante(dados["uf"], Regime(regime), contribuinte_icms, industria, cnpj=cnpj)
