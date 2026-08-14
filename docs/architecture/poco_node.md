# Nó Android Poco X3 NFC

## Decisão arquitetural

O Raspberry Pi continua sendo o núcleo confiável do ROD: Telegram, regras,
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

O transporte implementado é HTTP na LAN entre o agente e a API do Pi. Corpo e
caminho de cada requisição são autenticados com HMAC-SHA256, timestamp curto e
segredo aleatório guardado no Android Keystore. A criação de jobs aceita somente
chamadas locais do Pi. Não existe shell remoto nem porta aberta no Poco. Cada
tarefa possui `job_id`, ação enumerada e prazo. O estado percorre:

```text
queued -> accepted -> running -> completed
                            `-> failed
                            `-> expired
```

O Pi persiste fila, heartbeat e resultados em `storage/poco_node.json`. Jobs
abandonados expiram e não bloqueiam a fila seguinte. O agente consulta a fila a
cada 20 segundos e sempre devolve `completed` ou `failed` com erro sanitizado.

## RPA de contas

Saneago é consultada pelo aplicativo oficial instalado pela Play Store. O agente
acorda a tela por tempo limitado, descarta somente o bloqueio simples, abre o app,
lê primeiro a árvore de acessibilidade e usa OCR local ML Kit como fallback. A
sessão e as credenciais permanecem no Android. Login, senha e contas são cifrados
com AES-GCM por uma chave não exportável do Android Keystore; o Pi não recebe
senha, cookie, CPF, data de nascimento ou credencial.

A Equatorial usa o portal oficial no Chrome do Poco. O agente preenche CPF, data
de nascimento e unidade configurada, lê somente valor, referência e vencimento e
descarta os demais dados. Se Imperva, CAPTCHA ou outra verificação humana aparecer,
a tarefa encerra com diagnóstico explícito. O ROD não burla proteção antibot e
jamais apresenta uma consulta simulada.

O fluxo reconhece telas por `resource-id`, texto e descrição. OCR visual é
fallback para WebView/Canvas; coordenadas fixas não são o método principal. Uma
tela desconhecida encerra a execução e produz diagnóstico sanitizado.

O agente não pode pagar, confirmar PIX, negociar dívida, solicitar religação,
trocar titularidade ou alterar cadastro. Essas ações permanecem fora da lista de
jobs, mesmo quando a interface do aplicativo as oferece.

A leitura Saneago permite somente conta, valor da fatura atual, referência,
vencimento e consumo. Nome do titular e endereço são descartados no Android e
não entram no resultado, logs ou armazenamento do Pi.

Para evitar associar uma fatura ao imóvel errado, cada job leva apenas a chave
estável do imóvel (`kitnet_01`, `kitnet_02`, `sala_comercial` ou `casa`). O Poco
resolve o número no cofre. Na Saneago, uma conta diferente da solicitada causa
falha explícita; o ROD não renomeia o resultado incorreto.

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

## Estado da entrega

Implementado: inventário, agente Android, Keystore, heartbeat, fila persistente,
status/bateria/temperatura, validação real de internet, painel RDP, cofre das oito
unidades, login assistido Saneago, leitura Saneago, fluxo Equatorial via Chrome e
intents por imóvel.

Uma consulta só é considerada validada quando a concessionária devolve conteúdo
acessível no aparelho real. Mudanças de tela, CAPTCHA ou conta selecionada errada
geram falha honesta. Voz, alarmes e interface neural animada permanecem evolução
posterior, separada do núcleo confiável.
