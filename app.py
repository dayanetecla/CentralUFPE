import os
from datetime import date, datetime
from typing import get_args
from zoneinfo import ZoneInfo

import streamlit as st
from dotenv import load_dotenv

from services.ai_extractor import extrair_dados_atividade
from services.database import (
    atualizar_status_atividade,
    deletar_atividade,
    listar_atividades,
    salvar_atividade,
    upload_imagem,
)
from services.models import CategoriaTipo, CentroUFPE

load_dotenv()

st.set_page_config(
    page_title="Central UFPE | Oportunidades e Extensão",
    page_icon="🎓",
    layout="wide",
)

CATEGORIAS = list(get_args(CategoriaTipo))
CENTROS = list(get_args(CentroUFPE))
SENHA_MODERACAO = os.getenv("SENHA_MODERACAO", "ufpe123")


def hoje_recife() -> date:
    return datetime.now(ZoneInfo("America/Recife")).date()


def parse_data_iso(data_str: str | None) -> date | None:
    if not data_str:
        return None
    try:
        return date.fromisoformat(str(data_str)[:10])
    except ValueError:
        return None


def formatar_badge_prazo(prazo_str: str | None) -> tuple[str, bool]:
    """Retorna o texto do badge de urgência e um booleano indicando se já venceu."""
    prazo = parse_data_iso(prazo_str)
    if not prazo:
        return "🟢 Fluxo contínuo / Sem prazo", False

    dias_restantes = (prazo - hoje_recife()).days
    data_br = prazo.strftime("%d/%m/%Y")

    if dias_restantes < 0:
        return f"⚫ Encerrado ({data_br})", True
    if dias_restantes == 0:
        return f"🔥 Encerra HOJE ({data_br})", False
    if dias_restantes <= 3:
        return f"⚠️ Encerra em {dias_restantes} dia(s) ({data_br})", False
    return f"📅 Inscrições até {data_br}", False


def formatar_link_botao(link: str | None) -> tuple[str, str] | None:
    """Converte URLs ou @arrobas do Instagram em (rotulo, url_valida)."""
    if not link or not link.strip():
        return None
    limpo = link.strip()
    if limpo.startswith(("http://", "https://")):
        return ("🔗 Acessar Inscrição / Edital", limpo)
    if limpo.startswith("@"):
        usuario = limpo.lstrip("@").split()[0]
        return (f"📸 Ver no Instagram ({limpo})", f"https://instagram.com/{usuario}")
    return None


# --- CABEÇALHO ---
st.title("🎓 Central de Oportunidades — UFPE")
st.caption(
    "Ligas acadêmicas, projetos de extensão, empresas juniores, monitorias e eventos reunidos em um só lugar."
)

aba_mural, aba_publicar, aba_moderacao = st.tabs(
    ["📌 Mural de Oportunidades", "✨ Divulgar Atividade (IA)", "🛡️ Moderação"]
)

# ==============================================================================
# ABA 1: MURAL PÚBLICO
# ==============================================================================
with aba_mural:
    with st.sidebar:
        st.header("🔍 Filtros")
        filtro_busca = st.text_input(
            "Buscar por palavra-chave", placeholder="Ex: IA, robótica, saúde, edital..."
        )
        filtro_centro = st.selectbox("Centro Acadêmico", ["Todos"] + CENTROS)
        filtro_categoria = st.selectbox("Categoria", ["Todas"] + CATEGORIAS)
        ocultar_encerrados = st.checkbox("Ocultar prazos já encerrados", value=True)

    atividades = listar_atividades(
        status="aprovado",
        centro=filtro_centro,
        categoria=filtro_categoria,
        busca=filtro_busca,
    )

    atividades_filtradas = []
    for item in atividades:
        badge_texto, vencido = formatar_badge_prazo(item.get("prazo_inscricao"))
        if ocultar_encerrados and vencido:
            continue
        item["_badge_prazo"] = badge_texto
        atividades_filtradas.append(item)

    if not atividades_filtradas:
        st.info(
            "Nenhuma atividade encontrada com esses filtros no momento. "
            "Que tal divulgar a primeira na aba **✨ Divulgar Atividade (IA)**?"
        )
    else:
        st.write(f"**{len(atividades_filtradas)}** oportunidade(s) encontrada(s)")
        colunas = st.columns(2)

        for idx, item in enumerate(atividades_filtradas):
            with colunas[idx % 2]:
                with st.container(border=True):
                    st.markdown(
                        f"**`{item['centro']}`** • **`{item['categoria']}`** • {item['_badge_prazo']}"
                    )
                    st.subheader(item["titulo"])
                    st.write(item["resumo"])

                    detalhes = []
                    if item.get("local_ou_formato"):
                        detalhes.append(f"📍 **Local:** {item['local_ou_formato']}")
                    data_ev = parse_data_iso(item.get("data_evento"))
                    if data_ev:
                        detalhes.append(f"🗓️ **Data do evento:** {data_ev.strftime('%d/%m/%Y')}")
                    if detalhes:
                        st.markdown(" &nbsp;|&nbsp; ".join(detalhes))

                    botao = formatar_link_botao(item.get("link_inscricao"))
                    if botao:
                        st.link_button(botao[0], botao[1], use_container_width=True)
                    elif item.get("link_inscricao"):
                        st.info(f"Contato/Inscrição: {item['link_inscricao']}")

                    if item.get("imagem_url"):
                        with st.expander("🖼️ Ver cartaz original"):
                            st.image(item["imagem_url"], use_container_width=True)


# ==============================================================================
# ABA 2: PUBLICADOR MÁGICO COM IA
# ==============================================================================
with aba_publicar:
    st.subheader("Cadastre uma oportunidade em segundos")
    st.write(
        "Envie o **print do cartaz** (Instagram/WhatsApp) e/ou cole o **texto de divulgação**. "
        "A IA preenche o formulário para você revisar antes de publicar."
    )

    if "dados_extraidos" not in st.session_state:
        st.session_state.dados_extraidos = None
    if "imagem_upload" not in st.session_state:
        st.session_state.imagem_upload = None

    col_img, col_txt = st.columns(2)
    with col_img:
        arquivo_cartaz = st.file_uploader(
            "1. Print ou cartaz (opcional)",
            type=["png", "jpg", "jpeg", "webp"],
        )
    with col_txt:
        texto_divulgacao = st.text_area(
            "2. Texto da legenda ou mensagem (opcional)",
            height=140,
            placeholder="Cole aqui o texto do post do Instagram, mensagem do WhatsApp ou descrição do evento...",
        )

    col_btn1, col_btn2 = st.columns([2, 1])
    with col_btn1:
        extrair_clicado = st.button(
            "🤖 Extrair Informações com IA", type="primary", use_container_width=True
        )
    with col_btn2:
        manual_clicado = st.button(
            "✍️ Preencher Manualmente", use_container_width=True
        )

    if extrair_clicado:
        if not arquivo_cartaz and not texto_divulgacao.strip():
            st.warning("Envie pelo menos uma imagem ou cole um texto para a IA analisar.")
        else:
            with st.spinner("Lendo cartaz e organizando as informações..."):
                try:
                    img_bytes = arquivo_cartaz.getvalue() if arquivo_cartaz else None
                    mime = arquivo_cartaz.type if arquivo_cartaz else "image/jpeg"

                    resultado = extrair_dados_atividade(
                        texto=texto_divulgacao,
                        imagem_bytes=img_bytes,
                        mime_type=mime,
                    )
                    st.session_state.dados_extraidos = resultado.model_dump()
                    st.session_state.imagem_upload = (
                        {
                            "bytes": img_bytes,
                            "nome": arquivo_cartaz.name,
                            "mime": mime,
                        }
                        if arquivo_cartaz
                        else None
                    )
                except Exception as e:
                    st.error(f"Erro ao extrair dados com a IA: {e}")

    if manual_clicado:
        st.session_state.dados_extraidos = {
            "titulo": "",
            "categoria": CATEGORIAS[0],
            "centro": "Geral/Reitoria",
            "resumo": "",
            "data_evento": None,
            "prazo_inscricao": None,
            "local_ou_formato": "",
            "link_inscricao": "",
        }
        st.session_state.imagem_upload = (
            {
                "bytes": arquivo_cartaz.getvalue(),
                "nome": arquivo_cartaz.name,
                "mime": arquivo_cartaz.type,
            }
            if arquivo_cartaz
            else None
        )

    # ETAPA 2: FORMULÁRIO DE REVISÃO HUMANA
    if st.session_state.dados_extraidos is not None:
        st.divider()
        st.markdown("### 📝 Revise os dados antes de confirmar")
        dados = st.session_state.dados_extraidos

        with st.form("form_revisao_atividade"):
            titulo_ed = st.text_input("Título da atividade *", value=dados.get("titulo") or "")

            c1, c2 = st.columns(2)
            cat_atual = dados.get("categoria")
            idx_cat = CATEGORIAS.index(cat_atual) if cat_atual in CATEGORIAS else 0
            categoria_ed = c1.selectbox("Categoria *", CATEGORIAS, index=idx_cat)

            centro_atual = dados.get("centro")
            idx_centro = CENTROS.index(centro_atual) if centro_atual in CENTROS else CENTROS.index("Geral/Reitoria")
            centro_ed = c2.selectbox("Centro UFPE *", CENTROS, index=idx_centro)

            resumo_ed = st.text_area(
                "Resumo (máx. 3 frases) *", value=dados.get("resumo") or "", height=100
            )

            d1, d2 = st.columns(2)
            prazo_ed = d1.date_input(
                "Prazo de inscrição (deixe vazio se não houver)",
                value=parse_data_iso(dados.get("prazo_inscricao")),
                format="DD/MM/YYYY",
            )
            evento_ed = d2.date_input(
                "Data do evento (deixe vazio se não houver)",
                value=parse_data_iso(dados.get("data_evento")),
                format="DD/MM/YYYY",
            )

            l1, l2 = st.columns(2)
            local_ed = l1.text_input(
                "Local ou formato", value=dados.get("local_ou_formato") or ""
            )
            link_ed = l2.text_input(
                "Link de inscrição ou @instagram", value=dados.get("link_inscricao") or ""
            )

            confirmar = st.form_submit_button(
                "✅ Confirmar e Enviar Atividade", type="primary", use_container_width=True
            )

            if confirmar:
                if not titulo_ed.strip() or not resumo_ed.strip():
                    st.error("Os campos Título e Resumo são obrigatórios.")
                else:
                    with st.spinner("Salvando atividade..."):
                        try:
                            url_cartaz = None
                            img_info = st.session_state.imagem_upload
                            if img_info:
                                url_cartaz = upload_imagem(
                                    imagem_bytes=img_info["bytes"],
                                    nome_original=img_info["nome"],
                                    mime_type=img_info["mime"],
                                )

                            status_inicial = (
                                "aprovado"
                                if st.session_state.get("moderador_autenticado")
                                else "pendente"
                            )

                            salvar_atividade(
                                dados={
                                    "titulo": titulo_ed.strip(),
                                    "categoria": categoria_ed,
                                    "centro": centro_ed,
                                    "resumo": resumo_ed.strip(),
                                    "prazo_inscricao": prazo_ed.isoformat() if prazo_ed else None,
                                    "data_evento": evento_ed.isoformat() if evento_ed else None,
                                    "local_ou_formato": local_ed.strip() or None,
                                    "link_inscricao": link_ed.strip() or None,
                                },
                                imagem_url=url_cartaz,
                                status=status_inicial,
                            )

                            st.session_state.dados_extraidos = None
                            st.session_state.imagem_upload = None

                            if status_inicial == "aprovado":
                                st.success("Atividade publicada diretamente no mural!")
                            else:
                                st.success(
                                    "Atividade enviada com sucesso! Ela já está na fila de moderação e aparecerá no mural assim que aprovada."
                                )
                        except Exception as e:
                            st.error(f"Erro ao salvar no banco de dados: {e}")


# ==============================================================================
# ABA 3: MODERAÇÃO (CONTROLE ANTI-SPAM)
# ==============================================================================
with aba_moderacao:
    st.subheader("Fila de Aprovação")

    if "moderador_autenticado" not in st.session_state:
        st.session_state.moderador_autenticado = False

    if not st.session_state.moderador_autenticado:
        senha_digitada = st.text_input("Senha de moderação", type="password")
        if st.button("Entrar"):
            if senha_digitada == SENHA_MODERACAO:
                st.session_state.moderador_autenticado = True
                st.rerun()
            else:
                st.error("Senha incorreta.")
    else:
        st.success("Modo moderador ativo (novos envios feitos por você entram aprovados direto).")

        pendentes = listar_atividades(status="pendente")
        if not pendentes:
            st.info("Nenhuma atividade pendente na fila no momento.")
        else:
            st.write(f"**{len(pendentes)}** atividade(s) aguardando revisão:")
            for item in pendentes:
                with st.container(border=True):
                    c_info, c_acoes = st.columns([3, 1])
                    with c_info:
                        st.markdown(f"**`{item['centro']}`** • **`{item['categoria']}`**")
                        st.markdown(f"#### {item['titulo']}")
                        st.write(item["resumo"])
                        st.caption(
                            f"Prazo: {item.get('prazo_inscricao') or 'N/A'} | "
                            f"Local: {item.get('local_ou_formato') or 'N/A'} | "
                            f"Link: {item.get('link_inscricao') or 'N/A'}"
                        )
                        if item.get("imagem_url"):
                            with st.expander("Ver cartaz anexado"):
                                st.image(item["imagem_url"], width=350)

                    with c_acoes:
                        if st.button(
                            "✅ Aprovar",
                            key=f"aprovar_{item['id']}",
                            type="primary",
                            use_container_width=True,
                        ):
                            atualizar_status_atividade(item["id"], "aprovado")
                            st.rerun()

                        if st.button(
                            "🗑️ Rejeitar",
                            key=f"rejeitar_{item['id']}",
                            use_container_width=True,
                        ):
                            deletar_atividade(item["id"])
                            st.rerun()

        with st.expander("🗂️ Gerenciar atividades já publicadas no mural"):
            publicadas = listar_atividades(status="aprovado")
            for pub in publicadas:
                col_t, col_d = st.columns([4, 1])
                col_t.write(f"**{pub['titulo']}** ({pub['centro']} • {pub['categoria']})")
                if col_d.button("Excluir", key=f"del_pub_{pub['id']}"):
                    deletar_atividade(pub["id"])
                    st.rerun()