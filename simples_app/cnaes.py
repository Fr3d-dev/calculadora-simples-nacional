"""
Base de CNAEs e enquadramento no Simples Nacional.

O ENQUADRAMENTO agora é feito pelo motor legal em `enquadramento.py`
(tabela de classes de CNAE + itens da LC 116/2003). Este módulo mantém:

  - helpers de uso geral (apenas_digitos, normalizar, formatar_cnae);
  - `sugerir_anexo()` / `anexos_candidatos()`  -> delegam ao motor;
  - `listar_grupos()`                          -> resumo por divisão de CNAE
                                                  (tabela exibida em Empresas);
  - `anexo_usa_fator_r()` / `calcular_fator_r()` (regra do Fator "r").

A heurística antiga por palavras-chave foi removida: ela classificava
atividade pelo texto da descrição e gerava enquadramentos indevidos (ex.:
"Restaurantes e similares" caía no Anexo I por acaso, "instalação de
esquadrias" em CNAE de comércio virava Anexo IV etc.).

Observações:
  - O enquadramento definitivo depende do CNAE principal E das atividades
    secundárias, do faturamento, da folha e do destino do produto/serviço.
    Este módulo é orientativo e não substitui o contador.
  - Backup da versão anterior: `cnaes.py.bak_antes_enquadramento`.
"""

from __future__ import annotations

from typing import Optional

import enquadramento
from enquadramento import MOTOR, formatar_cnae


# ---------------------------------------------------------------------------
# Nomes das divisões (para a tabela informativa de "grupos")
# ---------------------------------------------------------------------------

_DIVISOES = [
    # (divisões agrupadas, nome do grupo)
    (("01", "02", "03", "05"), "Agricultura, pecuária, pesca e extrativismo"),
    (("10", "11", "12"), "Indústria de alimentos, bebidas e fumo"),
    (("13", "14", "15"), "Indústria têxtil, vestuário, couro e calçados"),
    (("16", "17", "18"), "Indústria de madeira, papel, gráfica e mobiliário"),
    (("19", "20", "21"), "Indústria química, farmacêutica e de borracha/plástico"),
    (("22", "23", "24"), "Metalurgia, siderurgia e produtos de metal"),
    (("25", "26", "27"), "Metalurgia, siderurgia e produtos de metal"),
    (("28", "29", "30"), "Fabricação de máquinas, veículos e equipamentos"),
    (("31", "32", "33", "39"), "Mobiliário, produtos diversos e serviços industriais"),
    (("35", "36", "37", "38"), "Eletricidade, água, esgoto e resíduos"),
    (("41", "42", "43"), "Construção civil e obras de engenharia"),
    (("45", "46", "47"), "Comércio de veículos, por atacado e varejista"),
    (("49", "50", "51"), "Transporte de cargas e passageiros"),
    (("52", "53"), "Armazenagem, apoio ao transporte e entregas"),
    (("55", "56"), "Alojamento e alimentação"),
    (("58", "59", "60"), "Edição, gravação, rádio e TV"),
    (("61",), "Telecomunicações"),
    (("62", "63"), "Tecnologia da informação e software"),
    (("64", "65", "66"), "Serviços financeiros e seguros"),
    (("68",), "Imobiliárias e locação de imóveis"),
    (("69", "70", "71"), "Serviços jurídicos, contábeis e de engenharia"),
    (("72", "73", "74"), "Pesquisa, publicidade e serviços técnicos"),
    (("75",), "Serviços veterinários"),
    (("77",), "Locação de máquinas e equipamentos"),
    (("79",), "Turismo"),
    (("80", "81"), "Vigilância, segurança, limpeza e conservação"),
    (("82",), "Serviços de escritório e apoio administrativo"),
    (("85",), "Ensino, treinamento e educação"),
    (("86", "87", "88"), "Saúde humana, veterinária e serviços sociais"),
    (("90", "91", "92"), "Artes, cultura, esporte e lazer"),
    (("93", "95", "96"), "Esportes, reparação e serviços pessoais"),
]

_NOMES_ANEXO = {
    "I": "Comércio",
    "II": "Indústria",
    "III": "Serviços gerais",
    "IV": "Construção, limpeza e vigilância",
    "V": "Serviços intelectuais (Fator \"r\")",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def apenas_digitos(codigo: str) -> str:
    """Remove pontos, traços e barras de um CNAE. Ex: '47.11-3/02' -> '4711302'."""
    return enquadramento.apenas_digitos(codigo)


def formatar_cnae(codigo: str) -> str:
    """
    Formata um CNAE no padrão 0000-0/00.
    Aceita '4711302', '47.11-3/02' ou '4711-3/02'.
    """
    return enquadramento.formatar_cnae(codigo)


def normalizar(texto: str) -> str:
    """Minúsculas e sem acentos, para comparação textual."""
    if not texto:
        return ""
    return enquadramento.normalizar(texto)


# ---------------------------------------------------------------------------
# API principal — delega ao motor legal
# ---------------------------------------------------------------------------

def sugerir_anexo(cnae: str, descricao: str = "") -> dict:
    """
    Sugere o Anexo do Simples Nacional para um CNAE.

    Delega para `enquadramento.MOTOR.enquadrar()`. A descrição só é usada
    para desempatar classes legalmente ambíguas (ex.: 18.13 impressão: ISS x
    ICMS) — nunca para inventar um anexo a partir de palavras soltas.

    Retorna:
      anexo              -> 'I'..'V' ou None (CNAE ausente/inválido)
      anexos_candidatos  -> todos os anexos legalmente possíveis
      descricao_grupo    -> rótulo do tipo de atividade
      observacao         -> ressalva (Fator "r", CPP à parte, etc.)
      confianca          -> 'alta' (anexo único) ou 'media' (ambíguo)
      tipo_atividade     -> 'comércio' / 'indústria' / 'serviço'
    """
    return MOTOR.enquadrar(cnae, descricao)


def anexos_candidatos(cnae: str, descricao: str = "") -> list:
    """
    Todos os anexos LEGALMENTE pertinentes ao CNAE.

    O primeiro é o recomendado. O Fator "r" só libera III<->V nas atividades
    do art. 18, §5º-D; o Anexo IV nunca é combinado com outro anexo.
    """
    return MOTOR.candidatos(cnae, descricao)


def anexo_usa_fator_r(anexo: str) -> bool:
    """
    Indica se o anexo está sujeito ao fator R (folha de salários).
    Anexos III e V são os afetados pela regra do fator R.
    """
    return (anexo or "").upper() in ("III", "V")


def calcular_fator_r(folha_12m, rbt12) -> dict:
    """
    Calcula o fator R = folha de salários dos últimos 12 meses / RBT12.

    Se fator R >= 0,28 -> Anexo III; caso contrário -> Anexo V.
    """
    try:
        folha = float(folha_12m or 0)
    except (TypeError, ValueError):
        folha = 0.0
    try:
        rbt = float(rbt12 or 0)
    except (TypeError, ValueError):
        rbt = 0.0

    fator = (folha / rbt) if rbt > 0 else 0.0
    return {
        "fator": fator,
        "anexo": "III" if fator >= 0.28 else "V",
        "corte": 0.28,
        "usa_fator_r": True,
    }


def listar_grupos() -> list:
    """Lista simplificada das divisões de CNAE e do anexo base (interface)."""
    vistos = set()
    saida = []
    for divisoes, nome in _DIVISOES:
        if nome in vistos:
            continue
        vistos.add(nome)
        anexo = enquadramento.TABELA_ANEXO.get(divisoes[0])
        saida.append({
            "descricao": nome,
            "prefixos": list(divisoes),
            "anexo": anexo,
            "observacao": f"Anexo {anexo}: {_NOMES_ANEXO.get(anexo, '')}"
                          if anexo else "Anexo definido por classe de CNAE.",
        })
    return saida


ANEXOS_SIMPLES = ["I", "II", "III", "IV", "V"]
