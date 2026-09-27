"""
Motor de cálculo do Simples Nacional.

Reproduz fielmente as fórmulas da planilha CALCULADORA SIMPLES.xlsx.

Convenções (equivalentes às células da planilha):
  - rbt12            -> célula F2
  - faturamento_mes  -> célula F3
  - aliquota_nominal -> célula F6
  - valor_deduzir    -> célula F9
  - aliquota_efetiva -> célula J12
  - das              -> célula F15

Fórmulas da planilha:
  F6  = IF(F2<=180000, K3, IF(AND(F2>=180000.01, F2<=360000), K4, ... ))
  F9  = IF(F6=K3, 0, IF(F6=K4, L4, IF(F6=K5, L5, ... )))
  J12 = ((F2*F6) - F9) / F2
  F15 = F3 * J12
"""

from __future__ import annotations

from datetime import date
from typing import Optional

# ---------------------------------------------------------------------------
# Tabelas base (faixas) — valores extraídos da planilha CALCULADORA SIMPLES.xlsx
# Cada faixa: (limite_inferior, limite_superior, aliquota_nominal, valor_a_deduzir)
# ---------------------------------------------------------------------------

FAIXAS = {
    "I": [
        (0.0, 180000.0, 0.040, 0.0),
        (180000.01, 360000.0, 0.073, 5940.0),
        (360000.01, 720000.0, 0.095, 13860.0),
        (720000.01, 1800000.0, 0.107, 22500.0),
        (1800000.01, 3600000.0, 0.143, 87300.0),
        (3600000.01, 4800000.0, 0.190, 378000.0),
    ],
    "II": [
        (0.0, 180000.0, 0.045, 0.0),
        (180000.01, 360000.0, 0.078, 5940.0),
        (360000.01, 720000.0, 0.100, 13860.0),
        (720000.01, 1800000.0, 0.112, 22500.0),
        (1800000.01, 3600000.0, 0.147, 85500.0),
        (3600000.01, 4800000.0, 0.300, 720000.0),
    ],
    "III": [
        (0.0, 180000.0, 0.060, 0.0),
        (180000.01, 360000.0, 0.112, 9360.0),
        (360000.01, 720000.0, 0.135, 17640.0),
        (720000.01, 1800000.0, 0.160, 35640.0),
        (1800000.01, 3600000.0, 0.210, 125640.0),
        (3600000.01, 4800000.0, 0.330, 648000.0),
    ],
    "IV": [
        (0.0, 180000.0, 0.045, 0.0),
        (180000.01, 360000.0, 0.090, 8100.0),
        (360000.01, 720000.0, 0.102, 12420.0),
        (720000.01, 1800000.0, 0.140, 39780.0),
        (1800000.01, 3600000.0, 0.220, 183780.0),
        (3600000.01, 4800000.0, 0.330, 828000.0),
    ],
}

# Percentual de repartição dos tributos por anexo e faixa (parte informativa).
# Chave do anexo -> lista de dicionários (tributo -> percentual) por faixa.
REPARTICAO = {
    "I": [
        {"IRPJ": 0.055, "CSLL": 0.035, "Cofins": 0.1274, "PIS/Pasep": 0.0276, "CPP": 0.415, "ICMS": 0.34},
        {"IRPJ": 0.055, "CSLL": 0.035, "Cofins": 0.1274, "PIS/Pasep": 0.0276, "CPP": 0.415, "ICMS": 0.34},
        {"IRPJ": 0.055, "CSLL": 0.035, "Cofins": 0.1274, "PIS/Pasep": 0.0276, "CPP": 0.42, "ICMS": 0.335},
        {"IRPJ": 0.055, "CSLL": 0.035, "Cofins": 0.1274, "PIS/Pasep": 0.0276, "CPP": 0.42, "ICMS": 0.335},
        {"IRPJ": 0.055, "CSLL": 0.035, "Cofins": 0.1274, "PIS/Pasep": 0.0276, "CPP": 0.42, "ICMS": 0.335},
        {"IRPJ": 0.135, "CSLL": 0.10, "Cofins": 0.2827, "PIS/Pasep": 0.0613, "CPP": 0.421, "ICMS": 0.0},
    ],
    "II": [
        {"IRPJ": 0.055, "CSLL": 0.035, "Cofins": 0.1151, "PIS/Pasep": 0.0249, "CPP": 0.375, "IPI": 0.075, "ICMS": 0.32},
        {"IRPJ": 0.055, "CSLL": 0.035, "Cofins": 0.1151, "PIS/Pasep": 0.0249, "CPP": 0.375, "IPI": 0.075, "ICMS": 0.32},
        {"IRPJ": 0.055, "CSLL": 0.035, "Cofins": 0.1151, "PIS/Pasep": 0.0249, "CPP": 0.375, "IPI": 0.075, "ICMS": 0.32},
        {"IRPJ": 0.055, "CSLL": 0.035, "Cofins": 0.1151, "PIS/Pasep": 0.0249, "CPP": 0.375, "IPI": 0.075, "ICMS": 0.32},
        {"IRPJ": 0.055, "CSLL": 0.035, "Cofins": 0.1151, "PIS/Pasep": 0.0249, "CPP": 0.375, "IPI": 0.075, "ICMS": 0.32},
        {"IRPJ": 0.085, "CSLL": 0.075, "Cofins": 0.2096, "PIS/Pasep": 0.0454, "CPP": 0.235, "IPI": 0.35, "ICMS": 0.0},
    ],
    "III": [
        {"IRPJ": 0.04, "CSLL": 0.035, "Cofins": 0.1282, "PIS/Pasep": 0.0278, "CPP": 0.434, "ISS": 0.335},
        {"IRPJ": 0.04, "CSLL": 0.035, "Cofins": 0.1405, "PIS/Pasep": 0.0305, "CPP": 0.434, "ISS": 0.32},
        {"IRPJ": 0.04, "CSLL": 0.035, "Cofins": 0.1364, "PIS/Pasep": 0.0296, "CPP": 0.434, "ISS": 0.325},
        {"IRPJ": 0.04, "CSLL": 0.035, "Cofins": 0.1364, "PIS/Pasep": 0.0296, "CPP": 0.434, "ISS": 0.325},
        {"IRPJ": 0.04, "CSLL": 0.035, "Cofins": 0.1282, "PIS/Pasep": 0.0278, "CPP": 0.434, "ISS": 0.335},
        {"IRPJ": 0.35, "CSLL": 0.15, "Cofins": 0.1603, "PIS/Pasep": 0.0347, "CPP": 0.305, "ISS": 0.0},
    ],
    "IV": [
        {"IRPJ": 0.188, "CSLL": 0.152, "Cofins": 0.1767, "PIS/Pasep": 0.0383, "ISS": 0.445},
        {"IRPJ": 0.198, "CSLL": 0.152, "Cofins": 0.2055, "PIS/Pasep": 0.0445, "ISS": 0.40},
        {"IRPJ": 0.208, "CSLL": 0.152, "Cofins": 0.1973, "PIS/Pasep": 0.0427, "ISS": 0.40},
        {"IRPJ": 0.178, "CSLL": 0.192, "Cofins": 0.189, "PIS/Pasep": 0.041, "ISS": 0.40},
        {"IRPJ": 0.188, "CSLL": 0.192, "Cofins": 0.1808, "PIS/Pasep": 0.0392, "ISS": 0.40},
        {"IRPJ": 0.535, "CSLL": 0.215, "Cofins": 0.2055, "PIS/Pasep": 0.0445, "ISS": 0.0},
    ],
}

MESES_NOMES = [
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
]


def mes_deslocado(chave: str, deslocamento: int) -> str:
    """Desloca uma competência "YYYY-MM" em N meses e devolve "YYYY-MM".

    ``deslocamento`` pode ser negativo (meses anteriores) ou positivo
    (meses à frente) — usado no modo simulação.
    """
    ano, mes = (int(p) for p in chave.split("-"))
    indice = (ano * 12 + (mes - 1)) + deslocamento
    novo_ano, novo_mes = divmod(indice, 12)
    return f"{novo_ano}-{novo_mes + 1:02d}"


def montar_mes(chave: str, indice: int = None) -> dict:
    """Monta o dicionário descritivo de um mês a partir da chave "YYYY-MM"."""
    ano, mes = (int(p) for p in chave.split("-"))
    item = {
        "mes": mes,
        "ano": ano,
        "mes_nome": MESES_NOMES[mes - 1],
        "rotulo": f"{MESES_NOMES[mes - 1]}/{ano}",
        "chave": f"{ano}-{mes:02d}",
    }
    if indice is not None:
        item["indice"] = indice
    return item


def meses_futuros(meses_lista: list, quantidade: int = 6) -> list:
    """Gera os próximos N meses após o último mês de *meses_lista*.

    Usada no modo simulação para permitir preencher competências à frente.
    Marca cada item com ``futuro=True``.
    """
    if not meses_lista or quantidade <= 0:
        return []
    ultima = meses_lista[-1]["chave"]
    futuros = []
    for i in range(1, quantidade + 1):
        item = montar_mes(mes_deslocado(ultima, i))
        item["futuro"] = True
        futuros.append(item)
    return futuros


def meses_para_rbt12(data_ref=None) -> list[dict]:
    """
    Gera a lista dos últimos 12 meses fechando no mês anterior ao mês
    da *data_ref* (padrão = data/hora atual do sistema).

    Cada item:
      {
        "indice": 1..12,           # posição na lista (1 = mês mais antigo)
        "mes": int 1..12,          # número do mês
        "ano": int,                # ano
        "rotulo": str,             # ex: "setembro/2025"
        "mes_nome": str,           # ex: "setembro"
        "chave": str,              # ex: "2025-09"
      }

    O mês *data_ref* é excluído porque o RBT12 considera os *últimos* 12 meses
    completos (iguais à lógica do PGDAS-D).
    """
    from datetime import date

    hoje = data_ref or date.today()

    # Vamos para o mês anterior ao mês atual
    if hoje.month == 1:
        mes_base, ano_base = 12, hoje.year - 1
    else:
        mes_base, ano_base = hoje.month - 1, hoje.year

    resultado = []
    for i in range(12):
        # i=0 -> 11 meses atrás; i=11 -> mês base
        m = mes_base - 11 + i
        ano_item = ano_base
        if m < 1:
            m += 12
            ano_item -= 1
        elif m > 12:
            m -= 12
            ano_item += 1
        resultado.append({
            "indice": i + 1,
            "mes": m,
            "ano": ano_item,
            "mes_nome": MESES_NOMES[m - 1],
            "rotulo": f"{MESES_NOMES[m - 1]}/{ano_item}",
            "chave": f"{ano_item}-{m:02d}",
        })
    return resultado

# ---------------------------------------------------------------------------
# Repartição de impostos (células J17:Q25 da planilha)
#
# A planilha divide a alíquota efetiva (J12) entre os tributos da faixa, usando
# o "Percentual de Repartição dos Tributos" (A18:H25):
#     percentual_dividido = percentual_tributo * aliquota_efetiva
#     valor               = percentual_dividido * faturamento_mes
# A soma dos valores fecha exatamente o DAS (F15), porque a soma dos
# percentuais divididos é a própria alíquota efetiva (J12) e DAS = F3 * J12.
# ---------------------------------------------------------------------------

# Regra do (*) dos Anexos III e IV (notas A26 da planilha):
# quando a alíquota efetiva ultrapassa o teto, o ISS efetivo é limitado a 5%
# e o excedente é redistribuído, proporcionalmente, aos tributos federais
# (todos menos o próprio ISS) da mesma faixa.
TETO_ISS = {
    "III": 0.1492537,   # 14,92537%
    "IV": 0.125,        # 12,5%
}
LIMITE_ISS = 0.05       # 5%


def _tributos_do_anexo(anexo: str) -> list:
    """Ordem fixa dos tributos de um anexo, conforme a planilha."""
    anexo = (anexo or "").upper()
    if anexo == "I":
        return ["IRPJ", "CSLL", "Cofins", "PIS/Pasep", "CPP", "ICMS"]
    if anexo == "II":
        return ["IRPJ", "CSLL", "Cofins", "PIS/Pasep", "CPP", "IPI", "ICMS"]
    if anexo == "III":
        return ["IRPJ", "CSLL", "Cofins", "PIS/Pasep", "CPP", "ISS"]
    if anexo == "IV":
        return ["IRPJ", "CSLL", "Cofins", "PIS/Pasep", "ISS"]
    return []


def _aplicar_regra_iss(anexo: str, aliquota_efetiva: float, percentuais: dict) -> dict:
    """
    Aplica a regra do (*) dos Anexos III e IV.

    A planilha limita o percentual DIVIDIDO do ISS a 5% (ou seja, o ISS nunca
    consome mais que 5 pontos percentuais da alíquota efetiva). O que sobra é
    redistribuído aos demais tributos, proporcionalmente ao peso atual deles.

    Recebe e devolve percentuais já divididos (percentual * alíquota_efetiva).
    """
    anexo = (anexo or "").upper()
    teto = TETO_ISS.get(anexo)
    if teto is None or aliquota_efetiva <= teto:
        return percentuais

    chave_iss = next((k for k in percentuais if k.upper().startswith("ISS")), None)
    if chave_iss is None:
        return percentuais

    iss_atual = percentuais.get(chave_iss) or 0.0
    if iss_atual <= LIMITE_ISS:
        return percentuais

    excedente = iss_atual - LIMITE_ISS
    federais = [k for k in percentuais if k != chave_iss]
    peso_total = sum(percentuais[k] or 0.0 for k in federais)

    ajustado = dict(percentuais)
    ajustado[chave_iss] = LIMITE_ISS

    if peso_total <= 0:
        # Sem tributos federais para absorver: devolve o ISS inteiro.
        return percentuais

    for k in federais:
        fatia = (percentuais[k] or 0.0) / peso_total
        ajustado[k] = (percentuais[k] or 0.0) + (excedente * fatia)
    return ajustado


def calcular_reparticao(anexo: str, faturamento_mes: float, aliquota_efetiva: float,
                        indice_faixa: Optional[int]) -> Optional[list]:
    """
    Monta a repartição de impostos de um anexo (bloco J17 da planilha).

    Devolve uma lista de dicionários, na ordem dos tributos:
        {"tributo": "IRPJ", "percentual": 0.0048273, "valor": 965.46}
    onde `percentual` é o percentual DIVIDIDO (percentual_tabela * aliquota
    efetiva) e `valor` é o valor em reais (percentual_dividido * faturamento
    do mês) — que é como a planilha monta a coluna M.

    Devolve None quando não há faixa/tabela aplicável.
    """
    if indice_faixa is None:
        return None

    linhas = REPARTICAO.get((anexo or "").upper())
    if not linhas or indice_faixa >= len(linhas):
        return None

    percentuais_tabela = linhas[indice_faixa] or {}
    tributos = _tributos_do_anexo(anexo)

    # Percentual dividido = percentual da tabela * alíquota efetiva
    divididos = {}
    for tributo in tributos:
        base = next(
            (v for k, v in percentuais_tabela.items() if k.upper() == tributo.upper()),
            0.0,
        )
        divididos[tributo] = (base or 0.0) * aliquota_efetiva

    divididos = _aplicar_regra_iss(anexo, aliquota_efetiva, divididos)

    base = faturamento_mes or 0.0
    return [
        {
            "tributo": tributo,
            "percentual": divididos.get(tributo, 0.0),
            "valor": divididos.get(tributo, 0.0) * base,
        }
        for tributo in tributos
    ]


def _to_float(valor) -> float:
    """Converte um valor possivelmente textual em float de forma tolerante."""
    if valor is None:
        return 0.0
    if isinstance(valor, (int, float)):
        return float(valor)
    texto = str(valor).strip()
    if not texto:
        return 0.0
    # Aceita formatos "1.234,56" e "1234.56"
    if "," in texto and "." in texto:
        texto = texto.replace(".", "").replace(",", ".")
    elif "," in texto:
        texto = texto.replace(",", ".")
    try:
        return float(texto)
    except ValueError:
        return 0.0


def calcular_rbt12(faturamentos: list) -> float:
    """
    Reproduz a fórmula da planilha: C15 = (12*SUM(C3:C14))/COUNTA(C3:C14)

    COUNTA conta apenas as células preenchidas (não vazias). Aqui consideramos
    "preenchida" qualquer valor diferente de None/"" — zero digitado conta.
    """
    valores_validos = []
    for v in faturamentos:
        if v is None or (isinstance(v, str) and v.strip() == ""):
            continue
        valores_validos.append(_to_float(v))

    if not valores_validos:
        return 0.0
    return (12 * sum(valores_validos)) / len(valores_validos)


def obter_faixa(anexo: str, rbt12: float) -> Optional[tuple]:
    """Retorna a tupla (inf, sup, aliquota, deducao) da faixa aplicável ou None."""
    faixas = FAIXAS.get(anexo.upper())
    if not faixas:
        return None
    for faixa in faixas:
        inf, sup, _aliq, _ded = faixa
        if inf <= rbt12 <= sup:
            return faixa
    return None


def calcular(anexo: str, rbt12, faturamento_mes) -> dict:
    """
    Calcula todos os campos derivados para um anexo.

    Retorna um dicionário com:
      rbt12, faturamento_mes, aliquota_nominal, valor_deduzir,
      aliquota_efetiva, das, faixa, reparticao
    """
    anexo = (anexo or "").upper()
    rbt12_f = _to_float(rbt12)
    faturamento_f = _to_float(faturamento_mes)

    faixa = obter_faixa(anexo, rbt12_f)

    if faixa is None:
        # Fora das faixas conhecidas: alíquota e dedução zeradas.
        aliquota_nominal = 0.0
        valor_deduzir = 0.0
        indice_faixa = None
    else:
        _inf, _sup, aliquota_nominal, valor_deduzir = faixa
        indice_faixa = FAIXAS[anexo].index(faixa)

    # J12 = ((F2*F6) - F9) / F2
    if rbt12_f > 0:
        aliquota_efetiva = ((rbt12_f * aliquota_nominal) - valor_deduzir) / rbt12_f
    else:
        aliquota_efetiva = 0.0

    # F15 = F3 * J12
    das = faturamento_f * aliquota_efetiva

    reparticao = None
    if indice_faixa is not None:
        reparticao = REPARTICAO.get(anexo, [None] * 6)[indice_faixa]

    # Repartição efetiva (bloco J17): percentual dividido e valor por tributo
    reparticao_detalhada = calcular_reparticao(
        anexo, faturamento_f, aliquota_efetiva, indice_faixa
    )

    return {
        "anexo": anexo,
        "rbt12": rbt12_f,
        "faturamento_mes": faturamento_f,
        "aliquota_nominal": aliquota_nominal,
        "valor_deduzir": valor_deduzir,
        "aliquota_efetiva": aliquota_efetiva,
        "das": das,
        "faixa": indice_faixa + 1 if indice_faixa is not None else None,
        "reparticao": reparticao,
        "reparticao_detalhada": reparticao_detalhada,
    }


def formatar_moeda(valor) -> str:
    """Formata um número no padrão brasileiro: R$ 1.234,56"""
    try:
        v = float(valor)
    except (TypeError, ValueError):
        v = 0.0
    inteiro = f"{v:,.2f}"
    return "R$ " + inteiro.replace(",", "X").replace(".", ",").replace("X", ".")


def formatar_percentual(valor, casas: int = 2) -> str:
    """Formata um número como percentual brasileiro: 10,70%"""
    try:
        v = float(valor)
    except (TypeError, ValueError):
        v = 0.0
    return f"{v * 100:.{casas}f}".replace(".", ",") + "%"
