import hmac
import io
import math
import re
import unicodedata
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import plotly.express as px
import streamlit as st
from pypdf import PdfReader
from supabase import Client, create_client


# =========================================================
# INVIORA — Copiloto de Compras
# Versão 0.6.0
# =========================================================

st.set_page_config(
    page_title="Inviora",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
        .block-container {
            padding-top: 1.3rem;
            padding-bottom: 2rem;
        }

        [data-testid="stSidebar"] {
            border-right: 1px solid rgba(128,128,128,0.18);
        }

        .brand {
            font-size: 2rem;
            font-weight: 800;
            letter-spacing: 0.08em;
        }

        .tagline {
            opacity: 0.70;
            margin-top: -0.4rem;
            margin-bottom: 1.2rem;
        }

        div[data-testid="stMetric"] {
            border: 1px solid rgba(128,128,128,0.20);
            padding: 0.8rem 1rem;
            border-radius: 0.8rem;
        }
    </style>
    """,
    unsafe_allow_html=True,
)


FORNECEDORES = [
    "Logista",
    "Tabaqueira",
]

PERIODOS = [
    "Atual",
    "Anterior",
]

TZ_PORTUGAL = ZoneInfo(
    "Europe/Lisbon"
)


# =========================================================
# DATA E CALENDÁRIO
# =========================================================

def hoje_portugal():

    return datetime.now(
        TZ_PORTUGAL
    ).date()


def proximo_dia_semana(
    weekday,
    incluir_hoje=True,
):

    hoje = hoje_portugal()

    dias = (
        weekday
        - hoje.weekday()
    ) % 7

    if (
        dias == 0
        and not incluir_hoje
    ):

        dias = 7

    return hoje + timedelta(
        days=dias
    )


def estado_fatura(
    data_saida,
):

    hoje = hoje_portugal()

    if data_saida > hoje:

        return "Pendente"

    if data_saida == hoje:

        return "🚚 Sai hoje"

    return "✅ Expedida"


# =========================================================
# SUPABASE
# =========================================================

SEGREDOS_OBRIGATORIOS = [
    "SUPABASE_URL",
    "SUPABASE_KEY",
    "APP_PASSWORD",
]

segredos_em_falta = [

    segredo

    for segredo
    in SEGREDOS_OBRIGATORIOS

    if segredo
    not in st.secrets
]

if segredos_em_falta:

    st.error(
        "Faltam Secrets no Streamlit: "
        + ", ".join(
            segredos_em_falta
        )
    )

    st.stop()


@st.cache_resource
def ligar_supabase():

    return create_client(

        st.secrets[
            "SUPABASE_URL"
        ],

        st.secrets[
            "SUPABASE_KEY"
        ],
    )


try:

    supabase = ligar_supabase()

    supabase.table(
        "faturas"
    ).select(
        "id"
    ).limit(
        1
    ).execute()

except Exception as erro:

    st.error(
        "Não foi possível ligar ao Supabase."
    )

    st.exception(
        erro
    )

    st.stop()


# =========================================================
# LOGIN SIMPLES
# =========================================================

if "autenticado" not in st.session_state:

    st.session_state.autenticado = False


if not st.session_state.autenticado:

    st.title(
        "🔒 Inviora"
    )

    password = st.text_input(
        "Palavra-passe",
        type="password",
    )

    if st.button(
        "Entrar",
        type="primary",
    ):

        password_correta = str(

            st.secrets[
                "APP_PASSWORD"
            ]
        )

        if hmac.compare_digest(

            password,

            password_correta,
        ):

            st.session_state.autenticado = True

            st.rerun()

        else:

            st.error(
                "Palavra-passe incorreta."
            )

    st.stop()


# =========================================================
# ESTADO TEMPORÁRIO DOS INVENTÁRIOS
# =========================================================

if "inventarios" not in st.session_state:

    st.session_state.inventarios = {

        fornecedor: {
            "Atual": None,
            "Anterior": None,
        }

        for fornecedor
        in FORNECEDORES
    }


if "nomes_ficheiros" not in st.session_state:

    st.session_state.nomes_ficheiros = {

        fornecedor: {
            "Atual": None,
            "Anterior": None,
        }

        for fornecedor
        in FORNECEDORES
    }


if "dias_objetivo" not in st.session_state:

    st.session_state.dias_objetivo = {
        "Logista": 1.0,
        "Tabaqueira": 3.0,
    }


if "margem_dias" not in st.session_state:

    st.session_state.margem_dias = {
        "Logista": 0.25,
        "Tabaqueira": 0.50,
    }


if "multiplo" not in st.session_state:

    st.session_state.multiplo = {
        "Logista": 1,
        "Tabaqueira": 1,
    }


if "dias_listagem" not in st.session_state:

    st.session_state.dias_listagem = 7.0


# =========================================================
# FUNÇÕES GERAIS
# =========================================================

def normalizar_texto(
    valor
):

    texto = (
        ""
        if valor is None
        else str(valor)
    )

    texto = unicodedata.normalize(
        "NFKD",
        texto,
    )

    texto = "".join(

        letra

        for letra
        in texto

        if not unicodedata.combining(
            letra
        )
    )

    texto = texto.lower().strip()

    texto = re.sub(
        r"[^a-z0-9]+",
        " ",
        texto,
    )

    return re.sub(
        r"\s+",
        " ",
        texto,
    ).strip()


def normalizar_referencia(
    valor
):

    texto = str(
        valor
    ).strip()

    if texto.endswith(
        ".0"
    ):

        texto = texto[:-2]

    return texto


def formatar_numero(
    valor,
    casas=0,
):

    try:

        return (

            f"{float(valor):,.{casas}f}"

            .replace(
                ",",
                "X",
            )

            .replace(
                ".",
                ",",
            )

            .replace(
                "X",
                ".",
            )
        )

    except Exception:

        return "0"


def converter_numeros(
    serie
):

    if pd.api.types.is_numeric_dtype(
        serie
    ):

        return pd.to_numeric(

            serie,

            errors="coerce",

        ).fillna(
            0
        )

    texto = serie.astype(
        str
    ).str.strip()

    texto = texto.str.replace(
        "\u00a0",
        "",
        regex=False,
    )

    texto = texto.str.replace(
        "€",
        "",
        regex=False,
    )

    texto = texto.str.replace(
        " ",
        "",
        regex=False,
    )

    tem_virgula = texto.str.contains(
        ",",
        regex=False,
        na=False,
    )

    tem_ponto = texto.str.contains(
        ".",
        regex=False,
        na=False,
    )

    tem_ambos = (
        tem_virgula
        & tem_ponto
    )

    texto.loc[
        tem_ambos
    ] = (

        texto.loc[
            tem_ambos
        ]

        .str.replace(
            ".",
            "",
            regex=False,
        )

        .str.replace(
            ",",
            ".",
            regex=False,
        )
    )

    texto.loc[
        tem_virgula
        & ~tem_ponto
    ] = (

        texto.loc[
            tem_virgula
            & ~tem_ponto
        ]

        .str.replace(
            ",",
            ".",
            regex=False,
        )
    )

    return pd.to_numeric(

        texto,

        errors="coerce",

    ).fillna(
        0
    )


def converter_para_excel(
    dados,
    folha="Dados",
):

    memoria = io.BytesIO()

    with pd.ExcelWriter(

        memoria,

        engine="openpyxl",

    ) as writer:

        dados.to_excel(

            writer,

            index=False,

            sheet_name=folha[:31],
        )

    memoria.seek(
        0
    )

    return memoria.getvalue()


# =========================================================
# LEITURA DOS EXCEL
# =========================================================

ALIASES = {

    "referencia": [
        "referencia",
        "ref",
        "codigo",
        "codigo artigo",
        "artigo",
    ],

    "produto": [
        "designacao",
        "descricao",
        "produto",
        "nome produto",
    ],

    "entradas": [
        "entrada",
        "entradas",
        "quantidade entradas",
        "qtd entradas",
    ],

    "saidas": [
        "saida",
        "saidas",
        "vendas",
        "quantidade saidas",
        "qtd saidas",
        "quantidade vendida",
    ],

    "stock_final": [
        "final",
        "stock final",
        "stock atual",
        "existencia final",
        "saldo final",
        "stock",
    ],
}


MAPA_COLUNAS = {}


for nome_final, alternativas in ALIASES.items():

    for alternativa in alternativas:

        MAPA_COLUNAS[
            normalizar_texto(
                alternativa
            )
        ] = nome_final


def identificar_coluna(
    nome
):

    normalizado = normalizar_texto(
        nome
    )

    if normalizado in MAPA_COLUNAS:

        return MAPA_COLUNAS[
            normalizado
        ]

    for alias, nome_final in sorted(

        MAPA_COLUNAS.items(),

        key=lambda item: len(
            item[0]
        ),

        reverse=True,
    ):

        if len(alias) >= 5:

            if (

                normalizado.startswith(
                    alias
                )

                or normalizado.endswith(
                    alias
                )
            ):

                return nome_final

    return None


def pontuar_cabecalho(
    valores
):

    encontrados = {

        identificar_coluna(
            valor
        )

        for valor in valores

        if identificar_coluna(
            valor
        )
    }

    return len(
        encontrados
    )


def limpar_linhas_tecnicas(
    dados
):

    dados = dados.copy()

    if "produto" in dados.columns:

        produtos = (

            dados[
                "produto"
            ]

            .astype(str)

            .map(
                normalizar_texto
            )
        )

        dados = dados.loc[

            ~produtos.isin(
                {
                    "total",
                    "totais",
                    "subtotal",
                    "rappel",
                    "rapel",
                }
            )

        ].copy()

    if "referencia" in dados.columns:

        referencias = (

            dados[
                "referencia"
            ]

            .astype(str)

            .map(
                normalizar_texto
            )
        )

        dados = dados.loc[

            ~referencias.isin(
                {
                    "ra",
                    "rappel",
                    "rapel",
                }
            )

        ].copy()

    return dados


def ler_ficheiro_tabular(
    ficheiro
):

    conteudo = ficheiro.getvalue()

    extensao = (

        ficheiro.name

        .lower()

        .rsplit(
            ".",
            1,
        )[-1]
    )

    if extensao == "csv":

        ultimo_erro = None

        for encoding in [

            "utf-8-sig",
            "utf-8",
            "latin-1",

        ]:

            try:

                dados = pd.read_csv(

                    io.BytesIO(
                        conteudo
                    ),

                    sep=None,

                    engine="python",

                    encoding=encoding,
                )

                cabecalho = 0

                break

            except Exception as erro:

                ultimo_erro = erro

        else:

            raise ValueError(

                f"Não foi possível ler o CSV: "
                f"{ultimo_erro}"
            )

    else:

        amostra = pd.read_excel(

            io.BytesIO(
                conteudo
            ),

            header=None,

            nrows=40,

            engine="openpyxl",
        )

        pontuacoes = amostra.apply(

            lambda linha: pontuar_cabecalho(
                linha.tolist()
            ),

            axis=1,
        )

        cabecalho = (

            int(
                pontuacoes.idxmax()
            )

            if len(
                pontuacoes
            )

            else 0
        )

        dados = pd.read_excel(

            io.BytesIO(
                conteudo
            ),

            header=cabecalho,

            engine="openpyxl",
        )

    dados = dados.dropna(
        how="all"
    ).copy()

    dados.columns = [

        str(
            coluna
        ).strip()

        for coluna
        in dados.columns
    ]

    renomear = {}

    usados = set()

    for coluna in dados.columns:

        nome_final = identificar_coluna(
            coluna
        )

        if (

            nome_final

            and nome_final
            not in usados
        ):

            renomear[
                coluna
            ] = nome_final

            usados.add(
                nome_final
            )

    dados = dados.rename(
        columns=renomear
    )

    for coluna in [

        "entradas",
        "saidas",
        "stock_final",

    ]:

        if coluna in dados.columns:

            dados[
                coluna
            ] = converter_numeros(

                dados[
                    coluna
                ]
            )

    if "referencia" in dados.columns:

        dados[
            "referencia"
        ] = dados[
            "referencia"
        ].map(
            normalizar_referencia
        )

    dados = limpar_linhas_tecnicas(
        dados
    )

    return (

        dados.reset_index(
            drop=True
        ),

        cabecalho,
    )


def garantir_produto(
    dados
):

    dados = dados.copy()

    if "produto" not in dados.columns:

        if "referencia" in dados.columns:

            dados[
                "produto"
            ] = dados[
                "referencia"
            ].astype(
                str
            )

        else:

            dados[
                "produto"
            ] = [

                f"Produto {indice + 1}"

                for indice
                in range(
                    len(
                        dados
                    )
                )
            ]

    return dados


def obter_inventario(
    fornecedor,
    periodo="Atual",
):

    return st.session_state.inventarios[
        fornecedor
    ][periodo]


def juntar_inventarios(
    periodo="Atual",
):

    blocos = []

    for fornecedor in FORNECEDORES:

        dados = obter_inventario(

            fornecedor,

            periodo,
        )

        if dados is not None:

            copia = garantir_produto(
                dados
            )

            copia[
                "fornecedor"
            ] = fornecedor

            blocos.append(
                copia
            )

    if not blocos:

        return None

    return pd.concat(

        blocos,

        ignore_index=True,

        sort=False,
    )


def identificar_fornecedor(
    referencia
):

    referencia = normalizar_referencia(
        referencia
    )

    for fornecedor in FORNECEDORES:

        for periodo in PERIODOS:

            dados = obter_inventario(

                fornecedor,

                periodo,
            )

            if (

                dados is not None

                and "referencia"
                in dados.columns
            ):

                referencias = set(

                    dados[
                        "referencia"
                    ]

                    .dropna()

                    .map(
                        normalizar_referencia
                    )
                )

                if referencia in referencias:

                    return fornecedor

    return "Não identificado"


# =========================================================
# LEITURA DAS FATURAS
# =========================================================

def extrair_texto_pdf(
    ficheiro
):

    leitor = PdfReader(

        io.BytesIO(
            ficheiro.getvalue()
        )
    )

    textos = []

    for pagina in leitor.pages:

        try:

            texto = pagina.extract_text(

                extraction_mode="layout"

            ) or ""

        except Exception:

            texto = pagina.extract_text() or ""

        textos.append(
            texto
        )

    return textos


def extrair_cabecalho_fatura(
    texto
):

    numero = "Sem número"

    resultado = re.search(

        r"FT\d+[A-Z]\d+/(\d+)",

        texto,

        flags=re.IGNORECASE,
    )

    if resultado:

        numero = resultado.group(
            1
        )

    datas = re.findall(

        r"\b(20\d{2}[-/.]\d{2}[-/.]\d{2})\b",

        texto,
    )

    data_fatura = None

    if datas:

        data_fatura = (

            datas[0]

            .replace(
                "/",
                "-",
            )

            .replace(
                ".",
                "-",
            )
        )

    return {
        "numero_fatura": numero,
        "data_fatura": data_fatura,
    }


def extrair_artigos_fatura(
    texto
):

    padrao = re.compile(

        r"^(?P<referencia>\d{2,6})\s+"

        r"(?P<produto>.+?)\s+"

        r"(?P<quantidade>\d+(?:[.,]\d+)?)\s+"

        r"M\d+\s+Reg\b",

        flags=re.IGNORECASE,
    )

    artigos = []

    encontrados = set()

    for linha in texto.splitlines():

        linha = re.sub(

            r"\s+",

            " ",

            linha.strip(),
        )

        resultado = padrao.search(
            linha
        )

        if not resultado:

            continue

        artigo = {

            "referencia":
                normalizar_referencia(

                    resultado.group(
                        "referencia"
                    )
                ),

            "produto":
                resultado.group(
                    "produto"
                ).strip(),

            "quantidade":
                float(

                    resultado.group(
                        "quantidade"
                    ).replace(
                        ",",
                        ".",
                    )
                ),
        }

        chave = (
            artigo["referencia"],
            artigo["produto"],
            artigo["quantidade"],
        )

        if chave not in encontrados:

            encontrados.add(
                chave
            )

            artigos.append(
                artigo
            )

    return artigos


def ler_fatura_pdf(
    ficheiro
):

    artigos = []

    processadas = set()

    cabecalho_final = None

    for texto in extrair_texto_pdf(
        ficheiro
    ):

        cabecalho = extrair_cabecalho_fatura(
            texto
        )

        numero = cabecalho[
            "numero_fatura"
        ]

        if numero in processadas:

            continue

        processadas.add(
            numero
        )

        cabecalho_final = cabecalho

        for artigo in extrair_artigos_fatura(
            texto
        ):

            artigo[
                "fornecedor"
            ] = identificar_fornecedor(

                artigo[
                    "referencia"
                ]
            )

            artigos.append(
                artigo
            )

    if (

        not artigos

        or cabecalho_final is None
    ):

        raise ValueError(
            "Não consegui reconhecer artigos nesta fatura."
        )

    return (

        cabecalho_final,

        pd.DataFrame(
            artigos
        ),
    )


# =========================================================
# SUPABASE — FATURAS
# =========================================================

def carregar_faturas_db():

    resposta_faturas = (

        supabase

        .table(
            "faturas"
        )

        .select(
            "*"
        )

        .order(
            "data_saida"
        )

        .execute()
    )

    resposta_linhas = (

        supabase

        .table(
            "fatura_linhas"
        )

        .select(
            "*"
        )

        .execute()
    )

    cabecalhos = (
        resposta_faturas.data
        or []
    )

    linhas = (
        resposta_linhas.data
        or []
    )

    if not cabecalhos:

        return pd.DataFrame(

            columns=[
                "fatura_id",
                "numero_fatura",
                "data_fatura",
                "data_saida",
                "ficheiro",
                "linha_id",
                "referencia",
                "produto",
                "quantidade",
                "fornecedor",
                "estado",
            ]
        )

    df_faturas = pd.DataFrame(
        cabecalhos
    ).rename(
        columns={
            "id": "fatura_id",
        }
    )

    df_linhas = pd.DataFrame(
        linhas
    )

    if df_linhas.empty:

        df = df_faturas.copy()

        for coluna in [

            "linha_id",
            "referencia",
            "produto",
            "quantidade",
            "fornecedor",

        ]:

            df[
                coluna
            ] = None

    else:

        df_linhas = df_linhas.rename(

            columns={
                "id": "linha_id",
            }
        )

        df = df_faturas.merge(

            df_linhas,

            on="fatura_id",

            how="left",
        )

    df[
        "data_saida"
    ] = pd.to_datetime(

        df[
            "data_saida"
        ],

        errors="coerce",

    ).dt.date

    df[
        "data_fatura"
    ] = pd.to_datetime(

        df[
            "data_fatura"
        ],

        errors="coerce",

    ).dt.date

    df[
        "quantidade"
    ] = pd.to_numeric(

        df[
            "quantidade"
        ],

        errors="coerce",

    ).fillna(
        0
    )

    df[
        "estado"
    ] = df[
        "data_saida"
    ].apply(
        estado_fatura
    )

    return df


def guardar_fatura_db(
    cabecalho,
    linhas,
    data_saida,
    ficheiro_nome,
):

    numero = str(

        cabecalho[
            "numero_fatura"
        ]
    )

    existente = (

        supabase

        .table(
            "faturas"
        )

        .select(
            "id"
        )

        .eq(
            "numero_fatura",
            numero,
        )

        .eq(
            "data_saida",
            data_saida.isoformat(),
        )

        .execute()

        .data
    )

    if existente:

        raise ValueError(
            "Esta fatura já está guardada para essa data."
        )

    resposta = (

        supabase

        .table(
            "faturas"
        )

        .insert(
            {
                "numero_fatura": numero,
                "data_fatura": cabecalho.get(
                    "data_fatura"
                ),
                "data_saida": data_saida.isoformat(),
                "ficheiro": ficheiro_nome,
            }
        )

        .execute()
    )

    if not resposta.data:

        raise RuntimeError(
            "O Supabase não devolveu o ID da fatura."
        )

    fatura_id = resposta.data[
        0
    ][
        "id"
    ]

    linhas_supabase = []

    for _, linha in linhas.iterrows():

        linhas_supabase.append(
            {
                "fatura_id": fatura_id,
                "referencia": str(
                    linha[
                        "referencia"
                    ]
                ),
                "produto": str(
                    linha[
                        "produto"
                    ]
                ),
                "quantidade": float(
                    linha[
                        "quantidade"
                    ]
                ),
                "fornecedor": str(
                    linha[
                        "fornecedor"
                    ]
                ),
            }
        )

    try:

        (

            supabase

            .table(
                "fatura_linhas"
            )

            .insert(
                linhas_supabase
            )

            .execute()
        )

    except Exception:

        (

            supabase

            .table(
                "faturas"
            )

            .delete()

            .eq(
                "id",
                fatura_id,
            )

            .execute()
        )

        raise


def atualizar_fornecedores_db(
    editado,
    original,
):

    mapa_original = (

        original

        .set_index(
            "linha_id"
        )[
            "fornecedor"
        ]

        .to_dict()
    )

    alteracoes = 0

    for _, linha in editado.iterrows():

        linha_id = linha[
            "linha_id"
        ]

        novo_fornecedor = str(

            linha[
                "fornecedor"
            ]
        )

        if (

            mapa_original.get(
                linha_id
            )

            != novo_fornecedor
        ):

            (

                supabase

                .table(
                    "fatura_linhas"
                )

                .update(
                    {
                        "fornecedor":
                            novo_fornecedor
                    }
                )

                .eq(
                    "id",
                    int(
                        linha_id
                    ),
                )

                .execute()
            )

            alteracoes += 1

    return alteracoes


# =========================================================
# CÁLCULO DA ENCOMENDA
# =========================================================

def calcular_encomenda(
    fornecedor
):

    atual = obter_inventario(

        fornecedor,

        "Atual",
    )

    anterior = obter_inventario(

        fornecedor,

        "Anterior",
    )

    if atual is None:

        return (

            None,

            f"Carrega primeiro o período atual de {fornecedor}.",
        )

    atual = garantir_produto(
        atual
    )

    if not {

        "saidas",
        "stock_final",

    }.issubset(
        atual.columns
    ):

        return (

            None,

            "A listagem precisa das colunas "
            "Saídas e Stock Final.",
        )

    chave = (

        "referencia"

        if "referencia"
        in atual.columns

        else "produto"
    )

    atuais = atual.groupby(

        chave,

        as_index=False,

    ).agg(

        produto=(
            "produto",
            "first",
        ),

        saidas_atual=(
            "saidas",
            "sum",
        ),

        stock_phc=(
            "stock_final",
            "sum",
        ),
    )

    if (

        anterior is not None

        and "saidas"
        in anterior.columns

        and chave
        in anterior.columns
    ):

        anterior = garantir_produto(
            anterior
        )

        anteriores = anterior.groupby(

            chave,

            as_index=False,

        ).agg(

            saidas_anterior=(
                "saidas",
                "sum",
            )
        )

        resultado = atuais.merge(

            anteriores,

            on=chave,

            how="left",
        )

    else:

        resultado = atuais.copy()

        resultado[
            "saidas_anterior"
        ] = 0

    resultado[
        "saidas_anterior"
    ] = resultado[
        "saidas_anterior"
    ].fillna(
        0
    )

    if anterior is None:

        resultado[
            "vendas_periodo"
        ] = resultado[
            "saidas_atual"
        ]

    else:

        resultado[
            "vendas_periodo"
        ] = (

            resultado[
                "saidas_atual"
            ] * 0.65

            + resultado[
                "saidas_anterior"
            ] * 0.35
        )

    resultado[
        "media_dia"
    ] = (

        resultado[
            "vendas_periodo"
        ]

        / float(

            st.session_state.dias_listagem
        )
    )

    resultado[
        "autonomia_dias"
    ] = resultado.apply(

        lambda linha: (

            linha[
                "stock_phc"
            ]

            / linha[
                "media_dia"
            ]

            if linha[
                "media_dia"
            ] > 0

            else 999.0
        ),

        axis=1,
    )

    objetivo = float(

        st.session_state.dias_objetivo[
            fornecedor
        ]
    )

    margem = float(

        st.session_state.margem_dias[
            fornecedor
        ]
    )

    resultado[
        "objetivo_dias"
    ] = objetivo + margem

    resultado[
        "stock_alvo"
    ] = (

        resultado[
            "media_dia"
        ]

        * resultado[
            "objetivo_dias"
        ]
    )

    necessidade = (

        resultado[
            "stock_alvo"
        ]

        - resultado[
            "stock_phc"
        ]

    ).clip(
        lower=0
    )

    multiplo = max(

        int(

            st.session_state.multiplo[
                fornecedor
            ]
        ),

        1,
    )

    resultado[
        "sugestao"
    ] = necessidade.apply(

        lambda quantidade: (

            int(

                math.ceil(

                    quantidade
                    / multiplo

                ) * multiplo
            )

            if quantidade > 0

            else 0
        )
    )

    resultado[
        "estado_stock"
    ] = resultado[
        "autonomia_dias"
    ].apply(

        lambda dias: (

            "🔴 Termina hoje"

            if dias < 1

            else "🟠 Termina amanhã"

            if dias < 2

            else "🟡 Menos de 3 dias"

            if dias < 3

            else "🟢 Cobertura suficiente"
        )
    )

    resultado[
        "fornecedor"
    ] = fornecedor

    return (

        resultado.sort_values(

            [
                "autonomia_dias",
                "sugestao",
            ],

            ascending=[
                True,
                False,
            ],
        ).reset_index(
            drop=True
        ),

        None,
    )


# =========================================================
# MENU
# =========================================================

with st.sidebar:

    st.markdown(
        '<div class="brand">INVIORA</div>',
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div class="tagline">'
        'Transformar dados em decisões.'
        '</div>',
        unsafe_allow_html=True,
    )

    pagina = st.radio(

        "Navegação",

        [
            "🏠 Home",
            "📥 Importar inventário",
            "🧾 Faturas",
            "📅 Calendário",
            "📦 Encomendas",
            "📈 Vendas",
            "📋 Produtos",
            "⚙️ Definições",
        ],

        label_visibility="collapsed",
    )

    st.divider()

    st.caption(
        f"Hoje: "
        f"{hoje_portugal().strftime('%d/%m/%Y')}"
    )

    st.caption(
        "🟢 Supabase ligado"
    )

    st.caption(
        "Inviora v0.6.0"
    )

    if st.button(
        "Terminar sessão"
    ):

        st.session_state.autenticado = False

        st.rerun()


faturas_db = carregar_faturas_db()

if faturas_db.empty:

    faturas_ativas = faturas_db.copy()

    historico = faturas_db.copy()

else:

    faturas_ativas = faturas_db[

        faturas_db[
            "data_saida"
        ] >= hoje_portugal()

    ].copy()

    historico = faturas_db[

        faturas_db[
            "data_saida"
        ] < hoje_portugal()

    ].copy()


# =========================================================
# PÁGINA HOJE
# =========================================================

if pagina == "🏠 Home":

    st.title(
        "Centro de Comando"
    )

    st.caption(

        datetime.now(
            TZ_PORTUGAL
        ).strftime(
            "%d/%m/%Y · %H:%M"
        )
    )

    if faturas_db.empty:

        faturas_hoje = (
            faturas_db.copy()
        )

        faturas_futuras = (
            faturas_db.copy()
        )

    else:

        faturas_hoje = faturas_db[

            faturas_db[
                "data_saida"
            ] == hoje_portugal()

        ].copy()

        faturas_futuras = faturas_db[

            faturas_db[
                "data_saida"
            ] > hoje_portugal()

        ].copy()

    coluna1, coluna2, coluna3, coluna4 = st.columns(
        4
    )

    coluna1.metric(

        "Faturas que saem hoje",

        (
            faturas_hoje[
                "numero_fatura"
            ].nunique()

            if not faturas_hoje.empty

            else 0
        ),
    )

    coluna2.metric(

        "Unidades que saem hoje",

        formatar_numero(

            faturas_hoje[
                "quantidade"
            ].sum()

            if not faturas_hoje.empty

            else 0,

            1,
        ),
    )

    coluna3.metric(

        "Faturas futuras",

        (
            faturas_futuras[
                "numero_fatura"
            ].nunique()

            if not faturas_futuras.empty

            else 0
        ),
    )

    coluna4.metric(

        "Linhas sem fornecedor",

        (

            int(

                (
                    faturas_ativas[
                        "fornecedor"
                    ]

                    == "Não identificado"

                ).sum()
            )

            if not faturas_ativas.empty

            else 0
        ),
    )

    st.subheader(
        "Prioridades de compra"
    )

    resumo_fornecedores = []

    for fornecedor in FORNECEDORES:

        resultado, erro = calcular_encomenda(
            fornecedor
        )

        if erro:

            resumo_fornecedores.append(
                {
                    "Fornecedor": fornecedor,
                    "Estado": erro,
                    "Produtos": 0,
                    "Quantidade": 0,
                }
            )

        else:

            resumo_fornecedores.append(
                {
                    "Fornecedor": fornecedor,
                    "Estado": "Pronto",
                    "Produtos": int(

                        (
                            resultado[
                                "sugestao"
                            ] > 0
                        ).sum()
                    ),
                    "Quantidade": int(

                        resultado[
                            "sugestao"
                        ].sum()
                    ),
                }
            )

    st.dataframe(

        pd.DataFrame(
            resumo_fornecedores
        ),

        use_container_width=True,

        hide_index=True,
    )

    if not faturas_hoje.empty:

        st.subheader(
            "🚚 Preparar hoje"
        )

        preparar = (

            faturas_hoje.groupby(

                [
                    "fornecedor",
                    "referencia",
                    "produto",
                ],

                as_index=False,

            )[
                "quantidade"
            ]

            .sum()
        )

        st.dataframe(

            preparar,

            use_container_width=True,

            hide_index=True,
        )

    else:

        st.success(
            "Não existem faturas agendadas para hoje."
        )


# =========================================================
# IMPORTAÇÃO
# =========================================================

elif pagina == "📥 Importar inventário":

    st.title(
        "Importar inventário"
    )

    fornecedor = st.selectbox(
        "Fornecedor",
        FORNECEDORES,
    )

    periodo = st.radio(
        "Período",
        PERIODOS,
        horizontal=True,
    )

    ficheiro = st.file_uploader(

        f"{fornecedor} — {periodo}",

        type=[
            "xlsx",
            "csv",
        ],

        key=(
            f"upload_"
            f"{fornecedor}_"
            f"{periodo}"
        ),
    )

    if ficheiro is not None:

        try:

            dados, cabecalho = (
                ler_ficheiro_tabular(
                    ficheiro
                )
            )

            st.session_state.inventarios[
                fornecedor
            ][periodo] = dados

            st.session_state.nomes_ficheiros[
                fornecedor
            ][periodo] = ficheiro.name

            st.success(

                f"{fornecedor} {periodo.lower()} "
                f"carregado: {len(dados)} linhas."
            )

            st.caption(

                f"Cabeçalho identificado "
                f"na linha {cabecalho + 1}."
            )

            st.dataframe(

                dados.head(
                    30
                ),

                use_container_width=True,

                hide_index=True,
            )

        except Exception as erro:

            st.error(

                f"Não consegui ler o ficheiro: "
                f"{erro}"
            )

    estado = []

    for nome_fornecedor in FORNECEDORES:

        for nome_periodo in PERIODOS:

            dados = obter_inventario(

                nome_fornecedor,

                nome_periodo,
            )

            estado.append(
                {
                    "Fornecedor":
                        nome_fornecedor,

                    "Período":
                        nome_periodo,

                    "Ficheiro":
                        st.session_state
                        .nomes_ficheiros[
                            nome_fornecedor
                        ][nome_periodo]
                        or "Não carregado",

                    "Linhas":
                        len(dados)
                        if dados is not None
                        else 0,
                }
            )

    st.dataframe(

        pd.DataFrame(
            estado
        ),

        use_container_width=True,

        hide_index=True,
    )


# =========================================================
# FATURAS
# =========================================================

elif pagina == "🧾 Faturas":

    st.title(
        "Faturas"
    )

    st.caption(
        "As faturas ficam guardadas permanentemente."
    )

    escolha_data = st.radio(

        "Data de saída",

        [
            "Próxima quarta-feira",
            "Próxima quinta-feira",
            "Escolher data",
        ],

        horizontal=True,
    )

    if escolha_data == "Próxima quarta-feira":

        data_saida = proximo_dia_semana(
            2,
            incluir_hoje=True,
        )

    elif escolha_data == "Próxima quinta-feira":

        data_saida = proximo_dia_semana(
            3,
            incluir_hoje=True,
        )

    else:

        data_saida = st.date_input(

            "Data concreta",

            value=hoje_portugal(),
        )

    st.info(

        f"Saída definida para "
        f"**{data_saida.strftime('%d/%m/%Y')}**."
    )

    ficheiros = st.file_uploader(

        "Carregar faturas PDF",

        type=[
            "pdf"
        ],

        accept_multiple_files=True,
    )

    if (

        ficheiros

        and st.button(
            "Ler e guardar",
            type="primary",
        )
    ):

        for ficheiro in ficheiros:

            try:

                cabecalho, linhas = ler_fatura_pdf(
                    ficheiro
                )

                guardar_fatura_db(

                    cabecalho,

                    linhas,

                    data_saida,

                    ficheiro.name,
                )

                st.success(

                    f"{ficheiro.name} "
                    f"guardada no Supabase."
                )

            except Exception as erro:

                st.error(

                    f"{ficheiro.name}: "
                    f"{erro}"
                )

        st.rerun()

    aba_pendentes, aba_hoje, aba_historico = st.tabs(
        [
            "Pendentes",
            "Sai hoje",
            "Histórico",
        ]
    )

    with aba_pendentes:

        pendentes = faturas_db[

            faturas_db[
                "data_saida"
            ] > hoje_portugal()

        ].copy()

        if pendentes.empty:

            st.info(
                "Sem faturas futuras."
            )

        else:

            st.dataframe(

                pendentes,

                use_container_width=True,

                hide_index=True,
            )

    with aba_hoje:

        sai_hoje = faturas_db[

            faturas_db[
                "data_saida"
            ] == hoje_portugal()

        ].copy()

        if sai_hoje.empty:

            st.info(
                "Sem faturas para hoje."
            )

        else:

            st.dataframe(

                sai_hoje,

                use_container_width=True,

                hide_index=True,
            )

    with aba_historico:

        if historico.empty:

            st.info(
                "O histórico ainda está vazio."
            )

        else:

            st.dataframe(

                historico,

                use_container_width=True,

                hide_index=True,
            )

    st.subheader(
        "Corrigir fornecedores"
    )

    rever = faturas_db[

        faturas_db[
            "linha_id"
        ].notna()

    ].copy()

    if not rever.empty:

        colunas_edicao = [
            "linha_id",
            "numero_fatura",
            "data_saida",
            "referencia",
            "produto",
            "quantidade",
            "fornecedor",
        ]

        editado = st.data_editor(

            rever[
                colunas_edicao
            ],

            hide_index=True,

            use_container_width=True,

            disabled=[
                "linha_id",
                "numero_fatura",
                "data_saida",
                "referencia",
                "produto",
                "quantidade",
            ],

            column_config={

                "fornecedor":

                    st.column_config.SelectboxColumn(

                        "Fornecedor",

                        options=[
                            "Logista",
                            "Tabaqueira",
                            "Não identificado",
                        ],

                        required=True,
                    )
            },
        )

        if st.button(
            "Guardar correções"
        ):

            alteracoes = atualizar_fornecedores_db(

                editado,

                rever[
                    colunas_edicao
                ],
            )

            st.success(

                f"{alteracoes} alterações guardadas."
            )

            st.rerun()


# =========================================================
# CALENDÁRIO
# =========================================================

elif pagina == "📅 Calendário":

    st.title(
        "Calendário de saídas"
    )

    if faturas_db.empty:

        st.info(
            "Ainda não existem faturas guardadas."
        )

    else:

        agenda = (

            faturas_db.groupby(

                [
                    "data_saida",
                    "estado",
                ],

                as_index=False,

            ).agg(

                faturas=(
                    "numero_fatura",
                    "nunique",
                ),

                unidades=(
                    "quantidade",
                    "sum",
                ),
            )

            .sort_values(
                "data_saida"
            )
        )

        st.dataframe(

            agenda,

            use_container_width=True,

            hide_index=True,
        )

        st.subheader(
            "Próximos 14 dias"
        )

        limite = (

            hoje_portugal()

            + timedelta(
                days=14
            )
        )

        proximas = agenda[

            (
                agenda[
                    "data_saida"
                ] >= hoje_portugal()
            )

            &

            (
                agenda[
                    "data_saida"
                ] <= limite
            )

        ]

        st.dataframe(

            proximas,

            use_container_width=True,

            hide_index=True,
        )


# =========================================================
# ENCOMENDAS
# =========================================================

elif pagina == "📦 Encomendas":

    st.title(
        "Encomendas"
    )

    fornecedor = st.selectbox(

        "Fornecedor do pedido",

        FORNECEDORES,
    )

    resultado, erro = calcular_encomenda(
        fornecedor
    )

    if erro:

        st.info(
            erro
        )

        st.stop()

    mostrar_apenas = st.toggle(

        "Mostrar apenas produtos a encomendar",

        value=True,
    )

    tabela = resultado.copy()

    if mostrar_apenas:

        tabela = tabela[

            tabela[
                "sugestao"
            ] > 0
        ]

    coluna1, coluna2, coluna3 = st.columns(
        3
    )

    coluna1.metric(

        "Produtos a encomendar",

        int(

            (
                resultado[
                    "sugestao"
                ] > 0
            ).sum()
        ),
    )

    coluna2.metric(

        "Quantidade sugerida",

        formatar_numero(

            resultado[
                "sugestao"
            ].sum()
        ),
    )

    autonomias_validas = resultado.loc[

        resultado[
            "autonomia_dias"
        ] < 999,

        "autonomia_dias",
    ]

    coluna3.metric(

        "Autonomia média",

        (
            f"{formatar_numero(autonomias_validas.mean(), 1)} dias"

            if not autonomias_validas.empty

            else "0 dias"
        ),
    )

    colunas = [
        "referencia",
        "produto",
        "stock_phc",
        "media_dia",
        "autonomia_dias",
        "objetivo_dias",
        "stock_alvo",
        "sugestao",
        "estado_stock",
    ]

    st.dataframe(

        tabela[
            colunas
        ],

        use_container_width=True,

        hide_index=True,
    )

    st.download_button(

        f"⬇️ Exportar pedido {fornecedor}",

        data=converter_para_excel(

            tabela[
                colunas
            ],

            f"Pedido {fornecedor}",
        ),

        file_name=(

            f"encomenda_"
            f"{fornecedor}_"
            f"{hoje_portugal().isoformat()}"
            f".xlsx"
        ),

        mime=(

            "application/vnd.openxmlformats-"
            "officedocument.spreadsheetml.sheet"
        ),
    )


# =========================================================
# VENDAS
# =========================================================

elif pagina == "📈 Vendas":

    st.title(
        "Vendas"
    )

    fornecedor = st.selectbox(

        "Fornecedor",

        [
            "Todos",
            *FORNECEDORES,
        ],
    )

    if fornecedor == "Todos":

        atual = juntar_inventarios(
            "Atual"
        )

    else:

        atual = obter_inventario(

            fornecedor,

            "Atual",
        )

    if atual is None:

        st.info(
            "Não existem dados carregados."
        )

        st.stop()

    atual = garantir_produto(
        atual
    )

    if "saidas" in atual.columns:

        ranking = (

            atual.groupby(

                "produto",

                as_index=False,

            )[
                "saidas"
            ]

            .sum()

            .nlargest(
                30,
                "saidas",
            )
        )

        st.dataframe(

            ranking,

            use_container_width=True,

            hide_index=True,
        )


# =========================================================
# PRODUTOS
# =========================================================

elif pagina == "📋 Produtos":

    st.title(
        "Produtos"
    )

    fornecedor = st.selectbox(

        "Fornecedor",

        [
            "Todos",
            *FORNECEDORES,
        ],
    )

    if fornecedor == "Todos":

        atual = juntar_inventarios(
            "Atual"
        )

    else:

        atual = obter_inventario(

            fornecedor,

            "Atual",
        )

    if atual is None:

        st.info(
            "Não existem dados carregados."
        )

        st.stop()

    atual = garantir_produto(
        atual
    )

    pesquisa = st.text_input(
        "Pesquisar produto ou referência"
    )

    tabela = atual.copy()

    if pesquisa:

        termo = normalizar_texto(
            pesquisa
        )

        mascara = (

            tabela[
                "produto"
            ]

            .astype(str)

            .map(
                normalizar_texto
            )

            .str.contains(
                termo,
                na=False,
            )
        )

        if "referencia" in tabela.columns:

            mascara = mascara | (

                tabela[
                    "referencia"
                ]

                .astype(str)

                .map(
                    normalizar_texto
                )

                .str.contains(
                    termo,
                    na=False,
                )
            )

        tabela = tabela[
            mascara
        ]

    st.dataframe(

        tabela,

        use_container_width=True,

        hide_index=True,
    )


# =========================================================
# DEFINIÇÕES
# =========================================================

else:

    st.title(
        "Definições"
    )

    st.session_state.dias_listagem = st.number_input(

        "Quantos dias representa cada listagem?",

        min_value=1.0,

        max_value=31.0,

        value=float(

            st.session_state.dias_listagem
        ),

        step=1.0,
    )

    for fornecedor in FORNECEDORES:

        st.subheader(
            fornecedor
        )

        st.session_state.dias_objetivo[
            fornecedor
        ] = st.number_input(

            f"Objetivo de autonomia — "
            f"{fornecedor} (dias)",

            min_value=0.5,

            max_value=30.0,

            value=float(

                st.session_state.dias_objetivo[
                    fornecedor
                ]
            ),

            step=0.5,

            key=(
                f"objetivo_"
                f"{fornecedor}"
            ),
        )

        st.session_state.margem_dias[
            fornecedor
        ] = st.number_input(

            f"Margem adicional — "
            f"{fornecedor} (dias)",

            min_value=0.0,

            max_value=10.0,

            value=float(

                st.session_state.margem_dias[
                    fornecedor
                ]
            ),

            step=0.25,

            key=(
                f"margem_"
                f"{fornecedor}"
            ),
        )

        st.session_state.multiplo[
            fornecedor
        ] = st.number_input(

            f"Múltiplo do pedido — "
            f"{fornecedor}",

            min_value=1,

            max_value=1000,

            value=int(

                st.session_state.multiplo[
                    fornecedor
                ]
            ),

            step=1,

            key=(
                f"multiplo_"
                f"{fornecedor}"
            ),
        )

        st.divider()

    st.code(

        "Média diária = saídas do período ÷ dias da listagem\n"

        "Autonomia = stock PHC ÷ média diária\n"

        "Objetivo final = autonomia desejada + margem\n"

        "Stock alvo = média diária × objetivo final\n"

        "Encomendar = stock alvo - stock PHC",

        language="text",
    )
