"""ICMS próprio, FCP, DIFAL (EC 87/2015), substituição tributária e benefícios fiscais."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from . import tabelas
from .modelos import ZERO, Beneficio, Item, Nota, Regime, Tratamento, Tributo, centavos, pct

# Res. Senado 22/1989: 7% de S/SE (exceto ES) para N, NE, CO e ES; 12% nas demais
_SUL_SUDESTE_SEM_ES = frozenset(["MG", "PR", "RJ", "RS", "SC", "SP"])
# Res. Senado 13/2012: 4% para importados e nacionais com conteúdo de importação acima de 40%
_ORIGENS_4_PORCENTO = frozenset({1, 2, 3, 8})


def aliquota_interestadual(uf_origem: str, uf_destino: str, origem: int) -> tuple[Decimal, str]:
    if origem in _ORIGENS_4_PORCENTO:
        return Decimal(4), f"Res. Senado 13/2012 (mercadoria importada, origem {origem})"
    if uf_origem in _SUL_SUDESTE_SEM_ES and uf_destino not in _SUL_SUDESTE_SEM_ES:
        return Decimal(7), "Res. Senado 22/1989 (S/SE para N/NE/CO/ES)"
    return Decimal(12), "Res. Senado 22/1989"


@dataclass(frozen=True)
class _Aplicado:
    tratamento: Tratamento
    percentual: Decimal
    cbenef: str | None
    fundamento: str
    # redução da base na UF de destino (DIFAL e ST); Conv. 52/91, cl. 5ª, por exemplo
    reducao_destino: Decimal


def _interna(item: Item, uf: str, nota: Nota) -> tuple[Decimal, Decimal, str]:
    """Alíquota interna do produto na UF, FCP e fundamento."""
    dados = tabelas.dados_uf(uf, nota.data)
    if item.aliquota_icms is not None:
        return item.aliquota_icms, dados.fcp, "alíquota interna informada para o produto"
    return dados.aliquota_interna, dados.fcp, f"alíquota modal de {uf} ({dados.fonte})"


def _beneficio(item: Item, nota: Nota, aliquota: Decimal) -> _Aplicado | None:
    b = item.beneficio
    if b is None:
        return None
    if isinstance(b, Beneficio):
        if b.tratamento == Tratamento.REDUCAO_BASE and not b.percentual:
            return None
        return _Aplicado(b.tratamento, b.percentual, b.cbenef, b.fundamento, b.reducao_destino or ZERO)
    emit, dest = nota.emitente.uf, nota.destinatario.uf
    regra = tabelas.regra(b, item.ncm, emit, dest, aliquota, nota.data)
    destino = ZERO
    if emit != dest:
        try:
            aliquota_dest = _interna(item, dest, nota)[0]
            interna = tabelas.regra(b, item.ncm, dest, dest, aliquota_dest, nota.data)
            if interna.tratamento == Tratamento.REDUCAO_BASE:
                destino = interna.percentual
        except ValueError:
            pass  # a regra não tem versão interna: o destino tributa pela base cheia
    if regra.tratamento == Tratamento.REDUCAO_BASE and not regra.percentual:
        return None
    return _Aplicado(regra.tratamento, regra.percentual, regra.cbenef, regra.fundamento, destino)


def calcular(nota: Nota, item: Item, valor_ipi: Decimal) -> dict[str, Tributo]:
    emit, dest = nota.emitente, nota.destinatario
    if item.cest:
        tabelas.conferir_cest(item.cest, item.ncm)
    # CF art. 155, §2º, XI: o IPI fica fora da base só entre contribuintes, para industrialização ou revenda
    base_cheia = item.valor_operacao + (valor_ipi if nota.consumidor_final else ZERO)
    if nota.interestadual:
        aliquota, fundamento = aliquota_interestadual(emit.uf, dest.uf, item.origem)
        fcp = ZERO  # o FCP da origem não incide na saída interestadual; o do destino vai no DIFAL ou na ST
    else:
        aliquota, fcp, fundamento = _interna(item, emit.uf, nota)

    beneficio = _beneficio(item, nota, aliquota)
    reducao = beneficio.percentual if beneficio and beneficio.tratamento == Tratamento.REDUCAO_BASE else ZERO
    base = centavos(base_cheia * (1 - pct(reducao)))
    icms_cheio = centavos(base * pct(aliquota))
    sem_icms = beneficio is not None and beneficio.tratamento in (Tratamento.ISENCAO, Tratamento.NAO_TRIBUTADA)

    tributos: dict[str, Tributo] = {}
    if emit.regime == Regime.SIMPLES:
        # o Simples deduz da ST o ICMS próprio calculado como se fosse do regime normal (Conv. 142/2018, cl. 13ª, §1º)
        st = _substituicao(nota, item, valor_ipi, aliquota, ZERO if sem_icms else icms_cheio, ZERO, beneficio)
        tributos["ICMS"] = _simples(item, nota, beneficio, st is not None)
    else:
        tributos["ICMS"] = _proprio(base, base_cheia, aliquota, icms_cheio, beneficio, fundamento)
        valor_fcp = ZERO
        if fcp and tributos["ICMS"].valor:
            valor_fcp = centavos(base * pct(fcp))
            tributos["FCP"] = Tributo(base, fcp, valor_fcp, fundamento=f"FCP de {emit.uf}")
        st = _substituicao(nota, item, valor_ipi, aliquota, tributos["ICMS"].valor, valor_fcp, beneficio)
        if st:
            tributos["ICMS"].cst = {"00": "10", "20": "70", "40": "30", "41": "30"}.get(tributos["ICMS"].cst, "90")
    if st:
        tributos.update(st)

    if nota.interestadual and nota.consumidor_final and not dest.contribuinte_icms:
        tributos.update(_difal(nota, item, base_cheia, aliquota, ZERO if sem_icms else icms_cheio, beneficio))
    return tributos


def _proprio(base, base_cheia, aliquota, icms_cheio, beneficio: _Aplicado | None, fundamento: str) -> Tributo:
    if beneficio is None:
        return Tributo(base, aliquota, icms_cheio, "00", fundamento)
    extras: dict = {"cbenef": beneficio.cbenef} if beneficio.cbenef else {}
    detalhe = f"{fundamento}; {beneficio.fundamento}"
    # valor desonerado pela fórmula simples (sem o ICMS por dentro); há UF que exige outra (ex.: RJ, Res. 720/14)
    sem_beneficio = centavos(base_cheia * pct(aliquota))
    match beneficio.tratamento:
        case Tratamento.REDUCAO_BASE:
            extras |= {"reducao_base": beneficio.percentual, "valor_desonerado": sem_beneficio - icms_cheio}
            return Tributo(base, aliquota, icms_cheio, "20", detalhe, extras)
        case Tratamento.ISENCAO:
            return Tributo(ZERO, ZERO, ZERO, "40", detalhe, extras | {"valor_desonerado": sem_beneficio})
        case Tratamento.NAO_TRIBUTADA:
            return Tributo(ZERO, ZERO, ZERO, "41", detalhe, extras | {"valor_desonerado": sem_beneficio})
        case Tratamento.DIFERIMENTO:
            # NT 2016.002: vICMSOp = vBC × pICMS; vICMSDif = vICMSOp × pDif; vICMS = vICMSOp − vICMSDif
            diferido = centavos(icms_cheio * pct(beneficio.percentual))
            extras |= {
                "valor_operacao": icms_cheio,
                "percentual_diferimento": beneficio.percentual,
                "valor_diferido": diferido,
            }
            return Tributo(base, aliquota, icms_cheio - diferido, "51", detalhe, extras)
    raise AssertionError(beneficio.tratamento)


def _simples(item: Item, nota: Nota, beneficio: _Aplicado | None, com_st: bool) -> Tributo:
    """Simples Nacional: o ICMS próprio vai no DAS e não é destacado (LC 123/2006, art. 13)."""
    if beneficio and beneficio.tratamento in (Tratamento.ISENCAO, Tratamento.NAO_TRIBUTADA):
        return Tributo(ZERO, ZERO, ZERO, "400", "não tributada pelo Simples Nacional; " + beneficio.fundamento)
    emit, dest = nota.emitente, nota.destinatario
    # LC 123/2006, art. 23, §1º: crédito só para destinatário fora do Simples que revende ou industrializa
    if emit.aliquota_credito_sn and dest.regime != Regime.SIMPLES and not nota.consumidor_final:
        credito = centavos(item.valor_operacao * pct(emit.aliquota_credito_sn))
        return Tributo(
            ZERO,
            ZERO,
            ZERO,
            "201" if com_st else "101",
            "Simples Nacional com permissão de crédito (LC 123/2006, art. 23)",
            {"aliquota_credito": emit.aliquota_credito_sn, "valor_credito": credito},
        )
    return Tributo(ZERO, ZERO, ZERO, "202" if com_st else "102", "Simples Nacional sem permissão de crédito")


def _difal(
    nota: Nota,
    item: Item,
    base_cheia: Decimal,
    aliquota_inter: Decimal,
    icms_origem: Decimal,
    beneficio: _Aplicado | None,
) -> dict[str, Tributo]:
    """Diferencial de alíquotas devido ao destino na venda a consumidor final não contribuinte."""
    if nota.emitente.regime == Regime.SIMPLES:
        # STF, ADI 5.464: suspensa a cláusula 9ª do Conv. ICMS 93/2015, que cobrava o DIFAL do Simples
        return {}
    dest = nota.destinatario.uf
    aliquota_dest, fcp, fundamento = _interna(item, dest, nota)
    dados = tabelas.dados_uf(dest, nota.data)
    metodo = nota.metodo_difal or dados.difal_base
    reducao = beneficio.reducao_destino if beneficio else ZERO
    v = base_cheia * (1 - pct(reducao))
    # V = valor com o ICMS de origem embutido. Com V=1000, 7% e 20%: única 130,00; dupla 162,50; por dentro 151,13
    if metodo == "unica":
        # Conv. ICMS 236/2021, cl. 2ª, §1º
        base_dest = centavos(v)
        valor = centavos(base_dest * pct(aliquota_dest)) - icms_origem
    else:
        # LC 87/1996, art. 13, §7º (LC 190/2022): base com o ICMS do destino "por dentro"
        base_dest = centavos((v - icms_origem) / (1 - pct(aliquota_dest)))
        if metodo == "dupla":
            valor = centavos(base_dest * pct(aliquota_dest)) - icms_origem
        else:
            valor = centavos(base_dest * pct(aliquota_dest - aliquota_inter))
    valor = max(valor, ZERO)
    extras: dict = {"aliquota_interestadual": aliquota_inter, "valor_icms_origem": icms_origem, "metodo": metodo}
    if reducao:
        extras["reducao_base_destino"] = reducao
    if not nota.metodo_difal and not dados.difal_conferido:
        extras["conferir"] = f"método do DIFAL de {dest} sem confirmação em fonte oficial da UF"
    modo = {"unica": "base única", "dupla": "base dupla", "por_dentro": "base por dentro"}[metodo]
    resultado = {
        "DIFAL": Tributo(
            base_dest,
            aliquota_dest,
            valor,
            fundamento=f"EC 87/2015, LC 190/2022 ({modo} em {dest}); {fundamento}",
            extras=extras,
        )
    }
    if fcp:
        resultado["FCP_DIFAL"] = Tributo(base_dest, fcp, centavos(base_dest * pct(fcp)), fundamento=f"FCP de {dest}")
    return resultado


def _substituicao(
    nota: Nota,
    item: Item,
    valor_ipi: Decimal,
    aliquota_propria: Decimal,
    icms_proprio: Decimal,
    fcp_proprio: Decimal,
    beneficio: _Aplicado | None,
) -> dict[str, Tributo] | None:
    dest = nota.destinatario
    revenda = dest.contribuinte_icms and not nota.consumidor_final
    if item.mva is not None:
        if not revenda:
            raise ValueError("MVA informada, mas a ST só cabe em venda para contribuinte que vai revender")
        mva, origem_mva = item.mva, "MVA informada"
    elif revenda and item.cest:
        achado = tabelas.mva(dest.uf, item.ncm, item.cest, nota.data)
        if achado is None:
            return None
        mva, origem_mva = achado
    else:
        return None

    aliquota_dest, fcp, _ = _interna(item, dest.uf, nota)
    mva_aplicada = mva
    # MVA ajustada: neutraliza a diferença entre a interestadual e a interna; não se aplica ao remetente do Simples
    # (Conv. ICMS 142/2018, cl. 11ª, §1º) nem quando a interna não é maior (Prot. ICMS 41/2008, §7º)
    if nota.interestadual and aliquota_dest > aliquota_propria and nota.emitente.regime != Regime.SIMPLES:
        mva_aplicada = ((1 + pct(mva)) * (1 - pct(aliquota_propria)) / (1 - pct(aliquota_dest)) - 1) * 100
        mva_aplicada = mva_aplicada.quantize(Decimal("0.0001"))
    reducao = ZERO
    if beneficio and beneficio.tratamento == Tratamento.REDUCAO_BASE:
        reducao = beneficio.reducao_destino if nota.interestadual else beneficio.percentual
    # Conv. ICMS 142/2018, cl. 11ª, III: valor + frete, seguro, impostos (IPI) e encargos, com a margem
    base_st = centavos((item.valor_operacao + valor_ipi) * (1 - pct(reducao)) * (1 + pct(mva_aplicada)))
    valor_st = max(centavos(base_st * pct(aliquota_dest)) - icms_proprio, ZERO)
    extras: dict = {
        "mva_original": mva,
        "mva_aplicada": mva_aplicada,
        "icms_proprio_deduzido": icms_proprio,
        "modalidade_base": "4",
    }
    if reducao:
        extras["reducao_base"] = reducao
    resultado = {
        "ICMS_ST": Tributo(
            base_st,
            aliquota_dest,
            valor_st,
            fundamento=f"{origem_mva}; LC 87/1996, art. 8º, II; Conv. ICMS 142/2018",
            extras=extras,
        )
    }
    if fcp:
        # NT 2016.002, regra N23d-10: vFCPST = vBCFCPST × pFCPST − vFCP
        resultado["FCP_ST"] = Tributo(
            base_st, fcp, max(centavos(base_st * pct(fcp)) - fcp_proprio, ZERO), fundamento=f"FCP-ST de {dest.uf}"
        )
    return resultado
