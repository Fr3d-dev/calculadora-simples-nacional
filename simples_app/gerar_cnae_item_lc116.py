# -*- coding: utf-8 -*-
"""Gera o arquivo de dados CNAE -> itens da LC 116 a partir da planilha oficial.

Uso:
    python gerar_cnae_item_lc116.py [caminho_da_planilha]

Gera `cnae_item_lc116.py` (dict literal) na mesma pasta. Fonte:
Cnae_X_Item_Lista_Servicos.xlsx, aba "Dados".

A planilha tem uma linha por par (CNAE, item): um CNAE pode apontar para
vários itens (até 18) e um item pode aparecer em vários CNAEs.
"""
from __future__ import annotations

import os
import sys

COL_CNAE = 0
COL_DESC_CNAE = 1
COL_ITEM = 2
COL_DESC_ITEM = 3


def _txt(v) -> str:
    if v is None:
        return ""
    return " ".join(str(v).split()).strip()


def _codigo(v) -> str:
    return "".join(c for c in str(v or "") if c.isdigit())


def main(argv):
    base = os.path.dirname(os.path.abspath(__file__))
    planilha = argv[1] if len(argv) > 1 else os.path.join(
        os.path.dirname(base), "Cnae_X_Item_Lista_Servicos.xlsx"
    )

    import openpyxl

    wb = openpyxl.load_workbook(planilha, data_only=True)
    ws = wb["Dados"]

    mapa = {}          # cnae -> [itens] (ordem de aparição)
    descricoes = {}    # cnae -> descrição oficial
    itens = {}         # subitem -> descrição legal

    linhas = 0
    descartadas = 0
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row or row[COL_CNAE] is None:
            continue
        cnae = _codigo(row[COL_CNAE])
        item = _txt(row[COL_ITEM])
        if not cnae or not item:
            descartadas += 1
            continue
        linhas += 1
        descricoes.setdefault(cnae, _txt(row[COL_DESC_CNAE]))
        itens.setdefault(item, _txt(row[COL_DESC_ITEM]))
        lista = mapa.setdefault(cnae, [])
        if item not in lista:
            lista.append(item)

    destino = os.path.join(base, "cnae_item_lc116.py")
    with open(destino, "w", encoding="utf-8", newline="\n") as fh:
        fh.write('# -*- coding: utf-8 -*-\n')
        fh.write('"""CNAE -> itens da LC 116/2003 (gerado por '
                 'gerar_cnae_item_lc116.py).\n\n')
        fh.write("Fonte: Cnae_X_Item_Lista_Servicos.xlsx (aba 'Dados').\n")
        fh.write("NAO EDITE A MAO: rode o gerador de novo.\n")
        fh.write('"""\n\n')
        fh.write("CNAE_ITEM = {\n")
        for cnae in sorted(mapa):
            fh.write("    %r: %r,\n" % (cnae, mapa[cnae]))
        fh.write("}\n\n")
        fh.write("CNAE_DESCRICAO = {\n")
        for cnae in sorted(descricoes):
            fh.write("    %r: %r,\n" % (cnae, descricoes[cnae]))
        fh.write("}\n\n")
        fh.write("ITEM_DESCRICAO = {\n")
        for item in sorted(itens):
            fh.write("    %r: %r,\n" % (item, itens[item]))
        fh.write("}\n")

    print("linhas=%d descartadas=%d cnaes=%d itens=%d -> %s"
          % (linhas, descartadas, len(mapa), len(itens), destino))


if __name__ == "__main__":
    main(sys.argv)
