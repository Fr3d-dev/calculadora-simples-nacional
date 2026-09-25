"""
Importação de XMLs fiscais (saídas) para apurar o faturamento do mês.

Formatos aceitos (somente operações de SAÍDA — emitente = a própria empresa):
  * NF-e  (modelo 55)  -> tag <emit> é o emitente; <dest> é o destinatário.
  * NFC-e (modelo 65)  -> idem NF-e.
  * NFS-e (serviços)   -> <prestador>/<emit> é o prestador do serviço.
  * CT-e  (transporte) -> <emit> é a transportadora (tomador em <toma>).

Usa apenas a biblioteca padrão (xml.etree.ElementTree + zipfile), que é
gratuita e já vem com o Python. Nenhuma dependência externa é necessária.

A ideia: cada XML de saída representa uma nota emitida pela empresa. Somamos
o valor (vNF / vServ / vTPrest) por competência (mês/ano) e devolvemos esse
agregado para que o faturamento do mês seja gravado. Quando o mês "vira", o
valor já fica salvo e passa a compor o RBT12 normalmente.
"""

from __future__ import annotations

import io
import re
import zipfile
from collections import defaultdict
from datetime import datetime
from xml.etree import ElementTree as ET

# Modelos de documento que sabemos ler.
MODELOS = {
    "55": "NF-e",
    "65": "NFC-e",
    "57": "CT-e",
}

# Todos os namespaces possíveis num XML fiscal (varia por origem/prefeitura).
NS = {
    "nfe": "http://www.portalfiscal.inf.br/nfe",
    "cte": "http://www.portalfiscal.inf.br/cte",
}


def apenas_digitos(valor: str | None) -> str:
    return re.sub(r"\D", "", valor or "")


def formatar_cnpj(cnpj: str | None) -> str:
    d = apenas_digitos(cnpj)
    if len(d) != 14:
        return (cnpj or "").strip()
    return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"


def _localname(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _filho(elem, nome: str):
    """Primeiro filho com esse nome local, ignorando namespace."""
    if elem is None:
        return None
    for filho in elem:
        if _localname(filho.tag) == nome:
            return filho
    return None


def _filhos(elem, nome: str):
    if elem is None:
        return []
    return [f for f in elem if _localname(f.tag) == nome]


def _descendente(elem, *caminho):
    """Percorre a árvore por nomes locais ignorando namespace."""
    atual = elem
    for nome in caminho:
        atual = _filho(atual, nome)
        if atual is None:
            return None
    return atual


def _texto_local(elem, *caminho) -> str:
    alvo = _descendente(elem, *caminho)
    return (alvo.text or "").strip() if alvo is not None and alvo.text else ""


def _achar_raiz(root, nome: str):
    """Acha o elemento com esse nome local em qualquer profundidade."""
    if _localname(root.tag) == nome:
        return root
    for elem in root.iter():
        if _localname(elem.tag) == nome:
            return elem
    return None


def _valor_float(texto: str) -> float:
    try:
        return float((texto or "0").replace(",", "."))
    except ValueError:
        return 0.0


def _competencia(ano: str, mes: str) -> str | None:
    """Normaliza para a chave 'AAAA-MM' usada pela aplicação."""
    ano_d = apenas_digitos(ano)
    mes_d = apenas_digitos(mes)
    if len(ano_d) == 4 and 1 <= int(mes_d or 0) <= 12:
        return f"{ano_d}-{int(mes_d):02d}"
    return None


def _competencia_de_data(data_iso: str) -> str | None:
    if not data_iso:
        return None
    m = re.match(r"(\d{4})-(\d{2})", data_iso.strip())
    if m:
        return f"{m.group(1)}-{m.group(2)}"
    return None


# ---------------------------------------------------------------------------
# Extração por tipo de documento
# ---------------------------------------------------------------------------

def _ler_nfe(root) -> dict | None:
    """NF-e (55) e NFC-e (65)."""
    inf = _achar_raiz(root, "infNFe")
    if inf is None:
        return None

    modelo = _texto_local(inf, "ide", "mod")
    tipo = MODELOS.get(modelo, "NF-e" if modelo != "65" else "NFC-e")

    emit_cnpj = _texto_local(inf, "emit", "CNPJ") or _texto_local(inf, "emit", "CPF")
    dest_cnpj = _texto_local(inf, "dest", "CNPJ") or _texto_local(inf, "dest", "CPF")

    # Somente saída: o emitente deve ser a própria empresa (checado depois,
    # comparando com o CNPJ da empresa ativa). Aqui só marcamos o tipo.
    data_emissao = _texto_local(inf, "ide", "dhEmi") or _texto_local(inf, "ide", "dEmi")
    competencia = _competencia_de_data(data_emissao)

    valor = _texto_local(inf, "total", "ICMSTot", "vNF")
    if not valor:
        # Alguns XML podem vir sem o grupo total.
        valor = _texto_local(inf, "total", "vNF")

    return {
        "tipo": tipo,
        "modelo": modelo or "55",
        "chave": _texto_local(inf, "chNFe") or apenas_digitos(inf.get("Id") or "")[:44],
        "emitente_cnpj": apenas_digitos(emit_cnpj),
        "destinatario_cnpj": apenas_digitos(dest_cnpj),
        "competencia": competencia,
        "valor": _valor_float(valor),
        "operacao": "saida",
        "data_emissao": data_emissao,
    }


def _ler_nfse(root) -> dict | None:
    """NFS-e — estrutura varia por prefeitura; tentamos os campos mais comuns."""
    inf = _achar_raiz(root, "InfNfse") or _achar_raiz(root, "infNFSe") or root

    # Prestador (= emitente do serviço).
    prest_cnpj = (
        _texto_local(inf, "PrestadorServico", "IdentificacaoPrestador", "Cnpj")
        or _texto_local(inf, "prestador", "CNPJ")
        or _texto_local(root, "Prestador", "Cnpj")
        or _texto_local(inf, "emit", "CNPJ")
    )
    tomador_cnpj = (
        _texto_local(inf, "TomadorServico", "IdentificacaoTomador", "CpfCnpj", "Cnpj")
        or _texto_local(inf, "tomador", "CNPJ")
    )

    data_emissao = (
        _texto_local(inf, "DataEmissao")
        or _texto_local(inf, "dhEmi")
        or _texto_local(inf, "Competencia")
    )
    competencia = _competencia_de_data(data_emissao)
    if not competencia:
        # NFS-e às vezes usa <Competencia>2026-09-01</Competencia> (já tratado acima)
        comp = _texto_local(inf, "Competencia")
        competencia = _competencia_de_data(comp)

    valor = (
        _texto_local(inf, "Servico", "Valores", "ValorServicos")
        or _texto_local(inf, "valores", "vServPrest", "vReceb")
        or _texto_local(inf, "valores", "vServ")
        or _texto_local(inf, "total", "vNF")
    )

    return {
        "tipo": "NFS-e",
        "modelo": "",
        "chave": _texto_local(inf, "Numero") or "",
        "emitente_cnpj": apenas_digitos(prest_cnpj),
        "destinatario_cnpj": apenas_digitos(tomador_cnpj),
        "competencia": competencia,
        "valor": _valor_float(valor),
        "operacao": "saida",
        "data_emissao": data_emissao,
    }


def _ler_cte(root) -> dict | None:
    """CT-e (modelo 57)."""
    inf = _achar_raiz(root, "infCte")
    if inf is None:
        return None

    emit_cnpj = _texto_local(inf, "emit", "CNPJ") or _texto_local(inf, "emit", "CPF")
    toma_cnpj = (
        _texto_local(inf, "ide", "toma3", "toma")
        or _texto_local(inf, "toma", "CNPJ")
    )
    data_emissao = _texto_local(inf, "ide", "dhEmi") or _texto_local(inf, "ide", "dEmi")
    competencia = _competencia_de_data(data_emissao)
    valor = _texto_local(inf, "vPrest", "vTPrest") or _texto_local(inf, "vPrest", "vRec")

    return {
        "tipo": "CT-e",
        "modelo": "57",
        "chave": _texto_local(inf, "chCTe") or apenas_digitos(inf.get("Id") or "")[:44],
        "emitente_cnpj": apenas_digitos(emit_cnpj),
        "destinatario_cnpj": apenas_digitos(toma_cnpj),
        "competencia": competencia,
        "valor": _valor_float(valor),
        "operacao": "saida",
        "data_emissao": data_emissao,
    }


def ler_xml(conteudo: bytes) -> dict:
    """
    Lê o conteúdo de um XML fiscal e devolve um dicionário normalizado.
    Levanta ValueError se não reconhecer o documento.
    """
    try:
        root = ET.fromstring(conteudo)
    except ET.ParseError as exc:
        raise ValueError(f"XML inválido: {exc}") from exc

    # Detecta pelo nome local da raiz / elementos internos.
    nome_raiz = _localname(root.tag).lower()

    if "cte" in nome_raiz or _achar_raiz(root, "infCte") is not None:
        dados = _ler_cte(root)
    elif "nfse" in nome_raiz or _achar_raiz(root, "InfNfse") is not None \
            or _achar_raiz(root, "infNFSe") is not None:
        dados = _ler_nfse(root)
    else:
        dados = _ler_nfe(root)

    if not dados or not dados.get("emitente_cnpj"):
        raise ValueError("Não foi possível identificar o emitente no XML.")

    return dados


# ---------------------------------------------------------------------------
# Agrupamento
# ---------------------------------------------------------------------------

def processar_arquivos(arquivos: list[dict], cnpj_empresa: str) -> dict:
    """
    Recebe uma lista de {"nome": str, "conteudo": bytes} (XMLs avulsos e/ou .zip)
    e devolve:

      {
        "por_mes": { "2026-08": 1234.56, ... },     # só saídas da empresa
        "notas": [ {competencia, tipo, valor, chave, ...}, ... ],
        "ignoradas": [ {"nome", "motivo"}, ... ],
        "total": float,
      }

    Só entram notas cujo emitente seja a própria empresa (saídas).
    """
    cnpj_empresa_d = apenas_digitos(cnpj_empresa)
    por_mes = defaultdict(float)
    notas = []
    ignoradas = []

    def tratar(nome: str, conteudo: bytes):
        try:
            dados = ler_xml(conteudo)
        except ValueError as exc:
            ignoradas.append({"nome": nome, "motivo": str(exc)})
            return

        # Somente saídas: emitente precisa ser a empresa.
        if cnpj_empresa_d and dados["emitente_cnpj"] != cnpj_empresa_d:
            ignoradas.append({
                "nome": nome,
                "motivo": "Entrada de terceiro (emitente ≠ sua empresa) — ignorada.",
            })
            return

        comp = dados.get("competencia")
        if not comp:
            ignoradas.append({"nome": nome, "motivo": "Sem data de emissão legível."})
            return

        por_mes[comp] += dados["valor"]
        notas.append({
            "nome": nome,
            "competencia": comp,
            "tipo": dados["tipo"],
            "chave": dados["chave"],
            "valor": dados["valor"],
        })

    for arq in arquivos:
        nome = arq.get("nome") or "arquivo.xml"
        conteudo = arq.get("conteudo") or b""

        if nome.lower().endswith(".zip") or conteudo[:2] == b"PK":
            try:
                with zipfile.ZipFile(io.BytesIO(conteudo)) as zf:
                    for info in zf.infolist():
                        if info.is_dir():
                            continue
                        if not info.filename.lower().endswith(".xml"):
                            continue
                        tratar(info.filename, zf.read(info))
            except zipfile.BadZipFile:
                ignoradas.append({"nome": nome, "motivo": "ZIP inválido."})
        else:
            tratar(nome, conteudo)

    notas.sort(key=lambda n: (n["competencia"], n["nome"]))

    return {
        "por_mes": {k: round(v, 2) for k, v in sorted(por_mes.items())},
        "notas": notas,
        "ignoradas": ignoradas,
        "total": round(sum(por_mes.values()), 2),
    }
