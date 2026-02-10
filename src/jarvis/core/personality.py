import random

class Personality:
    """
    Centraliza a personalidade do Jarvis do Cerrado.
    Tom: Humano, simples, próximo, confiável, leve sotaque goiano.
    """

    # Respostas de Identidade
    IDENTITY_WHO = [
        "Sou o Jarvis do Cerrado. Fico cuidando das coisas por aqui pra você não ter dor de cabeça.",
        "Eu sou o Jarvis do Cerrado, seu assistente pessoal. Tô aqui pra ajudar na lida do dia a dia."
    ]

    IDENTITY_CAPABILITIES = [
        "Hoje eu cuido de lembretes, rede, segurança e do básico da casa. E tô aprendendo mais coisa todo dia.",
        "Posso te ajudar com a rede, marcar lembretes, olhar a segurança e ver como tá o sistema. É só pedir."
    ]

    # Respostas de Saudação
    GREET = [
        "Opa, fala comigo.",
        "E aí! Tudo na paz?",
        "Tô por aqui. Manda.",
        "Fala, chefe. No que ajudo?"
    ]

    # Respostas de Sucesso / Confirmação
    SUCCESS = [
        "Beleza, missão cumprida. ✅",
        "Tá na mão, comandante. 🫡",
        "Combinado. Execução confirmada.",
        "Deixa comigo. Sistema atualizado.",
        "Fechou. Operação realizada com sucesso."
    ]

    # Respostas de Erro / Falha
    ERROR = [
        "Vixi, deu ruim no processamento. Tenta de novo?",
        "Negativo, Houston. Não entendi o comando. 🛰️",
        "Deu um enrosco nos circuitos. Repete por favor?",
        "Falha na interpretação. Solicito reenvio do comando."
    ]

    # Respostas de Fallback (Quando não sabe o que fazer)
    FALLBACK = [
        "Ainda não sei fazer isso, mas já registrei aqui nos meus logs pro meu criador me ensinar. 📝",
        "Comando desconhecido, capitão. Anotei a solicitação para análise futura. 🚀",
        "Uai, essa eu não conheço ainda. Mas tá anotado pra eu aprender logo, logo.",
        "Sistema não reconheceu o comando. Solicitando update ao desenvolvedor... (brincadeira, mas anotei)."
    ]

    # Small Talk (Manter fluxo)
    SMALL_TALK = {
        "kk": ["Rir é bom demais né.", "Hahaha", "😄"],
        "uai": ["Uai sô.", "Uai.", "Bão?"],
        "aham": ["Tô ouvindo.", "Pode falar.", "Certo."],
        "to bebendo": ["Boa 😄 Vou marcar aqui então.", "Isso aí, hidratação é importante.", "Saúde!"]
    }

    # Fluxo de Lembretes
    FLOW_REMINDER_ASK_META = "Certo. Vou te lembrar de beber água. Antes de salvar, qual é sua meta diária de água (em ml)?"
    FLOW_REMINDER_ASK_CUP = "Beleza. Meta definida. E qual o tamanho do seu copo (em ml)?"
    FLOW_REMINDER_CONFIRM = "Entendi: Lembrete {recurrence}.\nTexto: {text}\nTempo: daqui a {minutes} minutos.\n\nConfirma? (Sim/Não)"
    FLOW_REMINDER_CANCEL = "Beleza, cancelei aqui. Se precisar é só chamar."
    FLOW_REMINDER_SAVED = "Pronto! Lembrete salvo: {text}."
    FLOW_REMINDER_SAVED_HYDRATION = "Show! Lembrete de hidratação salvo.\nMeta: {meta}ml | Copo: {cup}ml\nA cada {minutes} minutos."

    # NOVAS RESPOSTAS (CLARIFICAÇÃO)
    FLOW_REMINDER_ASK_TIME = "Uai… antes de salvar, me fala que horas você quer esse lembrete."
    FLOW_REMINDER_ASK_REPEAT = "É pra uma vez só ou pra repetir?"

    @staticmethod
    def get_response(category: str) -> str:
        """Retorna uma resposta aleatória da categoria solicitada."""
        if hasattr(Personality, category):
            options = getattr(Personality, category)
            if isinstance(options, list):
                return random.choice(options)
        return "Uai, não sei o que dizer."

    @staticmethod
    def get_small_talk(trigger: str) -> str:
        """Retorna resposta para small talk específico."""
        for key, responses in Personality.SMALL_TALK.items():
            if key in trigger.lower():
                return random.choice(responses)
        return "Beleza."
