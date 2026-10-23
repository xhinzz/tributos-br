"""Auditoria de NF-e: a conta do próprio XML e o recálculo pela legislação.

'conta': o XML não fecha com ele mesmo (vICMS ≠ vBC × pICMS, base do IBS/CBS fora da fórmula da NT).
'regra': o recálculo dá outro valor (alíquota interestadual, DIFAL ausente, CST, cClassTrib, CEST).
'aviso': a nota pode estar certa, mas vale olhar (alíquota interna própria do produto, ICMS na base do PIS).

Benefício, cBenef, MVA e alíquota interna própria não têm como ser inferidos: vêm da nota, e a conferência
deles é só aritmética.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path

from . import tabelas
from .calculo import calcular
from .modelos import ZERO, Beneficio, Item, Nota, Participante, Regime, ResultadoNota, Tratamento, centavos, pct

TOLERANCIA = Decimal("0.01")  # a SEFAZ aceita ±0,01 nas validações de valor
_SEM_PIS_COFINS = {"04": "monofasico", "06": "aliquota_zero", "07": "isenta", "09": "suspensao"}
_CST_COM_ST = {"00": "10", "20": "70", "40": "30", "41": "30", "102": "202", "101": "201"}


@dataclass
class Achado:
    tipo: str  # conta | regra | aviso
    campo: str
    nota: Decimal | str | None
    esperado: Decimal | str | None
    item: int | None = None
    detalhe: str = ""


@dataclass
class Relatorio:
    chave: str
    achados: list[Achado] = field(default_factory=list)
    recalculo: ResultadoNota | None = None

    @property
    def ok(self) -> bool:
        return not any(a.tipo in ("conta", "regra") for a in self.achados)

    def como_dict(self) -> dict:
        def texto(v):
            return str(v) if isinstance(v, Decimal) else v

        return {
            "chave": self.chave,
            "ok": self.ok,
            "achados": [
                {
                    "tipo": a.tipo,
                    "item": a.item,
                    "campo": a.campo,
                    "nota": texto(a.nota),
                    "esperado": texto(a.esperado),
                    "detalhe": a.detalhe,
                }
                for a in self.achados
            ],
        }


def _no(no, caminho: str):
    return no.find(caminho) if no is not None else None


def _txt(no, caminho: str) -> str | None:
    achado = _no(no, caminho)
    return achado.text.strip() if achado is not None and achado.text else None


def _dec(no, caminho: str) -> Decimal | None:
    valor = _txt(no, caminho)
    return Decimal(valor) if valor is not None else None


def _grupo(no, caminho: str):
    """Primeiro filho do grupo (ICMS00, ICMSSN102, PISAliq...)."""
    pai = _no(no, caminho)
    return pai[0] if pai is not None and len(pai) else None


class _Auditoria:
    def __init__(self, inf, regime: Regime | str | None):
        self.inf = inf
        self.relatorio = Relatorio(inf.get("Id", "").removeprefix("NFe"))
        self.achados = self.relatorio.achados
        self.dets = inf.findall("det")
        emit, dest, ide = (inf.find(x) for x in ("emit", "dest", "ide"))
        self.uf_emit, self.uf_dest = _txt(emit, "enderEmit/UF"), _txt(dest, "enderDest/UF")
        self.data = date.fromisoformat(_txt(ide, "dhEmi")[:10])
        self.regime = self._regime(_txt(emit, "CRT"), regime)
        credito = next((c for d in self.dets if (c := _dec(_grupo(d, "imposto/ICMS"), "pCredSN"))), None)
        self.emitente = Participante(
            self.uf_emit,
            self.regime,
            industria=any(_no(d, "imposto/IPI/IPITrib") is not None for d in self.dets),
            aliquota_credito_sn=credito,
        )
        self.destinatario = Participante(self.uf_dest, contribuinte_icms=_txt(dest, "indIEDest") == "1")
        self.consumidor_final = _txt(ide, "indFinal") == "1"

    def anotar(self, tipo, campo, nota, esperado, item=None, detalhe=""):
        self.achados.append(Achado(tipo, campo, nota, esperado, item, detalhe))

    def comparar(self, n, campo, informado, esperado, detalhe="", tolerancia=TOLERANCIA):
        if informado is None and not esperado:
            return
        if informado is None:
            self.anotar("regra", campo, None, esperado, n, f"devido e ausente na nota: {detalhe}")
        elif abs(informado - (esperado or ZERO)) > tolerancia:
            self.anotar("regra", campo, informado, esperado or ZERO, n, detalhe)

    def conta(self, n, campo, base, aliquota, valor):
        if None in (base, aliquota, valor):
            return
        esperado = centavos(base * pct(aliquota))
        if abs(esperado - valor) > TOLERANCIA:
            self.anotar("conta", campo, valor, esperado, n, f"{base} × {aliquota}%")

    def _regime(self, crt, regime) -> Regime:
        if crt in ("1", "2", "4"):
            return Regime.SIMPLES
        if regime is not None:
            return Regime(regime)
        aliquotas = {_dec(_grupo(d, "imposto/PIS"), "pPIS") for d in self.dets}
        if Decimal("1.65") in aliquotas:
            return Regime.REAL
        if Decimal("0.65") in aliquotas:
            return Regime.PRESUMIDO
        self.anotar("aviso", "CRT", crt, None, detalhe="regime não deduzível pelo PIS: considerado Lucro Real")
        return Regime.REAL

    # --- conta: o XML contra ele mesmo ---

    def contas(self, n, det):
        imposto = _no(det, "imposto")
        icms = _grupo(imposto, "ICMS")
        if icms is not None:
            operacao = _dec(icms, "vICMSOp")
            campo, valor = ("vICMSOp", operacao) if operacao is not None else ("vICMS", _dec(icms, "vICMS"))
            self.conta(n, campo, _dec(icms, "vBC"), _dec(icms, "pICMS"), valor)
            self.conta(n, "vFCP", _dec(icms, "vBC"), _dec(icms, "pFCP"), _dec(icms, "vFCP"))
            self.conta_st(n, det, icms)
        ipi = _no(imposto, "IPI/IPITrib")
        self.conta(n, "vIPI", _dec(ipi, "vBC"), _dec(ipi, "pIPI"), _dec(ipi, "vIPI"))
        for nome in ("PIS", "COFINS"):
            g = _grupo(imposto, f"{nome}")
            self.conta(n, f"v{nome}", _dec(g, "vBC"), _dec(g, f"p{nome}"), _dec(g, f"v{nome}"))
        destino = _no(imposto, "ICMSUFDest")
        if destino is not None:
            self.conta(
                n,
                "vFCPUFDest",
                _dec(destino, "vBCFCPUFDest") or _dec(destino, "vBCUFDest"),
                _dec(destino, "pFCPUFDest"),
                _dec(destino, "vFCPUFDest"),
            )
        g = _no(imposto, "IBSCBS/gIBSCBS")
        if g is not None:
            self.conta_base_ibs_cbs(n, det, g)
            base = _dec(g, "vBC")
            for campo, caminho in (("vIBSUF", "gIBSUF"), ("vIBSMun", "gIBSMun"), ("vCBS", "gCBS")):
                aliquota = _dec(g, f"{caminho}/gRed/pAliqEfet") or _dec(g, f"{caminho}/p{campo[1:]}")
                self.conta(n, campo, base, aliquota, _dec(g, f"{caminho}/{campo}"))

    def conta_st(self, n, det, icms):
        base_st, mva, aliquota_st, valor_st = (_dec(icms, f"{c}") for c in ("vBCST", "pMVAST", "pICMSST", "vICMSST"))
        if None in (base_st, aliquota_st, valor_st):
            return
        if mva is not None:
            prod = _no(det, "prod")
            valor = sum((_dec(prod, f"{c}") or ZERO for c in ("vProd", "vFrete", "vSeg", "vOutro")), ZERO)
            valor += _dec(det, "imposto/IPI/IPITrib/vIPI") or ZERO
            valor -= _dec(prod, "vDesc") or ZERO
            esperado = centavos(valor * (1 - pct(_dec(icms, "pRedBCST") or ZERO)) * (1 + pct(mva)))
            if abs(esperado - base_st) > TOLERANCIA:
                self.anotar("conta", "vBCST", base_st, esperado, n, f"(produto + IPI) × (1 + {mva}%)")
        proprio = _dec(icms, "vICMS") or ZERO
        esperado = max(centavos(base_st * pct(aliquota_st)) - proprio, ZERO)
        if abs(esperado - valor_st) > TOLERANCIA:
            self.anotar("conta", "vICMSST", valor_st, esperado, n, f"{base_st} × {aliquota_st}% − {proprio}")

    def conta_base_ibs_cbs(self, n, det, g):
        # NT 2025.002, UB16-10, com os valores da própria nota
        prod, imposto = _no(det, "prod"), _no(det, "imposto")
        mais = sum((_dec(prod, f"{c}") or ZERO for c in ("vProd", "vFrete", "vSeg", "vOutro")), ZERO)
        menos = (_dec(prod, "vDesc") or ZERO) + sum(
            (
                _dec(imposto, c) or ZERO
                for c in (
                    "PIS/*/vPIS",
                    "COFINS/*/vCOFINS",
                    "ICMS/*/vICMS",
                    "ICMS/*/vFCP",
                    "ICMSUFDest/vICMSUFDest",
                    "ICMSUFDest/vFCPUFDest",
                )
            ),
            ZERO,
        )
        base = _dec(g, "vBC")
        if base is not None and abs(base - (mais - menos)) > TOLERANCIA:
            self.anotar("conta", "vBC (IBS/CBS)", base, mais - menos, n, "NT 2025.002, UB16-10")

    # --- regra: recálculo pela legislação ---

    def st_interestadual(self, n, cest, icms):
        """A MVA vem da nota; aqui só se a ST cabe, pelo acordo entre as UFs (Conv. 142/18, cl. 2ª)."""
        revenda = self.destinatario.contribuinte_icms and not self.consumidor_final
        if self.uf_emit == self.uf_dest or not revenda:
            return
        acordo = tabelas.acordo_st(cest, self.uf_emit, self.uf_dest, self.data)
        tem_st = _dec(icms, "vICMSST") is not None
        if acordo and not tem_st:
            self.anotar(
                "regra",
                "vICMSST",
                None,
                None,
                n,
                f"ST devida pelo {acordo.ato} entre {self.uf_emit} e {self.uf_dest} e ausente na nota",
            )
        elif tem_st and not acordo:
            self.anotar(
                "aviso",
                "vICMSST",
                _dec(icms, "vICMSST"),
                None,
                n,
                f"sem acordo de ST entre {self.uf_emit} e {self.uf_dest} para o CEST {cest}: "
                "confira termo de acordo ou regime especial",
            )

    def item(self, det) -> Item:
        n = int(det.get("nItem"))
        prod, imposto = _no(det, "prod"), _no(det, "imposto")
        icms = _grupo(imposto, "ICMS")
        ncm, cest = _txt(prod, "NCM"), _txt(prod, "CEST")
        if cest:
            try:
                tabelas.conferir_cest(cest, ncm)
            except ValueError as erro:
                self.anotar("regra", "CEST", cest, None, n, str(erro))
            self.st_interestadual(n, cest, icms)
        beneficio = _beneficio(icms, _txt(prod, "cBenef"))
        return Item(
            ncm=ncm,
            valor=_dec(prod, "vProd"),
            origem=int(_txt(icms, "orig") or 0),
            frete=_dec(prod, "vFrete") or ZERO,
            seguro=_dec(prod, "vSeg") or ZERO,
            outras=_dec(prod, "vOutro") or ZERO,
            desconto=_dec(prod, "vDesc") or ZERO,
            beneficio=beneficio,
            pis_cofins=_SEM_PIS_COFINS.get(_txt(_grupo(imposto, "PIS"), "CST")),
            cclass_trib=_txt(imposto, "IBSCBS/cClassTrib") or "000001",
            aliquota_icms=self.aliquota_propria(n, imposto, icms, ncm),
        )

    def aliquota_propria(self, n, imposto, icms, ncm) -> Decimal | None:
        """Alíquota interna que difere da do produto (ou da modal): aceita da nota, com aviso."""
        if self.regime == Regime.SIMPLES:
            return None
        if self.uf_emit == self.uf_dest:
            informada, uf = _dec(icms, "pICMS"), self.uf_emit
        else:
            informada, uf = _dec(imposto, "ICMSUFDest/pICMSUFDest"), self.uf_dest
        if informada is None or informada == 0:
            return None
        produto = tabelas.aliquota_produto(uf, ncm, self.data, final=self.consumidor_final)
        esperada = produto.aliquota if produto else tabelas.dados_uf(uf, self.data).aliquota_interna
        if informada == esperada:
            return None
        if produto:
            detalhe = f"{uf} tem {esperada}% para este NCM ({produto.fundamento})"
        else:
            detalhe = f"diferente da modal de {uf}: confira se o produto tem alíquota própria"
        self.anotar("aviso", "alíquota interna", informada, esperada, n, detalhe)
        return informada

    def regras(self, n, det, item: Item, t: dict):
        imposto = _no(det, "imposto")
        icms = _grupo(imposto, "ICMS")
        tem_st = _dec(icms, "vICMSST") is not None
        if "ICMS" in t and self.regime != Regime.SIMPLES:
            e = t["ICMS"]
            self.comparar(n, "pICMS", _dec(icms, "pICMS"), e.aliquota, e.fundamento, ZERO)
            self.comparar(n, "vBC", _dec(icms, "vBC"), e.base, e.fundamento)
            self.comparar(n, "vICMS", _dec(icms, "vICMS"), e.valor, e.fundamento)
            self.comparar(
                n,
                "vFCP",
                _dec(icms, "vFCP"),
                t["FCP"].valor if "FCP" in t else None,
                t["FCP"].fundamento if "FCP" in t else "FCP não devido",
            )
        cst = _txt(icms, "CST") or _txt(icms, "CSOSN")
        esperado = t["ICMS"].cst
        if tem_st:
            esperado = _CST_COM_ST.get(esperado, esperado)
        if cst and esperado and cst != esperado:
            detalhe = t["ICMS"].fundamento
            if cst in ("101", "201") and not _dec(icms, "pCredSN"):
                detalhe = "CSOSN com crédito, mas pCredSN zerado: sem alíquota informada não há crédito (LC 123, art. 23, §4º)"
            self.anotar("regra", "CST" if len(cst) == 2 else "CSOSN", cst, esperado, n, detalhe)

        if "IPI" in t and t["IPI"].valor:
            self.comparar(n, "pIPI", _dec(imposto, "IPI/IPITrib/pIPI"), t["IPI"].aliquota, t["IPI"].fundamento, ZERO)

        for nome in ("PIS", "COFINS"):
            if nome not in t:
                continue  # extintos a partir de 2027
            g, e = _grupo(imposto, nome), t[nome]
            if self.regime == Regime.SIMPLES:
                # ERP costuma preencher vBC com alíquota zero no PISOutr: no Simples só o valor importa
                self.comparar(n, f"v{nome}", _dec(g, f"v{nome}"), ZERO, e.fundamento)
                continue
            base = _dec(g, "vBC")
            if base is not None and base == item.valor_operacao and e.base != base:
                self.anotar(
                    "aviso",
                    f"vBC ({nome})",
                    base,
                    e.base,
                    n,
                    "ICMS dentro da base: a exclusão é direito do contribuinte (STF, Tema 69)",
                )
                continue
            if base is not None and base == item.valor_operacao - (_dec(icms, "vICMS") or ZERO) != e.base:
                continue  # coerente com o ICMS da nota: a divergência já foi apontada no ICMS
            self.comparar(n, f"p{nome}", _dec(g, f"p{nome}"), e.aliquota, e.fundamento, ZERO)
            self.comparar(n, f"v{nome}", _dec(g, f"v{nome}"), e.valor, e.fundamento)

        destino = _no(imposto, "ICMSUFDest")
        if "DIFAL" in t or destino is not None:
            e = t.get("DIFAL")
            detalhe = e.fundamento if e else "DIFAL não devido nesta operação"
            self.comparar(n, "vBCUFDest", _dec(destino, "vBCUFDest"), e.base if e else None, detalhe)
            self.comparar(n, "vICMSUFDest", _dec(destino, "vICMSUFDest"), e.valor if e else None, detalhe)
            f = t.get("FCP_DIFAL")
            self.comparar(n, "vFCPUFDest", _dec(destino, "vFCPUFDest"), f.valor if f else None, detalhe)

        if "CBS" in t:
            e = t["CBS"]
            if _no(imposto, "IBSCBS") is None:
                self.anotar("regra", "IBSCBS", None, e.cst, n, "grupo obrigatório para CRT 3 desde 03/08/2026")
                return
            self.comparar_texto(n, "CST (IBS/CBS)", _txt(imposto, "IBSCBS/CST"), e.cst, e.fundamento)
            g = _no(imposto, "IBSCBS/gIBSCBS")
            for campo, caminho, nome in (("pCBS", "gCBS", "CBS"), ("pIBSUF", "gIBSUF", "IBS_UF")):
                esperada = t[nome].extras.get("aliquota_efetiva", t[nome].aliquota)
                informada = _dec(g, f"{caminho}/gRed/pAliqEfet") or _dec(g, f"{caminho}/{campo}")
                if g is not None:
                    self.comparar(n, campo, informada, esperada, t[nome].fundamento, ZERO)

    def comparar_texto(self, n, campo, informado, esperado, detalhe):
        if informado != esperado:
            self.anotar("regra", campo, informado, esperado, n, detalhe)

    def rodar(self) -> Relatorio:
        for det in self.dets:
            self.contas(int(det.get("nItem")), det)
        ide = self.inf.find("ide")
        if _txt(ide, "tpNF") == "0" or _txt(ide, "finNFe") in ("2", "3", "4"):
            self.anotar(
                "aviso",
                "finNFe",
                _txt(ide, "finNFe"),
                "1",
                detalhe="entrada, complementar, ajuste ou devolução: só a conta foi conferida",
            )
            return self.relatorio
        itens = [self.item(det) for det in self.dets]
        nota = Nota(self.emitente, self.destinatario, itens, data=self.data, consumidor_final=self.consumidor_final)
        self.relatorio.recalculo = calcular(nota)
        for det, resultado in zip(self.dets, self.relatorio.recalculo.itens, strict=True):
            self.regras(int(det.get("nItem")), det, resultado.item, resultado.tributos)

        # a ST vem da nota (MVA não é inferida), então entra no total como informada
        st = sum((_dec(d, f"imposto/ICMS/*/{c}") or ZERO for d in self.dets for c in ("vICMSST", "vFCPST")), ZERO)
        total = _dec(self.inf, "total/ICMSTot/vNF")
        self.comparar(
            None,
            "vNF",
            total,
            self.relatorio.recalculo.valor_nota + st,
            "produtos − desconto + frete + seguro + outras + IPI + ST",
        )
        return self.relatorio


def _beneficio(icms, cbenef: str | None) -> Beneficio | None:
    if icms is None:
        return None
    cst = _txt(icms, "CST")
    if (reducao := _dec(icms, "pRedBC")) is not None and reducao > 0:
        return Beneficio(Tratamento.REDUCAO_BASE, reducao, cbenef, "redução informada na nota")
    if cst in ("40", "41"):
        return Beneficio(
            Tratamento.ISENCAO if cst == "40" else Tratamento.NAO_TRIBUTADA,
            cbenef=cbenef,
            fundamento="tratamento informado na nota",
        )
    if cst == "51" and (diferido := _dec(icms, "pDif")) is not None:
        return Beneficio(Tratamento.DIFERIMENTO, diferido, cbenef, "diferimento informado na nota")
    return None


def auditar(xml: str | bytes | Path, *, regime: Regime | str | None = None) -> Relatorio:
    """`xml`: conteúdo ou caminho. `regime` só vale quando o CRT é 3 e o PIS da nota não o denuncia."""
    if isinstance(xml, Path) or (isinstance(xml, str) and not xml.lstrip().startswith("<")):
        xml = Path(xml).read_bytes()
    raiz = ET.fromstring(xml)
    # ERP exporta com e sem nfeProc, com e sem o namespace do portal
    for no in raiz.iter():
        no.tag = no.tag.rsplit("}", 1)[-1]
    inf = raiz if raiz.tag == "infNFe" else raiz.find(".//infNFe")
    if inf is None:
        raise ValueError("XML sem infNFe: não é uma NF-e")
    return _Auditoria(inf, regime).rodar()
