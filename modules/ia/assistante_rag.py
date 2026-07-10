# modules/ia/assistante_rag.py
from langchain_ollama import OllamaLLM
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

class AssistenteRAG:
    def __init__(self, gerenciador_vetores, modelo_nome: str = "llama3.1"):
        self.gerenciador_vetores = gerenciador_vetores
        print(f"Inicializando modelo local '{modelo_nome}' via Ollama...")
        self.llm = OllamaLLM(model=modelo_nome)
        self.parser = StrOutputParser()

    def perguntar(self, pergunta_usuario: str) -> str:
        # Aumentamos para 10 para varrer bem todos os documentos
        contextos_brutos = self.gerenciador_vetores.buscar_contexto(pergunta_usuario, quantidade_resultados=10)
        
        # DEBUG PARA O DESENVOLVEDOR (VOCÊ):
        print("\n" + "-"*40)
        print("🔍 O QUE O BANCO VETORIAL ACHOU PARA A IA LER:")
        for i, trecho in enumerate(contextos_brutos):
            # Imprime os primeiros 100 caracteres de cada pedaço para você ver
            print(f"[{i+1}] {trecho[:100]}...") 
        print("-"*40 + "\n")

        contexto_unificado = "\n\n".join(contextos_brutos)

        prompt = ChatPromptTemplate.from_messages([
            ("system", (
                "Você é um assistente executivo focado em analisar documentos profissionais e dados de lojas.\n"
                "Responda de forma clara e direta, baseando-se EXCLUSIVAMENTE no Contexto abaixo.\n"
                "Se a informação não estiver clara no contexto, diga honestamente que não encontrou.\n\n"
                "--- CONTEXTO ---\n"
                "{contexto}\n"
                "-----------------"
            )),
            ("user", "{pergunta}")
        ])

        cadeia = prompt | self.llm | self.parser
        return cadeia.invoke({"contexto": contexto_unificado, "pergunta": pergunta_usuario})