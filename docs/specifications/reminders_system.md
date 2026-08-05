# Especificação do sistema de lembretes

## Objetivo

Criar e entregar lembretes pelo Telegram com persistência local, interpretação de datas em português e operação previsível após reinícios.

## Intents

- `reminder_set`: inicia criação e extrai texto, horário, repetição e prioridade.
- `reminder_list`: lista lembretes ativos.
- `reminder_today`: filtra a agenda do dia.
- `reminder_overdue`: mostra itens vencidos.
- `reminder_update`: altera um lembrete existente.
- `reminder_delete`: remove por índice após entrada reconhecida.
- `flow_input`: continua uma criação/edição multietapas.

## Entradas aceitas

- relativas: `em 10 minutos`, `daqui 2 horas`;
- calendário: `amanhã às 9h`, dia da semana e data reconhecida;
- recorrentes: intervalos e expressões suportadas pelo parser;
- linguagem natural com variações como `lembra`, `lmebra` e `lembar`.

## Dados

Cada lembrete pode conter:

- identificador e proprietário (`chat_id`);
- texto;
- data/hora de execução;
- estado ativo/concluído;
- recorrência e intervalo;
- prioridade, categoria e modo de insistência quando disponíveis;
- tipo de ação, como lembrete comum ou hidratação.

Os dados são gravados por `Persistence` em SQLite dentro do volume `src/jarvis/database`.

## Fluxo

1. O roteador reconhece pedido de lembrete.
2. O parser extrai o que puder sem LLM.
3. Informações ausentes iniciam fluxo curto no `ContextEngine`.
4. O executor valida e salva.
5. O scheduler consulta itens vencidos.
6. A entrega usa envio seguro do Telegram e callbacks.
7. Confirmações de entrega atualizam o banco de forma idempotente.

Fluxos abandonados expiram após 10 minutos para evitar interpretar uma conversa futura como continuação.

## Regras de confiabilidade

- Não inventar data ausente.
- Não criar silenciosamente quando a frase estiver ambígua.
- Não depender de LLM ou API paga.
- Não duplicar entrega ao processar o mesmo callback.
- Preservar lembretes durante rebuild do contêiner.
- Registrar erros sem expor token ou dados secretos.

## Exemplos de teste

```text
me lembra teste 2 min
me lembra de tomar remédio amanhã às 9h
listar lembretes
lembretes de hoje
apagar lembrete 1
editar lembrete 1
```

Mudanças no parser, scheduler, callbacks ou banco exigem testes automatizados específicos antes de deploy.
