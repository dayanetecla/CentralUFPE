import re
from datetime import date, datetime
from typing import Optional
from urllib.parse import urljoin

import requests
import urllib3
from bs4 import BeautifulSoup

from services.database import (
    deletar_atividade,
    listar_atividades,
    salvar_atividade,
)

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

SIGAA_INSCRICOES_URL = (
    "https://sigaa.ufpe.br/sigaa/public/extensao/paginaListaPeriodosInscricoesAtividadesPublico.jsf"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}


def mapear_centro_ufpe(texto: str) -> str:
    """Identifica o Centro Acadêmico a partir do nome do departamento/unidade."""
    u = texto.upper()
    mapa = [
        (["INFORMÁTICA", "CIN"], "CIn"),
        (["TECNOLOGIA E GEOCIÊNCIAS", "CTG", "ENGENHARIA"], "CTG"),
        (["CIÊNCIAS SOCIAIS APLICADAS", "CCSA", "ADMINISTRAÇÃO", "ECONOMIA", "CONTÁBEIS"], "CCSA"),
        (["CIÊNCIAS DA SAÚDE", "CCS", "MEDICINA", "ENFERMAGEM", "ODONTOLOGIA", "FARMÁCIA", "FISIOTERAPIA", "NUTRIÇÃO"], "CCS"),
        (["ARTES E COMUNICAÇÃO", "CAC", "DESIGN", "ARQUITETURA", "MÚSICA", "JORNALISMO"], "CAC"),
        (["EXATAS E DA NATUREZA", "CCEN", "FÍSICA", "QUÍMICA", "MATEMÁTICA", "ESTATÍSTICA"], "CCEN"),
        (["FILOSOFIA E CIÊNCIAS HUMANAS", "CFCH", "PSICOLOGIA", "HISTÓRIA", "GEOGRAFIA", "SOCIOLOGIA"], "CFCH"),
        (["EDUCAÇÃO", "PEDAGOGIA"], "CE"),
        (["CIÊNCIAS JURÍDICAS", "CCJ", "DIREITO"], "CCJ"),
        (["BIOCIÊNCIAS", "BIOLOGIA", "BIOQUÍMICA", "ZOOLOGIA", "BOTÂNICA"], "CB"),
        (["AGRESTE", "CARUARU", "CAA"], "CAA (Caruaru)"),
        (["VITÓRIA", "CAV"], "CAV (Vitória)"),
    ]
    for palavras_chave, centro in mapa:
        if any(p in u for p in palavras_chave):
            return centro
    return "Geral/Reitoria"


def _parse_intervalo(texto: str) -> tuple[Optional[str], Optional[str], bool]:
    """Converte '10/11/2026 a 25/11/2026' em (inicio_iso, fim_iso, ja_venceu)."""
    datas = re.findall(r"\d{2}/\d{2}/\d{4}", texto)
    if not datas:
        return None, None, False
    try:
        dt_ini = datetime.strptime(datas[0], "%d/%m/%Y").date()
        dt_fim = datetime.strptime(datas[-1], "%d/%m/%Y").date()
        return dt_ini.strftime("%Y-%m-%d"), dt_fim.strftime("%Y-%m-%d"), dt_fim < date.today()
    except ValueError:
        return None, None, False


def limpar_importacoes_antigas_sigaa() -> int:
    """
    Remove do banco qualquer registro importado da antiga consulta geral
    (consulta_extensao.jsf) e inscrições do SIGAA que já venceram.
    """
    hoje = date.today()
    todas = listar_atividades(status="aprovado") + listar_atividades(status="pendente")
    removidos = 0

    for item in todas:
        link = item.get("link_inscricao") or ""

        # Remove tudo que veio da página antiga de busca geral
        if "consulta_extensao.jsf" in link:
            deletar_atividade(item["id"])
            removidos += 1
            continue

        # Remove ações da página de inscrições abertas cujo prazo já passou
        if "paginaListaPeriodosInscricoesAtividadesPublico.jsf" in link:
            prazo = item.get("prazo_inscricao")
            if prazo:
                try:
                    if date.fromisoformat(str(prazo)[:10]) < hoje:
                        deletar_atividade(item["id"])
                        removidos += 1
                except ValueError:
                    pass

    return removidos


def buscar_inscricoes_abertas_sigaa() -> list[dict]:
    """
    Consulta exclusivamente a lista pública de Cursos e Eventos de Extensão
    com Períodos de Inscrição Abertos no SIGAA UFPE.
    """
    session = requests.Session()
    session.headers.update(HEADERS)

    resp = session.get(SIGAA_INSCRICOES_URL, verify=False, timeout=20)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    tabela = soup.find("table", class_="listagem")

    if not tabela:
        form = soup.find("form")
        if form:
            payload = {
                inp["name"]: inp.get("value", "")
                for inp in form.find_all("input", {"type": "hidden"})
                if inp.get("name")
            }
            for btn in form.find_all("input", {"type": "submit"}):
                if "BUSCAR" in btn.get("value", "").upper() and btn.get("name"):
                    payload[btn["name"]] = btn.get("value", "Buscar")
                    break

            action_url = urljoin(SIGAA_INSCRICOES_URL, form.get("action", ""))
            resp_post = session.post(action_url, data=payload, verify=False, timeout=25)
            resp_post.raise_for_status()
            soup = BeautifulSoup(resp_post.text, "html.parser")
            tabela = soup.find("table", class_="listagem")

    if not tabela:
        return []

    resultados = []
    for tr in tabela.find_all("tr"):
        if tr.find("th"):
            continue

        colunas = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
        if len(colunas) < 3:
            continue

        titulo = re.sub(r"^[A-Z]{2,5}\d+-\d+\s*-\s*", "", colunas[0]).lstrip("- ").strip()
        if not titulo:
            continue

        texto_linha = " | ".join(colunas)

        intervalos = re.findall(r"\d{2}/\d{2}/\d{4}\s*(?:a|até|-)\s*\d{2}/\d{2}/\d{4}", texto_linha)
        if not intervalos:
            continue

        _, prazo_insc_iso, insc_encerrada = _parse_intervalo(intervalos[0])
        if insc_encerrada or not prazo_insc_iso:
            continue

        data_evento_iso = None
        if len(intervalos) > 1:
            data_evento_iso, _, _ = _parse_intervalo(intervalos[1])

        categoria = "Evento" if "EVENTO" in texto_linha.upper() else "Extensão"
        centro = mapear_centro_ufpe(texto_linha)

        resumo = (
            f"Curso/Evento oficial da UFPE com inscrições abertas no SIGAA até "
            f"{datetime.strptime(prazo_insc_iso, '%Y-%m-%d').strftime('%d/%m/%Y')}."
        )
        if len(intervalos) > 1:
            resumo += f" Período de realização: {intervalos[1]}."

        resultados.append(
            {
                "titulo": titulo[:200],
                "categoria": categoria,
                "centro": centro,
                "resumo": resumo,
                "prazo_inscricao": prazo_insc_iso,
                "data_evento": data_evento_iso,
                "local_ou_formato": "UFPE (Inscrição via SIGAA)",
                "link_inscricao": SIGAA_INSCRICOES_URL,
            }
        )

    return resultados


def sincronizar_sigaa_com_banco(status_inicial: str = "pendente") -> int:
    """
    Limpa sobras da página antiga e importa apenas ações com inscrição aberta
    do SIGAA para a fila de moderação.
    """
    removidos = limpar_importacoes_antigas_sigaa()
    if removidos:
        print(f"Limpeza: {removidos} registro(s) antigo(s) removido(s) do banco.")

    existentes = listar_atividades(status="aprovado") + listar_atividades(status="pendente")
    titulos_existentes = {item["titulo"].strip().lower() for item in existentes}

    acoes = buscar_inscricoes_abertas_sigaa()
    novos = 0

    for acao in acoes:
        chave = acao["titulo"].strip().lower()
        if not chave or chave in titulos_existentes:
            continue

        salvar_atividade(dados=acao, status=status_inicial)
        titulos_existentes.add(chave)
        novos += 1

    return novos


if __name__ == "__main__":
    print("Limpando registros antigos e buscando inscrições abertas no SIGAA UFPE...")
    try:
        qtd = sincronizar_sigaa_com_banco(status_inicial="pendente")
        print(f"Concluído! {qtd} oportunidade(s) enviada(s) para a fila de moderação.")
    except Exception as e:
        print(f"Erro ao consultar o SIGAA: {e}")