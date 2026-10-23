# REGRAS.md — regras que o usuário me deu durante o trabalho

> Registro cronológico. **Não apagar linha antiga.** Se uma regra mudar,
> acrescentar a nova entrada dizendo que substitui a anterior.
>
> Regra de negócio ou proibição importante também vai para
> `.github/copilot-instructions.md` (seções 1 e 2), que é o que eu leio
> sozinho no começo de toda conversa.

---

## 2026-10-17 — Memória do projeto

- **Pode:** manter uma memória de trabalho minha, para eu lembrar do sistema
  quando voltarmos a mexer nele meses depois.
- **Não pode:** tratar essa memória como documentação para outras pessoas.
  É para meu uso ao ajudar o usuário.
- **Fazer sempre:** consultar a memória antes de perguntar qualquer coisa.
  Perguntar só o que não está registrado.
- **Fazer sempre:** gravar na hora — na mesma resposta — qualquer coisa que o
  usuário disser que pode ou não pode fazer.
- **Origem:** usuário pediu explicitamente que eu grave tudo, inclusive as
  permissões e proibições, para não precisar repetir instruções.

## 2026-10-17 — Não inventar coisas

- **Não pode:** inventar. Nem dado, nem descrição de CNAE, nem regra, nem
  resultado, nem memória do que o usuário disse.
- **Não pode:** preencher lacuna com suposição e apresentar como fato.
- **Fazer sempre:** o que não está registrado nem no código, eu não sei — e
  digo que não sei.
- **Fazer sempre:** separar o que é dado do que é dedução minha.
- **Origem:** instrução direta do usuário.

## 2026-10-17 — Memória do projeto criada

- Criado `.github/MEMORIA.md`: mapa verificado do código (arquivos, rotas,
  bancos, como rodar), com a fonte de cada afirmação marcada.
- O que não foi verificado fica na seção 7 como dúvida em aberto — não é
  preenchido por suposição.
- **Fonte:** pedido do usuário — "criar sua memória desse projeto com base no
  que fomos conversando hoje e no que eu fui pontuando".
- **Aviso registrado:** o histórico anterior desta conversa foi apagado
  automaticamente, então regras ditas antes e não gravadas em arquivo não
  podem ser recuperadas por mim.

## 2026-10-17 — Git: não commitar a memória

- **Não pode:** rodar `git add` / `git commit` para versionar a pasta
  `.github/`.
- Os arquivos de memória ficam salvos localmente, fora do Git. Usuário
  decidiu que "está bom assim".
- **Não repetir a oferta** de commit a menos que o usuário peça.
- **Origem:** resposta direta do usuário à minha sugestão de commit.
