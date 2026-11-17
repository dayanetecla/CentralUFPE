from typing import Literal, Optional
from pydantic import BaseModel, Field

CategoriaTipo = Literal[
    "Liga Acadêmica",
    "Extensão",
    "Empresa Júnior",
    "Evento",
    "Pesquisa/Monitoria",
    "Outro",
]

CentroUFPE = Literal[
    "CIn",
    "CTG",
    "CCSA",
    "CCS",
    "CAC",
    "CCEN",
    "CFCH",
    "CE",
    "CCJ",
    "CB",
    "CAA (Caruaru)",
    "CAV (Vitória)",
    "Geral/Reitoria",
]


class AtividadeExtraida(BaseModel):
    titulo: str = Field(
        description="Título curto e claro da atividade, liga, processo seletivo ou evento."
    )
    categoria: CategoriaTipo = Field(
        description="Categoria que melhor define a oportunidade."
    )
    centro: CentroUFPE = Field(
        description="Centro acadêmico da UFPE vinculado. Se envolver vários centros ou a universidade toda, use 'Geral/Reitoria'."
    )
    resumo: str = Field(
        description="Resumo objetivo em português (máximo 3 frases) explicando o que é, público-alvo e requisitos principais."
    )
    data_evento: Optional[str] = Field(
        default=None,
        description="Data em que o evento ocorre no formato YYYY-MM-DD. Retorne null se for um processo seletivo contínuo ou não houver data.",
    )
    prazo_inscricao: Optional[str] = Field(
        default=None,
        description="Data limite para inscrição no formato YYYY-MM-DD. Retorne null se não estiver explícito.",
    )
    local_ou_formato: Optional[str] = Field(
        default=None,
        description="Local físico na UFPE (ex: 'Auditório do CIn', 'Área II') ou formato (ex: 'Online', 'Híbrido').",
    )
    link_inscricao: Optional[str] = Field(
        default=None,
        description="URL de inscrição (Forms, Sympla, SIGAA, etc.) ou @ do Instagram mencionado. Retorne null se não houver.",
    )