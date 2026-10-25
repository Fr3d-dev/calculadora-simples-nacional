"""
Explicações do enquadramento de CNAEs no Simples Nacional.

Objetivo: dar suporte ao botão "Ver explicação" do cadastro de empresas. Para
cada CNAE, mostra *por que* ele cai em determinado Anexo — incluindo o item da
LC 116/2003 (ISS) quando aplicável, e o motivo de um serviço migrar para o
ICMS/ Anexo II.

Estrutura principal:
  EXPLICACOES_CNAE -> base curada por prefixo de CNAE (chave sem pontuação).
  explicar()       -> devolve a explicação (curada ou genérica) de um CNAE.

Regra de ouro reproduzida aqui: o ENQUADRAMENTO depende de COMO a atividade é
explorada, não só do código. Ex.: impressão para terceiro (ISS, item 13.05)
x impressão de rótulos/embalagens destinados a posterior comercialização ou
industrialização (ICMS, Anexo II).

Este módulo é ADITIVO: não altera sugerir_anexo()/anexos_candidatos().
"""

from __future__ import annotations

import re
from typing import Optional

import cnaes
from cnae_item_lc116 import CNAE_ITEM, ITEM_DESCRICAO
from enquadramento import MOTOR
from itens_lc116 import ITENS_LC116


_KB = None  # cache do banco de conhecimento (itens da LC 116)


# ---------------------------------------------------------------------------
# Base curada de explicações
# ---------------------------------------------------------------------------
# Chave: prefixo do CNAE (só dígitos). Casamento "startswith", do mais
# específico (mais dígitos) para o mais genérico.
#
# Cada item pode conter:
#   titulo          -> título curto do grupo
#   resumo          -> explicação principal (texto)
#   itens_lc116     -> lista de dicts com o detalhamento por item da LC 116:
#                        {"item", "descricao", "tributo", "anexo"}
#   fundamento      -> base legal / observação final
#   palavras_icms   -> palavras que fazem a atividade migrar para ICMS/II
#   palavras_iss    -> palavras que mantêm a atividade no ISS/III

EXPLICACOES_CNAE: list[dict] = [
    {
        "prefixos": ("1813", "1830", "1824"),
        "titulo": "Impressão e reprodução gráfica",
        "resumo": (
            "A impressão é uma atividade de \"dupla face\": pode prestar SERVIÇO "
            "(ISS, Anexo III) ou fornecer MERCADORIA (ICMS, Anexo II), conforme o "
            "destino do material impresso. O item 13.05 da LC 116/2003 é quem "
            "dita a fronteira."
        ),
        "itens_lc116": [
            {
                "item": "13.05",
                "descricao": (
                    "Impressão para terceiro (não vai para posterior "
                    "comercialização ou industrialização)"
                ),
                "tributo": "ISS",
                "anexo": "Anexo III",
            },
            {
                "item": "13.05 (parte final)",
                "descricao": (
                    "Impressão destinada a posterior comercialização ou "
                    "industrialização (rótulos, bulas, embalagens, caixas… que "
                    "serão revendidos ou incorporados a mercadoria) — \"sujeitos "
                    "ao ICMS\""
                ),
                "tributo": "ICMS",
                "anexo": "Anexo II",
            },
            {
                "item": "13.04",
                "descricao": "Cópia, reprografia e digitalização",
                "tributo": "ISS",
                "anexo": "Anexo III",
            },
        ],
        "palavras_icms": (
            "rotulo", "rótulo", "bula", "embalagem", "caixa", "cartucho",
            "etiqueta", "comercializacao", "comercialização", "industrializacao",
            "industrialização", "revenda", "incorporado a mercadoria",
        ),
        "palavras_iss": (
            "para terceiro", "a terceiro", "sob encomenda", "grafica", "gráfica",
            "reprografia", "fotocopia", "fotocópia", "digitalizacao",
            "digitalização", "copia", "cópia", "impressao de documentos",
            "impressão de documentos",
        ),
        "fundamento": (
            "Item 13.05 da LC 116/2003. Veja também o Anexo II (indústria) e o "
            "Anexo III (serviços gerais) da LC 123/2006."
        ),
    },
    {
        "prefixos": ("452", "453"),
        "titulo": "Reparação e manutenção de veículos",
        "resumo": (
            "Manutenção e reparação de veículos é SERVIÇO (Anexo III), mesmo o "
            "CNAE pertencendo à divisão 45 (comércio). O que define é a atividade "
            "executada, não o capítulo do Código."
        ),
        "itens_lc116": [
            {
                "item": "14.01",
                "descricao": "Lubrificação, limpeza, revisão, conserto, restauração e manutenção de veículos automotores (não próprios)",
                "tributo": "ISS",
                "anexo": "Anexo III",
            },
            {
                "item": "14.02",
                "descricao": "Manutenção e conservação de máquinas, veículos, aparelhos, equipamentos e instalações (exceto se em conjunto com a atividade-fim)",
                "tributo": "ISS",
                "anexo": "Anexo III",
            },
        ],
        "palavras_icms": ("revenda de veiculo", "revenda de veículo", "comercio de pecas",
                          "comércio de peças", "pecas", "peças"),
        "palavras_iss": ("manutencao", "manutenção", "reparacao", "reparação",
                         "conserto", "servico", "serviço"),
        "fundamento": (
            "Itens 14.01 e 14.02 da LC 116/2003 (manutenção e reparação). "
            "Serviço -> Anexo III; revenda de peças/veículos acompanha o Anexo I (comércio)."
        ),
    },
    {
        "prefixos": ("620", "631"),
        "titulo": "Tecnologia da informação e software",
        "resumo": (
            "Desenvolvimento de software e TI -> Anexo V (serviços intelectuais), "
            "sujeito ao fator R. Se a folha de salários atingir 28% da RBT12, a "
            "atividade migra para o Anexo III."
        ),
        "itens_lc116": [
            {
                "item": "1.01",
                "descricao": "Análise e desenvolvimento de sistemas",
                "tributo": "ISS",
                "anexo": "Anexo III/V",
            },
            {
                "item": "1.02",
                "descricao": "Programação (inclusive de jogos eletrônicos)",
                "tributo": "ISS",
                "anexo": "Anexo III/V",
            },
            {
                "item": "1.03",
                "descricao": "Processamento, armazenamento ou hospedagem de dados, textos, imagens, vídeos e páginas eletrônicas",
                "tributo": "ISS",
                "anexo": "Anexo III/V",
            },
            {
                "item": "1.04",
                "descricao": "Elaboração de programas de computadores, inclusive de jogos eletrônicos",
                "tributo": "ISS",
                "anexo": "Anexo III/V",
            },
            {
                "item": "1.05",
                "descricao": "Licenciamento ou cessão de direito de uso de programas de computação",
                "tributo": "ISS",
                "anexo": "Anexo III/V",
            },
            {
                "item": "1.06",
                "descricao": "Assessoria e consultoria em informática",
                "tributo": "ISS",
                "anexo": "Anexo III/V",
            },
            {
                "item": "1.07",
                "descricao": "Suporte técnico em informática, inclusive instalação, configuração e manutenção de programas de computação e bancos de dados",
                "tributo": "ISS",
                "anexo": "Anexo III/V",
            },
            {
                "item": "1.08",
                "descricao": "Planejamento, confecção, manutenção e atualização de páginas eletrônicas",
                "tributo": "ISS",
                "anexo": "Anexo III/V",
            },
        ],
        "palavras_iss": ("software", "programa", "sistema", "desenvolvimento",
                         "ti", "informatica", "informática"),
        "fundamento": (
            "Itens 1.01 a 1.08 da LC 116/2003. Anexos III e V da LC 123/2006 + "
            "fator R (folha ÷ RBT12 ≥ 28% -> Anexo III)."
        ),
    },
    {
        "prefixos": ("86",),
        "exceto": ("8640", "8650", "8660", "8690"),
        "titulo": "Saúde (consultórios, clínicas e laboratórios)",
        "resumo": (
            "Serviços de saúde se enquadram no Anexo V (intelectual) ou Anexo III, "
            "conforme o fator R. Representa o caso clássico de oscilação V<->III "
            "ano a ano."
        ),
        "itens_lc116": [
            {
                "item": "4.01",
                "descricao": "Medicina e biomedicina",
                "tributo": "ISS",
                "anexo": "Anexo V/III",
            },
            {
                "item": "4.02",
                "descricao": "Análises clínicas, patologia, eletricidade médica, radioterapia, quimioterapia, ultrassonografia e outros procedimentos",
                "tributo": "ISS",
                "anexo": "Anexo V/III",
            },
            {
                "item": "4.03",
                "descricao": "Hospitais, clínicas e laboratórios",
                "tributo": "ISS",
                "anexo": "Anexo V/III",
            },
            {
                "item": "4.04",
                "descricao": "Instrumentação cirúrgica",
                "tributo": "ISS",
                "anexo": "Anexo V/III",
            },
            {
                "item": "4.05",
                "descricao": "Enfermagem, inclusive serviços auxiliares",
                "tributo": "ISS",
                "anexo": "Anexo V/III",
            },
            {
                "item": "4.06",
                "descricao": "Odontologia",
                "tributo": "ISS",
                "anexo": "Anexo V/III",
            },
            {
                "item": "4.07",
                "descricao": "Psicologia, psicanálise e neuropsicologia",
                "tributo": "ISS",
                "anexo": "Anexo V/III",
            },
            {
                "item": "4.08",
                "descricao": "Fisioterapia e terapia ocupacional",
                "tributo": "ISS",
                "anexo": "Anexo V/III",
            },
            {
                "item": "4.09",
                "descricao": "Fonoaudiologia e terapia de fala",
                "tributo": "ISS",
                "anexo": "Anexo V/III",
            },
            {
                "item": "4.10",
                "descricao": "Nutrição e dietética",
                "tributo": "ISS",
                "anexo": "Anexo V/III",
            },
            {
                "item": "4.12",
                "descricao": "Medicina veterinária",
                "tributo": "ISS",
                "anexo": "Anexo V/III",
            },
            {
                "item": "4.13",
                "descricao": "Serviços de prótese, inclusive dentária e ortodôntica",
                "tributo": "ISS",
                "anexo": "Anexo V/III",
            },
        ],
        "fundamento": (
            "Itens 4.01 a 4.13 da LC 116/2003 (saúde e veterinária). "
            "Anexos III e V da LC 123/2006. Fator R ≥ 28% -> Anexo III."
        ),
    },
    {
        "prefixos": ("41", "42", "43"),
        "titulo": "Construção civil",
        "resumo": (
            "Construção de edifícios, obras e serviços de engenharia -> Anexo IV. "
            "Nesse anexo, a CPP é recolhida SEPARADAMENTE (fora do DAS), e o ISS "
            "não está incluído no DAS."
        ),
        "itens_lc116": [
            {
                "item": "7.02",
                "descricao": "Execução, por administração, empreitada ou subempreitada, de obras de construção civil, hidráulica ou elétrica e de outras obras semelhantes",
                "tributo": "ISS",
                "anexo": "Anexo IV",
            },
            {
                "item": "7.05",
                "descricao": "Reparação, conservação e reforma de edifícios, estradas, pontes, portos e congêneres (exceto o fornecimento de mercadorias produzidas pelo próprio prestador fora do local da obra)",
                "tributo": "ISS",
                "anexo": "Anexo IV",
            },
        ],
        "fundamento": (
            "Itens 7.02 e 7.05 da LC 116/2003. Anexo IV da LC 123/2006. "
            "CPP recolhida à parte; não se aplica a regra do fator R."
        ),
    },
    {
        "prefixos": ("80", "81"),
        "titulo": "Vigilância, segurança, limpeza e conservação",
        "resumo": (
            "Vigilância, segurança, limpeza e conservação -> Anexo IV (art. 18, "
            "§5º-C, da LC 123/2006). Como na construção, a CPP é recolhida "
            "separadamente e o ISS não está incluído no DAS. Não há fator R "
            "nessas atividades."
        ),
        "itens_lc116": [
            {
                "item": "11.02",
                "descricao": (
                    "Vigilância, segurança ou monitoramento de bens e pessoas "
                    "(inclusive por meio de cessão de mão de obra)"
                ),
                "tributo": "ISS",
                "anexo": "Anexo IV",
            },
            {
                "item": "11.04",
                "descricao": (
                    "Varrição, coleta, remoção, incineração, tratamento, reciclagem, "
                    "separação e destinação final de lixo, rejeitos e outros resíduos "
                    "(atividade de limpeza)"
                ),
                "tributo": "ISS",
                "anexo": "Anexo IV",
            },
            {
                "item": "7.10",
                "descricao": "Limpeza, manutenção e conservação de imóveis, inclusive vidraça, piscina e afins (exceto se em conjunto com a atividade-fim)",
                "tributo": "ISS",
                "anexo": "Anexo IV",
            },
            {
                "item": "7.11",
                "descricao": "Decoração e jardinagem, inclusive corte e poda de árvores",
                "tributo": "ISS",
                "anexo": "Anexo IV",
            },
            {
                "item": "7.13",
                "descricao": "Dedetização, desinfecção, desinsetização, imunização, higienização, desratização e afins",
                "tributo": "ISS",
                "anexo": "Anexo IV",
            },
        ],
        "palavras_icms": ("vigilancia sem cessao de mao de obra",
                          "vigilância sem cessão de mão de obra"),
        "palavras_iss": ("vigilancia", "vigilância", "seguranca", "segurança", "monitoramento",
                         "limpeza", "conservacao", "conservação", "dedetizacao", "dedetização",
                         "jardinagem", "portaria", "coleta de lixo"),
        "fundamento": (
            "Art. 18, §5º-C, da LC 123/2006: os serviços de vigilância, limpeza "
            "e conservação são tributados no Anexo IV, com a CPP recolhida "
            "separadamente (fora do DAS) e sem aplicação do fator R. Itens "
            "11.02, 11.04, 7.10, 7.11 e 7.13 da LC 116/2003."
        ),
    },
    {
        "prefixos": ("85",),
        "titulo": "Educação e ensino",
        "resumo": (
            "Escolas, cursos, treinamento e educação em geral -> Anexo III. "
            "Ensino livre/instrução (item 8.02) pode ir ao Anexo V pelo fator R."
        ),
        "itens_lc116": [
            {
                "item": "8.01",
                "descricao": "Ensino regular pré-escolar, fundamental, médio e superior",
                "tributo": "ISS",
                "anexo": "Anexo III",
            },
            {
                "item": "8.02",
                "descricao": "Instrução, treinamento, orientação pedagógica e educacional, avaliação de conhecimentos de qualquer natureza",
                "tributo": "ISS",
                "anexo": "Anexo III/V",
            },
        ],
        "palavras_iss": ("ensino", "escola", "curso", "treinamento", "educacao",
                         "educação", "instrucao", "instrução", "capacitacao", "capacitação"),
        "fundamento": (
            "Itens 8.01 e 8.02 da LC 116/2003. Anexo III da LC 123/2006 para o "
            "ensino regular (item 8.01); para o ensino livre/instrução (item "
            "8.02), Anexo III ou V conforme o fator R (§5º-B, I)."
        ),
    },
    {
        "prefixos": ("56",),
        "titulo": "Alimentação e bebidas",
        "resumo": (
            "Restaurantes, lanchonetes, padarias e similares -> Anexo I quando "
            "vendem mercadoria; a parte de serviço de preparo acompanha o Anexo I "
            "para quem explora a atividade como comércio."
        ),
        "itens_lc116": [
            {
                "item": "—",
                "descricao": (
                    "Não há item na LC 116/2003 para o preparo de alimentos: "
                    "fornecimento de alimentação é tributado pelo ICMS (item "
                    "1.01 do Anexo I da LC 123/2006)"
                ),
                "tributo": "ICMS",
                "anexo": "Anexo I",
            },
            {
                "item": "6.04",
                "descricao": "Organização de festas e recepções; bufê (exceto o fornecimento de alimentação e bebidas, que fica sujeito ao ICMS)",
                "tributo": "ISS",
                "anexo": "Anexo III/V",
            },
        ],
        "palavras_icms": ("restaurante", "lanchonete", "padaria", "bar", "pizzaria",
                          "cafeteria", "cantina", "alimentacao", "alimentação",
                          "bebida", "refeicao", "refeição", "delivery", "comercio"),
        "palavras_iss": ("bufe", "buffet", "festa", "recepcao", "recepção",
                         "evento", "fornecimento de mao de obra", "mão de obra"),
        "fundamento": (
            "A venda de mercadoria (alimentação preparada) segue o Anexo I da "
            "LC 123/2006 e o ICMS (art. 155, II, CF). Só a organização de festas "
            "e recepções/bufê (item 6.04 da LC 116/2003) é serviço de ISS."
        ),
    },
    {
        "prefixos": ("6920", "6921", "6922"),
        "titulo": "Contabilidade, auditoria e consultoria fiscal",
        "resumo": (
            "Serviços contábeis são atividade intelectual (ISS). Em regra caem no "
            "Anexo III; quando a folha de salários é baixa (< 28% da RBT12), o "
            "fator R empurra a atividade para o Anexo V."
        ),
        "itens_lc116": [
            {
                "item": "17.14",
                "descricao": "Auditoria, economia, consultoria, gestão, organização, controle e administração",
                "tributo": "ISS",
                "anexo": "Anexo III/V",
            },
            {
                "item": "17.16",
                "descricao": "Contabilidade, inclusive serviços técnicos e auxiliares",
                "tributo": "ISS",
                "anexo": "Anexo III/V",
            },
            {
                "item": "17.19",
                "descricao": (
                    "Contabilidade, inclusive serviços técnicos e auxiliares "
                    "(abrange contabilidade, auditoria e perícia contábil)"
                ),
                "tributo": "ISS",
                "anexo": "Anexo III/V",
            },
        ],
        "palavras_iss": ("contabilidade", "contábil", "contabil", "auditoria",
                         "consultoria", "assessoria", "fiscal"),
        "fundamento": (
            "Itens 17.14, 17.16 e 17.19 da LC 116/2003. Anexos III e V da LC 123/2006 "
            "(fator R: folha >= 28% da RBT12 -> Anexo III; abaixo -> Anexo V)."
        ),
    },
    {
        "prefixos": ("6911", "6912", "6913", "6914"),
        "titulo": "Serviços jurídicos",
        "resumo": (
            "Advocacia e serviços jurídicos são atividade intelectual (ISS). O "
            "enquadramento depende do fator R: folha >= 28% da RBT12 -> Anexo III; "
            "abaixo -> Anexo V."
        ),
        "itens_lc116": [
            {
                "item": "17.02",
                "descricao": "Datilografia, digitação, estenografia, expediente, secretária em geral, resposta audível, redação, edição, interpretação e tradução",
                "tributo": "ISS",
                "anexo": "Anexo III/V",
            },
            {
                "item": "17.14",
                "descricao": "Assessoria, consultoria, gestão, organização e controle (despachante, advogado, contador e congêneres)",
                "tributo": "ISS",
                "anexo": "Anexo III/V",
            },
        ],
        "palavras_iss": ("advocacia", "advogado", "juridico", "jurídico", "jurídica",
                         "despachante"),
        "fundamento": (
            "Item 17.14 da LC 116/2003 (assessoria e consultoria de qualquer "
            "natureza, incluindo advocacia) e item 17.02 (redação, edição, "
            "interpretação). Anexos III e V da LC 123/2006 (fator R aplicável)."
        ),
    },
    {
        "prefixos": ("7111", "7112", "7119", "7120"),
        "titulo": "Engenharia, arquitetura e serviços técnicos",
        "resumo": (
            "Engenharia, arquitetura e serviços técnicos são atividade intelectual "
            "(ISS). Ensaios e análises técnicas também são ISS, pelo item 17.09 da "
            "LC 116/2003. Anexo III ou V conforme o fator R (folha de salários x RBT12)."
        ),
        "itens_lc116": [
            {
                "item": "7.01",
                "descricao": "Engenharia, agronomia, agrimensura, arquitetura, geologia, urbanismo, paisagismo e congêneres",
                "tributo": "ISS",
                "anexo": "Anexo III/V",
            },
            {
                "item": "7.02",
                "descricao": "Execução, por administração, empreitada ou subempreitada, de obras de construção civil, hidráulica ou elétrica e de outras obras semelhantes",
                "tributo": "ISS",
                "anexo": "Anexo IV",
            },
            {
                "item": "7.03",
                "descricao": "Elaboração de planos diretores, estudos de viabilidade, estudos organizacionais e outros, relacionados com obras e serviços de engenharia; elaboração de anteprojetos, projetos básicos e projetos executivos para trabalhos de engenharia",
                "tributo": "ISS",
                "anexo": "Anexo III/V",
            },
            {
                "item": "7.19",
                "descricao": "Acompanhamento e fiscalização da execução de obras de engenharia, arquitetura e urbanismo",
                "tributo": "ISS",
                "anexo": "Anexo III/V",
            },
            {
                "item": "17.09",
                "descricao": "Perícias, laudos, exames técnicos e análises técnicas",
                "tributo": "ISS",
                "anexo": "Anexo III/V",
            },
            {
                "item": "28.01",
                "descricao": "Serviços de avaliação de bens e serviços de qualquer natureza",
                "tributo": "ISS",
                "anexo": "Anexo III/V",
            },
        ],
        "palavras_iss": ("engenharia", "arquitetura", "arquiteto", "engenheiro",
                         "projeto", "consultoria", "perícia", "pericia", "laudo",
                         "ensaio", "análise técnica", "analise tecnica"),
        "fundamento": (
            "Itens 7.01, 7.02, 7.03 e 7.19 da LC 116/2003; serviços de ensaio e "
            "análise técnica no item 17.09, e avaliação de bens no item 28.01. "
            "Anexos III/V (serviços intelectuais) e Anexo IV (execução de obras) "
            "da LC 123/2006."
        ),
    },
    {
        "prefixos": ("7311", "7319"),
        "titulo": "Publicidade e marketing",
        "resumo": (
            "Publicidade, propaganda e marketing são prestação de serviço (ISS) e "
            "seguem o Anexo III, salvo as atividades de propaganda que integrem o "
            "Anexo V (por exemplo, agenciamento de propaganda/produção de material "
            "publicitário enquadrado como criação intelectual), quando o fator R é "
            "inferior a 28%."
        ),
        "itens_lc116": [
            {
                "item": "17.06",
                "descricao": "Propaganda e publicidade, inclusive promoção de vendas, planejamento de campanhas ou sistemas de publicidade, elaboração de desenhos, textos e demais materiais publicitários",
                "tributo": "ISS",
                "anexo": "Anexo III/V",
            },
            {
                "item": "17.08",
                "descricao": "Franquia (franchising) e afins",
                "tributo": "ISS",
                "anexo": "Anexo III/V",
            },
        ],
        "palavras_icms": ("revenda de material", "comercio de material", "comércio de material",
                          "impressao de material", "impressão de material", "fabricacao de brinde",
                          "fabricação de brinde"),
        "palavras_iss": ("publicidade", "propaganda", "marketing", "anuncio", "anúncio",
                         "campanha", "agencia", "agência"),
        "fundamento": (
            "Itens 17.06 e 17.08 da LC 116/2003. Anexos III e V da LC 123/2006 "
            "(fator R quando a atividade for classificada no Anexo V)."
        ),
    },
    {
        "prefixos": ("7711", "7719"),
        "titulo": "Locação de bens móveis",
        "resumo": (
            "Locação de bens móveis (veículos, máquinas, equipamentos) -> Anexo III "
            "(ISS). Não confundir com locação de imóveis, que não é fato gerador de ISS."
        ),
        "itens_lc116": [
            {
                "item": "3.01",
                "descricao": (
                    "Locação e manutenção de máquinas, aparelhos, equipamentos, "
                    "motores, dentre outros, e de seus acessórios, sem operador"
                ),
                "tributo": "ISS",
                "anexo": "Anexo III",
            },
            {
                "item": "3.02",
                "descricao": (
                    "Cessão de andaimes, palcos, coberturas e outras estruturas de "
                    "uso e aplicação na construção civil"
                ),
                "tributo": "ISS",
                "anexo": "Anexo IV",
            },
            {
                "item": "3.05",
                "descricao": (
                    "Locação de animais (cavalos, bois, muares, ovelhas e semelhantes) "
                    "para qualquer finalidade"
                ),
                "tributo": "ISS",
                "anexo": "Anexo III",
            },
            {
                "item": "15.01",
                "descricao": (
                    "Locação de bens móveis sem operador, inclusive veículos "
                    "(exceto locação de máquinas/equipamentos, item 3.01)"
                ),
                "tributo": "ISS",
                "anexo": "Anexo III",
            },
        ],
        "palavras_icms": ("imovel", "imóvel", "locacao de imovel", "locação de imóvel",
                          "locacao de imoveis", "locação de imóveis"),
        "palavras_iss": ("locacao", "locação", "aluguel", "arrendamento", "sem operador",
                         "maquinas", "máquinas", "equipamentos", "veiculos", "veículos"),
        "fundamento": (
            "Itens 3.01, 3.02, 3.05 e 15.01 da LC 116/2003. Anexo III da "
            "LC 123/2006; a cessão de andaimes e estruturas para construção "
            "civil (item 3.02) é Anexo IV. Locação de imóveis não é ISS."
        ),
    },
    {
        "prefixos": ("49",),
        "titulo": "Transporte de cargas e logística",
        "resumo": (
            "Transporte municipal de bens -> ISS (Anexo III). Transporte "
            "intermunicipal/interestadual é tributado pelo ICMS e acompanha o Anexo I. "
            "Observe a natureza (cargas x passageiros) e a modalidade."
        ),
        "itens_lc116": [
            {
                "item": "16.01",
                "descricao": "Serviços de transporte coletivo municipal rodoviário, metroviário, ferroviário e aquaviário de passageiros",
                "tributo": "ISS",
                "anexo": "Anexo III",
            },
            {
                "item": "16.02",
                "descricao": "Outros serviços de transporte de natureza municipal (inclusive transporte de cargas dentro do município)",
                "tributo": "ISS",
                "anexo": "Anexo III",
            },
            {
                "item": "—",
                "descricao": (
                    "Transporte intermunicipal/interestadual (cargas ou "
                    "passageiros): não é ISS nem há item na LC 116/2003 — é "
                    "tributado pelo ICMS (Anexo I, item 1.01)"
                ),
                "tributo": "ICMS",
                "anexo": "Anexo I",
            },
        ],
        "palavras_icms": ("intermunicipal", "interestadual", "carga", "cargas", "logistica",
                          "logística", "frota", "rodoviario de cargas"),
        "palavras_iss": ("municipal", "coletivo", "passageiros", "entrega", "motoboy",
                         "urbano", "porte", "movimentacao", "movimentação", "armazenagem"),
        "fundamento": (
            "Itens 16.01 e 16.02 da LC 116/2003 (transporte de natureza municipal). "
            "Transporte intermunicipal/interestadual -> ICMS (art. 155, II, CF) e "
            "Anexo I da LC 123/2006."
        ),
    },
    {
        "prefixos": ("55",),
        "titulo": "Alojamento e alimentação",
        "resumo": (
            "Hotéis, pousadas e similares -> Anexo III (ISS, item 9.01). A venda de "
            "mercadoria (bares, restaurantes dentro do hotel) acompanha o Anexo I na "
            "parcela correspondente."
        ),
        "itens_lc116": [
            {
                "item": "9.01",
                "descricao": "Hospedagem de qualquer natureza em hotéis, motéis, pensões, albergues, pousadas, apart-hotéis, hotéis residência, ocupação por temporada e congêneres",
                "tributo": "ISS",
                "anexo": "Anexo III",
            },
            {
                "item": "9.02",
                "descricao": "Agenciamento, organização, promoção e execução de programas de turismo, passeios, viagens, excursões e congêneres",
                "tributo": "ISS",
                "anexo": "Anexo III/V",
            },
            {
                "item": "9.03",
                "descricao": "Guias de turismo",
                "tributo": "ISS",
                "anexo": "Anexo V",
            },
        ],
        "palavras_iss": ("hotel", "pousada", "hospedagem", "motel", "albergue", "turismo"),
        "fundamento": (
            "Itens 9.01, 9.02 e 9.03 da LC 116/2003. Anexo III da LC 123/2006 "
            "(hospedagem); venda de mercadoria segue o Anexo I."
        ),
    },
    {
        "prefixos": ("90", "91", "92", "93"),
        "titulo": "Artes, cultura, entretenimento e esporte",
        "resumo": (
            "Atividades artísticas, culturais, esportivas e de entretenimento -> "
            "Anexo III (ISS). Atenção às parcelas de venda de ingressos e mercadorias."
        ),
        "itens_lc116": [
            {
                "item": "12.01",
                "descricao": "Espetáculos teatrais, cinematográficos, circenses, musicais, festivais, shows, recitais e congêneres",
                "tributo": "ISS",
                "anexo": "Anexo III",
            },
            {
                "item": "12.02",
                "descricao": "Exibições cinematográficas, televisivas, de rádio e de entretenimento em geral",
                "tributo": "ISS",
                "anexo": "Anexo III",
            },
            {
                "item": "12.04",
                "descricao": "Exibição de filmes e programações de televisão, rádio e demais meios audiovisuais",
                "tributo": "ISS",
                "anexo": "Anexo III",
            },
            {
                "item": "12.05",
                "descricao": (
                    "Atividades culturais e artísticas, como música, dança, teatro, "
                    "escultura, desenho, pintura, fotografia, artesanato e similares"
                ),
                "tributo": "ISS",
                "anexo": "Anexo III",
            },
            {
                "item": "12.13",
                "descricao": (
                    "Produção, organização, exibição e administração de "
                    "atividades de lazer, cultura, esporte e entretenimento "
                    "(inclusive clubes, academias, piscinas e afins)"
                ),
                "tributo": "ISS",
                "anexo": "Anexo III",
            },
            {
                "item": "—",
                "descricao": (
                    "Venda de ingressos, mercadorias e bebidas em eventos segue "
                    "o ICMS (item 1.01 do Anexo I da LC 123/2006)"
                ),
                "tributo": "ICMS",
                "anexo": "Anexo I",
            },
        ],
        "palavras_icms": ("ingresso", "revenda", "bebida", "alimentacao", "alimentação", "bar"),
        "palavras_iss": ("cultural", "artistico", "artístico", "artista", "esporte",
                         "entretenimento", "evento", "show", "espetaculo", "espetáculo",
                         "academia", "clube", "lazer"),
        "fundamento": (
            "Itens 12.01 a 12.13 da LC 116/2003 (atividades artísticas, culturais, "
            "esportivas e de lazer). Anexo III da LC 123/2006. A venda de "
            "ingressos e mercadorias no evento sujeita-se ao ICMS (Anexo I)."
        ),
    },
    {
        "prefixos": ("95", "96"),
        "titulo": "Reparação, manutenção e serviços pessoais",
        "resumo": (
            "Reparação e manutenção (de objetos, eletrodomésticos, móveis etc.) e "
            "serviços pessoais -> Anexo III (ISS). A revenda de peças acompanha o "
            "Anexo I, quando destacada."
        ),
        "itens_lc116": [
            {
                "item": "6.01",
                "descricao": "Serviços de reparo, manutenção, conservação, restauração e reforma de quaisquer objetos ou bens móveis",
                "tributo": "ISS",
                "anexo": "Anexo III",
            },
            {
                "item": "14.05",
                "descricao": "Reparação e manutenção de bens móveis de uso pessoal ou doméstico",
                "tributo": "ISS",
                "anexo": "Anexo III",
            },
            {
                "item": "14.06",
                "descricao": (
                    "Reparação e manutenção de máquinas, motores, aparelhos, "
                    "equipamentos, instalações e congêneres (exceto serviços de "
                    "engenharia e reforma de prédios)"
                ),
                "tributo": "ISS",
                "anexo": "Anexo III",
            },
        ],
        "palavras_icms": ("revenda de peca", "revenda de peça", "comercio de peca",
                          "comércio de peça", "venda de pecas", "venda de peças"),
        "palavras_iss": ("reparacao", "reparação", "manutencao", "manutenção", "conserto",
                         "lavanderia", "cabeleireiro", "estetica", "estética"),
        "fundamento": (
            "Itens 6.01, 14.05 e 14.06 da LC 116/2003. Anexo III da LC 123/2006. "
            "A revenda de peças, quando destacada, acompanha o Anexo I."
        ),
    },
    {
        "prefixos": ("82",),
        "titulo": "Serviços de apoio administrativo",
        "resumo": (
            "Apoio administrativo, seleção de pessoal, cobrança, serviços gerais -> "
            "Anexo III (ISS), salvo atividades específicas que recaiam no Anexo V."
        ),
        "itens_lc116": [
            {
                "item": "17.02",
                "descricao": (
                    "Datilografia, digitação, estenografia, expediente, secretária "
                    "em geral, resposta audível, redação, edição, interpretação e "
                    "tradução, bem como apoio administrativo"
                ),
                "tributo": "ISS",
                "anexo": "Anexo III",
            },
            {
                "item": "17.05",
                "descricao": "Fornecimento de mão de obra, mesmo em caráter temporário, inclusive de empregados ou trabalhadores, avulsos ou temporários, contratados pelo prestador de serviço",
                "tributo": "ISS",
                "anexo": "Anexo IV",
            },
            {
                "item": "25.01",
                "descricao": "Serviços de coleta, remessa ou entrega de correspondências, documentos, objetos, bens ou valores (inclusive pelos Correios e congêneres)",
                "tributo": "ISS",
                "anexo": "Anexo III/V",
            },
        ],
        "palavras_iss": ("apoio administrativo", "administrativo", "cobranca", "cobrança",
                         "selecao", "seleção", "recrutamento", "terceirizacao", "terceirização"),
        "palavras_iss": ("apoio administrativo", "administrativo", "cobranca", "cobrança",
                         "selecao", "seleção", "recrutamento", "terceirizacao", "terceirização",
                         "entrega", "correspondencia", "correspondência", "motoboy"),
        "fundamento": (
            "Itens 17.02, 17.05 e 25.01 da LC 116/2003. Anexo III (apoio "
            "administrativo e entrega), Anexo III/V (quando o fator R do Anexo V "
            "for aplicável) e Anexo IV (cessão de mão de obra) da LC 123/2006."
        ),
    },
    {
        "prefixos": ("8630", "8640", "8650", "8660", "8690"),
        "titulo": "Serviços de saúde e laboratórios",
        "nota": (
            "Não há correspondência direta na LC 116/2003 para estes CNAEs; "
            "o enquadramento segue a natureza da atividade efetivamente prestada "
            "e o fator R (Anexos III ou V da LC 123/2006)."
        ),
        "resumo": (
            "Serviços de saúde em geral (laboratórios, clínicas, exames) são "
            "atividade de serviço (ISS). Laboratórios de análises clínicas/patologia "
            "e apoio diagnóstico caem no Anexo III (ISS), salvo atividade que a lei "
            "municipal submeta à substituição tributária."
        ),
        "itens_lc116": [
            {
                "item": "4.01",
                "descricao": "Medicina e biomedicina (consultas, exames e procedimentos)",
                "tributo": "ISS",
                "anexo": "Anexo III/V",
            },
            {
                "item": "4.02",
                "descricao": "Análises clínicas, patologia, eletricidade médica, radioterapia, quimioterapia, ultrassonografia, ressonância, radiografia e demais exames complementares",
                "tributo": "ISS",
                "anexo": "Anexo III/V",
            },
            {
                "item": "4.03",
                "descricao": "Hospitais, clínicas, laboratórios e congêneres",
                "tributo": "ISS",
                "anexo": "Anexo III/V",
            },
            {
                "item": "4.04",
                "descricao": "Instrumentação cirúrgica",
                "tributo": "ISS",
                "anexo": "Anexo III/V",
            },
            {
                "item": "4.05",
                "descricao": "Enfermagem, inclusive serviços auxiliares",
                "tributo": "ISS",
                "anexo": "Anexo III/V",
            },
            {
                "item": "4.13",
                "descricao": "Serviços de prótese, inclusive dentária e ortodôntica",
                "tributo": "ISS",
                "anexo": "Anexo III/V",
            },
        ],
        "palavras_iss": ("saude", "saúde", "laboratorio", "laboratório", "analises",
                         "análises", "patologia", "clinica", "clínica", "exame", "hospital"),
        "fundamento": (
            "Itens 4.01, 4.02 e 4.03 da LC 116/2003. Anexo III da LC 123/2006 "
            "(serviços de saúde em geral; fator R pode direcionar ao Anexo V)."
        ),
    },
]


# ---------------------------------------------------------------------------
# Funções
# ---------------------------------------------------------------------------

def _normalizar_codigo(cnae: str) -> str:
    """Somente dígitos do CNAE."""
    return cnaes.apenas_digitos(cnae)


def _buscar_curada(codigo: str) -> Optional[dict]:
    """
    Procura a explicação curada pelo prefixo mais específico (mais dígitos).

    O campo opcional "exceto" lista prefixos mais longos que NÃO pertencem ao
    grupo, mesmo que comecem pelo prefixo deste (ex.: grupo "86" genérico não
    deve capturar os laboratórios 8640/8690, que têm explicação própria).
    """
    melhor = None
    melhor_len = -1
    for item in EXPLICACOES_CNAE:
        if any(codigo.startswith(ex) for ex in item.get("exceto", ())):
            continue
        for prefixo in item["prefixos"]:
            if codigo.startswith(prefixo) and len(prefixo) > melhor_len:
                melhor = item
                melhor_len = len(prefixo)
    return melhor


def _anexo_de(curada: dict, tributo: str) -> str:
    """Anexo associado a um tributo (ICMS/ISS) na explicação curada."""
    for item in curada.get("itens_lc116", ()):
        if item.get("tributo") == tributo and item.get("anexo"):
            return item["anexo"]
    return ""


def _anexos_citados(curada: dict) -> list:
    """Todos os anexos (romanos) citados nos itens da explicação curada."""
    anexos = []
    for item in curada.get("itens_lc116", ()):
        for letra in re.findall(r"\b(I{1,3}|IV|V)\b", item.get("anexo", "")):
            if letra not in anexos:
                anexos.append(letra)
    return anexos


def _rotulo_anexo(valor: str, padrao: str) -> str:
    """Devolve 'Anexo X' sem duplicar o prefixo (ex.: 'Anexo III/V')."""
    valor = (valor or padrao).strip()
    return valor if valor.lower().startswith("anexo") else f"Anexo {valor}"


def _interpretar_destino(curada: dict, descricao: str, anexo_sugerido: str) -> str:
    """
    Usa palavras-chave para dizer se, no caso concreto, a atividade tende a
    ISS ou ICMS. Devolve o texto indicando o tributo e o Anexo correspondente.
    """
    if not curada:
        return ""

    texto = cnaes.normalizar(descricao)

    tem_icms = any(cnaes.normalizar(p) in texto for p in curada.get("palavras_icms", ()))
    tem_iss = any(cnaes.normalizar(p) in texto for p in curada.get("palavras_iss", ()))

    anexo_icms = _rotulo_anexo(_anexo_de(curada, "ICMS"), "II")
    anexo_iss = _rotulo_anexo(_anexo_de(curada, "ISS"), "III")

    if tem_icms and not tem_iss:
        return f"A tendência, pela descrição informada, é ICMS -> {anexo_icms}."
    if tem_iss and not tem_icms:
        return f"A tendência, pela descrição informada, é ISS -> {anexo_iss}."
    if tem_iss and tem_icms:
        return ("A descrição traz palavras de ISS e de ICMS — confirme o DESTINO do "
                f"produto/serviço para decidir entre {anexo_iss} e {anexo_icms}.")
    if anexo_sugerido in ("I", "II", "III", "IV", "V"):
        return f"Enquadramento automático sugerido: Anexo {anexo_sugerido}."
    return ""


def _nota_fator_r(candidatos: list) -> str:
    """
    Texto informativo sobre o Fator "r" (LC 123/2006), exibido quando o Anexo V
    estiver entre os anexos possíveis da atividade.

    Reproduz a regra: a atividade sujeita ao Fator "r" será tributada pelo
    Anexo V quando o Fator "r" for inferior a 28%; atingindo 28% ou mais, migra
    para o Anexo III. É apenas texto explicativo — não altera o enquadramento.
    """
    if "V" not in (candidatos or []):
        return ""
    return (
        "Sujeito ao Fator \"r\" (LC 123/2006): a atividade será tributada pelo "
        "Anexo V quando o Fator \"r\" for inferior a 28%. O Fator \"r\" corresponde "
        "à razão entre a folha de salários dos últimos 12 meses e a receita bruta "
        "acumulada dos últimos 12 meses (RBT12). Se o Fator \"r\" for igual ou "
        "superior a 28%, o enquadramento migra para o Anexo III."
    )


def _texto_lc116(subitem: str) -> str:
    """Texto oficial INTEGRAL do item/subitem da LC 116/2003.

    Preferência: ITENS_LC116 (itens_lc116.py, texto completo da lei).
    Fallback: ITEM_DESCRICAO (cnae_item_lc116.py), que é uma versão
    resumida/resumida da tabela gerada — usada só quando o item não existe
    no texto oficial.

    Os códigos da tabela vêm sem o zero à esquerda ("1.05"); o texto oficial
    usa dois dígitos ("01.05"), então normalizamos para o formato do catálogo.
    """
    codigo = (subitem or "").strip()
    if not codigo:
        return ""

    oficial = dict(ITENS_LC116)
    prefixo, _, sufixo = codigo.partition(".")
    if sufixo and prefixo.isdigit() and len(prefixo) == 1:
        candidato = f"0{prefixo}.{sufixo}"
        if candidato in oficial:
            return oficial[candidato]

    return oficial.get(codigo) or ITEM_DESCRICAO.get(codigo, "")


def _itens_tabela_cnae(cnae: str) -> list:
    """Itens da LC 116 vinculados ao CNAE na tabela editável (pode ser []).

    A tabela Cnae_X_Item_Lista_Servicos vive no banco (cnae_itens_lc116) e é
    mantida pela aba Tabelas. Aqui só lemos; se o banco não estiver acessível
    caímos para o dicionário gerado, garantindo que nada quebre fora do
    contexto de request.
    """
    codigo = _normalizar_codigo(cnae)
    if not codigo:
        return []

    itens = []
    try:
        from flask import has_app_context
        from database import itens_do_cnae

        if has_app_context():
            itens = itens_do_cnae(codigo)
    except Exception:  # noqa: BLE001 - explicação nunca deve derrubar a rota
        itens = []

    if not itens:
        itens = CNAE_ITEM.get(codigo) or []

    return [
        {
            "item": sub.lstrip("0") or sub,
            "descricao": _texto_lc116(sub),
            "tributo": "ISS",
            "anexo": "",
            "origem": "tabela",
        }
        for sub in itens
    ]


def _itens_por_cnae(cnae: str, descricao: str, curados: list) -> list:
    """Itens da LC 116 para o CNAE.

    Precedência:
      1) tabela oficial CNAE -> item (Cnae_X_Item_Lista_Servicos, editável na
         aba Tabelas). É vínculo legal, determinístico: devolve todos os
         itens do CNAE e nada mais;
      2) CNAE fora da tabela: detalhamento curado, se existir;
      3) sem nada disso, tenta casar pela DESCRIÇÃO da atividade.

    O casamento por descrição NUNCA é somado aos itens da tabela: era o que
    fazia o relatório sair com itens indevidos (ex.: CNAE de impressão
    recebendo o item 39.01 de ourivesaria).
    """
    tabela = _itens_tabela_cnae(cnae)

    if tabela:
        return tabela

    if not (descricao or "").strip():
        return curados

    try:
        kb = _conhecimento()
        subitem = kb.item_para_frase(descricao)
    except Exception:  # noqa: BLE001 - explicação nunca deve quebrar a rota
        return curados

    if not subitem:
        return curados

    texto_legal = _texto_lc116(subitem)
    casado = {
        "item": subitem,
        "descricao": texto_legal,
        "tributo": "ISS",
        "anexo": "",
        "origem": "descricao",
    }

    # Resume o curado apenas para detectar divergência de item.
    ja_listado = [i for i in curados if str(i.get("item", "")).strip() == subitem]
    if ja_listado:
        return curados

    resultado = [casado] + [dict(i) for i in curados]
    if curados:
        citados = ", ".join(
            str(i.get("item", "")).strip() for i in curados if i.get("item")
        )
        resultado[0]["ressalva"] = (
            "A descrição informada corresponde a este item da LC 116/2003"
            + (f" ({texto_legal})." if texto_legal else ".")
            + (f" O detalhamento abaixo cita o item {citados}."
               " Em caso de divergência, prevalece a descrição da atividade"
               " efetivamente prestada." if citados else "")
        )
    return resultado


def _conhecimento():
    """Instância única do banco de conhecimento (cria o catálogo na 1ª vez)."""
    global _KB
    if _KB is None:
        from enquadramento_db import Conhecimento
        _KB = Conhecimento()
        _KB.init()
    return _KB


def explicar(cnae: str, descricao: str = "") -> dict:
    """
    Monta a explicação do enquadramento de um CNAE.

    Retorna:
      cnae            -> CNAE formatado
      titulo          -> título curto (ou "Enquadramento genérico")
      resumo          -> texto principal
      itens_lc116     -> lista do detalhamento por item da LC 116 (pode ser [])
      fundamento      -> base legal / observação
      sugestao        -> {anexo, anexos_candidatos, descricao_grupo, confianca}
      destino         -> interpretação ISS x ICMS para o caso concreto (pode ser "")
      nota_fator_r    -> aviso sobre o Fator "r" quando o Anexo V for possível ("")
      curado          -> True se achou explicação específica para o CNAE
    """
    codigo = _normalizar_codigo(cnae)
    sugestao = cnaes.sugerir_anexo(cnae, descricao)
    candidatos = cnaes.anexos_candidatos(cnae, descricao)

    # O enquadramento técnico vem do motor legal (enquadramento.py). O texto
    # curado abaixo só acrescenta o detalhamento por item da LC 116.
    tecnico = MOTOR.explicacao(cnae, descricao)

    curada = _buscar_curada(codigo) if codigo else None

    if curada:
        resultado = {
            "titulo": curada.get("titulo", ""),
            "resumo": curada.get("resumo", ""),
            "itens_lc116": curada.get("itens_lc116", []),
            "fundamento": curada.get("fundamento", ""),
            "curado": True,
        }
    else:
        resultado = {
            "titulo": tecnico.get("titulo") or "Enquadramento genérico",
            "resumo": tecnico.get("resumo", ""),
            "itens_lc116": [],
            "fundamento": tecnico.get("fundamento") or (
                "LC 123/2006, art. 18. Em caso de dúvida, consulte um contador "
                "ou a Resolução CGSN aplicável ao ano."
            ),
            "curado": False,
        }

    # Item da LC 116 definido pelo CNAE (tabela legal), nunca por palavra.
    resultado["itens_lc116"] = _itens_por_cnae(
        cnae, descricao, resultado.get("itens_lc116") or []
    )

    if candidatos:
        resultado["resumo"] += (
            " Anexos possíveis para esta atividade: "
            + ", ".join(f"Anexo {a}" for a in candidatos) + "."
        )

    # O texto curado é apenas apoio didático: se os anexos que ele cita no item
    # de ISS/ICMS não coincidirem com o enquadramento legal, mostra a ressalva
    # e mantém a sugestão técnica como fonte de verdade.
    if curada:
        anexos_texto = set(_anexos_citados(curada))
        anexos_tecnicos = set(candidatos or ())
        if anexos_texto and anexos_tecnicos and not (anexos_texto & anexos_tecnicos):
            resultado["resumo"] += (
                " Ressalva: o enquadramento calculado para este CNAE "
                f"(Anexo {', Anexo '.join(candidatos)}) prevalece sobre a "
                "indicação geral desta explicação."
            )

    resultado.update({
        "cnae": cnaes.formatar_cnae(cnae),
        "sugestao": {
            "anexo": sugestao.get("anexo"),
            "anexos_candidatos": candidatos,
            "descricao_grupo": sugestao.get("descricao_grupo", ""),
            "confianca": sugestao.get("confianca", ""),
        },
        "destino": _interpretar_destino(curada, descricao, sugestao.get("anexo")),
        "nota_fator_r": _nota_fator_r(candidatos),
    })

    return resultado


def listar_explicacoes() -> list:
    """Lista simplificada das explicações curadas (para consulta/inspeção)."""
    return [
        {
            "titulo": item.get("titulo", ""),
            "prefixos": list(item.get("prefixos", ())),
            "exceto": list(item.get("exceto", ())),
            "fundamento": item.get("fundamento", ""),
            "itens_lc116": item.get("itens_lc116", []),
        }
        for item in EXPLICACOES_CNAE
    ]
