"""Monta XML de NF-e no leiaute 4.00 para os testes de auditoria."""


def _tags(campos: dict) -> str:
    return "".join(
        f"<{k}>{v}</{k}>" if not isinstance(v, dict) else f"<{k}>{_tags(v)}</{k}>" for k, v in campos.items()
    )


def item(
    n=1, ncm="84713012", v_prod="1000.00", icms=None, ipi=None, pis=None, cofins=None, difal=None, ibscbs=None, **prod
):
    imposto = {
        "ICMS": icms
        or {"ICMS00": {"orig": 0, "CST": "00", "modBC": 3, "vBC": "1000.00", "pICMS": "18.00", "vICMS": "180.00"}}
    }
    if ipi:
        imposto["IPI"] = {"cEnq": "999", "IPITrib": ipi}
    imposto["PIS"] = pis or {"PISAliq": {"CST": "01", "vBC": "820.00", "pPIS": "1.65", "vPIS": "13.53"}}
    imposto["COFINS"] = cofins or {"COFINSAliq": {"CST": "01", "vBC": "820.00", "pCOFINS": "7.60", "vCOFINS": "62.32"}}
    if difal:
        imposto["ICMSUFDest"] = difal
    if ibscbs is not False:
        imposto["IBSCBS"] = ibscbs or {
            "CST": "000",
            "cClassTrib": "000001",
            "gIBSCBS": {
                "vBC": "744.15",
                "gIBSUF": {"pIBSUF": "0.1000", "vIBSUF": "0.74"},
                "gIBSMun": {"pIBSMun": "0.0000", "vIBSMun": "0.00"},
                "vIBS": "0.74",
                "gCBS": {"pCBS": "0.9000", "vCBS": "6.70"},
            },
        }
    produto = {"cProd": n, "xProd": "Produto", "NCM": ncm, **prod, "CFOP": "5102", "vProd": v_prod}
    return f'<det nItem="{n}"><prod>{_tags(produto)}</prod><imposto>{_tags(imposto)}</imposto></det>'


def nfe(
    *itens,
    uf_emit="SP",
    uf_dest="SP",
    crt=3,
    ind_ie_dest=1,
    ind_final=0,
    v_nf="1000.00",
    data="2026-10-23T10:00:00-03:00",
):
    itens = itens or (item(),)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe" versao="4.00"><NFe><infNFe Id="NFe35261011222333000181550010000000011000000010" versao="4.00">
<ide><cUF>35</cUF><dhEmi>{data}</dhEmi><indFinal>{ind_final}</indFinal></ide>
<emit><CNPJ>11222333000181</CNPJ><enderEmit><UF>{uf_emit}</UF></enderEmit><CRT>{crt}</CRT></emit>
<dest><CNPJ>11444777000161</CNPJ><enderDest><UF>{uf_dest}</UF></enderDest><indIEDest>{ind_ie_dest}</indIEDest></dest>
{"".join(itens)}
<total><ICMSTot><vNF>{v_nf}</vNF></ICMSTot></total>
</infNFe></NFe></nfeProc>"""
