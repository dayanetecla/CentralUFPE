import os
from typing import Optional
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from services.ai_extractor import extrair_dados_atividade
from services.database import (
    atualizar_status_atividade,
    deletar_atividade,
    listar_atividades,
    salvar_atividade,
    upload_imagem,
)

load_dotenv()
SENHA_MODERACAO = os.getenv("SENHA_MODERACAO", "ufpe123")

app = FastAPI(title="Central UFPE API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Em produção, substitua pela URL do seu frontend
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class NovaAtividadeRequest(BaseModel):
    titulo: str
    categoria: str
    centro: str
    resumo: str
    data_evento: Optional[str] = None
    prazo_inscricao: Optional[str] = None
    local_ou_formato: Optional[str] = None
    link_inscricao: Optional[str] = None
    imagem_url: Optional[str] = None


@app.get("/atividades")
def get_atividades(
    centro: Optional[str] = None,
    categoria: Optional[str] = None,
    busca: Optional[str] = None,
):
    return listar_atividades(
        status="aprovado", centro=centro, categoria=categoria, busca=busca
    )


@app.post("/extrair")
async def post_extrair(
    texto: Optional[str] = Form(None),
    imagem: Optional[UploadFile] = File(None),
):
    if not texto and not imagem:
        raise HTTPException(400, "Envie um texto ou uma imagem.")

    img_bytes = await imagem.read() if imagem else None
    mime = imagem.content_type if imagem else "image/jpeg"

    extraido = extrair_dados_atividade(
        texto=texto, imagem_bytes=img_bytes, mime_type=mime
    )

    imagem_url = None
    if img_bytes and imagem:
        imagem_url = upload_imagem(
            imagem_bytes=img_bytes,
            nome_original=imagem.filename or "cartaz.jpg",
            mime_type=mime,
        )

    return {**extraido.model_dump(), "imagem_url": imagem_url}


@app.post("/atividades")
def post_atividade(
    payload: NovaAtividadeRequest,
    x_senha_moderacao: Optional[str] = Header(None),
):
    status = "aprovado" if x_senha_moderacao == SENHA_MODERACAO else "pendente"
    return salvar_atividade(dados=payload.model_dump(), status=status)


@app.get("/moderacao/pendentes")
def get_pendentes(x_senha_moderacao: Optional[str] = Header(None)):
    if x_senha_moderacao != SENHA_MODERACAO:
        raise HTTPException(401, "Senha de moderação inválida.")
    return listar_atividades(status="pendente")


@app.patch("/moderacao/{atividade_id}/aprovar")
def patch_aprovar(
    atividade_id: str, x_senha_moderacao: Optional[str] = Header(None)
):
    if x_senha_moderacao != SENHA_MODERACAO:
        raise HTTPException(401, "Senha de moderação inválida.")
    return atualizar_status_atividade(atividade_id, "aprovado")


@app.delete("/moderacao/{atividade_id}")
def delete_atividade(
    atividade_id: str, x_senha_moderacao: Optional[str] = Header(None)
):
    if x_senha_moderacao != SENHA_MODERACAO:
        raise HTTPException(401, "Senha de moderação inválida.")
    deletar_atividade(atividade_id)
    return {"ok": True}