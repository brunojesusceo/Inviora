import base64
import hashlib
import hmac
import io
import json
import math
import re
import unicodedata
import extra_streamlit_components as stx
try:
    from openai import OpenAI
except ImportError:
    OpenAI = None
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
DIAS_SEMANA = [
    "Segunda-feira",
    "Terça-feira",
    "Quarta-feira",
    "Quinta-feira",
    "Sexta-feira",
    "Sábado",
    "Domingo",
]
MAPA_DIAS = {
    0: "Segunda-feira",
    1: "Terça-feira",
    2: "Quarta-feira",
    3: "Quinta-feira",
    4: "Sexta-feira",
    5: "Sábado",
    6: "Domingo",
}

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
    "AUTH_SECRET",
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
# LOGIN PERSISTENTE — 6 HORAS
# =========================================================

COOKIE_LOGIN = "inviora_login"
HORAS_LOGIN = 6

cookie_manager = stx.CookieManager()


def criar_token_login():

    expira_em = int(
        (
            datetime.now(TZ_PORTUGAL)
            + timedelta(hours=HORAS_LOGIN)
        ).timestamp()
    )

    payload = {
        "exp": expira_em,
        "app": "inviora",
    }

    payload_json = json.dumps(
        payload,
        separators=(",", ":"),
    )

    assinatura = hmac.new(
        str(
            st.secrets["AUTH_SECRET"]
        ).encode("utf-8"),
        payload_json.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    conteudo = json.dumps(
        {
            "payload": payload,
            "assinatura": assinatura,
        },
        separators=(",", ":"),
    )

    return base64.urlsafe_b64encode(
        conteudo.encode("utf-8")
    ).decode("utf-8")


def validar_token_login(token):

    if not token:

        return False

    try:

        conteudo = base64.urlsafe_b64decode(
            token.encode("utf-8")
        ).decode("utf-8")

        dados = json.loads(
            conteudo
        )

        payload = dados["payload"]

        assinatura_recebida = dados[
            "assinatura"
        ]

        payload_json = json.dumps(
            payload,
            separators=(",", ":"),
        )

        assinatura_correta = hmac.new(
            str(
                st.secrets["AUTH_SECRET"]
            ).encode("utf-8"),
            payload_json.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        assinatura_valida = (
            hmac.compare_digest(
                assinatura_recebida,
                assinatura_correta,
            )
        )

        nao_expirou = (
            int(payload["exp"])
            > int(
                datetime.now(
                    TZ_PORTUGAL
                ).timestamp()
            )
        )

        return (
            assinatura_valida
            and nao_expirou
            and payload.get("app")
            == "inviora"
        )

    except Exception:

        return False


token_cookie = cookie_manager.get(
    COOKIE_LOGIN
)

if "autenticado" not in st.session_state:

    st.session_state.autenticado = (
        validar_token_login(
            token_cookie
        )
    )


if not st.session_state.autenticado:

    st.title(
        "🔒 Inviora"
    )

    st.caption(
        "A sessão ficará ativa durante 6 horas."
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

            token = criar_token_login()

            cookie_manager.set(
                COOKIE_LOGIN,
                token,
                expires_at=(
                    datetime.now(
                        TZ_PORTUGAL
                    )
                    + timedelta(
                        hours=HORAS_LOGIN
                    )
                ),
                key="guardar_login_inviora",
            )

            st.session_state.autenticado = True

            st.success(
                "Sessão iniciada."
            )

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

            periodo: {

                dia: None

                for dia
                in DIAS_SEMANA
            }

            for periodo
            in PERIODOS
        }

        for fornecedor
        in FORNECEDORES
    }


if "nomes_ficheiros" not in st.session_state:

    st.session_state.nomes_ficheiros = {

        fornecedor: {

            periodo: {

                dia: None

                for dia
                in DIAS_SEMANA
            }

            for periodo
            in PERIODOS
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
    dia_semana=None,
):

    if dia_semana is None:
        dia_semana = MAPA_DIAS[
            hoje_portugal().weekday()
        ]

    inventarios_fornecedor = (
        st.session_state.inventarios.get(
            fornecedor,
            {}
        )
    )

    inventarios_periodo = (
        inventarios_fornecedor.get(
            periodo,
            {}
        )
    )

    return inventarios_periodo.get(
        dia_semana
    )


def dia_stock_atual():

    return MAPA_DIAS[
        hoje_portugal().weekday()
    ]


def dia_entrega_seguinte():

    weekday = hoje_portugal().weekday()

    mapa_entrega = {
        0: "Terça-feira",
        1: "Quarta-feira",
        2: "Quinta-feira",
        3: "Sexta-feira",
        4: "Segunda-feira",
        5: "Segunda-feira",
        6: "Segunda-feira",
    }

    return mapa_entrega[
        weekday
    ]


def obter_inventarios_para_calculo(
    fornecedor,
):

    dia_atual = dia_stock_atual()

    dia_referencia = dia_entrega_seguinte()

    atual = obter_inventario(
        fornecedor,
        "Atual",
        dia_atual,
    )

    anterior = obter_inventario(
        fornecedor,
        "Anterior",
        dia_referencia,
    )

    return (
        atual,
        anterior,
        dia_atual,
        dia_referencia,
    )


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

def dataframe_para_json(
    dados,
):

    texto_json = dados.to_json(
        orient="records",
        date_format="iso",
        force_ascii=False,
    )

    return json.loads(
        texto_json
    )


def guardar_inventario_db(
    fornecedor,
    periodo,
    dia_semana,
    ficheiro_nome,
    dados,
):

    registo = {
        "fornecedor": str(
            fornecedor
        ),
        "periodo": str(
            periodo
        ),
        "dia_semana": str(
            dia_semana
        ),
        "ficheiro": str(
            ficheiro_nome
        ),
        "dados": dataframe_para_json(
            dados
        ),
        "atualizado_em": (
            datetime.now(
                TZ_PORTUGAL
            ).isoformat()
        ),
    }

    resposta = (
        supabase
        .table(
            "inventarios"
        )
        .upsert(
            registo,
            on_conflict=(
                "fornecedor,"
                "periodo,"
                "dia_semana"
            ),
        )
        .execute()
    )

    return resposta


def carregar_inventarios_db():

    resposta = (
        supabase
        .table(
            "inventarios"
        )
        .select(
            "*"
        )
        .execute()
    )

    registos = (
        resposta.data
        or []
    )

    for registo in registos:

        fornecedor = registo.get(
            "fornecedor"
        )

        periodo = registo.get(
            "periodo"
        )
        dia_semana = registo.get(
    "dia_semana"
)

        dados_json = registo.get(
            "dados"
        ) or []

        if (
            fornecedor
            not in FORNECEDORES
        ):

            continue

        if periodo not in PERIODOS:
            continue

        if dia_semana not in DIAS_SEMANA:
            continue

        dados = pd.DataFrame(
            dados_json
        )

        for coluna in [
            "entradas",
            "saidas",
            "stock_final",
        ]:

            if coluna in dados.columns:

                dados[coluna] = pd.to_numeric(
                    dados[coluna],
                    errors="coerce",
                ).fillna(0)

        if "referencia" in dados.columns:

            dados[
                "referencia"
            ] = dados[
                "referencia"
            ].map(
                normalizar_referencia
            )

        st.session_state.inventarios[
    fornecedor
][periodo][dia_semana] = dados

        st.session_state.nomes_ficheiros[
    fornecedor
][periodo][dia_semana] = registo.get(
    "ficheiro"
)



if "inventarios_recuperados" not in st.session_state:

    try:

        carregar_inventarios_db()

        st.session_state.inventarios_recuperados = True

    except Exception as erro:

        st.warning(
            "Não foi possível recuperar automaticamente "
            "os inventários guardados."
        )

        st.exception(
            erro
        )



def eliminar_inventarios_db():

    (
        supabase
        .table(
            "inventarios"
        )
        .delete()
        .neq(
            "id",
            0,
        )
        .execute()
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

    (
    atual,
    anterior,
    dia_atual,
    dia_referencia,
) = obter_inventarios_para_calculo(
    fornecedor
)

    if atual is None:

        return (
            None,
            (
                f"Falta carregar {fornecedor} — "
                f"Atual — {dia_atual}."
            ),
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
# ASSISTENTE INVIORA
# =========================================================

def construir_contexto_assistente():

    contexto = {
        "data": hoje_portugal().isoformat(),
        "faturas_hoje": 0,
        "unidades_hoje": 0,
        "faturas_futuras": 0,
        "linhas_sem_fornecedor": 0,
        "fornecedores": {},
    }

    faturas = carregar_faturas_db()

    if not faturas.empty:

        hoje_df = faturas[
            faturas[
                "data_saida"
            ] == hoje_portugal()
        ]

        futuras_df = faturas[
            faturas[
                "data_saida"
            ] > hoje_portugal()
        ]

        contexto[
            "faturas_hoje"
        ] = int(
            hoje_df[
                "numero_fatura"
            ].nunique()
        )

        contexto[
            "unidades_hoje"
        ] = float(
            hoje_df[
                "quantidade"
            ].sum()
        )

        contexto[
            "faturas_futuras"
        ] = int(
            futuras_df[
                "numero_fatura"
            ].nunique()
        )

        contexto[
            "linhas_sem_fornecedor"
        ] = int(
            (
                faturas[
                    "fornecedor"
                ]
                == "Não identificado"
            ).sum()
        )

    for fornecedor in FORNECEDORES:

        resultado, erro = calcular_encomenda(
            fornecedor
        )

        if erro:

            contexto[
                "fornecedores"
            ][fornecedor] = {
                "disponivel": False,
                "erro": erro,
            }

            continue

        autonomias = resultado.loc[
            resultado[
                "autonomia_dias"
            ] < 999,
            "autonomia_dias",
        ]

        contexto[
            "fornecedores"
        ][fornecedor] = {
            "disponivel": True,
            "artigos_encomendar": int(
                (
                    resultado[
                        "sugestao"
                    ] > 0
                ).sum()
            ),
            "quantidade_sugerida": int(
                resultado[
                    "sugestao"
                ].sum()
            ),
            "artigos_criticos": int(
                (
                    resultado[
                        "autonomia_dias"
                    ] < 1
                ).sum()
            ),
            "artigos_amanha": int(
                (
                    (
                        resultado[
                            "autonomia_dias"
                        ] >= 1
                    )
                    &
                    (
                        resultado[
                            "autonomia_dias"
                        ] < 2
                    )
                ).sum()
            ),
            "autonomia_media": float(
                autonomias.mean()
                if not autonomias.empty
                else 0
            ),
        }

    return contexto


def resposta_regras(
    contexto
):

    linhas = []

    if contexto[
        "faturas_hoje"
    ]:

        linhas.append(
            f"Hoje saem "
            f"{contexto['faturas_hoje']} faturas, "
            f"com {formatar_numero(contexto['unidades_hoje'], 1)} "
            f"unidades."
        )

    else:

        linhas.append(
            "Hoje não existem faturas agendadas para saída."
        )

    for fornecedor, dados in contexto[
        "fornecedores"
    ].items():

        if not dados.get(
            "disponivel"
        ):

            linhas.append(
                f"{fornecedor}: "
                f"{dados['erro']}"
            )

            continue

        if dados[
            "artigos_encomendar"
        ] > 0:

            linhas.append(
                f"{fornecedor}: encomendar "
                f"{dados['artigos_encomendar']} artigos, "
                f"num total sugerido de "
                f"{dados['quantidade_sugerida']} unidades."
            )

        else:

            linhas.append(
                f"{fornecedor}: não é necessário "
                f"encomendar com os dados atuais."
            )

        if dados[
            "artigos_criticos"
        ] > 0:

            linhas.append(
                f"{fornecedor}: "
                f"{dados['artigos_criticos']} artigos "
                f"têm menos de um dia de autonomia."
            )

    if contexto[
        "linhas_sem_fornecedor"
    ] > 0:

        linhas.append(
            f"Existem "
            f"{contexto['linhas_sem_fornecedor']} linhas "
            f"sem fornecedor identificado."
        )

    return "\n\n".join(
        linhas
    )


def resposta_openai(
    pergunta,
    contexto,
):

    api_key = st.secrets.get(
        "OPENAI_API_KEY",
        "",
    )

    if (
        not api_key
        or OpenAI is None
    ):

        return resposta_regras(
            contexto
        )

    cliente = OpenAI(
        api_key=api_key
    )

    instrucoes = """
És o Assistente Inviora, um copiloto de compras e stock.
Responde sempre em português de Portugal.
Usa apenas os dados fornecidos.
Não inventes produtos, valores, datas ou causas.
Quando faltarem dados, diz claramente que faltam dados.
Dá recomendações curtas, práticas e prudentes.
Nunca digas que uma encomenda deve ser enviada sem revisão humana.
"""

    conteudo = {
        "pergunta": pergunta,
        "dados_inviora": contexto,
    }

    try:

        resposta = cliente.responses.create(
            model="gpt-4.1-mini",
            instructions=instrucoes,
            input=json.dumps(
                conteudo,
                ensure_ascii=False,
            ),
            store=False,
        )

        return resposta.output_text

    except Exception:

        return (
            resposta_regras(
                contexto
            )
            + "\n\n"
            + "A resposta em linguagem natural não ficou "
            + "disponível; usei o modo seguro por regras."
        )
        # =========================================================
# ADMINISTRAÇÃO — ELIMINAR DADOS
# =========================================================

def eliminar_inventario_db(
    fornecedor,
    periodo,
):

    (
        supabase
        .table("inventarios")
        .delete()
        .eq("fornecedor", fornecedor)
        .eq("periodo", periodo)
        .execute()
    )

    st.session_state.inventarios[
        fornecedor
    ][periodo] = None

    st.session_state.nomes_ficheiros[
        fornecedor
    ][periodo] = None


def eliminar_fatura_db(
    fatura_id,
):

    # Primeiro elimina as linhas da fatura.
    (
        supabase
        .table("fatura_linhas")
        .delete()
        .eq("fatura_id", int(fatura_id))
        .execute()
    )

    # Depois elimina o cabeçalho da fatura.
    (
        supabase
        .table("faturas")
        .delete()
        .eq("id", int(fatura_id))
        .execute()
    )
    def eliminar_todas_faturas_db():
        supabase.table("fatura_linhas").delete().neq("id", 0).execute()
        supabase.table("faturas").delete().neq("id", 0).execute()
        return True


def eliminar_todos_inventarios_db():
    supabase.table("inventarios").delete().neq("id", 0).execute()

    st.session_state.inventarios = {
        fornecedor: {
            "Atual": None,
            "Anterior": None,
        }
        for fornecedor in FORNECEDORES
    }

    st.session_state.nomes_ficheiros = {
        fornecedor: {
            "Atual": None,
            "Anterior": None,
        }
        for fornecedor in FORNECEDORES
    }

    return True


def repor_aplicacao_db():

    eliminar_todas_faturas_db()
    eliminar_todos_inventarios_db()

    st.session_state.dias_objetivo = {
        "Logista": 1.0,
        "Tabaqueira": 3.0,
    }

    st.session_state.margem_dias = {
        "Logista": 0.25,
        "Tabaqueira": 0.50,
    }

    st.session_state.multiplo = {
        "Logista": 1,
        "Tabaqueira": 1,
    }

    st.session_state.dias_listagem = 7.0

# =========================================================
# MENU
# =========================================================

with st.sidebar:

    st.markdown(
        '<div class="brand">INVIORA</div>',
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div class="tagline">Transformar dados em decisões.</div>',
        unsafe_allow_html=True,
    )

    pagina = st.radio(
        "Navegação",
        
            [
    "🏠 Home",
    "🧠 Assistente",
    "📥 Importar inventário",
    "🧾 Faturas",
    "📅 Calendário",
    "📦 Encomendas",
    "📈 Vendas",
    "📋 Produtos",
    "🛠️ Administração",
    "⚙️ Definições",
]
        ,
        label_visibility="collapsed",
    )

    st.divider()

    st.caption(f"Hoje: {hoje_portugal().strftime('%d/%m/%Y')}")
    st.caption("🟢 Supabase ligado")
    st.caption("Inviora v0.6.0")

    if st.button("Terminar sessão"):
        cookie_manager.delete(
            COOKIE_LOGIN,
            key="apagar_login_inviora",
        )
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

if pagina == "🛠️ Administração":

    st.title(
        "🛠️ Administração"
    )

    st.warning(
        "Os dados apagados nesta página são removidos "
        "permanentemente do Supabase."
    )

    aba_inventarios, aba_faturas = st.tabs(
        [
            "📥 Inventários",
            "🧾 Faturas",
        ]
    )

    # =====================================================
    # APAGAR INVENTÁRIOS
    # =====================================================

    with aba_inventarios:

        st.subheader(
            "Apagar uma listagem"
        )

        opcoes_inventarios = []

        for fornecedor in FORNECEDORES:

            for periodo in PERIODOS:

                dados = st.session_state.inventarios[
                    fornecedor
                ][periodo]

                ficheiro = (
                    st.session_state
                    .nomes_ficheiros[
                        fornecedor
                    ][periodo]
                )

                if dados is not None:

                    opcoes_inventarios.append(
                        {
                            "fornecedor": fornecedor,
                            "periodo": periodo,
                            "ficheiro": (
                                ficheiro
                                or "Sem nome"
                            ),
                            "linhas": len(dados),
                        }
                    )

        if not opcoes_inventarios:

            st.info(
                "Não existem inventários guardados."
            )

        else:

            etiquetas_inventarios = {
                (
                    f"{item['fornecedor']} — "
                    f"{item['periodo']} — "
                    f"{item['ficheiro']} "
                    f"({item['linhas']} linhas)"
                ): item
                for item in opcoes_inventarios
            }

            inventario_escolhido = st.selectbox(
                "Escolher inventário",
                list(
                    etiquetas_inventarios.keys()
                ),
            )

            inventario = etiquetas_inventarios[
                inventario_escolhido
            ]

            confirmar_inventario = st.checkbox(
                (
                    "Confirmo que quero apagar "
                    f"{inventario['fornecedor']} — "
                    f"{inventario['periodo']}"
                ),
                key="confirmar_apagar_inventario",
            )

            if st.button(
                "🗑️ Apagar inventário",
                type="primary",
                disabled=not confirmar_inventario,
                use_container_width=True,
            ):

                try:

                    eliminar_inventario_db(
                        inventario[
                            "fornecedor"
                        ],
                        inventario[
                            "periodo"
                        ],
                    )

                    st.success(
                        "Inventário apagado."
                    )

                    st.rerun()

                except Exception as erro:

                    st.error(
                        "Não foi possível apagar "
                        "o inventário."
                    )

                    st.exception(
                        erro
                    )

    # =====================================================
    # APAGAR FATURAS
    # =====================================================

    with aba_faturas:

        st.subheader(
            "Apagar uma fatura"
        )

        faturas_admin = carregar_faturas_db()

        if faturas_admin.empty:

            st.info(
                "Não existem faturas guardadas."
            )

        else:

            faturas_unicas = (
                faturas_admin[
                    [
                        "fatura_id",
                        "numero_fatura",
                        "data_fatura",
                        "data_saida",
                        "ficheiro",
                    ]
                ]
                .drop_duplicates(
                    subset=["fatura_id"]
                )
                .sort_values(
                    "data_saida",
                    ascending=False,
                )
            )

            etiquetas_faturas = {}

            for _, linha in (
                faturas_unicas.iterrows()
            ):

                data_saida_texto = (
                    linha["data_saida"]
                    .strftime("%d/%m/%Y")
                    if isinstance(
                        linha["data_saida"],
                        date,
                    )
                    else "Sem data"
                )

                etiqueta = (
                    f"Fatura "
                    f"{linha['numero_fatura']} — "
                    f"saída {data_saida_texto} — "
                    f"{linha['ficheiro']}"
                )

                etiquetas_faturas[
                    etiqueta
                ] = int(
                    linha["fatura_id"]
                )

            fatura_escolhida = st.selectbox(
                "Escolher fatura",
                list(
                    etiquetas_faturas.keys()
                ),
            )

            confirmar_fatura = st.checkbox(
                (
                    "Confirmo que quero apagar "
                    "esta fatura e todos os seus artigos"
                ),
                key="confirmar_apagar_fatura",
            )

            if st.button(
                "🗑️ Apagar fatura",
                type="primary",
                disabled=not confirmar_fatura,
                use_container_width=True,
            ):

                try:

                    eliminar_fatura_db(
                        etiquetas_faturas[
                            fatura_escolhida
                        ]
                    )

                    st.success(
                        "Fatura apagada."
                    )

                    st.rerun()

                except Exception as erro:

                    st.error(
                        "Não foi possível apagar "
                        "a fatura."
                    )

                    st.exception(
                        erro
                    )

    st.divider()

    st.subheader(
        "⚠️ Zona de perigo"
    )

    st.warning(
        "Estas ações são permanentes e não podem ser anuladas."
    )

    # =====================================================
    # APAGAR TODAS AS FATURAS
    # =====================================================

    with st.expander(
        "🗑️ Apagar todas as faturas"
    ):

        confirmar_todas_faturas = st.text_input(
            "Escreve APAGAR FATURAS para confirmar",
            key="confirmar_todas_faturas",
        )

        if st.button(
            "Apagar todas as faturas",
            type="primary",
            disabled=(
                confirmar_todas_faturas
                != "APAGAR FATURAS"
            ),
            use_container_width=True,
            key="botao_apagar_todas_faturas",
        ):

            try:

                eliminar_todas_faturas_db()

                st.success(
                    "Todas as faturas foram apagadas."
                )

                st.rerun()

            except Exception as erro:

                st.error(
                    "Não foi possível apagar todas as faturas."
                )

                st.exception(
                    erro
                )

    # =====================================================
    # APAGAR TODOS OS INVENTÁRIOS
    # =====================================================

    with st.expander(
        "🗑️ Apagar todos os inventários"
    ):

        confirmar_todos_inventarios = st.text_input(
            "Escreve APAGAR INVENTÁRIOS para confirmar",
            key="confirmar_todos_inventarios",
        )

        if st.button(
            "Apagar todos os inventários",
            type="primary",
            disabled=(
                confirmar_todos_inventarios
                != "APAGAR INVENTÁRIOS"
            ),
            use_container_width=True,
            key="botao_apagar_todos_inventarios",
        ):

            try:

                eliminar_todos_inventarios_db()

                st.success(
                    "Todos os inventários foram apagados."
                )

                st.rerun()

            except Exception as erro:

                st.error(
                    "Não foi possível apagar os inventários."
                )

                st.exception(
                    erro
                )

    # =====================================================
    # REPOR A APLICAÇÃO
    # =====================================================

    with st.expander(
        "💣 Repor completamente a aplicação"
    ):

        st.error(
            "Esta ação apaga todas as faturas, inventários "
            "e repõe as definições padrão."
        )

        confirmar_reposicao = st.text_input(
            "Escreve REPOR INVIORA para confirmar",
            key="confirmar_reposicao",
        )

        if st.button(
            "Repor aplicação",
            type="primary",
            disabled=(
                confirmar_reposicao
                != "REPOR INVIORA"
            ),
            use_container_width=True,
            key="botao_repor_inviora",
        ):

            try:

                repor_aplicacao_db()

                st.success(
                    "A Inviora foi reposta."
                )

                st.rerun()

            except Exception as erro:

                st.error(
                    "Não foi possível repor a aplicação."
                )

                st.exception(
                    erro
                )


elif pagina == "🏠 Home":

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
    # =====================================================
    # RESUMO EXECUTIVO
    # =====================================================

    inventarios_carregados = 0
    total_linhas_inventario = 0
    ultima_atualizacao_texto = "Sem dados"

    for fornecedor_resumo in FORNECEDORES:

        for periodo_resumo in PERIODOS:

            dados_resumo = obter_inventario(
                fornecedor_resumo,
                periodo_resumo,
            )

            if dados_resumo is not None:

                inventarios_carregados += 1
                total_linhas_inventario += len(
                    dados_resumo
                )

    total_artigos_encomendar = 0
    total_quantidade_sugerida = 0
    total_artigos_criticos = 0

    for fornecedor_resumo in FORNECEDORES:

        resultado_resumo, erro_resumo = calcular_encomenda(
            fornecedor_resumo
        )

        if erro_resumo is None:

            total_artigos_encomendar += int(
                (
                    resultado_resumo[
                        "sugestao"
                    ] > 0
                ).sum()
            )

            total_quantidade_sugerida += int(
                resultado_resumo[
                    "sugestao"
                ].sum()
            )

            total_artigos_criticos += int(
                (
                    resultado_resumo[
                        "autonomia_dias"
                    ] < 1
                ).sum()
            )

    if not faturas_db.empty:

        faturas_futuras_resumo = faturas_db[
            faturas_db[
                "data_saida"
            ] > hoje_portugal()
        ]

        numero_faturas_futuras = int(
            faturas_futuras_resumo[
                "numero_fatura"
            ].nunique()
        )

    else:

        numero_faturas_futuras = 0

    st.subheader(
        "Resumo executivo"
    )

    resumo1, resumo2, resumo3, resumo4 = st.columns(
        4
    )

    resumo1.metric(
        "Inventários ativos",
        f"{inventarios_carregados}/4",
        help=(
            "Logista e Tabaqueira, "
            "período atual e anterior."
        ),
    )

    resumo2.metric(
        "Artigos a encomendar",
        total_artigos_encomendar,
        delta=(
            f"{total_quantidade_sugerida} unidades"
        ),
        delta_color="off",
    )

    resumo3.metric(
        "Artigos críticos",
        total_artigos_criticos,
        help=(
            "Produtos com menos de um dia "
            "de autonomia."
        ),
    )

    resumo4.metric(
        "Faturas futuras",
        numero_faturas_futuras,
    )

        # =====================================================
    # ESTADO DOS INVENTÁRIOS
    # =====================================================

    inventarios_em_falta = []

    for fornecedor_estado in FORNECEDORES:

        for periodo_estado in PERIODOS:

            dados_estado = obter_inventario(
                fornecedor_estado,
                periodo_estado,
            )

            if dados_estado is None:

                inventarios_em_falta.append(
                    f"{fornecedor_estado} — "
                    f"{periodo_estado}"
                )

    percentagem_inventarios = int(
        (
            inventarios_carregados
            / 4
        )
        * 100
    )

    st.caption(
        f"Preparação dos dados: "
        f"{percentagem_inventarios}%"
    )

    st.progress(
        percentagem_inventarios
    )

    if inventarios_carregados == 4:

        st.success(
            "✅ Todos os inventários necessários "
            "estão carregados e disponíveis."
        )

    elif inventarios_carregados > 0:

        st.warning(
            f"⚠️ Existem apenas "
            f"{inventarios_carregados} de 4 "
            f"inventários carregados."
        )

        st.markdown(
            "**Falta importar:**"
        )

        for inventario_em_falta in inventarios_em_falta:

            st.write(
                f"• {inventario_em_falta}"
            )

    else:

        st.error(
            "❌ Ainda não existem inventários carregados."
        )

        st.markdown(
            "**Falta importar:**"
        )

        for inventario_em_falta in inventarios_em_falta:

            st.write(
                f"• {inventario_em_falta}"
            )

    if total_artigos_criticos > 0:

        st.error(
            f"🚨 Atenção imediata: "
            f"{total_artigos_criticos} artigos "
            f"têm menos de um dia de autonomia."
        )

    elif total_artigos_encomendar > 0:

        st.info(
            f"📦 Existem "
            f"{total_artigos_encomendar} artigos "
            f"com sugestão de encomenda."
        )

    else:

        st.success(
            "🟢 Não existem compras urgentes "
            "com os dados atualmente carregados."
        )
    # =====================================================
    # GRÁFICO — NECESSIDADES POR FORNECEDOR
    # =====================================================

    dados_grafico_fornecedores = []

    for fornecedor_grafico in FORNECEDORES:

        resultado_grafico, erro_grafico = calcular_encomenda(
            fornecedor_grafico
        )

        if erro_grafico is None:

            artigos_encomendar_grafico = int(
                (
                    resultado_grafico[
                        "sugestao"
                    ] > 0
                ).sum()
            )

            artigos_criticos_grafico = int(
                (
                    resultado_grafico[
                        "autonomia_dias"
                    ] < 1
                ).sum()
            )

            dados_grafico_fornecedores.append(
                {
                    "Fornecedor": fornecedor_grafico,
                    "Indicador": "Artigos a encomendar",
                    "Quantidade": artigos_encomendar_grafico,
                }
            )

            dados_grafico_fornecedores.append(
                {
                    "Fornecedor": fornecedor_grafico,
                    "Indicador": "Artigos críticos",
                    "Quantidade": artigos_criticos_grafico,
                }
            )

    if dados_grafico_fornecedores:

        st.subheader(
            "Necessidades por fornecedor"
        )

        df_grafico_fornecedores = pd.DataFrame(
            dados_grafico_fornecedores
        )

        grafico_fornecedores = px.bar(
            df_grafico_fornecedores,
            x="Fornecedor",
            y="Quantidade",
            color="Indicador",
            barmode="group",
            text_auto=True,
        )

        grafico_fornecedores.update_layout(
            xaxis_title=None,
            yaxis_title="Número de artigos",
            legend_title=None,
            margin=dict(
                l=10,
                r=10,
                t=20,
                b=10,
            ),
            height=380,
        )

        grafico_fornecedores.update_traces(
            textposition="outside"
        )

        st.plotly_chart(
            grafico_fornecedores,
            use_container_width=True,
            config={
                "displayModeBar": False,
            },
        )

    else:

        st.info(
            "O gráfico ficará disponível quando existirem "
            "inventários atuais carregados."
        )
            # =====================================================
    # BRIEFING OPERACIONAL DO DIA
    # =====================================================

    faturas_saida_hoje_briefing = 0
    unidades_saida_hoje_briefing = 0

    if not faturas_db.empty:

        faturas_hoje_briefing = faturas_db[
            faturas_db[
                "data_saida"
            ] == hoje_portugal()
        ]

        faturas_saida_hoje_briefing = int(
            faturas_hoje_briefing[
                "numero_fatura"
            ].nunique()
        )

        unidades_saida_hoje_briefing = float(
            faturas_hoje_briefing[
                "quantidade"
            ].sum()
        )

    briefing_prioridades = []

    if total_artigos_criticos > 0:

        briefing_prioridades.append(
            (
                "🔴 Prioridade máxima: "
                f"{total_artigos_criticos} artigos "
                "têm menos de um dia de autonomia."
            )
        )

    if total_artigos_encomendar > 0:

        briefing_prioridades.append(
            (
                "📦 Preparar encomendas para "
                f"{total_artigos_encomendar} artigos, "
                f"num total sugerido de "
                f"{total_quantidade_sugerida} unidades."
            )
        )

    if faturas_saida_hoje_briefing > 0:

        briefing_prioridades.append(
            (
                "🚚 Hoje saem "
                f"{faturas_saida_hoje_briefing} faturas, "
                f"representando "
                f"{formatar_numero(unidades_saida_hoje_briefing, 1)} "
                "unidades."
            )
        )

    if inventarios_em_falta:

        briefing_prioridades.append(
            (
                "⚠️ Completar os inventários em falta: "
                + ", ".join(
                    inventarios_em_falta
                )
                + "."
            )
        )

    if numero_faturas_futuras > 0:

        briefing_prioridades.append(
            (
                "📅 Existem "
                f"{numero_faturas_futuras} faturas "
                "agendadas para datas futuras."
            )
        )

    if not briefing_prioridades:

        briefing_prioridades.append(
            (
                "🟢 Operação estável: "
                "não existem tarefas urgentes "
                "com os dados atualmente disponíveis."
            )
        )

    st.subheader(
        "Briefing operacional"
    )

    with st.container(
        border=True
    ):

        st.markdown(
            f"**Resumo de "
            f"{hoje_portugal().strftime('%d/%m/%Y')}**"
        )

        for prioridade in briefing_prioridades:

            st.write(
                prioridade
            )

        st.caption(
            "Gerado automaticamente pela Inviora "
            "com base nos dados guardados."
        )
            # =====================================================
    # AÇÕES RECOMENDADAS
    # =====================================================

    st.subheader(
        "O que fazer agora"
    )

    acoes_recomendadas = []

    for fornecedor_acao in FORNECEDORES:

        resultado_acao, erro_acao = calcular_encomenda(
            fornecedor_acao
        )

        if erro_acao is not None:

            acoes_recomendadas.append(
                {
                    "Fornecedor": fornecedor_acao,
                    "Ação": "Completar dados",
                    "Detalhe": erro_acao,
                    "Prioridade": "⚪ Dados em falta",
                }
            )

            continue

        artigos_criticos_acao = int(
            (
                resultado_acao[
                    "autonomia_dias"
                ] < 1
            ).sum()
        )

        artigos_encomendar_acao = int(
            (
                resultado_acao[
                    "sugestao"
                ] > 0
            ).sum()
        )

        quantidade_sugerida_acao = int(
            resultado_acao[
                "sugestao"
            ].sum()
        )

        if artigos_criticos_acao > 0:

            acoes_recomendadas.append(
                {
                    "Fornecedor": fornecedor_acao,
                    "Ação": "Preparar encomenda hoje",
                    "Detalhe": (
                        f"{artigos_criticos_acao} artigos críticos · "
                        f"{artigos_encomendar_acao} artigos a encomendar · "
                        f"{quantidade_sugerida_acao} unidades sugeridas"
                    ),
                    "Prioridade": "🔴 Alta",
                }
            )

        elif artigos_encomendar_acao > 0:

            acoes_recomendadas.append(
                {
                    "Fornecedor": fornecedor_acao,
                    "Ação": "Rever encomenda",
                    "Detalhe": (
                        f"{artigos_encomendar_acao} artigos · "
                        f"{quantidade_sugerida_acao} unidades sugeridas"
                    ),
                    "Prioridade": "🟠 Média",
                }
            )

        else:

            acoes_recomendadas.append(
                {
                    "Fornecedor": fornecedor_acao,
                    "Ação": "Não encomendar",
                    "Detalhe": (
                        "A cobertura atual é suficiente."
                    ),
                    "Prioridade": "🟢 Baixa",
                }
            )

    st.dataframe(
        pd.DataFrame(
            acoes_recomendadas
        )[
            [
                "Prioridade",
                "Fornecedor",
                "Ação",
                "Detalhe",
            ]
        ],
        use_container_width=True,
        hide_index=True,
    )

    # =====================================================
    # TOP PRODUTOS MAIS URGENTES
    # =====================================================

    produtos_urgentes = []

    for fornecedor_urgente in FORNECEDORES:

        resultado_urgente, erro_urgente = calcular_encomenda(
            fornecedor_urgente
        )

        if erro_urgente is not None:

            continue

        resultado_urgente = resultado_urgente[
            resultado_urgente[
                "autonomia_dias"
            ] < 3
        ].copy()

        if resultado_urgente.empty:

            continue

        resultado_urgente[
            "Fornecedor"
        ] = fornecedor_urgente

        produtos_urgentes.append(
            resultado_urgente
        )

    if produtos_urgentes:

        top_urgentes = (
            pd.concat(
                produtos_urgentes,
                ignore_index=True,
            )
            .sort_values(
                [
                    "autonomia_dias",
                    "sugestao",
                ],
                ascending=[
                    True,
                    False,
                ],
            )
            .head(
                10
            )
        )

        st.subheader(
            "Top 10 produtos mais urgentes"
        )

        colunas_urgentes = [
            coluna
            for coluna in [
                "Fornecedor",
                "referencia",
                "produto",
                "stock_phc",
                "media_dia",
                "autonomia_dias",
                "sugestao",
                "estado_stock",
            ]
            if coluna in top_urgentes.columns
        ]

        st.dataframe(
            top_urgentes[
                colunas_urgentes
            ],
            use_container_width=True,
            hide_index=True,
        )

    else:

        st.success(
            "Não existem produtos abaixo de 3 dias de autonomia."
        )
    st.divider()
    
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
# ASSISTENTE
# =========================================================

elif pagina == "🧠 Assistente":

    st.title(
        "🧠 Assistente Inviora"
    )

    st.caption(
        "Analisa inventários, encomendas e faturas "
        "sem enviar PDFs completos para a IA."
    )

    contexto = construir_contexto_assistente()

    st.subheader(
        "Briefing diário"
    )

    briefing = resposta_openai(
        "Cria um briefing operacional curto para hoje.",
        contexto,
    )

    st.info(
        briefing
    )

    st.subheader(
        "Perguntar à Inviora"
    )

    pergunta = st.text_input(
        "Pergunta",
        placeholder=(
            "Ex.: Posso adiar a Tabaqueira?"
        ),
    )

    coluna1, coluna2, coluna3 = st.columns(
        3
    )

    with coluna1:

        perguntar_criticos = st.button(
            "O que é crítico?",
            use_container_width=True,
        )

    with coluna2:

        perguntar_logista = st.button(
            "Posso adiar Logista?",
            use_container_width=True,
        )

    with coluna3:

        perguntar_tabaqueira = st.button(
            "Posso adiar Tabaqueira?",
            use_container_width=True,
        )

    pergunta_final = pergunta

    if perguntar_criticos:

        pergunta_final = (
            "Quais são as prioridades e riscos críticos?"
        )

    elif perguntar_logista:

        pergunta_final = (
            "Posso adiar a encomenda da Logista?"
        )

    elif perguntar_tabaqueira:

        pergunta_final = (
            "Posso adiar a encomenda da Tabaqueira?"
        )

    if pergunta_final:

        with st.spinner(
            "A analisar..."
        ):

            resposta = resposta_openai(
                pergunta_final,
                contexto,
            )

        st.success(
            resposta
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

    dia_semana = st.selectbox(
        "Dia da semana",
        DIAS_SEMANA,
    )

    ficheiro = st.file_uploader(
        f"{fornecedor} — {periodo} — {dia_semana}",
        type=[
            "xlsx",
            "csv",
        ],
        key=(
            f"upload_"
            f"{fornecedor}_"
            f"{periodo}_"
            f"{dia_semana}"
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
][periodo][dia_semana] = dados

            st.session_state.nomes_ficheiros[
    fornecedor
][periodo][dia_semana] = ficheiro.name

            guardar_inventario_db(
    fornecedor,
    periodo,
    ficheiro.name,
    dados,
)

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
