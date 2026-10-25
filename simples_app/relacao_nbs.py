"""Leitor da planilha RELAÇÃO NBS x cClassTrib x Indicador de Operação.

A planilha fica na raiz do projeto (um nível acima do pacote do app). Ela é
usada apenas como SEMENTE: na primeira execução, se a tabela `relacao_nbs`
estiver vazia, as linhas são copiadas para o banco. Depois disso a fonte da
verdade passa a ser o banco, editável em Administração > Tabelas > Relação NBS,
sem precisar mexer em código nem republicar o app.

Colunas da aba "tabela geral" (A..L):
    A Item LC 116 | B Descrição Item | C NBS | D DESCRIÇÃO NBS
    E PS ONEROSA? (S/N) | F ADQ EXTERIOR? (S/N) | G INDOP
    H Local incidência IBS | I cClassTrib | J nome cClassTrib
    K e L (colunas auxiliares da planilha original)
"""

from __future__ import annotations

import os

NOME_ARQUIVO = "RELAÇÃO NBS Cclasstrib e Ind Operac.xlsx"
ABA = "tabela geral"

# Ordem/nomes exatamente como na planilha.
COLUNAS = [
    "item_lc116",        # A - Item LC 116
    "descricao_item",    # B - Descrição Item
    "nbs",               # C - NBS
    "descricao_nbs",     # D - DESCRIÇÃO NBS
    "ps_onerosa",        # E - PS ONEROSA? (S/N)
    "adq_exterior",      # F - ADQ EXTERIOR? (S/N)
    "indop",             # G - INDOP
    "local_incidencia",  # H - Local incidência IBS
    "cclasstrib",        # I - cClassTrib
    "nome_cclasstrib",   # J - nome cClassTrib
]

ROTULOS = {
    "item_lc116": "Item LC 116",
    "descricao_item": "Descrição Item",
    "nbs": "NBS",
    "descricao_nbs": "DESCRIÇÃO NBS",
    "ps_onerosa": "PS ONEROSA? (S/N)",
    "adq_exterior": "ADQ EXTERIOR? (S/N)",
    "indop": "INDOP",
    "local_incidencia": "Local incidência IBS",
    "cclasstrib": "cClassTrib",
    "nome_cclasstrib": "nome cClassTrib",
}


def caminho_planilha(app_dir: str) -> str:
    """Caminho da planilha: primeiro ao lado do app, depois na raiz do projeto."""
    candidatos = [
        os.path.join(app_dir, NOME_ARQUIVO),
        os.path.join(os.path.dirname(app_dir.rstrip("/\\")), NOME_ARQUIVO),
    ]
    for caminho in candidatos:
        if os.path.exists(caminho):
            return caminho
    # Se não achar, devolve o candidato mais provável (para a mensagem de erro).
    return candidatos[1]


def _texto(valor) -> str:
    if valor is None:
        return ""
    if isinstance(valor, float) and valor.is_integer():
        valor = int(valor)
    return str(valor).strip()


def ler_planilha(caminho: str | None = None, app_dir: str | None = None) -> list[dict]:
    """Lê a aba "tabela geral" e devolve uma lista de dicionários.

    A linha 1 é o cabeçalho; cada linha seguinte vira um registro com as 10
    colunas de COLUNAS preenchidas (strings, já sem espaços nas pontas).
    """
    import openpyxl

    if caminho is None:
        base = app_dir or os.path.dirname(os.path.abspath(__file__))
        caminho = caminho_planilha(base)
    if not os.path.exists(caminho):
        raise FileNotFoundError(f"Planilha não encontrada: {caminho}")

    wb = openpyxl.load_workbook(caminho, read_only=True, data_only=True)
    try:
        if ABA in wb.sheetnames:
            ws = wb[ABA]
        else:
            ws = wb[wb.sheetnames[0]]

        registros = []
        for numero, linha in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
            if linha is None or all(v is None or _texto(v) == "" for v in linha):
                continue
            registro = {col: "" for col in COLUNAS}
            for indice, col in enumerate(COLUNAS):
                if indice < len(linha):
                    registro[col] = _texto(linha[indice])
            # Linha sem NBS e sem cClassTrib não é dado: é sobra de formatação.
            if not registro["nbs"] and not registro["cclasstrib"]:
                continue
            registro["ordem"] = numero - 1
            registros.append(registro)
        return registros
    finally:
        wb.close()
