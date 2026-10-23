# -*- coding: utf-8 -*-
"""Banco de conhecimento do enquadramento (modo sombra).

Separa o que hoje está misturado em `enquadramento.py`:

  * LC 123/2006  -> qual ANEXO é possível para o CNAE (regra determinística)
  * LC 116/2003  -> qual ITEM de serviço casa com a DESCRIÇÃO (leitura da frase)

Este módulo NÃO altera a resposta do motor. Ele registra:
  * o catálogo de CNAE e de itens da LC 116;
  * cada decisão tomada (origem, item casado, score);
  * as correções humanas, que têm precedência.

Banco separado (`instance/enquadramento.db`) para não conflitar com o
`simples.db` de usuários/empresas.

Uso:
    from enquadramento_db import Conhecimento

    kb = Conhecimento()
    kb.init()
    kb.registrar_cnae("7112000", "Serviços de engenharia")
    item, score, motivo = kb.casar_lc116("serviços de engenharia e projeto")
    kb.registrar_decisao(...)
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import unicodedata
from datetime import datetime
from typing import Optional

try:  # pragma: no cover - import relativo quando usado como pacote
    from .itens_lc116 import ITENS_LC116, ITENS_VETADOS
except ImportError:  # pragma: no cover
    from itens_lc116 import ITENS_LC116, ITENS_VETADOS


# ---------------------------------------------------------------------------
# Normalização (mantida idêntica à do motor, para o hash casar com o texto
# que o motor realmente viu)
# ---------------------------------------------------------------------------

def _sem_acento(texto: str, colapsar: bool = False) -> str:
    texto = unicodedata.normalize("NFKD", str(texto or ""))
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = texto.lower()
    return " ".join(texto.split()) if colapsar else texto


def _digitos(codigo) -> str:
    return "".join(c for c in str(codigo or "") if c.isdigit())


def hash_frase(descricao: str) -> str:
    """Impressão digital da frase normalizada.

    Duas frases só compartilham correção se forem IDÊNTICAS depois de
    normalizadas (acento/caixa/espaço). Frase parecida não herda correção:
    evita aprendizado errado por semelhança.
    """
    return hashlib.sha1(
        _sem_acento(descricao, colapsar=True).encode("utf-8")
    ).hexdigest()


# ---------------------------------------------------------------------------
# Esquema
# ---------------------------------------------------------------------------

SCHEMA = """
-- 1) CNAE: fonte fria, o que a Receita publica.
CREATE TABLE IF NOT EXISTS cnae (
    codigo       TEXT PRIMARY KEY,        -- 7 dígitos: 7120100
    divisao      TEXT NOT NULL,           -- 2 dígitos
    classe       TEXT NOT NULL,           -- 4 dígitos
    descricao    TEXT NOT NULL,
    atualizado_em TEXT NOT NULL
);

-- 2) Item da LC 116: catálogo imutável (carregado de itens_lc116.py).
CREATE TABLE IF NOT EXISTS lc116_item (
    subitem   TEXT PRIMARY KEY,           -- 7.02
    descricao TEXT NOT NULL,
    vetado    INTEGER NOT NULL DEFAULT 0
);

-- 3) Decisão registrada pelo motor (modo sombra).
CREATE TABLE IF NOT EXISTS decisao (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    cnae          TEXT NOT NULL,
    classe        TEXT,
    descricao     TEXT NOT NULL,
    hash_frase    TEXT NOT NULL,
    tipo          TEXT,                   -- serviço / comércio / indústria
    anexos        TEXT NOT NULL,          -- JSON: ["V","III"]
    anexo_principal TEXT,
    item_lc116    TEXT,                   -- item casado pela leitura da frase
    item_score    REAL,
    item_motivo   TEXT,
    origem        TEXT NOT NULL,          -- tabela / lc116 / curado / humano
    versao_motor  TEXT,
    criado_em     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_decisao_cnae ON decisao(cnae);
CREATE INDEX IF NOT EXISTS ix_decisao_hash ON decisao(hash_frase);

-- 4) Correção humana: precedência sobre tudo.
CREATE TABLE IF NOT EXISTS correcao (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    cnae          TEXT NOT NULL,
    hash_frase    TEXT NOT NULL,
    descricao     TEXT NOT NULL,
    anexo_final   TEXT NOT NULL,
    tributo       TEXT,                   -- ISS / ICMS / ambos
    item_lc116    TEXT,
    justificativa TEXT NOT NULL,          -- obrigatória: correção sem motivo não vale
    autor         TEXT,
    criado_em     TEXT NOT NULL,
    UNIQUE (cnae, hash_frase)
);

-- 5) Divergência detectada entre o motor e o banco (relatório, não ação).
CREATE TABLE IF NOT EXISTS divergencia (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    decisao_id    INTEGER,
    cnae          TEXT NOT NULL,
    descricao     TEXT,
    anexo_motor   TEXT,
    anexo_banco   TEXT,
    detalhe       TEXT,
    criado_em     TEXT NOT NULL,
    FOREIGN KEY (decisao_id) REFERENCES decisao(id) ON DELETE CASCADE
);
"""

VERSAO_MOTOR = "sombra-1"


# ---------------------------------------------------------------------------
# Comparação frase inteira <-> descrição oficial da LC 116
# ---------------------------------------------------------------------------

# Palavras que aparecem em quase toda descrição e não discriminam nada.
_VAZIAS = frozenset("""

a o as os de da do das dos e ou em na no nas nos para por com sem que
relativos relativas congêneres congeneres qualquer
natureza inclusive outros outras demais prestados prestadas
""".split())
# NOTA: "servico"/"servicos" NÃO podem estar aqui. A primeira palavra da
# descrição do CNAE é justamente o que declara a natureza da atividade —
# descartá-la fazia "Serviço de usinagem" ser lido como "usinagem" e cair na
# lista de não-serviço.

# Termos que se repetem em praticamente todos os itens e não identificam
# serviço nenhum ("execução de obras de engenharia", "atividades de ...").
# Também sem "servico": é termo de decisão em _texto_e_nao_servico().
_TERMOS_LEI = frozenset("""
obra obras empresa empresas local locais forma fim caso parte
atividade atividades estabelecimento
""".split())

# Ligações que, sozinhas, não identificam serviço nenhum: "obras de arte SOB
# ENCOMENDA" e "desenvolvimento de software SOB ENCOMENDA" não são o mesmo.
# "desenvolvimento" idem: desenvolver SOFTWARE e desenvolver PESQUISA não são o
# mesmo serviço — o que identifica é o objeto (software, sistema, pesquisa),
# nunca o ato de desenvolver. Sem isso o motor ligava 6201-5/01 a 2.01.
_SEM_VALOR = frozenset("""
sob sobre encomenda demanda medida meio meios qualquer cada desenvolv
""".split())

# Sinônimos que aproximam a linguagem do CNAE da linguagem da lei.
# Cada entrada vale como se a frase tivesse a palavra-chave.
_SINONIMOS = {
    "pericia": {"pericia", "laudo", "avaliacao"},
    "avaliacao": {"avaliacao", "pericia", "laudo"},
    "laudo": {"laudo", "pericia", "avaliacao"},
    "seguranca": {"seguranca", "higiene"},
    "trabalho": {"trabalho", "ocupacional"},
    "ocupacional": {"ocupacional", "trabalho"},
    "manutencao": {"manutencao", "reparacao", "conservacao"},
    "reparacao": {"reparacao", "manutencao", "conserto"},
    "conserto": {"conserto", "reparacao", "manutencao"},
    "limpeza": {"limpeza", "asseio", "higienizacao"},
    "vigilancia": {"vigilancia", "seguranca", "monitoramento"},
    "treinamento": {"treinamento", "instrucao", "capacitacao"},
    "ensino": {"ensino", "instrucao", "educacao"},
    "instrucao": {"instrucao", "ensino", "treinamento"},
    "publicidade": {"publicidade", "propaganda"},
    "propaganda": {"propaganda", "publicidade"},
    "transporte": {"transporte", "conducao", "frete"},
    "locacao": {"locacao", "arrendamento", "aluguel"},
    "aluguel": {"aluguel", "locacao", "arrendamento"},
    # o CNAE fala "advocatícios"/"advogado"; a LC 116 fala "advocacia"
    "advocacia": {"advocacia", "advocatic", "advocaticio", "advogad"},
    "advocatic": {"advocatic", "advocaticio", "advocacia", "advogad"},
    "advocaticio": {"advocaticio", "advocatic", "advocacia", "advogad"},
    "advogad": {"advogad", "advocacia", "advocaticio"},
    "representacao": {"representacao", "agenciamento"},
    "agenciamento": {"agenciamento", "representacao"},
    # expressões fixas: o CNAE encurta o que a LC 116 escreve por extenso
    # "Desenvolvimento de programas de computador" (CNAE 6201-5/01) e "Análise
    # e desenvolvimento de sistemas" (1.01) / "Elaboração de programas de
    # computadores" (1.04) são o MESMO serviço de software. Sem este elo, 1.01
    # nunca era candidato e o motor caía em 2.01 (pesquisa) só por causa de
    # "desenvolvimento".
    "programa": {"programa", "comput", "software", "sistema"},
    "comput": {"comput", "programa", "software", "sistema"},
    "software": {"software", "programa", "comput", "sistema"},
    "sistema": {"sistema", "programa", "comput", "software"},
    "informatic": {"informatic", "comput", "programa", "sistema"},
}


def _tokens(texto: str) -> set:
    texto = _sem_acento(texto, colapsar=True)
    brutos = set()
    for p in texto.replace("/", " ").replace(",", " ").replace(";", " ").split():
        p = "".join(c for c in p if c.isalnum())
        if len(p) < 3 or p in _VAZIAS:
            continue
        brutos.add(p)
    # expande sinônimos, sem inflar a contagem além do necessário
    expandido = set(brutos)
    for p in brutos:
        expandido |= _SINONIMOS.get(p, set())
    return expandido


def _tokens_brutos(texto: str) -> set:
    """Tokens sem expansão de sinônimos (base do casamento por núcleo).

    Respeita a caixa original: itens da LC 116 são escritos em minúsculas,
    então sigla em caixa alta (TI, TV) só pode vir da descrição do CNAE.
    """
    partes = []
    for p in texto.replace("/", " ").replace(",", " ").replace(";", " ").split():
        limpo = "".join(c for c in p if c.isalnum())
        if not limpo:
            continue
        # tira acento sem perder a caixa (sigla TI/TV x texto corrido)
        limpo = unicodedata.normalize("NFKD", limpo)
        limpo = "".join(c for c in limpo if not unicodedata.combining(c))
        sigla = len(limpo) == 2 and limpo.isupper()
        if len(limpo) < 3 and not sigla:
            continue
        partes.append((limpo, limpo.lower()))

    def _aceito(par):
        original, baixo = par
        if baixo in _VAZIAS:
            return False
        # termo genérico só entra se a frase não tiver outro núcleo
        return baixo not in _TERMOS_LEI

    nucleos = {b for o, b in partes if _aceito((o, b))}
    if nucleos:
        return nucleos
    return {b for o, b in partes if b not in _VAZIAS}


def _stem(p: str) -> str:
    """Radical grosseiro: 'pericia'/'pericias', 'obra'/'obras'."""
    for suf in ("oes", "aes", "s", "es"):
        if len(p) > 4 and p.endswith(suf):
            return p[: -len(suf)]
    return p


def _radicais(tokens: set) -> set:
    return {_stem(t) for t in tokens}


def comparar_frases(descricao: str, item_desc: str) -> float:
    """Pontuação 0..1 entre a frase do CNAE e a descrição do item da LC 116.

    Mede o quanto as duas falas falam do MESMO assunto, comparando a frase
    inteira — não uma palavra solta. Usa coeficiente de Dice sobre radicais.
    """
    a = _radicais(_tokens(descricao))
    b = _radicais(_tokens(item_desc))
    if not a or not b:
        return 0.0
    inter = len(a & b)
    return 2.0 * inter / (len(a) + len(b))


def _radicais_nucleo(tokens: set) -> set:
    """Radicais do núcleo, com sinônimos (advocat -> advocacia/advogad)."""
    radicais = _radicais(tokens)
    expandido = set(radicais)
    for r in radicais:
        expandido |= _SINONIMOS.get(r, set())
    return expandido


# Termos ESTRUTURAIS: aparecem em milhares de descrições e não dizem QUAL é o
# serviço. "Sob encomenda", "de qualquer natureza", "desenvolvimento de..." são
# forma, não objeto. Sem esta lista, "Próteses sob encomenda" (item genérico)
# casava com qualquer atividade "sob encomenda" — inclusive software.
_ESTRUTURAIS = frozenset("""
sob sobre encomenda demanda medida meio meios qualquer cada desenvol
servico servicos atividade atividades obra obras execucao
inclusive outros outras demais relacao relativo relativos
natureza genero forma fim caso parte
similare congenere assemelhad afim diverso variado
de da do das dos e ou em na no nas nos para por com sem que a o as os
""".split())

# Só-tokens que são SERVICO mas também aparecem em descrição de hospedagem e
# moradia (17.01/17.02 "inclusive cadastro e similares"). Se a descrição se
# identifica como atividade de ESTABELECIMENTO (restaurante, loja), não pode
# vencer por esse elo.
_NUCLEO_ESTABELECIMENTO = frozenset("""
restaurante bar padaria hotel pousada motel hospital clinica
supermercad loja farmacia
""".split())


def _objeto(radicais: set) -> set:
    """Radicais que identificam o OBJETO do serviço (sem termos estruturais)."""
    return radicais - _ESTRUTURAIS


# Atividades que NÃO são serviço e por isso não têm item na LC 116.
# A LC 116/2003 tributa "serviços de qualquer natureza", não a circulação de
# mercadorias nem a produção.
#
# A natureza da atividade está no PRIMEIRO termo da descrição, não em qualquer
# palavra dela. É o que ensina a forma das descrições oficiais de CNAE:
#
#   "Fabricação de produtos de padaria"        -> não é serviço
#   "Comércio varejista de artigos do vestuário" -> não é serviço
#   "Industrialização de leite"                 -> não é serviço
#   "Serviços de manutenção de máquinas industriais" -> é serviço
#
# Procurar a palavra em qualquer posição produzia erro grosseiro: itens da
# própria LC 116 — que são serviços por definição — eram bloqueados:
#   23.01 "desenho industrial", 13.05/24.01/1.08 "confecção de...",
#   12.13 "produção de eventos", 20.01-20.03 "serviços portuários...
#   mercadorias". A palavra ali é objeto/adjetivo do serviço, não a natureza.
#
# São PREFIXOS, não radicais exatos, porque o radical depende do tamanho da
# palavra ("fabricacao" não vira "fabricac" pelo stemmer).
_NAO_SERVICO_INICIO = (
    # comércio
    "comerci", "comercial", "varejist", "atacad", "revend", "loja",
    "mercad", "supermercad", "minimercad", "hipermercad", "farmacia",
    "drogari", "papelari", "livrari", "bazar", "brecho", "quiosque",
    "boutique", "tabacari", "armazin", "deposit",
    # indústria / fabricação / industrialização / beneficiamento
    # ("distribuic" NÃO entra: "Distribuição de bens de terceiros" é o item
    #  10.10 da LC 116 — serviço. Só "distribuição de energia/água" não é.)
    "fabric", "industri", "industrializ", "manufatur", "montadora",
    "producao", "beneficiament", "transformac",
    # ("usinagem" NÃO entra: "Serviço de usinagem sob encomenda" é serviço de
    #  terceiros. Usinagem própria aparece como "Fabricação", já barrado.)
    "metalurg", "siderurg", "fundicao", "serrar", "serrari",
    "tecelagem", "textil", "confeccao", "vestuari", "ceramic", "olaria",
    "laticini", "abatedour", "frigorific", "usina", "destilar", "refinar",
    "envasament", "extraca",
    # agropecuária / extração
    # ("florestament"/"silvicultur" NÃO entram: o item 7.16 da LC 116 começa
    #  por "Florestamento, reflorestamento, semeadura..." — é serviço.)
    "agricultura", "agricol", "agropecuar", "pecuar", "lavoura",
    "plantac", "cultivo", "criacao", "granja", "avicultur",
    "suinocultur", "bovinocultur", "piscicultur",
    "minerac", "garimp", "pedreir",
)

# Termos que, quando abrem a descrição, declaram prestação de SERVIÇO e
# sobrepõem a lista acima ("Serviços de embalagem", "Serviços de pintura
# industrial", "Serviço de usinagem sob encomenda").
_ABERTURA_SERVICO = (
    "servic", "servico", "atividad", "atividade", "instalac", "manutenc",
    "reparac", "reparo", "assistenci", "locac", "transport", "ensino",
    "educac", "consultori", "assessori", "agenciament", "corretag",
    "administrac", "organizac", "promoc", "intermediac",
    "recondicionament", "restaurac",
)

# "Distribuição" só é serviço quando distribui BEM DE TERCEIROS (item 10.10 da
# LC 116). Distribuir energia, água, gás ou combustível é concessão/indústria,
# não prestação de serviço.
_DISTRIBUICAO_NAO_SERVICO = (
    "energia", "eletric", "agua", "gas", "combustiv", "derivad",
    "petroleo", "vapor", "saneament",
)

# Objetos de "produção" que a LC 116 tributa como serviço:
# 12.13 "Produção, mediante ou sem encomenda prévia, de eventos, espetáculos,
# entrevistas, shows, ballet...". Se o objeto está aqui, é serviço.
_PRODUCAO_DE_SERVICO = (
    "evento", "espetacul", "show", "entrevist", "ballet", "danca",
    "desfile", "baile", "teatro", "opera", "concerto", "recital",
    "festival", "filme", "audiovisual",
)


def _tokens_iniciais(descricao: str, quantos: int = 3) -> list:
    """Primeiros radicais de conteúdo da descrição, NA ORDEM do texto.

    Não pode usar _tokens_brutos(): ele devolve CONJUNTO (sem ordem) e descarta
    palavras de ligação e termos da lei, então "Fabricação de cimento" voltava
    vazio e "Criação de bovinos" voltava como {'bovino', 'criacao'}.

    Aqui a leitura é sequencial, direto do texto original: normaliza, remove
    palavra de ligação e devolve os primeiros radicais na ordem em que o autor
    escreveu — que é o que define a natureza da atividade.
    """
    ordem = []
    for parte in descricao.replace("/", " ").replace(",", " ").replace(
            ";", " ").replace("-", " ").replace("(", " ").replace(")", " ").split():
        limpo = "".join(c for c in parte if c.isalnum())
        if not limpo:
            continue
        limpo = unicodedata.normalize("NFKD", limpo)
        limpo = "".join(c for c in limpo if not unicodedata.combining(c)).lower()
        if len(limpo) < 3 or limpo in _VAZIAS:
            continue
        r = _stem(limpo)
        if r not in ordem:
            ordem.append(r)
        if len(ordem) >= quantos:
            break
    return ordem[:quantos]


def _abre_com(radical: str, prefixos) -> bool:
    """Casa o radical com um prefixo, tolerando diferenças de singular/plural.

    _stem() remove o "s" só em palavras com mais de 4 letras, então a mesma
    palavra vira 'servic' no plural e 'servico' no singular; e 'eventos' vira
    'event' contra o prefixo 'evento'.

    Regra: casa quando um é prefixo do outro com pelo menos 5 letras em comum.
      'servico' x 'servic'  -> um é prefixo do outro, 6 letras -> casa
      'event'   x 'evento'  -> um é prefixo do outro, 5 letras -> casa
      'usina'   x 'usinagem'-> um é prefixo do outro, mas só 5 e é falso
                               positivo (usinagem é serviço) -> resolvido por
                               'usinagem' não constar em _NAO_SERVICO_INICIO.
    """
    if not radical:
        return False
    for p in prefixos:
        curto = p if len(p) <= len(radical) else radical
        longo = radical if len(p) <= len(radical) else p
        if len(curto) >= 5 and longo.startswith(curto):
            return True
    return False


def _texto_e_nao_servico(descricao: str) -> bool:
    """True quando a atividade descrita não é prestação de serviço.

    A decisão vem do INÍCIO da descrição: abre dizendo "serviço/atividade/
    manutenção/instalação..." -> é serviço; abre dizendo "comércio de",
    "fabricação de", "industrialização de", "produção de"... -> não é serviço.
    """
    # 6 tokens, não 4: o objeto que decide pode vir depois de expressões como
    # "Produção, mediante ou sem encomenda prévia, de eventos..." (12.13),
    # onde "eventos" é a 5ª palavra de conteúdo da frase.
    toks = _tokens_iniciais(descricao, quantos=6)
    if not toks:
        return False
    # A abertura manda. "Serviço de usinagem" e "Produção, mediante ou sem
    # encomenda prévia, de eventos" (12.13) são serviços, embora contenham
    # termos da lista de bloqueio. A sobreposição é POR TERMO e em ordem: vale
    # o primeiro termo que decidir, seja de serviço, seja de não-serviço.
    # Só o termo de abertura decide; os seguintes servem apenas de desempate
    # para "Produção ... de eventos" (objeto de serviço vem antes do bloqueio).
    # O objeto de serviço tem precedência sobre o verbo de produção: em
    # "Produção ... de eventos/espetáculos" (12.13) o que define é o objeto.
    if any(_abre_com(r, _PRODUCAO_DE_SERVICO) for r in toks):
        return False
    # Distribuição só conta quando ELA abre a frase: "Distribuição de energia".
    # Olhar a frase inteira pegava "Análises clínicas, ... eletricidade médica"
    # (item 4.02), onde "eletricidade" é objeto de exame, não de distribuição.
    if _abre_com(toks[0], ("distribuicao", "distribuic")):
        for r in toks[1:]:
            if _abre_com(r, _DISTRIBUICAO_NAO_SERVICO):
                return True
            break
    if _abre_com(toks[0], _ABERTURA_SERVICO):
        return False
    if _abre_com(toks[0], _NAO_SERVICO_INICIO):
        return True
    return False


def _especificidade_legal(objeto_desc: set, objeto_item: set) -> float:
    """Fração do OBJETO do item que a descrição da atividade realmente nomeia.

    Serve para desempatar itens vizinhos que falam do mesmo assunto porém de
    serviços diferentes. Sem isto, três itens de informática empatavam em 1.000
    para "desenvolvimento de programas de computador":

        1.01 Análise e desenvolvimento de sistemas        -> 2 de 2 núcleos  = 1.00
        1.03 Processamento, armazenamento, hospedagem...  -> 2 de 6 núcleos  = 0.33
        1.04 Elaboração de programas de computadores      -> 2 de 3 núcleos  = 0.67

    Empate em 1.000 não é decisão: é ausência de decisão. O item que a
    atividade nomeia por inteiro tem de prevalecer sobre o que só cita uma
    palavra do mesmo campo.
    """
    if not objeto_item:
        return 0.0
    return len(objeto_item & objeto_desc) / len(objeto_item)


def comparar_item(descricao: str, item_desc: str) -> float:
    """Pontuação 0..1 entre a descrição da atividade e o item da LC 116.

    Mede se as duas falas tratam do MESMO OBJETO de serviço — não se repetem
    palavras quaisquer. Dois passos:

    1. Descarta os termos ESTRUTURAIS ("sob encomenda", "de qualquer
       natureza", "desenvolvimento"), que aparecem em milhares de itens e não
       identificam serviço nenhum.
    2. Exige que o OBJETO do serviço descrito esteja presente no item. Item que
       só se liga pela forma ("Próteses sob encomenda") não pode vencer uma
       descrição de software.

    Sinônimos valem dos dois lados (sistema <-> programa <-> comput <-> software),
    porque a LC 116 redige o mesmo serviço com palavras diferentes: "Análise e
    desenvolvimento de sistemas" (1.01) é o serviço de "programas de computador"
    (1.04).

    A pontuação final é a média entre o quanto do OBJETO DESCRITO o item cobre
    e o quanto do OBJETO DO ITEM a descrição nomeia. A segunda metade é o que
    separa itens vizinhos do mesmo campo — sem ela, 1.01, 1.03 e 1.04 empatavam
    em 1.000 e a escolha virava sorteio.
    """
    a = _radicais(_tokens_brutos(descricao))
    b = _radicais(_tokens_brutos(item_desc))
    if not a or not b:
        return 0.0

    # Atividade que não é prestação de serviço não tem item na LC 116.
    # A decisão vem do INÍCIO da descrição (ver _texto_e_nao_servico): abre
    # com "comércio de", "fabricação de", "industrialização de" -> não é
    # serviço; abre com "serviço/atividade/manutenção/instalação" -> é serviço.
    if _texto_e_nao_servico(descricao):
        return 0.0

    objeto_desc = _objeto(a)
    objeto_item = _objeto(b)
    if not objeto_desc or not objeto_item:
        return 0.0

    # "Restaurante" x "17.01 ... inclusive cadastro e similares": o único elo
    # era a palavra genérica. Quando a atividade é um ESTABELECIMENTO e o item
    # não é do mesmo ramo, exige-se ao menos uma palavra de conteúdo em comum.
    if (objeto_desc & _NUCLEO_ESTABELECIMENTO) and not (objeto_desc & objeto_item):
        return 0.0

    a_exp = set(objeto_desc)
    for r in objeto_desc:
        a_exp |= _SINONIMOS.get(r, set())
    b_exp = set(objeto_item)
    for r in objeto_item:
        b_exp |= _SINONIMOS.get(r, set())

    inter = (a_exp & b_exp) - _ESTRUTURAIS
    if not inter:
        # nenhum elo de objeto: o item fala de outro serviço, por mais que
        # repita "sob encomenda", "serviços de" ou "desenvolvimento"
        return 0.0

    # Sinônimo vale menos que palavra literal — nunca zero. A LC 116 escreve
    # "sistemas" onde o CNAE escreve "programas de computador": sem essa
    # paráfrase, 1.01 jamais seria candidato. Mas parafrasear não pode
    # equivaler a nomear: "perícia" é sinônimo de "avaliação", e só por isso
    # 15.18 ("avaliação e vistoria de imóvel") empatava em 1.000 com "perícia
    # técnica", objetos que nada têm em comum. Por isso, no elo:
    #   palavra literal  -> peso 1
    #   sinônimo         -> peso 0,4
    # O item que traz a palavra da descrição vence o que só traz paráfrase.
    literal = (objeto_desc & objeto_item) - _ESTRUTURAIS
    sinonimos = inter - literal
    if len(inter) < 2 and not literal:
        # Um único elo por paráfrase não identifica serviço.
        return 0.0
    forca = (len(literal) + 0.4 * len(sinonimos)) / len(inter)

    # cobertura: quanto do objeto descrito o item contempla
    cobertura = len(inter) / len(objeto_desc)
    # precisão: quanto do objeto do item a descrição nomeia (literal)
    precisao = _especificidade_legal(objeto_desc, objeto_item)
    # bônus quando o radical LITERAL do objeto está no item (não só sinônimo):
    # "Advocacia" x "Advocacia." vale mais que "Advocacia" x "Assessoria..."
    bonus = 0.10 if literal else 0.0

    bruto = 0.50 * cobertura + 0.50 * precisao + bonus
    return round(min(1.0, bruto * forca), 4)


def vazias_lista_lc116() -> set:
    """Palavras que se repetem na lista inteira e não identificam serviço."""
    return _VAZIAS


class Conhecimento:
    """Acesso ao banco de conhecimento do enquadramento."""

    MIN_SCORE = 0.20  # abaixo disso não há casamento confiável
    MIN_SCORE_ITEM = 0.30  # casamento item LC 116 x descrição da atividade

    def __init__(self, caminho: Optional[str] = None):
        if caminho is None:
            base = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "instance"
            )
            os.makedirs(base, exist_ok=True)
            caminho = os.path.join(base, "enquadramento.db")
        self.caminho = caminho
        self._itens_cache = None

    # -- conexão ---------------------------------------------------------
    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.caminho)
        conn.row_factory = sqlite3.Row
        return conn

    def init(self) -> None:
        with self._conn() as conn:
            conn.executescript(SCHEMA)
        self.carregar_lc116()

    # -- carga do catálogo LC 116 ---------------------------------------
    def carregar_lc116(self) -> int:
        with self._conn() as conn:
            for subitem, descricao in ITENS_LC116.items():
                conn.execute(
                    """INSERT OR IGNORE INTO lc116_item
                       (subitem, descricao, vetado) VALUES (?, ?, ?)""",
                    (subitem, descricao, 1 if subitem in ITENS_VETADOS else 0),
                )
            total = conn.execute(
                "SELECT COUNT(*) FROM lc116_item WHERE vetado = 0"
            ).fetchone()[0]
        self._itens_cache = None
        return total

    def _itens(self) -> list:
        if self._itens_cache is None:
            with self._conn() as conn:
                self._itens_cache = [
                    (r["subitem"], r["descricao"])
                    for r in conn.execute(
                        "SELECT subitem, descricao FROM lc116_item "
                        "WHERE vetado = 0"
                    )
                ]
        return self._itens_cache

    # -- leitura da frase ------------------------------------------------
    def casar_lc116(self, descricao: str, top: int = 3) -> list:
        """Itens da LC 116 mais próximos da frase, do melhor ao pior.

        Retorna [(subitem, score, descricao_item), ...].
        Não decide anexo: apenas diz QUAL serviço a frase descreve.
        """
        texto = _sem_acento(descricao, colapsar=True)[:600]
        if not texto.strip():
            return []
        pontuados = []
        for subitem, item_desc in self._itens():
            s = comparar_item(texto, item_desc)
            if s >= self.MIN_SCORE:
                pontuados.append((subitem, round(s, 3), item_desc))
        pontuados.sort(key=lambda x: (-x[1], x[0]))
        return pontuados[:top]

    def melhor_item(self, descricao: str):
        casados = self.casar_lc116(descricao, top=1)
        return casados[0] if casados else (None, 0.0, None)

    def descricao_cnae(self, cnae: str) -> str:
        """Descrição oficial gravada para o CNAE ("" quando não houver)."""
        d = _digitos(cnae)
        if len(d) != 7:
            return ""
        with self._conn() as conn:
            linha = conn.execute(
                "SELECT descricao FROM cnae WHERE codigo = ?", (d,)
            ).fetchone()
        return (linha["descricao"] if linha else "")

    def item_para_cnae(self, cnae: str, descricao: str) -> Optional[str]:
        """Item da LC 116 que descreve o serviço efetivamente prestado.

        O código CNAE sozinho não define o item: quem define é a DESCRIÇÃO da
        atividade. Usa a descrição informada; sem ela, a descrição oficial
        cadastrada para o código. Devolve None quando o casamento não é
        confiável. Não decide anexo: apenas identifica o item da LC 116/2003.
        """
        frase = (descricao or "").strip()
        if not frase:
            frase = self.descricao_cnae(cnae)
        if not frase:
            return None
        return self.item_para_frase(frase)

    def item_para_frase(self, frase: str) -> Optional[str]:
        """Item da LC 116 para uma descrição de atividade (sem saber o CNAE)."""
        texto = _sem_acento(frase, colapsar=True)[:600]
        melhor = None
        melhor_score = 0.0
        for subitem, item_desc in self._itens():
            # comparar_item já zera quando não há elo de OBJETO; o pré-filtro
            # literal que existia aqui bloqueava casamentos por sinônimo
            # ("programas de computador" x "sistemas" na 1.01).
            s = comparar_item(texto, item_desc)
            if s > melhor_score:
                melhor, melhor_score = subitem, s
        if melhor and melhor_score >= self.MIN_SCORE_ITEM:
            return melhor
        return None

    # -- escrita ---------------------------------------------------------
    def registrar_cnae(self, codigo: str, descricao: str) -> None:
        d = _digitos(codigo)
        if len(d) != 7:
            return
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO cnae (codigo, divisao, classe, descricao,
                                    atualizado_em)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(codigo) DO UPDATE SET
                     descricao = excluded.descricao,
                     atualizado_em = excluded.atualizado_em""",
                (d, d[:2], d[:4], descricao or "",
                 datetime.now().isoformat(timespec="seconds")),
            )

    def registrar_decisao(self, cnae: str, descricao: str, tipo: str,
                          anexos: list, origem: str = "tabela") -> int:
        """Grava a decisão do motor e o item que a frase sugere."""
        d = _digitos(cnae)
        item, score, motivo = self.melhor_item(descricao)
        with self._conn() as conn:
            cur = conn.execute(
                """INSERT INTO decisao
                   (cnae, classe, descricao, hash_frase, tipo, anexos,
                    anexo_principal, item_lc116, item_score, item_motivo,
                    origem, versao_motor, criado_em)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    d, d[:4], descricao or "", hash_frase(descricao),
                    tipo, json.dumps(anexos, ensure_ascii=False),
                    anexos[0] if anexos else None,
                    item, float(score or 0), motivo, origem,
                    VERSAO_MOTOR,
                    datetime.now().isoformat(timespec="seconds"),
                ),
            )
            return cur.lastrowid

    def registrar_divergencia(self, decisao_id: int, cnae: str,
                              descricao: str, anexo_motor: str,
                              anexo_banco: str, detalhe: str = "") -> None:
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO divergencia
                   (decisao_id, cnae, descricao, anexo_motor, anexo_banco,
                    detalhe, criado_em)
                   VALUES (?,?,?,?,?,?,?)""",
                (decisao_id, _digitos(cnae), descricao, anexo_motor,
                 anexo_banco, detalhe,
                 datetime.now().isoformat(timespec="seconds")),
            )

    def corrigir(self, cnae: str, descricao: str, anexo_final: str,
                 justificativa: str, autor: str = "",
                 tributo: str = "", item_lc116: str = "") -> None:
        """Correção humana. Justificativa é obrigatória (auditoria)."""
        if not (justificativa or "").strip():
            raise ValueError("Correção exige justificativa.")
        d = _digitos(cnae)
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO correcao
                   (cnae, hash_frase, descricao, anexo_final, tributo,
                    item_lc116, justificativa, autor, criado_em)
                   VALUES (?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(cnae, hash_frase) DO UPDATE SET
                     anexo_final = excluded.anexo_final,
                     tributo = excluded.tributo,
                     item_lc116 = excluded.item_lc116,
                     justificativa = excluded.justificativa,
                     autor = excluded.autor,
                     criado_em = excluded.criado_em""",
                (d, hash_frase(descricao), descricao, anexo_final, tributo,
                 item_lc116, justificativa.strip(), autor,
                 datetime.now().isoformat(timespec="seconds")),
            )

    # -- leitura do banco ------------------------------------------------
    def correcao_de(self, cnae: str, descricao: str):
        """Correção humana exata para esta frase (ou None)."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM correcao WHERE cnae = ? AND hash_frase = ?",
                (_digitos(cnae), hash_frase(descricao)),
            ).fetchone()
        return dict(row) if row else None

    def resumo(self) -> dict:
        with self._conn() as conn:
            def n(sql):
                return conn.execute(sql).fetchone()[0]
            return {
                "itens_lc116": n(
                    "SELECT COUNT(*) FROM lc116_item WHERE vetado = 0"),
                "cnaes": n("SELECT COUNT(*) FROM cnae"),
                "decisoes": n("SELECT COUNT(*) FROM decisao"),
                "correcoes": n("SELECT COUNT(*) FROM correcao"),
                "divergencias": n("SELECT COUNT(*) FROM divergencia"),
            }

    def divergencias(self, limite: int = 50) -> list:
        with self._conn() as conn:
            return [dict(r) for r in conn.execute(
                """SELECT * FROM divergencia
                   ORDER BY id DESC LIMIT ?""", (limite,))]


if __name__ == "__main__":  # pragma: no cover - verificação rápida
    kb = Conhecimento()
    kb.init()
    print("Banco:", kb.caminho)
    print("Resumo:", kb.resumo())
    for frase in (
        "Serviços de perícia técnica relacionados à segurança do trabalho",
        "Obras de construção de edifícios",
        "Manutenção e reparação de veículos automotores",
        "Comércio varejista de artigos do vestuário",
        "Desenvolvimento de programas de computador sob encomenda",
    ):
        print("\n>", frase)
        for sub, score, _desc in kb.casar_lc116(frase):
            print(f"   {sub}  {score:.3f}")
