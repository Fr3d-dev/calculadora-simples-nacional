# LEIA-ME — esta pasta é a memória do Copilot sobre o projeto

Não é documentação do sistema para usuários. É o que me faz lembrar como
trabalhamos aqui, mesmo depois de um ano sem abrir o projeto.

| Arquivo | O que é | Quem escreve |
|---|---|---|
| `copilot-instructions.md` | Minha lei: proibições, regras de negócio, método de trabalho, cicatrizes, pendências | Eu, com base no que o usuário decide |
| `MEMORIA.md` | Mapa verificado do código: arquivos, rotas, bancos, como rodar. Toda afirmação tem a fonte marcada | Eu, lendo o código |
| `REGRAS.md` | Diário cronológico de tudo que o usuário disse que pode ou não pode | Eu, **na hora** em que ele fala |

## Para quem voltar daqui a um ano

1. Abra esta pasta como workspace no VS Code — o `copilot-instructions.md`
   é carregado automaticamente.
2. Se o Copilot parecer não saber nada, peça a ele para ler os três arquivos.
3. O que estiver desatualizado deve ser corrigido **com data**, nunca
   apagado. O histórico é parte da memória.

## Aviso gravado em 2026-10-17

O histórico da conversa de 2026-10-17 foi apagado automaticamente. Regras
ditas nela e não gravadas em arquivo se perderam. Os itens não confirmados
estão listados na seção 7 do `MEMORIA.md` — **não foram preenchidos por
suposição**.

## Recuperar no Git

Estes três arquivos ainda não foram commitados. Para versioná-los junto com
o resto:

```powershell
git add .github
git commit -m "memoria de trabalho do Copilot: instrucoes, mapa do projeto e regras"
```
