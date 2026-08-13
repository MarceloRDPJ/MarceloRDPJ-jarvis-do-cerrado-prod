# Nó Android Poco X3 NFC

## Decisão arquitetural

O Raspberry Pi continua sendo o núcleo confiável do Jarvis: Telegram, regras,
agenda, banco principal, monitoramento da rede e ações sensíveis permanecem no
Pi. O Poco X3 NFC (`surya`) funciona como satélite de voz, interface física e
worker para tarefas que se beneficiam do Android, da câmera ou de mais CPU/RAM.

O funcionamento normal não depende de ADB. ADB é usado apenas para preparação,
manutenção e desenvolvimento. Em produção, o Poco permanece carregando pela
USB-C e comunica-se com o Pi pela rede Wi-Fi local.

## Responsabilidades

### Raspberry Pi

- fonte de verdade dos lembretes, contas e histórico;
- bot do Telegram e autorização por `ALLOWED_USER_ID`;
- roteamento determinístico de intents;
- Mosquitto ou transporte HTTPS local autenticado;
- fila de jobs, supervisão e política de retentativas;
- rede, AdGuard, Wake-on-LAN e Home Assistant;
- validação final antes de apresentar ou persistir resultados.

### Poco X3 NFC

- interface neural e respostas faladas;
- palavra de ativação e transcrição de comandos;
- alarmes locais sincronizados;
- RPA somente leitura nos aplicativos oficiais;
- OCR, QR/barcode, imagem, áudio e documentos;
- diagnóstico Wi-Fi e speedtest a partir do celular;
- câmera e sensores quando uma skill explícita solicitar;
- cache local e fila de resultados para sobreviver a oscilações do Wi-Fi.

## Transporte e estados

O transporte previsto é MQTT local autenticado, sem exposição à internet. Cada
tarefa possui `job_id`, versão, ação permitida, prazo, nonce e assinatura. O
estado percorre:

```text
queued -> accepted -> running -> completed
                            `-> failed
                            `-> expired
```

O Poco persiste o job antes de confirmá-lo. Reenvio com o mesmo `job_id` nunca
repete um efeito. Se o Wi-Fi cair durante a execução, o job termina localmente e
o resultado permanece na fila até a reconexão.

Tópicos previstos:

```text
jarvis/poco/heartbeat
jarvis/poco/status
jarvis/poco/jobs
jarvis/poco/results
jarvis/poco/events
jarvis/poco/alerts
```

## RPA de contas

Saneago é consultada pelo aplicativo oficial instalado pela Play Store. A
Equatorial é consultada pelo portal oficial aberto no Chrome, porque o aplicativo
recusa execução quando a depuração Android está ativa. Login e sessão permanecem
no Android. O Pi não recebe senha, cookie ou credencial do titular.

O fluxo reconhece telas por `resource-id`, texto e descrição. OCR visual é
fallback para WebView/Canvas; coordenadas fixas não são o método principal. Uma
tela desconhecida encerra a execução e produz diagnóstico sanitizado.

O agente não pode pagar, confirmar PIX, negociar dívida, solicitar religação,
trocar titularidade ou alterar cadastro. Essas ações permanecem fora da lista de
jobs, mesmo quando a interface do aplicativo as oferece.

A leitura Saneago permite somente conta, valor da fatura atual, referência,
vencimento e consumo. Nome do titular e endereço são descartados no Android e
não entram no resultado, logs ou armazenamento do Pi.

## Disponibilidade

O Poco envia heartbeat periódico e o Pi aplica backoff e circuit breaker. A
ausência de heartbeat não dispara cliques nem reinícios em loop. Depois de uma
falha, a recuperação segue: reconexão, reinício do agente, reinício do app alvo
e alerta. Reinício completo do aparelho é último recurso.

Se o Pi ficar indisponível, o Poco mantém interface, alarmes já sincronizados,
diagnóstico local e cache. Um modo de contingência do Telegram só poderá ser
ativado depois de implementar eleição que impeça Pi e Poco de consumir o mesmo
token simultaneamente.

## Energia e temperatura

- Poco e Pi usam alimentação própria; o Poco não alimenta o Pi por OTG.
- ADB sem fio pareado ou o agente local permitem manter a USB-C no carregador.
- O aparelho opera sem capa, em suporte ventilado e fora de caixas fechadas.
- A interface reduz FPS e brilho em repouso.
- O agente consulta bateria e status térmico do Android.
- Estado térmico `MODERATE` suspende OCR, STT e speedtest pesados.
- Estado `SEVERE` encerra workers, apaga a tela e alerta o Pi.
- Limites numéricos de bateria são política conservadora ajustada por benchmark,
  não especificação oficial da Xiaomi.

## Sistema e segurança

A primeira implantação usa a ROM global oficial, bootloader bloqueado, Verified
Boot e SELinux. LineageOS só será considerado se testes prolongados demonstrarem
que a MIUI não sustenta o agente. Root, bootloader desbloqueado, Docker em PRoot
e ADB TCP/5555 permanente não fazem parte da arquitetura.

O Poco deve ser dedicado, sem aplicativos bancários ou dados pessoais. O agente
aceita somente ações enumeradas, guarda chaves no Android Keystore e não oferece
shell genérico ao Telegram. Logs e screenshots não podem conter CPF, senha,
token, código de barras ou conteúdo integral de faturas por padrão.

## Fases de entrega

1. inventário, limpeza reversível e baseline térmico;
2. instalação dos apps oficiais e login manual;
3. prova de comunicação Wi-Fi e heartbeat;
4. agente Android mínimo com fila persistente;
5. RPA somente leitura da Equatorial;
6. RPA somente leitura da Saneago;
7. intents e respostas de contas no Telegram;
8. diagnóstico de internet Pi versus Poco;
9. voz, alarmes e interface neural;
10. teste de estabilidade e recuperação por pelo menos 30 dias.
