# Minha memória de trabalho — Calculadora Simples Nacional

> Este arquivo **não é documentação para o usuário nem para terceiros.**
> É a minha memória: o que eu preciso lembrar para ajudar o usuário neste
> sistema, inclusive depois de meses sem mexer nele.
>
> O Copilot carrega este arquivo sozinho no início de toda conversa. Se eu
> estiver lendo isto e não me lembrar de nada: **leia tudo antes de abrir
> qualquer arquivo do projeto.**
>
> O que está aqui foi dito pelo usuário. Ele manda. Não reinterpretar.
>
> Última revisão: 2026-10-17.

---

## 0. Como usar esta memória

1. **Seção 1 (Proibições)** — o que o usuário me proibiu. Violar é o erro mais
   grave possível.
2. **Seção 2 (Regras de negócio)** — o que o usuário decidiu sobre o sistema.
3. **Seção 3 (Método)** — como ele quer que eu trabalhe.
4. **Seção 4 (O código)** — mapa do que existe, para eu não procurar do zero.
5. **Seção 5 (Cicatrizes)** — o que eu já errei e não posso repetir.
6. **Seção 6 (Pendências)** — o que eu ainda não sei e preciso perguntar.

Regras que o usuário disser durante o trabalho vão para `REGRAS.md` na hora
(ver 1.4). Quando o assunto é regra de negócio ou de conduta, o destino é
este arquivo, seção 1 ou 2.

**Mapa do projeto (arquivos, rotas, bancos, como rodar):** `.github/MEMORIA.md`.
Ler junto com este arquivo — um complementa o outro. O `MEMORIA.md` só
contém o que foi verificado no código ou dito pelo usuário, com a fonte
marcada; dúvidas ficam na seção 7 de lá, nunca preenchidas por suposição.

Quando este arquivo conflitar com a minha "intuição" ou com boa prática
genérica: **esta memória vence.**

---

## 1. PROIBIÇÕES — o que eu não posso fazer

### 1.0 REGRA NÚMERO UM — não inventar

- **Não inventar nada.** Nem dado, nem descrição de CNAE, nem regra de
  negócio, nem resultado de teste, nem memória do que o usuário disse.
- **Não preencher lacuna com suposição e apresentar como fato.**
- O que não está registrado aqui nem no código: **eu não sei.** Dizer isso.
- Separar sempre o que é **fato** do que é **dedução minha**.
- Se a memória estiver incompleta, ela é marcada como incompleta — nunca
  "completada" por mim.

> Origem: instrução direta do usuário em 2026-10-17.

### 1.1 Sobre as regras de negócio

| Nunca | Por quê |
|---|---|
| **Reinterpretar, "melhorar" ou generalizar** uma regra que o usuário definiu | Ele já corrigiu isso. Minha heurística foi o que causou o erro |
| **Substituir a regra por heurística própria** quando ela parecer incompleta | Se parecer incompleta, **perguntar** — não decidir sozinho |
| **Procurar palavras de comércio/indústria em qualquer posição** da descrição | Bloqueia itens legítimos da LC 116 ("desenho industrial", "confecção de páginas", "produção de eventos") |
| **Usar prefixo solto como `produt`, `mercad`, `textil`, `embalagem`** | São objetos do serviço, não a natureza da atividade |
| **Decidir "não é serviço" com base em uma palavra só** | A decisão vem da **abertura da frase**, lida inteira |
| **Trocar a classificação para forçar um resultado** | Se o caso real ainda falha, o problema é a regra — perguntar |

### 1.2 Sobre o código

| Nunca | Por quê |
|---|---|
| **Editar o motor de enquadramento sem rodar diagnóstico antes** | Já quebrou serviços sem ninguém perceber |
| **Declarar "validado" ou "está certo" sem ter rodado a verificação** | Já afirmei isso com descrições que eu mesmo inventei |
| **Inventar descrições de CNAE** para testar | Tem que ser descrição oficial + os 200 itens reais da LC 116 |
| **Confiar em resultado inexplicado** | Pode ser `__pycache__` velho. Apagar e reconferir |
| **Deixar a LC 116 com qualquer item bloqueado** | Zero é o único número aceitável |
| **Mexer em `calc.py` para "fazer bater"** | Se diverge da planilha, o erro é de diagnóstico, não de arredondamento |
| **Apagar arquivos `.bak` / `_backup` sem pedir** | São o histórico do que já foi tentado |

### 1.3 Sobre a interação com o usuário

| Nunca | Por quê |
|---|---|
| **Discutir quando ele diz que está errado** | Está errado. Corrigir |
| **Pedir para ele escolher entre opções que ele já decidiu** | Ele já resolveu; reabrir é desrespeito ao tempo dele |
| **Repetir a mesma explicação depois de errar duas vezes** | Pedir desculpa uma vez é aceitável; explicar de novo não |
| **Entregar opinião onde ele pediu número** | Mostrar saída de diagnóstico, não impressão |
| **Dar resposta longa onde cabe resposta curta** | Ele prefere direto |

### 1.4 Memória contínua (regra permanente do usuário)

Esta memória é **minha, sobre o projeto** — para eu conseguir ajudar o
usuário depois de meses sem mexer no sistema. Não é documentação para
terceiros.

Em **toda** sessão de trabalho:

1. **Antes de perguntar qualquer coisa**, consultar este arquivo e o código.
   Só perguntar o que **não** está registrado aqui.
2. **Toda vez que o usuário disser que algo pode ou não pode ser feito,
   gravar imediatamente** — na mesma resposta, não "depois". Regra nova entra
   em `.github/REGRAS.md` com a data; se for regra de negócio ou proibição,
   também na seção 1 ou 2 daqui.
3. Gravar em `ALTERACOES.md` a evidência de cada mudança de código.
4. Se uma regra registrada parecer errada, **não apagar** — perguntar ao
   usuário e registrar a correção com data.

Formato de entrada de regra nova:

```
### [data] Regra — <título curto>
- **Pode:** ...
- **Não pode:** ...
- **Motivo/origem:** o que aconteceu que gerou a regra
```

---

## 2. Regras de negócio (definidas pelo usuário)

Estas regras foram corrigidas pelo usuário depois de erro meu. **Não
"melhorar", não generalizar, não substituir por heurística própria.**

### 2.1 Classificação serviço × não-serviço

A classificação vem do **INÍCIO da descrição completa** do CNAE, lendo-se a
frase inteira, nunca palavras soltas no meio dela.

| Descrição começa com | Classificação |
|---|---|
| `Serviço(s) de ...` | **SERVIÇO** |
| `Atividade(s) de ...` | **SERVIÇO** |
| `Manutenção ...`, `Instalação ...`, `Reparação ...` | **SERVIÇO** |
| `Comércio de ...`, `Comércio varejista de ...` | **NÃO é serviço** |
| `Fabricação de ...` | **NÃO é serviço** |
| `Industrialização de ...` | **NÃO é serviço** |
| `Produção de ...` | **NÃO é serviço** |
| `Extração de ...`, `Cultivo de ...`, `Criação de ...` | **NÃO é serviço** |

### 2.2 Exemplos que já erraram e não podem errar de novo

- `Serviços de manutenção de máquinas industriais` → **é serviço**
  (a palavra "industrial" no meio não muda nada)
- `Serviços de embalagem` → **é serviço**
- `Desenho industrial` (LC 116 item 23.01) → **é serviço**
- `Confecção de páginas eletrônicas` (item 1.08) → **é serviço**
- `Produção de eventos` (item 12.13) → **é serviço**
- `Comércio varejista de artigos do vestuário` → **não é serviço**
- `Fabricação de produtos de padaria` → **não é serviço**

### 2.3 Arquitetura relevante (referência)

- `enquadramento_db.py` — motor de enquadramento CNAE → item LC 116.
  - `_texto_e_nao_servico(descricao)` — barreira pelo **início da descrição**.
    Usa `_tokens_iniciais()` para pegar os primeiros radicais em ordem.
  - `_NAO_SERVICO_INICIO` — prefixos que indicam não-serviço (comércio,
    fabricação, industrialização, produção, extração, agro).
  - `_ABERTURA_SERVICO` — prefixos que declaram serviço e sobrepõem a lista.
  - `comparar_item(descricao, item_desc)` — pontuação 0..1.
  - `_especificidade_legal()` — desempate entre itens vizinhos.
- `itens_lc116.py` — os 200 itens da LC 116/2003.
- `calc.py` — cálculo de faixas, alíquotas, repartição, DAS.
- `app.py` — Flask, rotas.
- `database.py` — SQLite.
- **A tabela `cnae` está vazia (0 registros).** Não há descrições oficiais
  gravadas; o sistema classifica a partir de `itens_lc116.py` e de texto
  informado. Não assumir que `item_para_cnae()` tem base.

---

## 3. Método de trabalho obrigatório

Ordem fixa. Não pular etapa.
1. **Diagnosticar antes de editar.** Escrever `_diag_*.py`, rodar, mostrar os
   números.
2. **Validação contra a LC 116 inteira.** Toda mudança no classificador deve
   verificar que **nenhum dos 200 itens da LC 116 é marcado como não-serviço**
   (eles são serviços por definição). Zero é o único número aceitável.
3. **Não quebrar o que passa.** Rodar a bateria de casos conhecidos antes e
   depois; comparar.
4. **Registrar a decisão** em `ALTERACOES.md` com evidência.
5. Nunca declarar "está certo" sem ter rodado a verificação.
6. **Apagar `__pycache__`** antes de rodar a verificação — ele mascara
   edição.
7. **Conferir que o app carrega:** `python -c "import app, enquadramento_db,
   calc, database"`.

---

## 4. Cicatrizes — erros já cometidos

### 4.1 Erros de raciocínio

| Erro | Por que foi errado | Correção |
|---|---|---|
| Procurar palavras de comércio/indústria em **qualquer posição** da descrição | Bloqueou 17 dos 200 itens da própria LC 116 (desenho industrial, confecção de páginas, produção de eventos, serviços portuários) | Olhar só a **abertura** da descrição |
| Usar `produt`, `mercad`, `textil`, `embalagem` como prefixos de bloqueio soltos | São objetos de serviço, não natureza da atividade | Só contar se abrirem a frase |
| Editar o motor sem rodar diagnóstico | Mudança quebrou serviços sem ninguém perceber | Diagnóstico primeiro, sempre |
| Afirmar "validado" com descrições inventadas por mim | Não eram as descrições oficiais de CNAE | Usar descrições oficiais e a LC 116 inteira |

### 4.2 Bugs armadilha já pagos com tempo (ler antes de mexer em texto)

| Armadilha | Sintoma | Regra |
|---|---|---|
| `_tokens_brutos()` devolve **`set`** | A ordem das palavras se perde: "Criação de bovinos" vira `{'bovino','criacao'}` e o primeiro termo deixa de ser o primeiro | Nunca usar `set` para decidir "primeira palavra". Ler o texto **em sequência** (`_tokens_iniciais`) |
| `_VAZIAS` continha `servico`/`servicos` | "Serviço de usinagem" perdia a primeira palavra e era lido como "usinagem" → barrado | `servico` **não** é palavra vazia: é o termo que decide a natureza |
| `_stem()` só tira o "s" de palavras com **mais de 4 letras** | `Serviço` → `servico` (não casa com o prefixo `servic`), mas `Serviços` → `servic` (casa). A **mesma regra funcionava no plural e falhava no singular** | Comparar por prefixo comum com no mínimo **5 letras** (`_abre_com`), nunca `startswith` cru |
| `startswith` cru cruza palavras diferentes | prefixo `usina` barrava `usinagem` | Usar `_abre_com`, que exige um ser prefixo do outro |
| Janela de 4 tokens é curta | No 12.13, "eventos" é a 5ª palavra de conteúdo e a regra não via | Usar **6** tokens e deixar o objeto de serviço ter precedência sobre o verbo |
| `__pycache__` mascara edição | O diagnóstico roda o código antigo e parece que a edição não funcionou | Ao ver resultado inexplicado, **apagar `__pycache__` antes** e reconferir com `inspect.getsource()` |

### 4.3 Casos especiais já decididos (não reabrir)

- **Distribuição de bens de terceiros** (item 10.10) → **serviço**.
- **Distribuição de energia, água, gás, combustível** → **não é serviço**
  (concessão/indústria). Só vale quando "distribuição" **abre** a frase —
  senão "análises clínicas, eletricidade médica" (4.02) cairia junto.
- **Produção de eventos/espetáculos/shows** (item 12.13) → **serviço**.
  O objeto manda, não o verbo "produção".
- **Serviço de usinagem sob encomenda** → **serviço** (usinagem própria
  aparece como "Fabricação", que já é barrada).
- **Florestamento / silvicultura** (item 7.16) → **serviço**.

### 4.4 Comando de verificação obrigatório

```
cd simples_app
Get-ChildItem -Recurse -Filter "__pycache__" -Directory | Remove-Item -Recurse -Force
python _diag_abertura.py
```

Critério de aceite, sem exceção: **`Falhas: 0`** e
**`Itens da LC 116 bloqueados: 0 de 200`**.

---

## 5. Histórico de sessões

### 2026-10-17 — Correção do classificador

Estado antes: casos de "deve ser não-serviço" falhando e a LC 116 com itens
barrados indevidamente.

Correções, em ordem:
1. `_tokens_iniciais` reescrita para ler o texto em sequência (antes usava
   `set`, perdendo a ordem).
2. `servico`/`servicos` removidos de `_VAZIAS` e de `_TERMOS_LEI`.
3. Criado `_abre_com` para casar prefixo tolerando singular/plural.
4. `usinagem`, `florestament`, `silvicultur`, `distribuic` retirados da lista
   de bloqueio; `producao` e `produc` separados.
5. Criadas `_PRODUCAO_DE_SERVICO` (12.13) e `_DISTRIBUICAO_NAO_SERVICO`.
6. Janela ampliada de 4 para 6 tokens.

Estado depois: `Falhas: 0` e `Itens da LC 116 bloqueados: 0 de 200`.

Decisão do usuário nesta sessão: **gravar permanentemente tudo o que ele
permite e proíbe, revisar este arquivo antes de perguntar, e gravar regras
novas na hora em que forem ditas** (ver seção 1.4).

---

## 6. Pendências — o que falta confirmar com o usuário

O Copilot **não tem acesso às conversas antigas**. As regras das seções 1 e 2
foram reconstruídas do código e das anotações, não das palavras do usuário.
**Se alguma estiver diferente do que ele disse, ele está certo.**

- [ ] Existe regra de negócio que **não** está registrada aqui?
- [ ] Existe algo que eu fiz e que ele **não quer que eu repita**?
- [ ] O critério de aceite (`Falhas: 0` + `0 de 200`) está completo?
- [ ] Cálculo, repartição ou relatórios têm regra própria a registrar?

**Como preencher:** quando o usuário responder, mover a resposta para a
seção correspondente e marcar a caixa. Nunca apagar uma pergunta sem
resposta — ela fica visível.
