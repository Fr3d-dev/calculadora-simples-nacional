"""
Consulta pública de CNPJ (dados abertos da Receita Federal).

Usa serviços gratuitos, sem necessidade de cadastro ou chave de API:

  1. BrasilAPI  -> https://brasilapi.com.br/api/cnpj/v1/{cnpj}   (principal)
  2. ReceitaWS  -> https://receitaws.com.br/v1/cnpj/{cnpj}       (reserva)

Ambos retornam os dados cadastrais da empresa: razão social, nome fantasia,
CNAE principal com descrição, CNAEs secundários, município/UF, situação
cadastral e indicativo de opção pelo Simples Nacional.

Apenas a biblioteca padrão do Python é usada (urllib), mantendo o projeto
sem dependências externas além do Flask.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

# Tempo máximo de espera por resposta (segundos).
TIMEOUT = 15

# User-Agent identificando a aplicação (boas práticas de uso das APIs públicas).
USER_AGENT = "CalculadoraSimplesNacional/1.0 (+contato@exemplo.local)"

_BRASILAPI = "https://brasilapi.com.br/api/cnpj/v1/{cnpj}"
_RECEITAWS = "https://receitaws.com.br/v1/cnpj/{cnpj}"


class ConsultaCNPJError(Exception):
    """Erro de consulta de CNPJ (rede, CNPJ inválido, limite de uso, etc.)."""


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def apenas_digitos(cnpj: str) -> str:
    return "".join(ch for ch in str(cnpj or "") if ch.isdigit())


def formatar_cnpj(cnpj: str) -> str:
    """Formata 14 dígitos no padrão 00.000.000/0001-00."""
    d = apenas_digitos(cnpj)
    if len(d) == 14:
        return f"{d[0:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:14]}"
    return str(cnpj or "").strip()


def validar_cnpj(cnpj: str) -> bool:
    """
    Valida os dígitos verificadores do CNPJ.

    Rejeita também sequências repetidas (00000000000000, 11111111111111, ...),
    que passam no cálculo mas não são CNPJs válidos.
    """
    d = apenas_digitos(cnpj)
    if len(d) != 14 or d == d[0] * 14:
        return False

    def _digito(base: str, pesos: list) -> str:
        soma = sum(int(n) * p for n, p in zip(base, pesos))
        resto = soma % 11
        return "0" if resto < 2 else str(11 - resto)

    pesos1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    pesos2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]

    if _digito(d[:12], pesos1) != d[12]:
        return False
    if _digito(d[:13], pesos2) != d[13]:
        return False
    return True


def _get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise ConsultaCNPJError("CNPJ não encontrado na base da Receita Federal.") from exc
        if exc.code == 429:
            raise ConsultaCNPJError(
                "Limite de consultas atingido. Aguarde alguns instantes e tente novamente."
            ) from exc
        raise ConsultaCNPJError(f"Serviço respondeu com erro HTTP {exc.code}.") from exc
    except urllib.error.URLError as exc:
        raise ConsultaCNPJError(
            "Não foi possível conectar ao serviço de consulta. "
            "Verifique sua conexão com a internet."
        ) from exc
    except (TimeoutError, json.JSONDecodeError) as exc:
        raise ConsultaCNPJError("Resposta inválida do serviço de consulta.") from exc


# ---------------------------------------------------------------------------
# Normalização dos dados
# ---------------------------------------------------------------------------

def _normalizar_brasilapi(d: dict) -> dict:
    secundarios = []
    for item in d.get("cnaes_secundarios") or []:
        codigo = str(item.get("codigo") or "").strip()
        descricao = str(item.get("descricao") or "").strip()
        if codigo:
            secundarios.append({"codigo": codigo, "descricao": descricao})

    return {
        "fonte": "BrasilAPI (dados abertos da Receita Federal)",
        "cnpj": formatar_cnpj(d.get("cnpj") or ""),
        "razao_social": (d.get("razao_social") or "").strip(),
        "nome_fantasia": (d.get("nome_fantasia") or "").strip(),
        "cnae_principal": str(d.get("cnae_fiscal") or "").strip(),
        "cnae_descricao": (d.get("cnae_fiscal_descricao") or "").strip(),
        "cnaes_secundarios": secundarios,
        "municipio": (d.get("municipio") or "").strip(),
        "uf": (d.get("uf") or "").strip().upper(),
        "situacao_cadastral": (d.get("descricao_situacao_cadastral") or "").strip(),
        "porte": (d.get("porte") or "").strip(),
        "natureza_juridica": (d.get("natureza_juridica") or "").strip(),
        "data_inicio_atividade": (d.get("data_inicio_atividade") or "").strip(),
        "opcao_pelo_simples": d.get("opcao_pelo_simples"),
        "data_opcao_pelo_simples": (d.get("data_opcao_pelo_simples") or "").strip(),
        "opcao_pelo_mei": d.get("opcao_pelo_mei"),
        "regime_tributario": d.get("regime_tributario") or [],
        "email": (d.get("email") or "").strip(),
        "telefone": (d.get("ddd_telefone_1") or "").strip(),
    }


def _normalizar_receitaws(d: dict) -> dict:
    secundarios = []
    for item in d.get("atividades_secundarias") or []:
        codigo = str(item.get("code") or "").replace(".", "").replace("-", "").replace("/", "").strip()
        descricao = str(item.get("text") or "").strip()
        if codigo:
            secundarios.append({"codigo": codigo, "descricao": descricao})

    principal = (d.get("atividade_principal") or [{}])[0]
    cnae_principal = str(principal.get("code") or "")
    cnae_principal = cnae_principal.replace(".", "").replace("-", "").replace("/", "").strip()

    simples = (d.get("simples") or {})
    mei = (d.get("simei") or {})

    return {
        "fonte": "ReceitaWS (dados públicos da Receita Federal)",
        "cnpj": formatar_cnpj(d.get("cnpj") or ""),
        "razao_social": (d.get("nome") or "").strip(),
        "nome_fantasia": (d.get("fantasia") or "").strip(),
        "cnae_principal": cnae_principal,
        "cnae_descricao": (principal.get("text") or "").strip(),
        "cnaes_secundarios": secundarios,
        "municipio": (d.get("municipio") or "").strip(),
        "uf": (d.get("uf") or "").strip().upper(),
        "situacao_cadastral": (d.get("situacao") or "").strip(),
        "porte": (d.get("porte") or "").strip(),
        "natureza_juridica": (d.get("natureza_juridica") or "").strip(),
        "data_inicio_atividade": (d.get("abertura") or "").strip(),
        "opcao_pelo_simples": simples.get("mei") if simples else None,
        "data_opcao_pelo_simples": (simples.get("data_opcao") or "").strip() if simples else "",
        "opcao_pelo_mei": mei.get("mei") if mei else None,
        "regime_tributario": [],
        "email": (d.get("email") or "").strip(),
        "telefone": (d.get("telefone") or "").strip(),
    }


# ---------------------------------------------------------------------------
# Função principal
# ---------------------------------------------------------------------------

def consultar_cnpj(cnpj: str, validar: bool = True) -> dict:
    """
    Consulta os dados cadastrais de um CNPJ.

    Tenta primeiro a BrasilAPI e, se indisponível, cai para a ReceitaWS.
    Retorna dicionário normalizado (mesmas chaves em ambas as fontes).

    Levanta ConsultaCNPJError em caso de falha.
    """
    d = apenas_digitos(cnpj)

    if len(d) != 14:
        raise ConsultaCNPJError("O CNPJ deve ter 14 dígitos.")
    if validar and not validar_cnpj(d):
        raise ConsultaCNPJError("CNPJ inválido — verifique os dígitos informados.")

    erros = []

    try:
        bruto = _get_json(_BRASILAPI.format(cnpj=d))
        dados = _normalizar_brasilapi(bruto)
        if dados["razao_social"]:
            return dados
        erros.append("BrasilAPI respondeu sem razão social.")
    except ConsultaCNPJError as exc:
        erros.append(str(exc))

    # Fallback: ReceitaWS
    try:
        bruto = _get_json(_RECEITAWS.format(cnpj=d))
        if isinstance(bruto, dict) and bruto.get("status") not in (None, "OK"):
            raise ConsultaCNPJError(str(bruto.get("message") or "Consulta recusada."))
        dados = _normalizar_receitaws(bruto)
        if dados["razao_social"]:
            return dados
        erros.append("ReceitaWS respondeu sem razão social.")
    except ConsultaCNPJError as exc:
        erros.append(str(exc))

    raise ConsultaCNPJError(" | ".join(erros) or "Não foi possível consultar o CNPJ.")
