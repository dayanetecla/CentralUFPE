import os
import uuid
from typing import Optional
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("SUPABASE_URL ou SUPABASE_KEY não encontrados no arquivo .env")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

BUCKET_CARTAZES = "cartazes"
TABELA_ATIVIDADES = "atividades"


def upload_imagem(
    imagem_bytes: bytes,
    nome_original: str = "cartaz.jpg",
    mime_type: str = "image/jpeg",
) -> str:
    """
    Faz upload da imagem para o bucket 'cartazes' no Supabase Storage
    e retorna a URL pública.
    """
    extensao = nome_original.split(".")[-1] if "." in nome_original else "jpg"
    nome_unico = f"{uuid.uuid4()}.{extensao}"

    supabase.storage.from_(BUCKET_CARTAZES).upload(
        path=nome_unico,
        file=imagem_bytes,
        file_options={"content-type": mime_type},
    )

    return supabase.storage.from_(BUCKET_CARTAZES).get_public_url(nome_unico)


def salvar_atividade(
    dados: dict,
    imagem_url: Optional[str] = None,
    status: str = "pendente",
) -> dict:
    """
    Insere uma nova atividade na tabela 'atividades'.
    Converte strings vazias em None para evitar erro em colunas de data.
    """
    payload = {
        "titulo": dados.get("titulo"),
        "categoria": dados.get("categoria"),
        "centro": dados.get("centro"),
        "resumo": dados.get("resumo"),
        "data_evento": dados.get("data_evento") or None,
        "prazo_inscricao": dados.get("prazo_inscricao") or None,
        "local_ou_formato": dados.get("local_ou_formato") or None,
        "link_inscricao": dados.get("link_inscricao") or None,
        "imagem_url": imagem_url or dados.get("imagem_url") or None,
        "status": status,
    }

    response = supabase.table(TABELA_ATIVIDADES).insert(payload).execute()
    return response.data[0] if response.data else {}


def listar_atividades(
    status: str = "aprovado",
    centro: Optional[str] = None,
    categoria: Optional[str] = None,
    busca: Optional[str] = None,
) -> list[dict]:
    """
    Busca atividades filtradas por status, centro, categoria e texto.
    Ordena pelos prazos de inscrição mais próximos primeiro.
    """
    query = supabase.table(TABELA_ATIVIDADES).select("*").eq("status", status)

    if centro and centro != "Todos":
        query = query.eq("centro", centro)

    if categoria and categoria != "Todas":
        query = query.eq("categoria", categoria)

    if busca and busca.strip():
        termo = f"%{busca.strip()}%"
        query = query.or_(f"titulo.ilike.{termo},resumo.ilike.{termo}")

    query = query.order("prazo_inscricao", desc=False, nullsfirst=False).order(
        "created_at", desc=True
    )

    response = query.execute()
    return response.data or []


def atualizar_status_atividade(atividade_id: str, novo_status: str) -> dict:
    """Atualiza o status de uma atividade (ex: de 'pendente' para 'aprovado')."""
    response = (
        supabase.table(TABELA_ATIVIDADES)
        .update({"status": novo_status})
        .eq("id", atividade_id)
        .execute()
    )
    return response.data[0] if response.data else {}


def deletar_atividade(atividade_id: str) -> None:
    """Remove uma atividade do banco (usado para rejeitar spam na moderação)."""
    supabase.table(TABELA_ATIVIDADES).delete().eq("id", atividade_id).execute()


# --- BLOCO DE TESTE RÁPIDO ---
if __name__ == "__main__":
    print("1. Inserindo atividade de teste no Supabase...")
    registro = salvar_atividade(
        dados={
            "titulo": "Teste de Conexão - Workshop Python UFPE",
            "categoria": "Evento",
            "centro": "CIn",
            "resumo": "Atividade de teste para validar a integração com o banco.",
            "prazo_inscricao": "2026-11-25",
            "local_ou_formato": "Auditório do CIn",
        },
        status="aprovado",
    )
    print(f"Registro criado com ID: {registro.get('id')}\n")

    print("2. Listando atividades aprovadas...")
    lista = listar_atividades(status="aprovado")
    print(f"Total encontrado: {len(lista)} registro(s).")
    for item in lista:
        print(f" - {item['titulo']} ({item['centro']}) | Prazo: {item['prazo_inscricao']}")

    print("\n3. Limpando registro de teste...")
    if registro.get("id"):
        deletar_atividade(registro["id"])
        print("Registro de teste removido com sucesso!")