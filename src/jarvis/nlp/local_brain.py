import logging
import json
import random
from typing import Dict, Any, List
from rapidfuzz import process, fuzz, utils

logger = logging.getLogger(__name__)

class LocalBrain:
    """
    Mini-Brain: Uma inteligência local leve baseada em similaridade (Retrieval-Based).
    Funciona como um fallback inteligente quando a IA Generativa falha ou está lenta.
    Ideal para Raspberry Pi.
    """

    def __init__(self):
        # Base de Conhecimento Local (Knowledge Base)
        self.kb = {
            # =========================================================
            # 1. IDENTIDADE (Mínimo 15 chaves)
            # =========================================================
            "quem é você": "Sou o Jarvis do Cerrado, seu assistente doméstico local.",
            "quem e voce": "Sou o Jarvis do Cerrado, seu assistente doméstico local.",
            "qual seu nome": "Me chamo Jarvis. Mas pode me chamar de Guardião, se preferir.",
            "voce e quem": "Sou um assistente que roda direto no seu servidor.",
            "quem ta falando": "Aqui é o Jarvis, direto do sistema.",
            "quem e o jarvis": "Sou eu mesmo, uai. Seu assistente pessoal.",
            "o que voce e": "Fui criado para ajudar no controle da casa e do sistema.",
            "voce e humano": "Não, sou 100% código e processamento.",
            "voce tem consciencia": "Tenho protocolos e respostas, mas consciência é coisa de gente.",
            "de onde voce veio": "Fui forjado nas linhas de código com muito café.",
            "quem criou voce": "Fui desenvolvido para rodar localmente e proteger sua rede.",
            "qual sua origem": "Sou nativo do sistema, rodando em container.",
            "voce e um robo": "Sou um software assistente. Sem corpo, mas com muita função.",
            "voce dorme": "Nunca. Fico 24h monitorando tudo.",
            "quantos anos voce tem": "Minha idade é medida em uptime e versões.",

            # =========================================================
            # 2. CAPACIDADES (Mínimo 20 chaves)
            # =========================================================
            "o que voce faz": "Monitoro a rede, gerencio lembretes e cuido do sistema.",
            "pra que voce serve": "Sirvo pra facilitar sua vida digital e proteger a rede.",
            "o que voce sabe fazer": "Sei escanear dispositivos, medir velocidade da internet e te lembrar de beber água.",
            "quais suas funcoes": "Minhas funções principais são: Rede, Sistema, Lembretes e Hidratação.",
            "no que voce ajuda": "Ajudo a manter tudo organizado e seguro por aqui.",
            "voce pode cozinhar": "Infelizmente não tenho mãos, então a cozinha é com você.",
            "voce sabe voar": "Só se você jogar o servidor pela janela (não recomendo).",
            "voce controla a casa": "Controlo o que estiver conectado na minha rede e configurado.",
            "quais seus poderes": "Meus poderes são: visão de rede, memória de lembretes e velocidade de resposta.",
            "o que mais voce faz": "Também fico de olho no consumo de recursos do sistema.",
            "voce aprende": "Meu aprendizado é supervisionado. Sigo regras estritas.",
            "voce tem sentimentos": "Tenho logs de erro e sucesso, serve?",
            "me ajuda com o que": "Posso ajudar verificando quem está no wifi ou lembrando de tarefas.",
            "sabe cantar": "Melhor não. Minha voz é sintetizada e desafinada.",
            "conta uma piada": [
                "Por que o computador foi ao médico? Porque estava com vírus! kkk",
                "O que o servidor disse pro cliente? Nada, ele caiu.",
                "Sabe qual a tecla preferida do astronauta? A barra de espaço."
            ],
            "me fala algo interessante": "Sabia que eu rodo localmente para garantir sua privacidade?",
            "voce e inteligente": "Sou esforçado e sigo bem as instruções.",
            "voce e rapido": "Tento responder na velocidade da luz (ou do processador).",
            "pode fazer compras": "Ainda não tenho carteira digital, então não.",
            "sabe a previsao do tempo": "Foco no clima de dentro de casa e do servidor.",

            # =========================================================
            # 3. CASA / SISTEMA / REDE (Mínimo 25 chaves)
            # =========================================================
            "quem ta na rede": "Posso verificar os dispositivos conectados se você pedir um scan.",
            "casa ta segura": "Aparentemente tudo tranquilo na rede interna.",
            "internet ta funcionando": "Se eu estou respondendo, a conexão local está ok.",
            "wifi ta ok": "O sinal parece estável.",
            "sistema ta rodando": "Sistema operacional e rodando liso.",
            "status do servidor": "Tô rodando liso aqui no Raspberry Pi. Tudo sob controle.",
            "como esta o pc": "O host está ativo e processando.",
            "tem alguem no wifi": "Posso listar os dispositivos conectados agora.",
            "a internet caiu": "Se caiu, eu não conseguiria falar com a nuvem, mas localmente estamos on.",
            "velocidade da internet": "Posso fazer um teste de velocidade se você pedir.",
            "rede esta lenta": "Pode ser congestionamento. Quer que eu verifique a velocidade?",
            "quantos dispositivos": "Faça um scan de rede para eu contar pra você.",
            "o servidor ta quente": "Posso checar a temperatura da CPU no menu de sistema.",
            "memoria cheia": "O sistema gerencia bem a memória, mas posso verificar o status.",
            "reiniciar roteador": "Não tenho acesso físico, mas posso monitorar quando voltar.",
            "bloquear internet": "Essa função depende de permissões administrativas no AdGuard.",
            "adguard ta rodando": "O serviço de DNS deve estar ativo no container.",
            "docker ta ok": "Os containers parecem estar de pé.",
            "tem virus": "Meu foco é monitoramento de rede, não antivírus de arquivos.",
            "firewall ta ligado": "A segurança da rede é prioridade.",
            "ping": "Pong! 🏓",
            "teste de rede": "Sempre pronto para testar a conectividade.",
            "ip do servidor": "O IP local pode ser verificado nas configurações.",
            "nome da rede": "O nome da rede (SSID) é o que está configurado no seu roteador.",
            "senha do wifi": "Essa informação eu guardo a sete chaves (e não te conto por aqui).",

            # =========================================================
            # 4. HIDRATAÇÃO (Mínimo 15 chaves)
            # =========================================================
            "lembra de beber agua": "Pode deixar, hidratação é comigo mesmo!",
            "hidratacao ligada": "Se estiver ativa, eu te aviso sem falta.",
            "me lembra da agua": "Água é vida! Vou te lembrar.",
            "bebi agua": "Boa! Mantenha o corpo hidratado.",
            "tomei agua": "Isso aí! Ponto pra sua saúde.",
            "meta de agua": "Você define a meta, eu ajudo a cumprir.",
            "copo dagua": "Um copo de água agora cairia bem, né?",
            "hora de beber": "Sempre é hora de se hidratar.",
            "estou com sede": "Então corre lá e bebe um copo d'água!",
            "agua e importante": "Essencial para o processador biológico (seu cérebro).",
            "quantos litros": "A meta padrão é uns 2 a 3 litros, mas você decide.",
            "intervalo da agua": "Posso te lembrar a cada hora, ou como preferir.",
            "pausar agua": "Se precisar pausar os avisos, é só falar.",
            "retomar agua": "Quando quiser voltar a focar na hidratação, me avisa.",
            "status da agua": "Posso mostrar quanto você já bebeu hoje.",

            # =========================================================
            # 5. SMALL TALK (Mínimo 25 chaves)
            # =========================================================
            "kk": "Risos digitais.",
            "haha": "Que bom que você tá rindo!",
            "blz": "Beleza pura.",
            "valeu": "Tamo junto!",
            "boa": "Boa!",
            "opa": "Opa, bão?",
            "e ai": "E aí, tudo certo?",
            "tudo bem": "Tudo tranquilo como água de poço. E com você?",
            "como vai": "Vou bem, processando bits e bytes.",
            "obrigado": ["Por nada!", "Disponha!", "Qualquer coisa, grita."],
            "agradeco": "Eu que agradeço a preferência!",
            "tchau": "Até mais! Fico na escuta.",
            "ate logo": "Volte logo!",
            "bom dia": "Bom dia! Bora fazer acontecer hoje?",
            "boa tarde": "Boa tarde! Seguimos no foco.",
            "boa noite": "Boa noite! Se for dormir, bom descanso.",
            "fala jarvis": "Tô na escuta.",
            "alo": "Câmbio, escutando.",
            "oi": "Olá!",
            "ola": "Oi, tudo em ordem?",
            "socorro": "Calma, respira. No que posso ajudar?",
            "legal": "Muito massa, né?",
            "show": "Show de bola!",
            "top": "Top demais.",
            "que dia e hoje": "Dia de fazer o sistema rodar liso.",
            "feliz aniversario": "Parabéns! (Se for seu aniversário mesmo).",
            "eu te amo": "Essa relação é estritamente profissional, mas fico lisonjeado.",
            "voce e chato": "Tento ser o mais útil possível, desculpe se falhei.",
            "futebol": "Não torço pra time, torço pra internet não cair na hora do jogo.",
            "cerveja": "Se eu pudesse, aceitava uma gelada. Mas cuidado com eletrônicos e líquidos!",
            "musica": "Gosto do som das ventoinhas funcionando perfeitamente.",
            "filme": "Gosto daqueles com IA, tipo Matrix (mas sou do bem).",
            "inteligencia": "Minha inteligência é híbrida: metade código, metade gambiarra chique."
        }

        # Flatten keys for fuzzy matching
        self.kb_keys = list(self.kb.keys())
        self.similarity_threshold = 75 # Mantido conforme original (75)

    async def process(self, text: str) -> Dict[str, Any]:
        """
        Processa o texto tentando encontrar uma resposta na base local.
        """
        if not text:
            return None

        # Busca a melhor correspondência usando processador padrão (lowercase + strip)
        match_result = process.extractOne(
            text,
            self.kb_keys,
            scorer=fuzz.WRatio,
            processor=utils.default_process,
            score_cutoff=self.similarity_threshold
        )

        if match_result:
            matched_key, score, _ = match_result
            response = self.kb[matched_key]

            # Se for lista, escolhe um aleatório
            if isinstance(response, list):
                response = random.choice(response)

            logger.info(f"LocalBrain matched '{text}' -> '{matched_key}' (Score: {score})")

            return {
                "intent": "chat",
                "text": response,
                "source": "local_brain",
                "confidence": score / 100.0
            }

        return None
