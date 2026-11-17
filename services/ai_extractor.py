import os
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Optional

from dotenv import load_dotenv
from google import genai
from google.genai import types

from services.models import AtividadeExtraida

load_dotenv()

client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY"),
    http_options={"api_version": "v1beta"},
)


def extrair_dados_atividade(
    texto: Optional[str] = None,
    imagem_bytes: Optional[bytes] = None,
    mime_type: str = "image/jpeg",
) -> AtividadeExtraida:
    """
    Recebe texto de divulgação e/ou bytes de um cartaz/print e retorna
    os dados estruturados conforme o modelo AtividadeExtraida.
    """
    if not texto and not imagem_bytes:
        raise ValueError("Forneça pelo menos um texto ou uma imagem.")

    hoje_recife = datetime.now(ZoneInfo("America/Recife")).strftime("%Y-%m-%d (%A)")

    system_instruction = f"""
    Você é um assistente especializado em organizar oportunidades acadêmicas da UFPE (Universidade Federal de Pernambuco).
    Sua tarefa é ler cartazes (imagens) e/ou textos de divulgação e extrair as informações estruturadas.

    Regras importantes:
    1. A data de hoje em Recife é {hoje_recife}. Use isso para calcular datas relativas como "amanhã", "nesta sexta" ou "até dia 20" e converta sempre para YYYY-MM-DD.
    2. Identifique o centro da UFPE pelo contexto (ex: RobôCIn, CITi, LIANA -> CIn; PET Engenharia, Concreto -> CTG; Liga de Cardiologia -> CCS). Se não ficar claro, use 'Geral/Reitoria'.
    3. Não invente links ou datas que não estejam no material. Se não encontrar, retorne null.
    """

    conteudos = []

    if imagem_bytes:
        conteudos.append(
            types.Part.from_bytes(data=imagem_bytes, mime_type=mime_type)
        )

    if texto and texto.strip():
        conteudos.append(f"Texto da divulgação:\n{texto.strip()}")
    else:
        conteudos.append("Extraia todas as informações presentes na imagem acima.")

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=conteudos,
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            response_mime_type="application/json",
            response_schema=AtividadeExtraida,
            temperature=0.1,
        ),
    )

    return response.parsed


# --- BLOCO DE TESTE RÁPIDO ---
if __name__ == "__main__":
    print("Testando extração com texto simulado da UFPE...\n")

    texto_teste = """
    🚀 PROCESSO SELETIVO LIGIA 2026.2!
    Estão abertas as inscrições para a Liga Acadêmica de Inteligência Artificial do CIn-UFPE!
    Quer aprender na prática sobre LLMs, Visão Computacional e participar de projetos reais?
    📅 Inscrições até esta sexta-feira!
    📍 Aula inaugural presencial no Auditório do CIn.
    🔗 Inscreva-se pelo link: https://forms.gle/exemploLigiaUFPE ou siga @ligia.ufpe
    """

    resultado = extrair_dados_atividade(texto=texto_teste)
    print(resultado.model_dump_json(indent=2))