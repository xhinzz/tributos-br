"""Tabelas de dados/, por vigência: alíquota nova é linha nova no CSV, e nota antiga segue com a regra antiga."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from functools import cache, lru_cache
from importlib import resources

from .modelos import D, Tratamento


def _ler(nome: str) -> list[dict[str, str]]:
    with resources.files("tributos_br").joinpath("dados", *nome.split("/")).open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _vigente(linha: dict[str, str], data: date) -> bool:
    inicio = date.fromisoformat(linha["vigencia_inicio"])
    fim = linha.get("vigencia_fim") or ""
    return inicio <= data and (not fim or data <= date.fromisoformat(fim))


@dataclass(frozen=True)
class DadosUF:
    uf: str
    aliquota_interna: Decimal
    fcp: Decimal
    difal_base: str  # unica | dupla | por_dentro
    difal_conferido: bool  # método confirmado em fonte oficial da UF
    difal_fonte: str
    fonte: str


@lru_cache(maxsize=1)
def _ufs() -> list[dict[str, str]]:
    return _ler("ufs.csv")


def dados_uf(uf: str, data: date) -> DadosUF:
    vigentes = [linha for linha in _ufs() if linha["uf"] == uf and _vigente(linha, data)]
    if not vigentes:
        raise LookupError(f"sem alíquota de ICMS de {uf} vigente em {data:%d/%m/%Y}")
    linha = max(vigentes, key=lambda x: x["vigencia_inicio"])
    return DadosUF(
        uf,
        D(linha["aliquota_interna"]),
        D(linha["fcp"]),
        linha["difal_base"],
        linha["difal_conferido"] == "sim",
        linha["difal_fonte"],
        linha["fonte"],
    )


@lru_cache(maxsize=1)
def _tipi() -> dict[tuple[str, str], str]:
    return {(linha["ncm"], linha["ex"]): linha["aliquota"] for linha in _ler("tipi.csv")}


def aliquota_tipi(ncm: str, ex: str = "") -> Decimal | None:
    """None se NT. KeyError se o NCM não está na TIPI."""
    aliquota = _tipi()[(ncm, ex)]
    return None if aliquota == "NT" else D(aliquota)


@dataclass(frozen=True)
class Regra:
    codigo: str
    tratamento: Tratamento
    percentual: Decimal
    cbenef: str | None
    fundamento: str


@lru_cache(maxsize=1)
def _beneficios() -> list[dict[str, str]]:
    return _ler("beneficios.csv")


@cache
def _lista(nome: str) -> tuple[str, ...]:
    return tuple(linha["ncm"] for linha in _ler(f"listas/{nome}.csv"))


def _ncms_da_regra(linha: dict[str, str]) -> tuple[str, ...]:
    """Vazio: o ato descreve o produto sem NCM."""
    campo = linha["ncm"]
    if campo.startswith("@"):
        return _lista(campo[1:])
    return tuple(p for p in campo.split("|") if p)


def _cobre(prefixos: tuple[str, ...], ncm: str) -> bool:
    return not prefixos or any(ncm.startswith(p) for p in prefixos)


def regra(codigo: str, ncm: str, uf_origem: str, uf_destino: str, aliquota: Decimal, data: date) -> Regra:
    """Benefício declarado por quem emite.

    Só ele sabe se as condições do ato se cumprem (destinação, registro no MAPA, descrição exata); aqui só se recusa
    o que comprovadamente não cabe.
    """
    linhas = [linha for linha in _beneficios() if linha["codigo"] == codigo]
    if not linhas:
        raise ValueError(f"benefício desconhecido: {codigo!r}")
    operacao = "interestadual" if uf_origem != uf_destino else "interna"
    motivos = []
    for linha in linhas:
        if linha["uf"] not in ("*", uf_origem):
            motivos.append(f"só vale em {linha['uf']}")
        elif linha["operacao"] not in ("qualquer", operacao):
            motivos.append(f"só vale em operação {linha['operacao']}")
        elif linha["aliquota"] and D(linha["aliquota"]) != aliquota:
            motivos.append(f"faixa da alíquota de {linha['aliquota']}%")
        elif not _vigente(linha, data):
            motivos.append(f"vigência {linha['vigencia_inicio']} a {linha['vigencia_fim'] or 'indeterminada'}")
        elif not _cobre(_ncms_da_regra(linha), ncm):
            motivos.append(f"NCM {ncm} fora da lista da regra")
        else:
            return Regra(
                codigo,
                Tratamento(linha["tratamento"]),
                _percentual(linha, aliquota),
                linha["cbenef"] or None,
                linha["fundamento"],
            )
    raise ValueError(f"benefício {codigo} não se aplica: " + "; ".join(dict.fromkeys(motivos)))


def _percentual(linha: dict[str, str], aliquota: Decimal) -> Decimal:
    if not linha["carga"]:
        return D(linha["percentual"] or 0)
    # carga efetiva -> redução de base
    carga = D(linha["carga"])
    if carga >= aliquota:
        return Decimal(0)
    return ((1 - carga / aliquota) * 100).quantize(Decimal("0.0001"))


def sugerir(ncm: str, data: date) -> list[tuple[str, str, str]]:
    """(código, descrição, critério). 'ncm': casou na lista do ato; 'descricao': só lendo o ato."""
    vistos: dict[str, tuple[str, str]] = {}
    for linha in _beneficios():
        prefixos = _ncms_da_regra(linha)
        if _vigente(linha, data) and _cobre(prefixos, ncm):
            vistos.setdefault(linha["codigo"], (linha["descricao"], "ncm" if prefixos else "descricao"))
    return sorted(((c, d, k) for c, (d, k) in vistos.items()), key=lambda x: x[2] != "ncm")


@lru_cache(maxsize=1)
def _cest() -> dict[str, tuple[str, ...]]:
    tabela: dict[str, list[str]] = {}
    for linha in _ler("cest.csv"):
        tabela.setdefault(linha["cest"], []).append(linha["ncm"])
    return {cest: tuple(ncms) for cest, ncms in tabela.items()}


def conferir_cest(cest: str, ncm: str) -> None:
    """Conv. 142/18, cl. 7ª."""
    ncms = _cest().get(cest)
    if ncms is None:
        raise ValueError(f"CEST {cest} não existe no Conv. ICMS 142/2018")
    if not _cobre(ncms, ncm):
        raise ValueError(f"NCM {ncm} não pertence ao CEST {cest}")


@lru_cache(maxsize=1)
def _mva() -> list[dict[str, str]]:
    return _ler("mva.csv")


def mva(uf_destino: str, ncm: str, cest: str | None, data: date) -> tuple[Decimal, str] | None:
    """MVA original por UF de destino e CEST."""
    candidatas = []
    for linha in _mva():
        if linha["uf"] != uf_destino or not _vigente(linha, data):
            continue
        if linha["cest"] and linha["cest"] != (cest or ""):
            continue
        prefixo = next((p for p in linha["ncm"].split("|") if ncm.startswith(p)), None)
        if prefixo is not None:
            candidatas.append((bool(linha["cest"]), len(prefixo), linha))
    if not candidatas:
        return None
    linha = max(candidatas, key=lambda c: c[:2])[2]
    return D(linha["mva"]), linha["fundamento"]


@dataclass(frozen=True)
class ClassTrib:
    cst: str
    codigo: str
    nome: str
    tipo: str  # Padrão | Sem alíquota | Fixa | Uniforme...
    red_ibs: Decimal
    red_cbs: Decimal
    anexo: int | None  # anexo da LC 214 com a lista de NCMs
    fundamento: str


@lru_cache(maxsize=1)
def _cclass() -> dict[str, list[dict[str, str]]]:
    tabela: dict[str, list[dict[str, str]]] = {}
    for linha in _ler("cclass_trib.csv"):
        tabela.setdefault(linha["cclass_trib"], []).append(linha)
    return tabela


def cclass_trib(codigo: str, data: date) -> ClassTrib:
    """IT 2025.002. ValueError se não existe, não vale na data ou não é de NF-e."""
    linhas = _cclass().get(codigo)
    if not linhas:
        raise ValueError(f"cClassTrib {codigo} não existe")
    linha = next((x for x in linhas if _vigente(x, data)), None)
    if linha is None:
        raise ValueError(f"cClassTrib {codigo} sem vigência em {data:%d/%m/%Y}")
    if linha["nfe"] != "1":
        raise ValueError(f"cClassTrib {codigo} não é usado em NF-e")
    fundamento = f"LC 214/2025, {linha['fundamento']}" if linha["fundamento"] else "LC 214/2025"
    return ClassTrib(
        linha["cst"],
        codigo,
        linha["nome"],
        linha["tipo"],
        D(linha["p_red_ibs"]),
        D(linha["p_red_cbs"]),
        int(linha["anexo"]) if linha["anexo"] else None,
        fundamento,
    )


def no_anexo_lc214(anexo: int, ncm: str) -> bool:
    """Exceção ("!0709 5" para "exceto ... 0709.5") vence a inclusão mais genérica."""
    codigos = _lista(f"lc214_anexo_{anexo}")
    if any(ncm.startswith(c[1:]) for c in codigos if c.startswith("!")):
        return False
    return any(ncm.startswith(c) for c in codigos if not c.startswith("!"))


def sugerir_cclass_trib(ncm: str, data: date) -> list[tuple[str, str]]:
    """cClassTrib de NF-e cujo anexo da LC 214 lista o NCM."""
    saida = []
    for codigo, linhas in _cclass().items():
        linha = next((x for x in linhas if _vigente(x, data)), None)
        if linha and linha["nfe"] == "1" and linha["anexo"] and no_anexo_lc214(int(linha["anexo"]), ncm):
            saida.append((codigo, linha["nome"]))
    return saida


@dataclass(frozen=True)
class AcordoST:
    codigo: str
    ato: str
    base: str  # mva | preco (PMPF, preço sugerido)
    mva: Decimal | None  # a do próprio ato; None quando vale a legislação do destino
    fundamento: str


@lru_cache(maxsize=1)
def _acordos() -> list[dict[str, str]]:
    return _ler("st_acordos.csv")


def _excluido(excecoes: str, cest: str, uf_origem: str, uf_destino: str) -> bool:
    """cest:p1,p2 (sempre) | uf:XX:p1,p2 (XX na origem ou no destino) | destino:XX:p1,p2. Sem prefixo, vale tudo."""
    for regra in filter(None, excecoes.split("|")):
        partes = regra.split(":")
        prefixos = [p for p in partes[-1].split(",") if p]
        if partes[0] == "uf" and partes[1] not in (uf_origem, uf_destino):
            continue
        if partes[0] == "destino" and partes[1] != uf_destino:
            continue
        if not prefixos or any(cest.startswith(p) for p in prefixos):
            return True
    return False


def acordo_st(cest: str, uf_origem: str, uf_destino: str, data: date) -> AcordoST | None:
    """Acordo de ST do segmento do CEST com as duas UFs signatárias (Conv. 142/18, cl. 2ª)."""
    for linha in _acordos():
        ufs = linha["ufs"].split("|")
        if (
            cest[:2] in linha["segmentos"].split("|")
            and uf_origem in ufs
            and uf_destino in ufs
            and _vigente(linha, data)
            and not _excluido(linha["excecoes"], cest, uf_origem, uf_destino)
        ):
            proprio = uf_destino in linha["mva_destino_proprio"].split("|")
            mva = D(linha["mva"]) if linha["mva"] and not proprio else None
            return AcordoST(linha["codigo"], linha["ato"], linha["base"], mva, linha["fundamento"])
    return None
