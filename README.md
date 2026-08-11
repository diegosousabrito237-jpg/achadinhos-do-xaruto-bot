# Achadinhos do Xaruto — bot de ofertas

Bot do Telegram preparado para o canal `@achadinhosdoxaruto`. Ele roda na
nuvem pelo GitHub Actions, verifica os preços dos produtos monitorados a cada
30 minutos e publica somente quando o desconto chega a 35% ou mais.

## O que ele faz

- publica foto, título, preço anterior, preço atual e percentual de desconto;
- usa exclusivamente o link de afiliado informado pelo dono do canal;
- não repete a mesma oferta, a menos que o preço melhore bastante ou passem
  14 dias;
- permite controlar os produtos conversando com o bot pelo Telegram;
- só aceita comandos de administradores de `@achadinhosdoxaruto`;
- mantém o token secreto fora do código.

## Limite importante do Mercado Livre

O bot não inventa nem altera links de afiliado. Para preservar o rastreamento e
seguir a orientação do programa, cada produto deve receber um link criado no
Gerador de Links do Mercado Livre. Depois que o link é adicionado, a verificação
de preço e a publicação são automáticas.

Normalmente basta mandar o link curto ao bot. Caso ele não consiga descobrir o
produto por causa do redirecionamento, mande também o link normal do anúncio.

## Instalação no GitHub

1. Crie um repositório chamado `achadinhos-do-xaruto-bot`.
2. Envie todos os arquivos deste pacote, incluindo a pasta `.github`.
3. No repositório, abra **Settings → Secrets and variables → Actions**.
4. Clique em **New repository secret**.
5. Nomeie o segredo como `TELEGRAM_BOT_TOKEN`.
6. Cole o token fornecido pelo BotFather e salve.
7. Abra **Actions → Bot de ofertas → Run workflow** para executar a primeira
   vez.

O token nunca deve ser colocado em `bot.py`, no README ou em uma mensagem.

## Primeiro teste

Depois da primeira execução, abra uma conversa privada com o bot e envie:

```text
/teste
```

Em até 30 minutos, o bot processará o comando e publicará uma mensagem de teste
no canal. Para executar imediatamente, abra a ação no GitHub e clique em
**Run workflow**.

## Adicionar uma oferta

Envie ao bot:

```text
/adicionar https://meli.la/SEU_LINK
```

Se o link curto não revelar o produto, envie os dois links na mesma mensagem:

```text
/adicionar https://meli.la/SEU_LINK https://produto.mercadolivre.com.br/MLB-1234567890-produto-_JM
```

O bot responderá com o desconto atual. Se estiver abaixo de 35%, continuará
monitorando e publicará quando atingir o mínimo.

## Outros comandos

```text
/listar
/remover MLB1234567890
/ajuda
```

## Ajustes

No arquivo `.github/workflows/ofertas.yml`:

- `MIN_DISCOUNT: "35"` controla o desconto mínimo;
- `MAX_POSTS_PER_RUN: "1"` evita excesso de publicações;
- `cron: "7,37 * * * *"` executa duas vezes por hora.

## Aviso ao público

Cada publicação informa que o link é de afiliado e que o canal pode receber
comissão. Preços e disponibilidade podem mudar depois da publicação.
