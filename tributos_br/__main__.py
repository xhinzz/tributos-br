"""Nota em JSON -> cálculo; NF-e em XML -> auditoria. Arquivo ou '-' para stdin."""

from __future__ import annotations

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path

from .auditoria import auditar
from .calculo import calcular
from .modelos import Beneficio, Item, Nota, Participante


def nota_de_dict(dados: dict) -> Nota:
    itens = []
    for i in dados["itens"]:
        i = dict(i)
        if isinstance(i.get("beneficio"), dict):
            i["beneficio"] = Beneficio(**i["beneficio"])
        itens.append(Item(**i))
    extras = {k: dados[k] for k in ("consumidor_final", "metodo_difal") if k in dados}
    if "data" in dados:
        extras["data"] = date.fromisoformat(dados["data"])
    return Nota(Participante(**dados["emitente"]), Participante(**dados["destinatario"]), itens, **extras)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="tributos-br", description=__doc__.splitlines()[0])
    parser.add_argument("arquivo", help="JSON da nota ou XML da NF-e; '-' lê do stdin")
    parser.add_argument("--regime", choices=["real", "presumido"], help="auditoria: regime quando o CRT é 3")
    args = parser.parse_args(argv)
    texto = sys.stdin.read() if args.arquivo == "-" else Path(args.arquivo).read_text(encoding="utf-8")
    try:
        if texto.lstrip().startswith("<"):
            relatorio = auditar(texto.encode("utf-8"), regime=args.regime)
            print(json.dumps(relatorio.como_dict(), ensure_ascii=False, indent=2))
            return 0 if relatorio.ok else 3
        resultado = calcular(nota_de_dict(json.loads(texto)))
    except (LookupError, TypeError, ValueError, ET.ParseError) as erro:
        print(json.dumps({"erro": str(erro)}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps(resultado.como_dict(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
