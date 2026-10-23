"""Entrada e saída. Dinheiro e percentual em Decimal; 18 é 18%."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from enum import Enum

ZERO = Decimal(0)
CEM = Decimal(100)


def D(valor) -> Decimal:
    """float passa por repr: 0.1 vira Decimal('0.1'), não 0.1000000000000000055."""
    if isinstance(valor, Decimal):
        return valor
    if isinstance(valor, float):
        return Decimal(repr(valor))
    return Decimal(valor)


def centavos(valor: Decimal) -> Decimal:
    return valor.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def pct(valor: Decimal) -> Decimal:
    return valor / CEM


class Regime(str, Enum):
    SIMPLES = "simples"
    PRESUMIDO = "presumido"
    REAL = "real"


class Tratamento(str, Enum):
    REDUCAO_BASE = "reducao_base"
    ISENCAO = "isencao"
    NAO_TRIBUTADA = "nao_tributada"
    DIFERIMENTO = "diferimento"


UFS = frozenset(
    [
        "AC",
        "AL",
        "AM",
        "AP",
        "BA",
        "CE",
        "DF",
        "ES",
        "GO",
        "MA",
        "MG",
        "MS",
        "MT",
        "PA",
        "PB",
        "PE",
        "PI",
        "PR",
        "RJ",
        "RN",
        "RO",
        "RR",
        "RS",
        "SC",
        "SE",
        "SP",
        "TO",
    ]
)


@dataclass(frozen=True)
class Participante:
    uf: str
    regime: Regime = Regime.REAL
    contribuinte_icms: bool = True
    # destaca IPI
    industria: bool = False
    # CSOSN 101/201: alíquota de ICMS do DAS no mês
    aliquota_credito_sn: Decimal | None = None
    cnpj: str | None = None

    def __post_init__(self):
        object.__setattr__(self, "uf", self.uf.upper())
        if self.uf not in UFS:
            raise ValueError(f"UF inválida: {self.uf!r}")
        object.__setattr__(self, "regime", Regime(self.regime))
        if self.aliquota_credito_sn is not None:
            object.__setattr__(self, "aliquota_credito_sn", D(self.aliquota_credito_sn))


@dataclass(frozen=True)
class Beneficio:
    """Benefício que a base de regras não tem."""

    tratamento: Tratamento
    percentual: Decimal = ZERO  # redução de base ou % diferido
    cbenef: str | None = None
    fundamento: str = "informado pelo usuário"
    # redução que o destino aplica no DIFAL/ST
    reducao_destino: Decimal = ZERO

    def __post_init__(self):
        object.__setattr__(self, "tratamento", Tratamento(self.tratamento))
        for nome in ("percentual", "reducao_destino"):
            valor = D(getattr(self, nome))
            if not 0 <= valor <= 100:
                raise ValueError(f"{nome} deve estar entre 0 e 100")
            object.__setattr__(self, nome, valor)


@dataclass(frozen=True)
class Item:
    ncm: str
    valor: Decimal  # vProd
    origem: int = 0  # 0 a 8, tabela da NF-e
    frete: Decimal = ZERO
    seguro: Decimal = ZERO
    outras: Decimal = ZERO
    desconto: Decimal = ZERO  # incondicional
    cest: str | None = None
    ex_tipi: str = ""
    descricao: str = ""
    # sobrescrevem as tabelas
    aliquota_ipi: Decimal | None = None
    aliquota_icms: Decimal | None = None
    mva: Decimal | None = None  # liga a ST
    # código da base (conv52_91_anexo_i...) ou Beneficio
    beneficio: Beneficio | str | None = None
    # monofasico (CST 04) | aliquota_zero (06) | isenta (07) | suspensao (09)
    pis_cofins: str | None = None

    def __post_init__(self):
        if self.pis_cofins not in (None, "monofasico", "aliquota_zero", "isenta", "suspensao"):
            raise ValueError(f"pis_cofins inválido: {self.pis_cofins!r}")
        ncm = self.ncm.replace(".", "").strip()
        if len(ncm) != 8 or not ncm.isdigit():
            raise ValueError(f"NCM deve ter 8 dígitos: {self.ncm!r}")
        object.__setattr__(self, "ncm", ncm)
        if self.origem not in range(9):
            raise ValueError(f"origem deve ser de 0 a 8: {self.origem!r}")
        for nome in ("valor", "frete", "seguro", "outras", "desconto", "aliquota_ipi", "aliquota_icms", "mva"):
            if (v := getattr(self, nome)) is not None:
                v = D(v)
                if v < 0:
                    raise ValueError(f"{nome} não pode ser negativo")
                object.__setattr__(self, nome, v)
        if self.desconto > self.valor:
            raise ValueError("desconto maior que o valor do item")

    @property
    def valor_operacao(self) -> Decimal:
        return self.valor + self.frete + self.seguro + self.outras - self.desconto


@dataclass(frozen=True)
class Nota:
    emitente: Participante
    destinatario: Participante
    itens: list[Item]
    data: date = field(default_factory=date.today)
    # indFinal; sem informar, segue o contribuinte_icms do destinatário
    consumidor_final: bool | None = None
    # sobrescreve o método da UF: unica | dupla | por_dentro
    metodo_difal: str | None = None

    def __post_init__(self):
        if not self.itens:
            raise ValueError("a nota precisa de ao menos um item")
        if self.metodo_difal not in (None, "unica", "dupla", "por_dentro"):
            raise ValueError(f"metodo_difal inválido: {self.metodo_difal!r}")
        if self.consumidor_final is None:
            object.__setattr__(self, "consumidor_final", not self.destinatario.contribuinte_icms)

    @property
    def interestadual(self) -> bool:
        return self.emitente.uf != self.destinatario.uf


@dataclass
class Tributo:
    base: Decimal
    aliquota: Decimal
    valor: Decimal
    cst: str | None = None
    fundamento: str = ""
    extras: dict[str, Decimal | str] = field(default_factory=dict)


@dataclass
class ResultadoItem:
    item: Item
    tributos: dict[str, Tributo]

    @property
    def valor_total(self) -> Decimal:
        """Parcela do item no vNF. IBS/CBS ficam de fora em 2026 (NT 2025.002, VB01-10)."""
        t = self.tributos
        acrescimos = sum((t[n].valor for n in ("IPI", "ICMS_ST", "FCP_ST") if n in t), ZERO)
        return self.item.valor_operacao + acrescimos


@dataclass
class ResultadoNota:
    itens: list[ResultadoItem]

    @property
    def totais(self) -> dict[str, Decimal]:
        soma: dict[str, Decimal] = {}
        for r in self.itens:
            for nome, t in r.tributos.items():
                soma[nome] = soma.get(nome, ZERO) + t.valor
        return soma

    @property
    def valor_nota(self) -> Decimal:
        return sum((r.valor_total for r in self.itens), ZERO)

    def como_dict(self) -> dict:
        """Decimal vira str, para o JSON não perder casa."""

        def limpar(obj):
            if isinstance(obj, Decimal):
                return str(obj)
            if isinstance(obj, Enum):
                return obj.value
            if isinstance(obj, dict):
                return {k: limpar(v) for k, v in obj.items()}
            if isinstance(obj, (list, tuple)):
                return [limpar(v) for v in obj]
            return obj

        return limpar(
            {
                "itens": [
                    {
                        "ncm": r.item.ncm,
                        "valor_total": r.valor_total,
                        "tributos": {n: asdict(t) for n, t in r.tributos.items()},
                    }
                    for r in self.itens
                ],
                "totais": self.totais,
                "valor_nota": self.valor_nota,
            }
        )
