"""
Leitura do PDF "Extrato do Simples Nacional" (PGDAS-D).

O extrato é gerado pelo portal do Simples Nacional e contém, entre outras
informações, a discriminação da Receita Bruta mês a mês (seções 2.1 e 2.2).
Este módulo extrai esses dados para permitir o preenchimento automático da
tabela de faturamento (RBT12) do sistema.

Estrutura relevante do PDF
--------------------------
  Seção 1  -> CNPJ básico, nome empresarial, município/UF
  Seção 2.1-> Período de Apuração (PA), Receita Bruta do PA (RPA), RBT12, RBA
  Seção 2.2-> Receitas Brutas Anteriores por mês (MM/AAAA, MM/AAAA, ...)
  Seção 0  -> Data de geração ("Gerado em dd/mm/aaaa")

As datas vêm no formato brasileiro (dd/mm/aaaa) e os valores no formato
brasileiro de moeda (1.234.567,89), que são convertidos para tipos nativos.

Este módulo depende apenas de ``pypdf`` (leve) e da biblioteca padrão.
"""

from __future__ import annotations

import io
import re
from datetime import date
from typing import Optional, Union

_MESES_CURTOS = [
    "jan", "fev", "mar", "abr", "mai", "jun",
    "jul", "ago", "set", "out", "nov", "dez",
]

_MESES_NOMES = [
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
]

# ---------------------------------------------------------------------------
# Conversores de formato brasileiro
# ---------------------------------------------------------------------------


def _para_numero(texto: Union[str, None]) -> Optional[float]:
    """Converte '1.234.567,89' -> 1234567.89. Devolve None se vazio/inválido."""
    if texto is None:
        return None
    texto = texto.strip()
    if not texto:
        return None
    texto = texto.replace("\xa0", " ").replace(" ", "")
    texto = texto.replace(".", "").replace(",", ".")
    try:
        return float(texto)
    except ValueError:
        return None


def _para_data(texto: Union[str, None]) -> Optional[date]:
    """Converte 'dd/mm/aaaa' -> date."""
    if not texto:
        return None
    m = re.search(r"(\d{2})/(\d{2})/(\d{4})", texto)
    if not m:
        return None
    dia, mes, ano = (int(x) for x in m.groups())
    try:
        return date(ano, mes, dia)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Extração de texto (aceita caminho, bytes ou file-like)
# ---------------------------------------------------------------------------


def extrair_texto(fonte) -> str:
    """
    Extrai o texto de todas as páginas do PDF do extrato.

    ``fonte`` pode ser um caminho (str/Path), bytes ou um arquivo (file-like).
    """
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "A biblioteca 'pypdf' é necessária para ler o extrato. "
            "Instale com: pip install pypdf"
        ) from exc

    if isinstance(fonte, (bytes, bytearray)):
        fonte = io.BytesIO(fonte)

    leitor = PdfReader(fonte)
    partes = []
    for pagina in leitor.pages:
        partes.append(pagina.extract_text() or "")
    return "\n".join(partes)


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

_RE_PERIODO = re.compile(r"Per[íi]odo de Apura[çc][ãa]o\s*\(PA\)\s*:\s*(\d{2})\s*/\s*(\d{4})")
_RE_CNPJ_BASICO = re.compile(r"CNPJ\s+B[áa]sico\s*:\s*([\d.\-/]+)", re.IGNORECASE)
_RE_NOME = re.compile(r"Nome\s+Empresarial\s*:\s*(.+)", re.IGNORECASE)
_RE_MUNICIPIO = re.compile(r"Munic[íi]pio\s*:\s*(.+?)\s+UF\s*:\s*([A-Za-z]{2})")
_RE_RPA = re.compile(r"Receita\s+Bruta\s+do\s+PA\s*\(RPA\).*?([\d.]{1,20},\d{2})\s+([\d.]{1,20},\d{2})\s+([\d.]{1,20},\d{2})", re.DOTALL)
_RE_RBT12 = re.compile(r"\(RBT12\)\s*([\d.]{1,20},\d{2})\s+([\d.]{1,20},\d{2})\s+([\d.]{1,20},\d{2})")
_RE_GERADO = re.compile(r"Gerado em (\d{2}/\d{2}/\d{4})")
_RE_MES_VALOR = re.compile(r"(\d{2})/(\d{4})\s+([\d.]{1,20},\d{2})")


def _extrair_receitas_anteriores(texto: str) -> dict[str, float]:
    """
    Extrai os pares 'MM/AAAA valor' das seções 2.2.1 (mercado interno) e
    2.2.2 (mercado externo).

    Mercado interno:  usa os valores diretamente.
    Mercado externo:  soma (a maioria dos extratos traz zeros).
    """
    resultado: dict[str, float] = {}

    # Isola a seção 2.2 até a seção 2.3 ("Folha de Salários").
    m_ini = re.search(r"2\.2\)\s*Receitas\s+Brutas\s+Anteriores", texto)
    m_fim = re.search(r"2\.3\)\s*Folha\s+de\s+Sal[áa]rios", texto)
    trecho = texto
    if m_ini:
        trecho = texto[m_ini.start(): m_fim.start() if m_fim else len(texto)]

    # Divide entre mercado interno e externo, quando possível.
    corte = re.search(r"Mercado\s+Externo", trecho)
    if corte:
        interno = trecho[: corte.start()]
        externo = trecho[corte.start():]
    else:
        interno, externo = trecho, ""

    for parte in (interno, externo):
        for mes, ano, valor_txt in _RE_MES_VALOR.findall(parte):
            mes_i = int(mes)
            if not 1 <= mes_i <= 12:
                continue
            valor = _para_numero(valor_txt)
            if valor is None:
                continue
            chave = f"{ano}-{mes_i:02d}"
            # Soma caso apareça mais de uma vez (interno + externo).
            resultado[chave] = round(resultado.get(chave, 0.0) + valor, 2)

    return resultado


def _montar_meses_recentes(receitas: dict[str, float], quantidade: int = 12) -> list[dict]:
    """
    A partir do dict {MM/AAAA: valor}, devolve os últimos ``quantidade`` meses
    em ordem cronológica crescente.
    """
    if not receitas:
        return []

    chaves_ordenadas = sorted(receitas.keys())
    ultimas = chaves_ordenadas[-quantidade:]

    meses = []
    for indice, chave in enumerate(ultimas, start=1):
        ano, mes = (int(x) for x in chave.split("-"))
        meses.append({
            "indice": indice,
            "chave": chave,
            "ano": ano,
            "mes": mes,
            "mes_nome": _MESES_NOMES[mes - 1],
            "rotulo": f"{_MESES_NOMES[mes - 1]}/{ano}",
            "valor": receitas[chave],
        })
    return meses


def ler_extrato(fonte) -> dict:
    """
    Lê o PDF do extrato e devolve um dicionário estruturado::

        {
          "cnpj_basico": "11.538.454",
          "nome_empresarial": "PRIME CONSTRUCOES LTDA",
          "municipio": "INDAIAL",
          "uf": "SC",
          "periodo_apuracao": "2021-07",
          "periodo_rotulo": "07/2021",
          "gerado_em": date(2021, 9, 8),
          "rpa": 1846164.55,
          "rbt12": 1840769.27,
          "receitas_meses": {           # todas as chaves encontradas
              "2020-01": 0.0, "2020-08": 20855.0, "2021-06": 325397.95, ...
          },
          "meses": [                    # últimos 12 meses, em ordem
              {"indice": 1, "chave": "2020-07", "ano": 2020, "mes": 7,
               "mes_nome": "julho", "rotulo": "julho/2020", "valor": 0.0},
              ...
          ],
        }

    Levanta ``ValueError`` se o texto não parecer um extrato do Simples.
    """
    texto = extrair_texto(fonte)

    if "Extrato do Simples Nacional" not in texto and "Discriminativo de Receitas" not in texto:
        raise ValueError(
            "O arquivo enviado não parece ser um extrato do Simples Nacional "
            "(PGDAS-D). Verifique se você selecionou o PDF correto."
        )

    dados: dict = {
        "cnpj_basico": None,
        "nome_empresarial": None,
        "municipio": None,
        "uf": None,
        "periodo_apuracao": None,
        "periodo_rotulo": None,
        "gerado_em": None,
        "rpa": None,
        "rbt12": None,
        "receitas_meses": {},
        "meses": [],
    }

    m = _RE_CNPJ_BASICO.search(texto)
    if m:
        dados["cnpj_basico"] = m.group(1).strip()

    m = _RE_NOME.search(texto)
    if m:
        dados["nome_empresarial"] = m.group(1).strip()

    m = _RE_MUNICIPIO.search(texto)
    if m:
        dados["municipio"] = m.group(1).strip()
        dados["uf"] = m.group(2).strip().upper()

    m = _RE_PERIODO.search(texto)
    if m:
        mes, ano = int(m.group(1)), int(m.group(2))
        dados["periodo_apuracao"] = f"{ano}-{mes:02d}"
        dados["periodo_rotulo"] = f"{mes:02d}/{ano}"

    m = _RE_GERADO.search(texto)
    if m:
        dados["gerado_em"] = _para_data(m.group(1))

    m = _RE_RPA.search(texto)
    if m:
        dados["rpa"] = _para_numero(m.group(3))

    m = _RE_RBT12.search(texto)
    if m:
        dados["rbt12"] = _para_numero(m.group(3))

    receitas = _extrair_receitas_anteriores(texto)
    dados["receitas_meses"] = receitas
    dados["meses"] = _montar_meses_recentes(receitas, 12)

    return dados


__all__ = ["ler_extrato", "extrair_texto"]
