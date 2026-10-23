"""
Tabela legal de enquadramento no Simples Nacional (motor novo).

Este módulo é a fonte ÚNICA de verdade do enquadramento por CNAE/atividade.
Ele substitui a heurística por palavras-chave do `cnaes.py` (ponta a ponta).

Estrutura:
    MotorEnquadramento
        .enquadrar(cnae, descricao)        -> dict (mesmo formato de sugerir_anexo)
        .candidatos(cnae, descricao)       -> list de anexos legalmente possíveis
        .explicacao(cnae, descricao)       -> dict (mesmo formato de explicacoes.explicar)

Regras empregadas (LC 123/2006, art. 18, §§ 4º, 5º-B, 5º-C a 5º-I, e Anexos I a V):

  CNAE de 7 dígitos -> classe (0000-0). Classes repetidas em anexos diferentes
  são "ambíguas" (ex.: 18.13 impressão -> II ou III; 86.30 odontologia x
  ambulatório -> V ou III). A ambiguidade é resolvida pelo TIPO DA ATIVIDADE
  (comércio / indústria / serviço) e, no serviço, pelo ITEM DA LC 116/2003,
  nunca por palavras soltas na descrição.

  1) Atividade NÃO serviço (comércio/indústria) -> Anexo I ou II, conforme o
     tipo real de operação. Nunca Anexo III/IV/V.
     - Anexo IV (construção 41–43, vigilância 80, limpeza 81) permanece IV.
  2) Atividade SERVIÇO -> Anexo III, IV ou V:
     - Anexo IV: serviços de construção civil e serviços de limpeza,
       vigilância e afins (art. 18, §5º-C e §5º-I).
     - Anexo V x Anexo III: apenas as atividades do §5º-C *em conjunto* com
       os itens da LC 116 do art. 18, §5º-D (serviços intelectuais). Só para
       elas o Fator "r" (folha >= 28% da RBT12) faz a migração V -> III.
     - Todas as demais atividades de serviço são EXCLUSIVAMENTE Anexo III e
       não migram para o Anexo V (ex.: transporte, educação regular, locação
       de bens móveis, academias, reparação/manutenção, beleza).
  3) Anexo IV nunca recebe os anexos I, II, III ou V como candidatos: a CPP é
     recolhida à parte e a regra do Fator "r" não se aplica.
  4) CNAE ausente/inválido -> sem sugestão (confiança baixa), nunca um palpite
     gerado pela descrição isolada.

Compatibilidade: `cnaes.sugerir_anexo()` e `cnaes.anexos_candidatos()` passam
a delegar para este motor; `explicacoes.explicar()` usa a explicação daqui para
resolver o enquadramento (o texto curado por CNAE continua sendo o do
`explicacoes.py`).
"""

from __future__ import annotations

import unicodedata
from typing import Optional


# ---------------------------------------------------------------------------
# Tabela: divisões (2 dígitos) e classes (4 dígitos) -> Anexo base
# ---------------------------------------------------------------------------

TABELA_ANEXO = {
    # I — comércio (revenda de mercadorias) e produção própria agropecuária
    "01": "I", "02": "I", "03": "I", "05": "I",
    "45": "I", "46": "I", "47": "I",
    # II — indústria e serviços industriais de utilidade pública
    "10": "II", "11": "II", "12": "II", "13": "II", "14": "II", "15": "II",
    "16": "II", "17": "II", "18": "II", "19": "II", "20": "II", "21": "II",
    "22": "II", "23": "II", "24": "II", "25": "II", "26": "II", "27": "II",
    "28": "II", "29": "II", "30": "II", "31": "II", "32": "II", "33": "II",
    "35": "II", "36": "II", "37": "II", "38": "II",
    # III — serviços gerais
    "49": "III",  # transporte terrestre
    "50": "III",  # transporte aquaviário
    "51": "III",  # transporte aéreo
    "52": "III",  # armazenagem, manuseio de cargas, estacionamento
    "53": "III",  # correio e outras atividades de entrega
    "55": "III",  # alojamento
    "56": "I",    # alimentação (preparo e venda ao consumidor)
    "61": "III",  # telecomunicações
    "77": "III",  # locação de bens móveis (sem cessão de mão de obra)
    "79": "III",  # agências de viagens e turismo
    "82": "III",  # serviços de escritório e apoio administrativo
    "85": "III",  # educação (ensino regular e cursos do item 8.02)
    "90": "III", "91": "III", "92": "III", "93": "III",
    "95": "III", "96": "III",
    # IV — construção civil, vigilância e limpeza (CPP fora do DAS)
    "41": "IV", "42": "IV", "43": "IV",
    "80": "IV", "81": "IV",
    # V — serviços intelectuais do §5º-C (sujeitos ao Fator "r")
    "58": "V",  # edição (jornalismo) e gravação (audiovisual)
    "59": "V",  # cinema, vídeo, rádio e TV
    "60": "V",  # edição, gravação e reprodução (sob encomenda)
    "62": "V",  # TI e software
    "63": "V",  # provedores de dados, hospedagem de conteúdo
    "64": "V",  # serviços financeiros
    "65": "V",  # seguros
    "66": "V",  # atividades auxiliares dos serviços financeiros
    "69": "V", "70": "V", "71": "V", "72": "V", "73": "V", "74": "V",
    "75": "V",
    "68": "V",  # imobiliárias (a corretagem é do V; locação própria é III)
    "86": "V", "87": "V", "88": "V",
}

# Exceção ao Anexo V: a locação/administração de imóveis próprios (68.10 e
# 68.22) é receita de aluguel e vai ao Anexo III; só a CORRETAGEM (68.21) é
# serviço intelectual do Anexo V (§5º-F da LC 123).
CLASSES_ANEXO_III = {
    "6810": "III",  # aluguel de imóveis próprios
    "6822": "III",  # gestão e administração da propriedade imobiliária
}

# Classes ambíguas na descrição. Mantidas em tabela explícita para não
# depender de heurística e permitir revisão jurídica direta.
CLASSES_AMBIGUAS = {
    # 18.13 é a antiga classe de serviços gráficos: ICMS (II) se a impressão
    # for destinada a comercialização/industrialização; ISS (III) se for para
    # terceiro (item 13.05 da LC 116).
    "1813": ("II", "III"),
    # 85.99: os cursos livres (item 8.02 da LC 116) podem ser tributados no
    # Anexo V pelo Fator "r"; a base é o Anexo III.
    "8599": ("III", "V"),
    # 56.11: restaurantes e lanchonetes vendem mercadoria (Anexo I) e prestam
    # serviço de preparo (Anexo III) no mesmo CNAE. Não há como decidir só
    # pelo código: o contribuinte separa as receitas.
    "5611": ("I", "III"),
    # 38.31/38.32/38.39: recuperação de materiais. Industrialização de
    # material próprio (compra, transforma e revende) -> II (ICMS); serviço de
    # recuperação prestado a terceiro -> III (item 14.xx da LC 116). A divisão
    # 38 sozinha diria "II", o que seria errado para o prestador de serviço.
    "3831": ("II", "III"),
    "3832": ("II", "III"),
    "3839": ("II", "III"),
}

# Serviços construídos, de limpeza e de vigilância (Anexo IV).
# Antes de checar a tabela/classes: um CNAE dessas divisões nunca vai para os
# anexos I, II, III ou V.
DIVISOES_ANEXO_IV = ("41", "42", "43", "80", "81")

# Divisões cujo enquadramento é EXCLUSIVAMENTE Anexo III (serviços comuns, não
# sujeitos ao Fator "r"): transporte, locação de bens móveis, academias,
# reparação/manutenção, beleza e cursos.
DIVISOES_EXCLUSIVO_III = (
    "49", "50", "51", "52", "53", "55", "56", "77", "79",
    "90", "91", "92", "93", "95", "96",
)

# Serviços que SÓ existem no Anexo V (não migram para o III) — art. 18, §5º-F
# (corretagem e administração de seguros/imóveis, corretagem de valores).
DIVISOES_EXCLUSIVO_V = ("64", "65", "66", "68")

# Classes de SERVIÇO que estão dentro de divisões de comércio/indústria
# (ex.: manutenção de veículos na divisão 45). Sempre Anexo III.
#
# Critério (LC 123/2006): mercadoria -> I, indústria -> II, serviço -> III/IV/V.
# O CNAE agrupa atividades por setor, NÃO por natureza do fato gerador: uma
# divisão "de comércio" contém classes de puro serviço. Estas entram AQUI e
# são resolvidas ANTES da tabela de divisões.
#
# Escopo restrito: apenas classes cuja descrição oficial é INEQUIVOCAMENTE de
# serviço (manutenção, reparação, instalação, coleta, tratamento e destinação
# de resíduos prestados a terceiro). Classes de natureza ambígua (ex.: 3831/
# 3832/3839 — recuperação de materiais, que pode ser industrialização própria)
# NÃO entram aqui: seguem a divisão e são desempatadas pelos gatilhos abaixo.
CLASSES_SERVICO = {
    # 33 — manutenção e instalação (divisão industrial)
    "3316": "III",  # manutenção e reparação de aeronaves
    "3321": "III",  # instalação de máquinas e equipamentos industriais
    "3329": "III",  # instalação de equipamentos não especificados
    # 38 — coleta, tratamento e destinação de resíduos (prestados a terceiro)
    "3811": "III",  # coleta de resíduos não perigosos
    "3812": "III",  # coleta de resíduos perigosos
    "3821": "III",  # tratamento e disposição de resíduos não perigosos
    "3822": "III",  # tratamento e disposição de resíduos perigosos
    "3900": "III",  # descontaminação e outros serviços de gestão de resíduos
    # 45 — manutenção e reparação de veículos (divisão de comércio)
    "4520": "III",  # manutenção e reparação de veículos automotores
    "4542": "III",  # manutenção e reparação de motocicletas
    "4543": "III",  # manutenção e reparação de triciclos/motonetas
}

# Classes de SERVIÇO dentro de divisões "de serviços", mas que na prática são
# COMÉRCIO (revenda de mercadoria) e por isso vão ao Anexo I.
CLASSES_COMERCIO = {
    "4541": "I",   # comércio de motocicletas e peças
}

# ---------------------------------------------------------------------------
# Item da LC 116/2003: serviço x mercadoria, por descrição (dentro das classes
# ambíguas). Usado SOMENTE para desempatar a classe, nunca para criar anexo.
# ---------------------------------------------------------------------------

# Construção (Anexo IV) e limpeza/vigilância (Anexo IV).
GATILHOS_ANEXO_IV = (
    "construcao", "construção", "obra", "obras", "edificacao", "edificação",
    "infraestrutura", "terraplenagem", "demolicao", "demolição", "alvenaria",
    "limpeza", "conservacao de imovel", "conservação de imóvel", "paisagismo",
    "jardinagem", "dedetizacao", "dedetização", "vigilancia", "vigilância",
    "monitoramento de bens", "escolta", "portaria",
)

# Indícios de ICMS (Anexo II) em classes ambíguas de indústria/serviço.
GATILHOS_ICMS = (
    "comercializacao", "industrializacao", "revenda",
    "destinado a posterior", "rotulo", "bula", "embalagem", "etiqueta",
    # recuperação/reciclagem de material próprio (38.31/38.32/38.39)
    "material proprio", "materiais proprios",
)

# Indícios de ISS (Anexo III) nas mesmas classes.
GATILHOS_ISS = ("servico", "para terceiro", "sob encomenda")


def _sem_acento(texto: str, colapsar: bool = False) -> str:
    texto = unicodedata.normalize("NFKD", str(texto or ""))
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = texto.lower()
    return " ".join(texto.split()) if colapsar else texto


def _digitos(codigo) -> str:
    return "".join(c for c in str(codigo or "") if c.isdigit())


def _tem(texto: str, palavras) -> bool:
    return any(_sem_acento(p) in texto for p in palavras)


def formatar_cnae(codigo: str) -> str:
    """Formata '4613300' em '4613-3/00' (mantém o que não for 7 dígitos)."""
    d = _digitos(codigo)
    if len(d) == 7:
        return f"{d[0:4]}-{d[4]}/{d[5:]}"
    return str(codigo or "").strip()


class MotorEnquadramento:
    """Motor de enquadramento baseado em CNAE (classe) + item da LC 116."""

    def __init__(self):
        self._cache: dict = {}

    # -- API pública -------------------------------------------------------

    def limpar_cache(self):
        """Descarta os enquadramentos memorizados.

        Precisa ser chamado sempre que a relação CNAE x Anexo (ou qualquer
        fonte consultada pelo motor) for alterada na aba Tabelas: o cache é
        por processo, então sem isso um CNAE já consultado continuaria
        exibindo o anexo antigo até o app ser reiniciado.
        """
        self._cache.clear()

    def candidatos(self, cnae: str, descricao: str = "") -> list:
        """Anexos legalmente possíveis, do mais provável ao menos provável."""
        tipo, anexos = self._enquadrar(cnae, descricao)
        unicos = []
        for a in anexos:
            if a and a not in unicos:
                unicos.append(a)
        return unicos

    def anexo_sugerido(self, cnae: str, descricao: str = "") -> Optional[str]:
        """Apenas o anexo principal (None quando o CNAE é inválido)."""
        anexos = self.candidatos(cnae, descricao)
        return anexos[0] if anexos else None

    def enquadrar(self, cnae: str, descricao: str = "") -> dict:
        """Anexo sugerido + metadados (compatível com cnaes.sugerir_anexo)."""
        tipo, anexos = self._enquadrar(cnae, descricao)
        if not anexos:
            return {
                "anexo": None,
                "descricao_grupo": "",
                "observacao": (
                    "CNAE ausente ou inválido: não é possível enquadrar "
                    "automaticamente. Informe o CNAE para obter a sugestão."
                ),
                "confianca": "baixa",
                "tipo_atividade": "",
                "anexos_candidatos": [],
            }
        anexos = self.candidatos(cnae, descricao)
        principal = anexos[0]
        return {
            "anexo": principal,
            "descricao_grupo": self._rotulo(tipo, principal),
            "observacao": self._observacao(tipo, anexos),
            "confianca": "alta" if len(anexos) == 1 else "media",
            "tipo_atividade": tipo,
            "anexos_candidatos": anexos,
        }

    def explicacao(self, cnae: str, descricao: str = "") -> dict:
        """Explicação técnica do enquadramento (base para explicacoes.explicar)."""
        tipo, anexos = self._enquadrar(cnae, descricao)
        if not anexos:
            return {
                "titulo": "CNAE ausente ou inválido",
                "resumo": ("Sem um CNAE de 7 dígitos não há enquadramento. "
                           "Informe o código oficial da atividade."),
                "anexos_candidatos": [],
                "fundamento": "LC 123/2006, art. 18, caput e Anexos I a V.",
            }
        anexos = self.candidatos(cnae, descricao)
        return {
            "titulo": self._rotulo(tipo, anexos[0]),
            "resumo": self._resumo(tipo, anexos),
            "anexos_candidatos": anexos,
            "fundamento": self._fundamento(tipo, anexos),
        }

    # -- Núcleo ------------------------------------------------------------

    def _enquadrar(self, cnae: str, descricao: str):
        d = _digitos(cnae)
        if len(d) != 7:
            return "", []
        texto = _sem_acento(descricao, colapsar=True)[:600]
        chave = (d[:4], texto)
        if chave in self._cache:
            return self._cache[chave]

        # 0) Relação CNAE x ANEXO mantida na aba Tabelas (banco) tem
        #    precedência sobre a regra fixa: corrigir um anexo lá vale na hora,
        #    sem republicar o app. Banco indisponível -> segue a regra fixa.
        gravado = self._da_tabela(d)
        if gravado is not None:
            resultado = gravado
        else:
            resultado = self._resolver(d[:4], d[:2], texto)

        self._cache[chave] = resultado
        return resultado

    def _da_tabela(self, cnae_7: str):
        """Anexo definido na tabela editável. None quando não houver linha."""
        try:
            from database import buscar_cnae_anexo
            import json as _json

            linha = buscar_cnae_anexo(cnae_7)
            if linha is None:
                return None
            try:
                anexos = _json.loads(linha["anexos"] or "[]")
            except Exception:  # noqa: BLE001
                anexos = []
            anexos = [a for a in anexos if a in ("I", "II", "III", "IV", "V")]
            if not anexos:
                # Linha existente sem anexo (extrativismo, administração
                # pública, doméstico): não é enquadrável no Simples.
                return "", []
            tipo = "indústria" if anexos[0] == "II" else "serviço"
            if anexos[0] == "I":
                tipo = "comércio"
            if "I" in anexos and "III" in anexos:
                tipo = "comércio e serviço"
            return tipo, anexos
        except Exception:  # noqa: BLE001 - motor nunca depende do Flask
            return None

    def _resolver(self, classe: str, divisao: str, texto: str):
        # ORDEM DE PREVALÊNCIA (LC 123/2006): a natureza do fato gerador vem
        # da CLASSE (atividade efetiva), não da divisão. A divisão do CNAE é
        # apenas um agrupamento setorial e contém serviços em divisões de
        # comércio/indústria. Por isso a classe decide primeiro.

        # 1) Serviços de construção, limpeza e vigilância (Anexo IV).
        if divisao in DIVISOES_ANEXO_IV:
            return "serviço", ["IV"]

        # 2) Classes de serviço em divisões de comércio/indústria (Anexo III).
        if classe in CLASSES_SERVICO:
            return "serviço", [CLASSES_SERVICO[classe]]

        # 3) Exceções dentro das divisões de serviços (ex.: locação de imóvel).
        if classe in CLASSES_ANEXO_III:
            return "serviço", [CLASSES_ANEXO_III[classe]]

        # 4) Classes que são comércio apesar de estar em divisão de serviços.
        if classe in CLASSES_COMERCIO:
            return "comércio", [CLASSES_COMERCIO[classe]]

        # Classe ambígua de indústria x serviço (ex.: 18.13 impressão).
        if classe in CLASSES_AMBIGUAS:
            anexos = list(CLASSES_AMBIGUAS[classe])
            # Os gatilhos de ICMS só fazem sentido quando o Anexo II está em
            # jogo (na divisão 56, "para comercialização" indicaria IV).
            if ("II" in anexos
                    and _tem(texto, GATILHOS_ICMS)
                    and not _tem(texto, GATILHOS_ISS)):
                anexos.sort(key=lambda a: a != "II")
            elif _tem(texto, GATILHOS_ISS) and not _tem(texto, GATILHOS_ICMS):
                anexos.sort(key=lambda a: a != "III")
            principal = anexos[0]
            tipo = "indústria" if principal == "II" else "serviço"
            if "I" in anexos:
                # Atividade mista (mercadoria + serviço): comércio e serviços.
                tipo = "comércio e serviço"
            return tipo, anexos

        base = TABELA_ANEXO.get(divisao)
        if base is None:
            return "", []

        # Anexo IV nunca combina com os demais.
        if base == "IV":
            return "serviço", ["IV"]

        # Serviços exclusivos do V (§5º-F): não migram para o III.
        if divisao in DIVISOES_EXCLUSIVO_V:
            return "serviço", ["V"]

        if base == "V":
            if divisao in DIVISOES_EXCLUSIVO_III or _tem(texto, GATILHOS_ANEXO_IV):
                return "serviço", ["III"]
            return "serviço", ["V", "III"]

        if base == "III":
            return "serviço", ["III"]

        if base == "II":
            return "indústria", ["II"]

        return "comércio", ["I"]

    # -- Textos ------------------------------------------------------------

    def _rotulo(self, tipo: str, anexo: str) -> str:
        nomes = {
            "I": "Comércio (revenda de mercadorias)",
            "II": "Indústria",
            "III": "Serviços gerais",
            "IV": "Serviços de construção civil/limpeza e vigilância",
            "V": "Serviços intelectuais (§5º-C da LC 123)",
        }
        return nomes.get(anexo, "")

    def _observacao(self, tipo: str, anexos: list) -> str:
        if anexos == ["IV"]:
            return ("Anexo IV: a CPP (patronal) é recolhida à parte e a regra "
                    "do Fator \"r\" não se aplica. ISS/ICMS conforme a atividade.")
        if anexos == ["III"]:
            return "Anexo III: não sujeito ao Fator \"r\"."
        if anexos == ["V"]:
            return ("Anexo V: sujeito ao Fator \"r\", mas sem migração para o "
                    "Anexo III (§5º-F da LC 123).")
        if anexos == ["II"]:
            return ("Anexo II: industrialização por conta própria ou serviço "
                    "industrial de utilidade pública (tributação pelo ICMS).")
        if anexos == ["I"]:
            return "Anexo I: revenda de mercadorias."
        if "V" in anexos and "III" in anexos:
            return ("Anexo III ou V: depende do Fator \"r\" (folha de salários "
                    ">= 28% da RBT12 leva ao Anexo III).")
        if "I" in anexos and "III" in anexos:
            return ("Anexo I para a receita de revenda de mercadorias e Anexo III "
                    "para a receita de serviço (LC 116/2003): o contribuinte "
                    "segrega as receitas.")
        if "II" in anexos and "III" in anexos:
            return ("Anexo II ou III: depende do destino do serviço/produto "
                    "(ISS x ICMS).")
        return ""

    def _resumo(self, tipo: str, anexos: list) -> str:
        if len(anexos) == 1:
            return f"A atividade ({tipo}) é enquadrada no Anexo {anexos[0]}."
        if "V" in anexos and "III" in anexos:
            return (f"A atividade ({tipo}) está sujeita ao Fator \"r\" "
                    "(LC 123/2006): Anexo V quando o Fator \"r\" for inferior a "
                    "28% e Anexo III quando for igual ou superior.")
        if "II" in anexos and "III" in anexos:
            return (f"A atividade ({tipo}) pode ser tributada pelo ICMS/ISS "
                    "conforme o item da LC 116 aplicável à operação concreta.")
        if "I" in anexos and "III" in anexos:
            return (f"A atividade ({tipo}) tem receita mista: revenda de "
                    "mercadorias (Anexo I) e prestação de serviço (Anexo III), "
                    "com segregação de receitas.")
        return f"A atividade ({tipo}) admite os seguintes anexos: " + \
            ", ".join(f"Anexo {a}" for a in anexos) + "."

    def _fundamento(self, tipo: str, anexos: list) -> str:
        if anexos == ["IV"]:
            return ("LC 123/2006, art. 18, §5º-C e §5º-I (Anexo IV) e Anexo IV "
                    "da referida lei: CPP recolhida separadamente.")
        if "V" in anexos:
            return ("LC 123/2006, art. 18, §5º-C a §5º-H e §5º-D (Fator \"r\"): "
                    "Anexo V quando o Fator \"r\" < 28%; Anexo III quando >= 28%.")
        if "I" in anexos:
            return ("LC 123/2006, art. 18, §§4º-A e 4º-B e Anexos I e III "
                    "(receitas segregadas por tipo: mercadoria x serviço).")
        if "II" in anexos:
            return "LC 123/2006, art. 18, §5º-A e Anexo II (ICMS)."
        if anexos == ["III"]:
            return "LC 123/2006, Anexo III (ISS/ICMS)."
        return "LC 123/2006, Anexo I (comércio)."


MOTOR = MotorEnquadramento()


# ---------------------------------------------------------------------------
# Helpers de compatibilidade (mantidos em cnaes.py por causa dos imports)
# ---------------------------------------------------------------------------

def apenas_digitos(codigo: str) -> str:
    return _digitos(codigo)


def normalizar(texto: str) -> str:
    return _sem_acento(texto)


def formatar(codigo: str) -> str:
    return formatar_cnae(codigo)
