"""
Base de CNAEs e regras de enquadramento no Simples Nacional.

Objetivo: permitir que, ao cadastrar a empresa, o usuário informe o CNAE
principal e o sistema sugira automaticamente o Anexo do Simples Nacional
(I, II, III, IV ou V) aplicável à atividade.

Observações importantes (não substituem a análise de um contador):
  - O enquadramento depende do CNAE principal E das atividades secundárias,
    do faturamento e de fatores como folha de salários e ISS/ICMS.
  - Serviços do Anexo IV e V não têm CST/CSOSN como os demais; e o Anexo V
    depende do fator R = folha 12m / RBT12 (>= 28% migra para o Anexo III).
  - Este módulo trabalha por heurística de palavras-chave sobre a descrição
    do CNAE, o que cobre a grande maioria dos casos práticos.

Estrutura:
  GRUPOS_CNAE -> lista de grupos com faixa de código, palavras-chave e anexo.
  sugerir_anexo() -> função principal de enquadramento por CNAE.
"""

from __future__ import annotations

from typing import Optional

# ---------------------------------------------------------------------------
# Palavras-chave de apoio
# ---------------------------------------------------------------------------

# Palavras que indicam comércio (Anexo I) mesmo quando o código é 47xx.
_PALAVRAS_COMERCIO = (
    "comercio", "comércio", "loja", "mercado", "mercearia", "venda", "varejo",
    "revenda", "papelaria", "farmácia", "farmacia", "supermercado", "magazine",
    "boutique", "autopecas", "autopeças", "material de construcao",
    "material de construção", "livraria", "floricultura", "otic", "ótic",
    "joalheria", "bicicleta", "vestuario", "vestuário", "calcados", "calçados",
    "eletrodomesticos", "eletrodomésticos", "inflamaveis", "inflamáveis",
)

# Palavras que indicam indústria / industrialização (Anexo II).
_PALAVRAS_INDUSTRIA = (
    "fabricacao", "fabricação", "fabrica", "fábrica", "industria", "indústria",
    "industrializacao", "industrialização", "producao", "produção", "confecao",
    "confecção", "beneficiamento", "montagem de", "usinagem", "solda",
    "metalurgia", "marcenaria", "panificacao", "panificação", "abate",
    "laticinio", "laticínio", "alimentos", "mobiliario", "mobiliário",
)

# Palavras que indicam prestação de serviços (Anexo III ou V, conforme fator R).
_PALAVRAS_SERVICOS = (
    "servico", "serviço", "servicos", "serviços", "assessoria", "consultoria",
    "contabilidade", "contabil", "contábil", "advocacia", "advogado",
    "engenharia", "arquitetura", "publicidade", "propaganda", "marketing",
    "informatica", "informática", "software", "desenvolvimento de",
    "manutencao", "manutenção", "reparacao", "reparação", "instalacao",
    "instalação", "treinamento", "ensino", "educacao", "educação", "escola",
    "clinica", "clínica", "medicina", "odontologia", "odontológic",
    "veterinaria", "veterinária", "fisioterapia", "nutricao", "nutrição",
    "psicologia", "laboratorio", "laboratório", "analises", "análises",
    "academia", "fitness", "estetica", "estética", "barbearia", "cabeleireiro",
    "transporte", "fretamento", "taxis", "táxi", "hotelaria", "hospedagem",
    "turismo", "agenciamento", "representacao", "representação", "locacao",
    "locação", "seguros", "corretagem", "auditoria", "gestao", "gestão",
)

# Serviços que tipicamente vão para o Anexo V (sujeitos ao fator R).
_PALAVRAS_ANEXO_V = (
    "auditoria", "jornalismo", "publicidade", "propaganda", "engenharia",
    "arquitetura", "medicina", "odontologia", "advocacia", "contabilidade",
    "consultoria", "assessoria", "programacao", "programação", "software",
    "desenvolvimento de sistemas", "design", "treinamento", "ensino",
    "representacao comercial", "representação comercial", "corretagem",
    "gestao", "gestão", "marketing", "fisioterapia", "nutricao", "nutrição",
    "psicologia", "veterinaria", "veterinária", "enfermagem", "farmácia",
    "analises clinicas", "análises clínicas", "laboratorio", "laboratório",
)

# Serviços que vão para o Anexo IV (tributação separada de ISS/ICMS/CPP).
_PALAVRAS_ANEXO_IV = (
    "construcao civil", "construção civil", "obra", "obras", "reforma",
    "demolicao", "demolição", "terraplenagem", "pintura de", "instalacao de",
    "instalação de", "limpeza", "conservacao", "conservação", "vigilancia",
    "vigilância", "seguranca patrimonial", "segurança patrimonial", "controle de pragas",
    "dedetizacao", "dedetização", "paisagismo", "jardinagem",
)

# Serviços que permanecem no Anexo III mesmo contendo palavras típicas do V.
# Ex.: "treinamento" (educação) e "manutencao" (reparação) são Anexo III.
_PALAVRAS_ANEXO_III_FORTE = (
    "ensino", "educacao", "educação", "escola", "curso", "treinamento",
    "pre-escola", "pré-escola", "universidade", "idioma", "reparacao",
    "reparação", "manutencao", "manutenção", "conserto", "restaurante",
    "lanchonete", "padaria", "academia", "fitness", "transporte",
    "locacao", "locação", "aluguel", "estacionamento", "hotel", "hospedagem",
    "fisioterapia", "estetica", "estética", "barbearia", "cabeleireiro",
)


# ---------------------------------------------------------------------------
# Grupos de CNAE -> Anexo sugerido
# ---------------------------------------------------------------------------
# 'prefixos' identifica divisões/grupos da CNAE (2 a 4 dígitos).
# 'palavras' refina o enquadramento dentro do grupo.
# 'prioridade' desempata: quanto maior, mais forte a sugestão.

GRUPOS_CNAE = [
    {
        "descricao": "Agricultura, pecuária, pesca e extrativismo",
        "prefixos": ("01", "02", "03", "05"),
        "palavras": ("cultivo", "agricultura", "pecuaria", "pecuária", "criacao",
                     "criação", "pesca", "extracao", "extração", "silvicultura",
                     "horticultura", "fruticultura"),
        "anexo": "I",
        "prioridade": 40,
        "observacao": "Comércio/industrialização de produção própria costuma enquadrar no Anexo I.",
    },
    {
        "descricao": "Indústria de alimentos, bebidas e fumo",
        "prefixos": ("10", "11", "12"),
        "palavras": ("fabricacao", "fabricação", "abate", "laticinio", "laticínio",
                     "panificacao", "panificação", "usina", "bebida", "moagem"),
        "anexo": "II",
        "prioridade": 60,
        "observacao": "Industrialização por conta própria -> Anexo II.",
    },
    {
        "descricao": "Indústria têxtil, vestuário, couro e calçados",
        "prefixos": ("13", "14", "15"),
        "palavras": ("fabricacao", "fabricação", "confecao", "confecção",
                     "beneficiamento", "tecelagem", "fiacao", "fiação", "curtume"),
        "anexo": "II",
        "prioridade": 60,
        "observacao": "Industrialização por conta própria -> Anexo II.",
    },
    {
        "descricao": "Indústria de madeira, papel, celulose e mobiliário",
        "prefixos": ("16", "17", "18", "31"),
        "palavras": ("fabricacao", "fabricação", "serraria", "marcenaria",
                     "moveis", "móveis", "celulose", "beneficiamento"),
        "anexo": "II",
        "prioridade": 60,
        "observacao": "Marcenaria com fabricação própria -> Anexo II.",
    },
    {
        "descricao": "Indústria química, farmacêutica, borracha, plástico e metalurgia",
        "prefixos": ("19", "20", "21", "22", "23", "24", "25", "26", "27", "28", "29", "30"),
        "palavras": ("fabricacao", "fabricação", "refino", "metalurgia",
                     "usinagem", "fundicao", "fundição", "solda", "estamparia"),
        "anexo": "II",
        "prioridade": 60,
        "observacao": "Industrialização -> Anexo II. Revenda de terceiros pode ser Anexo I.",
    },
    {
        "descricao": "Eletricidade, água, esgoto e coleta de resíduos",
        "prefixos": ("35", "36", "37", "38"),
        "palavras": ("energia", "agua", "água", "esgoto", "residuos", "resíduos",
                     "coleta", "tratamento", "saneamento"),
        "anexo": "II",
        "prioridade": 45,
        "observacao": "Serviços industriais de utilidade pública -> Anexo II.",
    },
    {
        "descricao": "Construção civil e obras",
        "prefixos": ("41", "42", "43"),
        "palavras": ("construcao", "construção", "obra", "edificacao", "edificação",
                     "infraestrutura", "demolicao", "demolição", "instalacao",
                     "instalação", "eletrica", "elétrica", "hidraulica", "hidráulica",
                     "acabamento", "reforma", "pintura"),
        "anexo": "IV",
        "prioridade": 70,
        "observacao": "Construção civil -> Anexo IV (tributos separados, CPP fora do DAS).",
    },
    {
        "descricao": "Comércio de veículos e peças",
        "prefixos": ("45",),
        "palavras": ("comercio", "comércio", "revenda", "pecas", "peças",
                     "autopecas", "autopeças", "concessionaria", "concessionária",
                     "motociclet", "venda"),
        "anexo": "I",
        "prioridade": 55,
        "observacao": "Revenda de mercadorias -> Anexo I. Manutenção e reparação de "
                      "veículos (45.20-0) são serviços -> Anexo III.",
    },
    {
        "descricao": "Comércio por atacado",
        "prefixos": ("46",),
        "palavras": ("atacado", "atacadista", "comercio", "comércio", "distribuicao",
                     "distribuição", "revenda"),
        "anexo": "I",
        "prioridade": 55,
        "observacao": "Comércio atacadista -> Anexo I.",
    },
    {
        "descricao": "Comércio varejista",
        "prefixos": ("47",),
        "palavras": _PALAVRAS_COMERCIO,
        "anexo": "I",
        "prioridade": 55,
        "observacao": "Comércio varejista -> Anexo I. Se produzir o que vende, avaliar Anexo II.",
    },
    {
        "descricao": "Transporte terrestre de passageiros e fretamento",
        "prefixos": ("49",),
        "palavras": ("passageiro", "fretamento", "taxi", "táxi", "onibus", "ônibus",
                     "van", "escolar", "coletivo", "transporte de passageiro"),
        "anexo": "III",
        "prioridade": 65,
        "observacao": "Transporte de passageiros -> Anexo III (pode ir ao V pelo fator R).",
    },
    {
        "descricao": "Transporte de cargas",
        "prefixos": ("49",),
        "palavras": ("carga", "cargueiro", "mudanca", "mudança", "frete", "transporte de carga"),
        "anexo": "III",
        "prioridade": 65,
        "observacao": "Transporte de cargas -> Anexo III (fator R pode elevar ao V).",
    },
    {
        "descricao": "Armazenamento e atividades auxiliares dos transportes",
        "prefixos": ("52",),
        "palavras": ("armazenamento", "deposito", "depósito", "logistica", "logística",
                     "estacionamento", "movimentacao", "movimentação"),
        "anexo": "III",
        "prioridade": 45,
        "observacao": "Atividade auxiliar de transporte -> Anexo III.",
    },
    {
        "descricao": "Alimentação: restaurantes, bares, lanchonetes e similares",
        "prefixos": ("56",),
        "palavras": ("restaurante", "lanchonete", "bar", "bar", "cafe", "café",
                     "pizzaria", "hamburgueria", "churrascaria", "alimentacao",
                     "alimentação", "confeitaria", "padaria", "food", "delivery",
                     "fornecimento de alimentos", "marmita", "panqueca"),
        "anexo": "I",
        "prioridade": 75,
        "observacao": "Restaurantes e similares -> Anexo I (CNAE 56.11-2 e correlatos).",
    },
    {
        "descricao": "Edição, gravação, rádio e TV",
        "prefixos": ("58", "59", "60"),
        "palavras": ("edicao", "edição", "gravacao", "gravação", "radio", "rádio",
                     "televisao", "televisão", "musica", "música", "filme", "streaming"),
        "anexo": "V",
        "prioridade": 55,
        "observacao": "Produção audiovisual -> Anexo V (fator R pode mover para III).",
    },
    {
        "descricao": "Telecomunicações",
        "prefixos": ("61",),
        "palavras": ("telecomunicacao", "telecomunicação", "telefonia", "internet",
                     "provedor", "comunicacao", "comunicação"),
        "anexo": "III",
        "prioridade": 50,
        "observacao": "Telecomunicações -> Anexo III.",
    },
    {
        "descricao": "Tecnologia da informação e software",
        "prefixos": ("62", "63"),
        "palavras": ("software", "programa", "sistema", "ti", "informatica",
                     "informática", "dados", "hospedagem", "suporte tecnico",
                     "suporte técnico", "desenvolvimento", "web", "app"),
        "anexo": "V",
        "prioridade": 70,
        "observacao": "TI e software -> Anexo V, mas com folha >= 28% da RBT12 vão para o Anexo III.",
    },
    {
        "descricao": "Serviços financeiros, seguros e imobiliários",
        "prefixos": ("64", "65", "66", "68"),
        "palavras": ("financeir", "seguro", "corretora", "corretagem", "imobiliaria",
                     "imobiliária", "incorporacao", "incorporação", "arrendamento",
                     "administracao de bens", "administração de bens", "condominio",
                     "condomínio", "locacao", "locação", "aluguel"),
        "anexo": "III",
        "prioridade": 45,
        "observacao": "Administração de imóveis -> Anexo III. Corretagem pode ir ao V.",
    },
    {
        "descricao": "Serviços profissionais, científicos e técnicos",
        "prefixos": ("69", "70", "71", "72", "73", "74", "75"),
        "palavras": ("advocacia", "advogado", "contabilidade", "contabil", "contábil",
                     "auditoria", "consultoria", "assessoria", "engenharia", "arquitetura",
                     "publicidade", "propaganda", "marketing", "design", "pesquisa",
                     "veterinaria", "veterinária", "laboratorio", "laboratório",
                     "medicina", "odontologia", "psicologia", "nutricao", "nutrição",
                     "fisioterapia", "analises", "análises", "diagnostico", "diagnóstico"),
        "anexo": "V",
        "prioridade": 70,
        "observacao": "Serviços intelectuais -> Anexo V; com folha >= 28% da RBT12, Anexo III.",
    },
    {
        "descricao": "Locação de máquinas, equipamentos e objetos pessoais",
        "prefixos": ("77",),
        "palavras": ("locacao", "locação", "aluguel", "arrendamento de maquinas",
                     "arrendamento de máquinas", "equipamento"),
        "anexo": "III",
        "prioridade": 45,
        "observacao": "Locação de bens móveis (sem cessão de mão de obra) -> Anexo III.",
    },
    {
        "descricao": "Vigilância, segurança e investigação",
        "prefixos": ("80",),
        "palavras": ("vigilancia", "vigilância", "seguranca", "segurança",
                     "patrimonial", "monitoramento", "escolta", "investigacao",
                     "investigação", "rastreamento"),
        "anexo": "IV",
        "prioridade": 80,
        "observacao": "Vigilância e segurança patrimonial -> Anexo IV.",
    },
    {
        "descricao": "Limpeza, conservação, paisagismo e apoio a edifícios",
        "prefixos": ("81",),
        "palavras": ("limpeza", "conservacao", "conservação", "paisagismo",
                     "jardinagem", "dedetizacao", "dedetização", "desinsetizacao",
                     "desinsetização", "portaria", "condominio", "condomínio",
                     "zeladoria", "manutencao de jardim", "manutenção de jardim"),
        "anexo": "IV",
        "prioridade": 80,
        "observacao": "Limpeza, conservação e similares -> Anexo IV (CPP fora do DAS).",
    },
    {
        "descricao": "Ensino, treinamento e educação",
        "prefixos": ("85",),
        "palavras": ("ensino", "educacao", "educação", "escola", "curso",
                     "treinamento", "pre-escola", "pré-escola", "universidade",
                     "idioma", "musica", "música", "dança", "danca"),
        "anexo": "III",
        "prioridade": 55,
        "observacao": "Educação -> Anexo III (franquias/regulamentados podem ir ao V).",
    },
    {
        "descricao": "Saúde humana, veterinária e serviços sociais",
        "prefixos": ("86", "87", "88"),
        "palavras": ("clinica", "clínica", "medicina", "medico", "médico",
                     "odontolog", "dentista", "veterinaria", "veterinária",
                     "fisioterapia", "enfermagem", "nutricao", "nutrição",
                     "psicologia", "assistencia social", "assistência social",
                     "laboratorio", "laboratório", "hospital"),
        "anexo": "V",
        "prioridade": 70,
        "observacao": "Saúde e serviços sociais -> Anexo V; com folha >= 28% da RBT12, Anexo III.",
    },
    {
        "descricao": "Artes, cultura, esporte e lazer",
        "prefixos": ("90", "91", "92", "93"),
        "palavras": ("arte", "cultura", "esporte", "lazer", "academia", "fitness",
                     "ginasio", "ginásio", "clube", "biblioteca", "museu",
                     "espetaculo", "espetáculo", "musica", "música", "danca", "dança",
                     "natacao", "natação", "jogos"),
        "anexo": "III",
        "prioridade": 50,
        "observacao": "Academias e atividades esportivas -> Anexo III.",
    },
    {
        "descricao": "Reparação, manutenção e serviços pessoais",
        "prefixos": ("95", "96"),
        "palavras": ("reparacao", "reparação", "manutencao", "manutenção", "conserto",
                     "reforma de", "barbearia", "cabeleireiro", "estetica", "estética",
                     "manicure", "salao", "salão", "lavanderia", "petshop", "pet shop",
                     "banho e tosa", "costura", "sapateiro", "chaveiro", "eletronica",
                     "eletrônica", "celular", "computador", "maquina", "máquina"),
        "anexo": "III",
        "prioridade": 55,
        "observacao": "Reparação/manutenção e beleza -> Anexo III (pode ir ao V pelo fator R).",
    },
]


# ---------------------------------------------------------------------------
# Funções auxiliares
# ---------------------------------------------------------------------------

def apenas_digitos(codigo: str) -> str:
    """Remove pontos, traços e barras de um CNAE. Ex: '47.11-3/02' -> '4711302'."""
    return "".join(ch for ch in str(codigo or "") if ch.isdigit())


def formatar_cnae(codigo: str) -> str:
    """
    Formata um CNAE no padrão 0000-0/00.
    Aceita '4711302', '47.11-3/02' ou '4711-3/02'.
    """
    d = apenas_digitos(codigo)
    if len(d) == 7:
        return f"{d[0:4]}-{d[4]}/{(d[5:7]).zfill(2)}"
    return str(codigo or "").strip()


def normalizar(texto: str) -> str:
    """Minúsculas e sem acentos, para comparação tolerante de palavras-chave."""
    if not texto:
        return ""
    tabela = str.maketrans(
        "áàâãäéèêëíìîïóòôõöúùûüçñÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇÑ",
        "aaaaaeeeeiiiiooooouuuucnaaaaaeeeeiiiiooooouuuucn",
    )
    return texto.translate(tabela).lower()


def sugerir_anexo(cnae: str, descricao: str = "") -> dict:
    """
    Sugere o Anexo do Simples Nacional a partir do CNAE e/ou da descrição.

    Retorna um dicionário com:
      anexo          -> 'I', 'II', 'III', 'IV' ou 'V' (ou None se indefinido)
      descricao_grupo-> descrição do grupo identificado
      observacao     -> ressalvas relevantes
      confianca      -> 'alta', 'media' ou 'baixa'
    """
    digitos = apenas_digitos(cnae)
    texto = normalizar(descricao)
    prefixo4 = digitos[:4]
    prefixo2 = digitos[:2]

    melhor = None
    melhor_score = -1

    # Serviços de reparação/manutenção de veículos ficam no grupo 45 (comércio),
    # mas são Anexo III. Trata antes da lógica geral para evitar conflito.
    if digitos.startswith("452") or digitos.startswith("453"):
        return {
            "anexo": "III",
            "descricao_grupo": "Reparação e manutenção de veículos",
            "observacao": "Manutenção e reparação de veículos -> Anexo III "
                          "(serviço, e não revenda de mercadoria).",
            "confianca": "alta",
        }

    for grupo in GRUPOS_CNAE:
        score = 0

        # Casamento por prefixo do CNAE (mais forte).
        for p in grupo["prefixos"]:
            if digitos.startswith(p):
                score += 50 + len(p)
                break

        # Casamento por palavra-chave na descrição ou no próprio texto do CNAE.
        alvo = normalizar(descricao) + " " + normalizar(cnae)
        for palavra in grupo.get("palavras", ()):
            if palavra and normalizar(palavra) in alvo:
                score += 30
                break

        # Desempate por prioridade do grupo.
        if score > 0:
            score += grupo.get("prioridade", 0) / 10.0

        if score > melhor_score:
            melhor_score = score
            melhor = grupo

    if melhor is None or melhor_score <= 0:
        # Segunda tentativa: só por palavras-chave, sem CNAE válido.
        alvo = normalizar(descricao)
        for grupo in GRUPOS_CNAE:
            for palavra in grupo.get("palavras", ()):
                if palavra and normalizar(palavra) in alvo:
                    anexo = _refinar_servico(grupo["anexo"], alvo)
                    return {
                        "anexo": anexo,
                        "descricao_grupo": grupo["descricao"],
                        "observacao": grupo.get("observacao", ""),
                        "confianca": "media",
                    }
        return {
            "anexo": None,
            "descricao_grupo": "",
            "observacao": "Não foi possível enquadrar automaticamente. "
                          "Confirme o CNAE ou informe a descrição da atividade.",
            "confianca": "baixa",
        }

    anexo = _refinar_servico(melhor["anexo"], normalizar(descricao))
    confianca = "alta" if melhor_score >= 55 else "media"

    return {
        "anexo": anexo,
        "descricao_grupo": melhor["descricao"],
        "observacao": melhor.get("observacao", ""),
        "confianca": confianca,
    }


def _refinar_servico(anexo: str, texto_normalizado: str) -> str:
    """
    Ajusta o Anexo III/IV/V de acordo com palavras-chave adicionais.

    - Construção, vigilância e limpeza -> Anexo IV.
    - Serviços intelectuais -> Anexo V.
    - Educação, reparação, transporte, locação e academias -> Anexo III
      (têm precedência sobre "treinamento"/"manutenção" do Anexo V).
    """
    if anexo not in ("III", "V"):
        return anexo

    # Atividades do Anexo IV têm precedência.
    for palavra in _PALAVRAS_ANEXO_IV:
        if normalizar(palavra) in texto_normalizado:
            return "IV"

    # Serviços que são Anexo III mesmo contendo palavras típicas do Anexo V
    # (ex.: "treinamento" em educação, "manutenção" em reparação).
    for palavra in _PALAVRAS_ANEXO_III_FORTE:
        if normalizar(palavra) in texto_normalizado:
            return "III"

    for palavra in _PALAVRAS_ANEXO_V:
        if normalizar(palavra) in texto_normalizado:
            return "V"

    return anexo


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
    Retorna dicionário com o valor do fator, o anexo resultante e a alíquota
    de corte usada (28%).
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
    """Lista simplificada dos grupos cadastrados (para consulta na interface)."""
    return [
        {
            "descricao": g["descricao"],
            "prefixos": list(g["prefixos"]),
            "anexo": g["anexo"],
            "observacao": g.get("observacao", ""),
        }
        for g in GRUPOS_CNAE
    ]


ANEXOS_SIMPLES = ["I", "II", "III", "IV", "V"]
