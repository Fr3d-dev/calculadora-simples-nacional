"""Relatório Reforma: preenche NBS / cClassTrib / IndOper por item de serviço.

Este módulo é isolado: não altera cálculo, motor nem as tabelas existentes.
Ele apenas LÊ a relação NBS x cClassTrib x INDOP (planilha "RELAÇÃO NBS
Cclasstrib e Ind Operac", editável em Administração > Tabelas) e a cruza com o
código do item da LC 116/2003 que a empresa já usa no relatório atual.

Regra principal: se um mesmo código de serviço tiver mais de uma classificação
de NBS / cClassTrib / IndOper, cada classificação ocupa uma linha PRÓPRIA,
logo abaixo da anterior (a coluna CNAE/Item não pode ser mesclada, senão a
informação some ao filtrar a planilha).
"""

from __future__ import annotations

import re

# Colunas do relatório, na ordem em que saem no Excel.
CABECALHO = [
    "CNAE",
    "Item (LC 116/2003)",
    "Descrição",
    "NBS",
    "Descrição NBS",
    "CClassTrib",
    "Descrição CClassTrib",
    "IndOper",
    "PS Onerosa",
    "Adq. Exterior",
    "Local incidência IBS",
]

# Texto usado quando o item não tem classificação na relação NBS.
SEM_RELACAO = "Sem classificação na Relação NBS"

# Regimes escolhidos antes de gerar o relatório.
REGIME_NORMAL = "normal"
REGIME_HIBRIDO = "hibrido"
REGIMES = {
    REGIME_NORMAL: "Simples Normal",
    REGIME_HIBRIDO: "Simples Híbrido",
}
# No Simples Normal só entram as classificações tributadas integralmente
# (cClassTrib 000001). No Híbrido entram todas as classificações do item.
CCLASSTRIB_SIMPLES_NORMAL = "000001"

def normalizar_regime(valor) -> str:
    """Devolve "normal" ou "hibrido"; qualquer outro valor -> "normal"."""
    texto = ("" if valor is None else str(valor)).strip().lower()
    return texto if texto in REGIMES else REGIME_NORMAL

def _eh_cclasstrib_normal(valor) -> bool:
    """True quando o cClassTrib corresponde a 000001, tolerando formatação.

    O banco pode devolver o valor como texto ("000001", " 000001 ") ou como
    número (1, 0001). Comparar por texto puro fazia a linha sumir do regime
    Normal mesmo estando cadastrada corretamente.
    """
    texto = re.sub(r"\D", "", str("" if valor is None else valor))
    if not texto:
        return False
    try:
        return int(texto) == int(CCLASSTRIB_SIMPLES_NORMAL)
    except ValueError:
        return False


def filtrar_por_regime(classificacoes, regime):
    """Filtra as classificações de um item conforme o regime escolhido.

    Simples Normal: apenas cClassTrib 000001. Simples Híbrido: todas.
    Se o filtro do Normal não deixar nenhuma linha, devolve lista vazia
    (o item aparece no relatório como "Sem classificação").
    """
    if normalizar_regime(regime) == REGIME_HIBRIDO:
        return list(classificacoes or [])
    return [
        c for c in (classificacoes or [])
        if _eh_cclasstrib_normal(c["cclasstrib"])
    ]


def normalizar_item(valor) -> str:
    """Normaliza o código do item LC 116 para comparar.

    Aceita "01.01", "1.01", "01.1", " 01.01 (parte final)" e devolve "01.01".
    Preserva o item taxativo de 3 níveis: "99.02.01" continua "99.02.01".
    Devolve "" quando não há código reconhecível.
    """
    texto = ("" if valor is None else str(valor)).strip()
    if not texto:
        return ""
    # Item da LC 116 (2 níveis) + subitem (3 níveis), ex.: "99.02.01".
    achado = re.search(r"(\d+)\s*[.,]?\s*(\d*)\s*[.,]?\s*(\d*)", texto)
    if not achado:
        return ""
    inteiro, decimal, sub = achado.group(1), achado.group(2), achado.group(3)
    inteiro = str(int(inteiro)) if inteiro else ""
    if not decimal:
        return inteiro
    if not sub:
        return f"{inteiro}.{decimal}"
    return f"{inteiro}.{decimal}.{sub}"


def _chave_canonica(valor) -> str:
    """Chave de comparação sem depender da formatação ("1.01" == "01.01").

    Compara parte a parte, sem truncar: "99.02.01" não vira "99.02".
    """
    normalizado = normalizar_item(valor)
    if not normalizado:
        return ""
    partes = normalizado.split(".")
    try:
        return ".".join(str(int(p)) for p in partes)
    except ValueError:
        return normalizado


def indexar_por_item(registros) -> dict:
    """Monta {chave_do_item: [linhas da relação NBS]} preservando a ordem.

    `registros` são as linhas da tabela relacao_nbs (sqlite3.Row ou dict).
    """
    mapa: dict[str, list] = {}
    for registro in registros:
        item = registro["item_lc116"] if "item_lc116" in registro.keys() \
            else registro.get("item_lc116", "")
        chave = _chave_canonica(item)
        if not chave:
            continue
        mapa.setdefault(chave, []).append(registro)
    return mapa


def montar_linhas(linhas_cnae, registros_nbs, regime=REGIME_HIBRIDO) -> list[dict]:
    """Cruza os itens de serviço da empresa com a relação NBS.

    `linhas_cnae` é a mesma lista usada no relatório atual (um dict por CNAE,
    com "codigo", "descricao" e "explicacao" -> "itens_lc116").
    `regime` decide quais classificações entram:
      - "normal"  -> Simples Normal: só cClassTrib 000001;
      - "hibrido" -> Simples Híbrido: todas as classificações do item.

    Devolve uma lista de dicts com as chaves de CABECALHO. Para cada item da
    LC 116 com N classificações na relação NBS, devolve N linhas seguidas:
    a primeira traz o código CNAE/item, as seguintes repetem o código e ficam
    como continuação (coluna Descrição vazia, para não poluir a leitura).
    """
    indice = indexar_por_item(registros_nbs)
    resultado: list[dict] = []

    for linha_cnae in linhas_cnae or []:
        cnae = (linha_cnae.get("codigo") or "").strip()
        descricao_cnae = (linha_cnae.get("descricao") or "").strip()
        explicacao = linha_cnae.get("explicacao") or {}
        itens = explicacao.get("itens_lc116") or []

        if not itens:
            # Sem item da LC 116: uma linha só, sem classificação possível.
            resultado.append({
                "CNAE": cnae,
                "Item (LC 116/2003)": descricao_cnae or "—",
                "Descrição": descricao_cnae,
                "NBS": "",
                "Descrição NBS": "",
                "CClassTrib": "",
                "Descrição CClassTrib": "",
                "IndOper": "",
                "PS Onerosa": "",
                "Adq. Exterior": "",
                "Local incidência IBS": SEM_RELACAO,
            })
            continue

        for item in itens:
            # O código do item pode vir em "codigo" ou em "item": os itens do
            # CNAE (explicacoes.explicar) usam "codigo", enquanto o cadastro
            # da relação NBS usa "item". Busca e exibição precisam usar a
            # MESMA chave, senão a classificação não é encontrada e as colunas
            # da reforma saem vazias.
            codigo = (item.get("codigo") or "").strip() or \
                normalizar_item(item.get("item", ""))
            descricao_item = (item.get("descricao") or "").strip() or descricao_cnae
            classificacoes = filtrar_por_regime(
                indice.get(_chave_canonica(codigo), []), regime)

            if not classificacoes:
                resultado.append({
                    "CNAE": cnae,
                    "Item (LC 116/2003)": codigo or item.get("item", ""),
                    "Descrição": descricao_item,
                    "NBS": "",
                    "Descrição NBS": "",
                    "CClassTrib": "",
                    "Descrição CClassTrib": "",
                    "IndOper": "",
                    "PS Onerosa": "",
                    "Adq. Exterior": "",
                    "Local incidência IBS": SEM_RELACAO,
                })
                continue

            for posicao, classificacao in enumerate(classificacoes):
                resultado.append({
                    "CNAE": cnae,
                    "Item (LC 116/2003)": codigo or item.get("item", ""),
                    "Descrição": descricao_item if posicao == 0 else "",
                    "NBS": classificacao["nbs"] or "",
                    "Descrição NBS": classificacao["descricao_nbs"] or "",
                    "CClassTrib": classificacao["cclasstrib"] or "",
                    "Descrição CClassTrib": classificacao["nome_cclasstrib"] or "",
                    "IndOper": classificacao["indop"] or "",
                    "PS Onerosa": classificacao["ps_onerosa"] or "",
                    "Adq. Exterior": classificacao["adq_exterior"] or "",
                    "Local incidência IBS": classificacao["local_incidencia"] or "",
                })

    return resultado


def preencher_planilha(ws, linhas, ident=None, regime=None) -> None:
    """Escreve o Relatório Reforma em uma worksheet do openpyxl.

    Formata apenas o necessário (negrito no cabeçalho, largura das colunas,
    congelamento e filtro) e destaca as linhas "Sem classificação".
    """
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    ws.title = "Relatório Reforma"

    ws.append(["Relatório Reforma — Simples Nacional"])
    ws["A1"].font = Font(bold=True, size=13)
    if regime:
        ws.append(["Regime", REGIMES.get(normalizar_regime(regime), "")])
    if ident:
        ws.append([])
        ws.append(["Razão social", ident.get("razao_social", "")])
        ws.append(["Nome fantasia", ident.get("nome_fantasia", "")])
        ws.append(["CNPJ", ident.get("cnpj", "")])
    ws.append([])

    linha_cabecalho = ws.max_row + 1
    ws.append(CABECALHO)
    cor_cabecalho = PatternFill("solid", fgColor="1F4E79")
    for coluna in range(1, len(CABECALHO) + 1):
        celula = ws.cell(row=linha_cabecalho, column=coluna)
        celula.font = Font(bold=True, color="FFFFFF")
        celula.fill = cor_cabecalho
        celula.alignment = Alignment(vertical="center", wrap_text=True)

    cor_sem_relacao = PatternFill("solid", fgColor="FFF2CC")
    for registro in linhas:
        ws.append([registro.get(coluna, "") for coluna in CABECALHO])
        if registro.get("Local incidência IBS") == SEM_RELACAO:
            for coluna in range(1, len(CABECALHO) + 1):
                ws.cell(row=ws.max_row, column=coluna).fill = cor_sem_relacao

    larguras = {
        "CNAE": 13, "Item (LC 116/2003)": 17, "Descrição": 46,
        "NBS": 16, "Descrição NBS": 50, "CClassTrib": 13,
        "Descrição CClassTrib": 46, "IndOper": 11, "PS Onerosa": 12,
        "Adq. Exterior": 13, "Local incidência IBS": 38,
    }
    for indice, coluna in enumerate(CABECALHO, start=1):
        ws.column_dimensions[get_column_letter(indice)].width = larguras.get(
            coluna, 16)

    ws.freeze_panes = ws.cell(row=linha_cabecalho + 1, column=1)
    ws.auto_filter.ref = (
        f"A{linha_cabecalho}:"
        f"{get_column_letter(len(CABECALHO))}{max(ws.max_row, linha_cabecalho)}"
    )
