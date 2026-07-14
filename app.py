import io
import math
import re
import unicodedata
from datetime import date

import pandas as pd
import plotly.express as px
import streamlit as st
from pypdf import PdfReader


# =========================================================
# INVIORA — Smart Inventory Intelligence
# Versão 0.5.0
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
            padding-top: 1.4rem;
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
            opacity: 0.72;
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

DIAS_SAIDA = [
    "Quarta-feira",
    "Quinta-feira",
]


# =========================================================
# ESTADO DA APLICAÇÃO
# =========================================================

if "inventarios" not in st.session_state:

    st.session_state.inventarios = {

        fornecedor: {
            "Atual": None,
            "Anterior": None,
        }

        for fornecedor in FORNECEDORES
    }


if "nomes_ficheiros" not in st.session_state:

    st.session_state.nomes_ficheiros = {

        fornecedor: {
            "Atual": None,
            "Anterior": None,
        }

        for fornecedor in FORNECEDORES
    }


if "faturas" not in st.session_state:

    st.session_state.faturas = pd.DataFrame(

        columns=[
            "numero_fatura",
            "cliente",
            "vendedor",
            "data_fatura",
            "dia_saida",
            "referencia",
            "produto",
            "quantidade",
            "fornecedor",
            "ficheiro",
        ]
    )


if "dias_objetivo" not in st.session_state:

    st.session_state.dias_objetivo = {
        "Logista": 1.0,
        "Tabaqueira": 3.0,
    }


if "prazo_entrega" not in st.session_state:

    st.session_state.prazo_entrega = {
        "Logista": 1.0,
        "Tabaqueira": 1.0,
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

def normalizar_texto(valor):

    texto = "" if valor is None else str(valor)

    texto = unicodedata.normalize(
        "NFKD",
        texto,
    )

    texto = "".join(

        letra

        for letra in texto

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


def normalizar_referencia(valor):

    texto = str(valor).strip()

    if texto.endswith(".0"):

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


def converter_numeros(serie):

    if pd.api.types.is_numeric_dtype(
        serie
    ):

        return pd.to_numeric(

            serie,

            errors="coerce",

        ).fillna(0)

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

    apenas_virgula = (
        tem_virgula
        & ~tem_ponto
    )

    texto.loc[
        apenas_virgula
    ] = (

        texto.loc[
            apenas_virgula
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

    ).fillna(0)


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

    memoria.seek(0)

    return memoria.getvalue()


# =========================================================
# IDENTIFICAÇÃO DAS COLUNAS
# =========================================================

ALIASES = {

    "referencia": [
        "referencia",
        "ref",
        "codigo",
        "codigo artigo",
        "cod artigo",
        "artigo",
        "codigo produto",
        "cod produto",
    ],

    "produto": [
        "designacao",
        "descricao",
        "produto",
        "nome produto",
        "designacao artigo",
        "descricao artigo",
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

    "data": [
        "data",
        "data documento",
        "data movimento",
        "data venda",
        "data faturacao",
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


def identificar_coluna(nome):

    nome_normalizado = normalizar_texto(
        nome
    )

    if nome_normalizado in MAPA_COLUNAS:

        return MAPA_COLUNAS[
            nome_normalizado
        ]

    for alternativa, nome_final in sorted(

        MAPA_COLUNAS.items(),

        key=lambda item: len(
            item[0]
        ),

        reverse=True,
    ):

        if len(alternativa) >= 5:

            if (

                nome_normalizado.startswith(
                    alternativa
                )

                or nome_normalizado.endswith(
                    alternativa
                )
            ):

                return nome_final

    return None


def pontuar_cabecalho(valores):

    encontrados = set()

    for valor in valores:

        coluna = identificar_coluna(
            valor
        )

        if coluna:

            encontrados.add(
                coluna
            )

    return len(encontrados)


# =========================================================
# LEITURA DOS EXCEL
# =========================================================

def limpar_linhas_tecnicas(dados):

    dados = dados.copy()

    if "produto" in dados.columns:

        produto_normalizado = (

            dados["produto"]

            .astype(str)

            .map(
                normalizar_texto
            )
        )

        dados = dados.loc[

            ~produto_normalizado.isin(
                [
                    "total",
                    "totais",
                    "subtotal",
                    "rappel",
                    "rapel",
                ]
            )

        ].copy()

    if "referencia" in dados.columns:

        referencia_normalizada = (

            dados["referencia"]

            .astype(str)

            .map(
                normalizar_texto
            )
        )

        dados = dados.loc[

            ~referencia_normalizada.isin(
                [
                    "ra",
                    "rappel",
                    "rapel",
                ]
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

                linha_cabecalho = 0

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

            sheet_name=0,

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

        linha_cabecalho = (

            int(
                pontuacoes.idxmax()
            )

            if len(pontuacoes)

            else 0
        )

        dados = pd.read_excel(

            io.BytesIO(
                conteudo
            ),

            sheet_name=0,

            header=linha_cabecalho,

            engine="openpyxl",
        )

    dados = dados.dropna(
        how="all"
    ).copy()

    dados.columns = [

        str(coluna).strip()

        if str(coluna).strip()

        else f"coluna_{indice}"

        for indice, coluna

        in enumerate(
            dados.columns
        )
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

        linha_cabecalho,
    )


def garantir_produto(dados):

    dados = dados.copy()

    if "produto" not in dados.columns:

        if "referencia" in dados.columns:

            dados[
                "produto"
            ] = dados[
                "referencia"
            ].astype(str)

        else:

            dados[
                "produto"
            ] = [

                f"Produto {indice + 1}"

                for indice
                in range(
                    len(dados)
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


# =========================================================
# IDENTIFICAÇÃO DOS FORNECEDORES
# =========================================================

def referencias_por_fornecedor():

    referencias = {
        "Logista": set(),
        "Tabaqueira": set(),
    }

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

                lista = (

                    dados[
                        "referencia"
                    ]

                    .dropna()

                    .map(
                        normalizar_referencia
                    )

                    .tolist()
                )

                referencias[
                    fornecedor
                ].update(
                    lista
                )

    return referencias


def identificar_fornecedor(
    referencia,
):

    referencia = normalizar_referencia(
        referencia
    )

    referencias = referencias_por_fornecedor()

    if referencia in referencias[
        "Logista"
    ]:

        return "Logista"

    if referencia in referencias[
        "Tabaqueira"
    ]:

        return "Tabaqueira"

    return "Não identificado"


# =========================================================
# FATURAS PDF
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

    numero_fatura = "Sem número"

    data_fatura = ""

    resultado = re.search(

        r"FT\d+[A-Z]\d+/(\d+)",

        texto,

        flags=re.IGNORECASE,
    )

    if resultado:

        numero_fatura = resultado.group(
            1
        )

    datas = re.findall(

        r"\b(20\d{2}[-/.]\d{2}[-/.]\d{2})\b",

        texto,
    )

    if datas:

        data_fatura = datas[0]

    return {

        "numero_fatura": numero_fatura,

        "cliente": "Não identificado",

        "vendedor": "Não identificado",

        "data_fatura": data_fatura,
    }


def extrair_artigos_fatura(
    texto
):

    artigos = []

    padrao = re.compile(

        r"^(?P<referencia>\d{2,6})\s+"

        r"(?P<produto>.+?)\s+"

        r"(?P<quantidade>\d+(?:[.,]\d+)?)\s+"

        r"M\d+\s+Reg\b",

        flags=re.IGNORECASE,
    )

    for linha in texto.splitlines():

        linha = re.sub(

            r"\s+",

            " ",

            linha.strip(),
        )

        resultado = padrao.search(
            linha
        )

        if resultado is None:

            continue

        artigos.append(
            {
                "referencia": normalizar_referencia(

                    resultado.group(
                        "referencia"
                    )
                ),

                "produto": resultado.group(

                    "produto"

                ).strip(),

                "quantidade": float(

                    resultado.group(
                        "quantidade"
                    ).replace(
                        ",",
                        ".",
                    )
                ),
            }
        )

    artigos_unicos = []

    encontrados = set()

    for artigo in artigos:

        chave = (

            artigo[
                "referencia"
            ],

            artigo[
                "produto"
            ],

            artigo[
                "quantidade"
            ],
        )

        if chave in encontrados:

            continue

        encontrados.add(
            chave
        )

        artigos_unicos.append(
            artigo
        )

    return artigos_unicos


def ler_fatura_pdf(
    ficheiro,
    dia_saida,
):

    paginas = extrair_texto_pdf(
        ficheiro
    )

    registos = []

    processadas = set()

    for texto in paginas:

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

        artigos = extrair_artigos_fatura(
            texto
        )

        for artigo in artigos:

            registos.append(
                {
                    **cabecalho,

                    "dia_saida": dia_saida,

                    "referencia": artigo[
                        "referencia"
                    ],

                    "produto": artigo[
                        "produto"
                    ],

                    "quantidade": artigo[
                        "quantidade"
                    ],

                    "fornecedor": identificar_fornecedor(

                        artigo[
                            "referencia"
                        ]
                    ),

                    "ficheiro": ficheiro.name,
                }
            )

    if not registos:

        raise ValueError(
            "Não consegui reconhecer artigos nesta fatura."
        )

    return pd.DataFrame(
        registos
    )


def adicionar_fatura(
    nova_fatura
):

    combinado = pd.concat(

        [
            st.session_state.faturas,

            nova_fatura,
        ],

        ignore_index=True,
    )

    combinado = combinado.drop_duplicates(

        subset=[
            "numero_fatura",
            "referencia",
            "quantidade",
            "dia_saida",
        ]
    )

    st.session_state.faturas = (

        combinado.reset_index(
            drop=True
        )
    )


# =========================================================
# AUTONOMIA E ENCOMENDAS
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
    ].fillna(0)

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
    ] = (

        objetivo
        + margem
    )

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
        "estado"
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

    resultado = resultado.sort_values(

        [
            "autonomia_dias",
            "sugestao",
        ],

        ascending=[
            True,
            False,
        ],
    )

    return (

        resultado.reset_index(
            drop=True
        ),

        None,
    )# =========================================================
# MENU LATERAL
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
            "🏠 Dashboard",
            "📥 Importar inventário",
            "🧾 Faturas pendentes",
            "📦 Encomendas",
            "📈 Vendas",
            "📋 Produtos",
            "⚙️ Definições",
        ],
        label_visibility="collapsed",
    )

    st.divider()

    for fornecedor in FORNECEDORES:

        atual = obter_inventario(
            fornecedor,
            "Atual",
        )

        anterior = obter_inventario(
            fornecedor,
            "Anterior",
        )

        estado_atual = (
            "🟢"
            if atual is not None
            else "⚪"
        )

        estado_anterior = (
            "🟢"
            if anterior is not None
            else "⚪"
        )

        st.caption(
            f"{estado_atual} {fornecedor} atual · "
            f"{estado_anterior} anterior"
        )

    numero_faturas = (
        st.session_state.faturas[
            "numero_fatura"
        ].nunique()
        if not st.session_state.faturas.empty
        else 0
    )

    st.caption(
        f"🧾 Faturas pendentes: {numero_faturas}"
    )

    st.caption(
        "Inviora v0.5.0"
    )


# =========================================================
# DASHBOARD
# =========================================================

if pagina == "🏠 Dashboard":

    st.title(
        "Dashboard"
    )

    st.caption(
        "Prioridades de compra e dias de autonomia."
    )

    fornecedor = st.selectbox(
        "Fornecedor",
        FORNECEDORES,
    )

    resultado, erro = calcular_encomenda(
        fornecedor
    )

    if erro:

        st.info(erro)

        st.stop()

    terminam_hoje = int(

        (
            resultado[
                "autonomia_dias"
            ] < 1
        ).sum()
    )

    terminam_amanha = int(

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
    )

    menos_de_tres_dias = int(

        (
            (
                resultado[
                    "autonomia_dias"
                ] >= 2
            )

            &

            (
                resultado[
                    "autonomia_dias"
                ] < 3
            )
        ).sum()
    )

    produtos_reforco = int(

        (
            resultado[
                "sugestao"
            ] > 0
        ).sum()
    )

    coluna1, coluna2, coluna3, coluna4 = st.columns(
        4
    )

    coluna1.metric(
        "Terminam hoje",
        terminam_hoje,
    )

    coluna2.metric(
        "Terminam amanhã",
        terminam_amanha,
    )

    coluna3.metric(
        "Menos de 3 dias",
        menos_de_tres_dias,
    )

    coluna4.metric(
        "Precisam de reforço",
        produtos_reforco,
    )

    st.divider()

    st.subheader(
        "Prioridades de hoje"
    )

    prioridades = resultado[

        resultado[
            "autonomia_dias"
        ] < 3

    ].copy()

    colunas_prioridades = [

        coluna

        for coluna in [

            "referencia",
            "produto",
            "stock_phc",
            "media_dia",
            "autonomia_dias",
            "objetivo_dias",
            "sugestao",
            "estado",

        ]

        if coluna
        in prioridades.columns
    ]

    if prioridades.empty:

        st.success(
            "Nenhum produto abaixo de 3 dias de autonomia."
        )

    else:

        st.dataframe(

            prioridades[
                colunas_prioridades
            ],

            use_container_width=True,

            hide_index=True,

            column_config={

                "stock_phc":
                    st.column_config.NumberColumn(
                        "Stock PHC",
                        format="%.1f",
                    ),

                "media_dia":
                    st.column_config.NumberColumn(
                        "Média por dia",
                        format="%.2f",
                    ),

                "autonomia_dias":
                    st.column_config.NumberColumn(
                        "Autonomia",
                        format="%.1f dias",
                    ),

                "objetivo_dias":
                    st.column_config.NumberColumn(
                        "Objetivo",
                        format="%.1f dias",
                    ),

                "sugestao":
                    st.column_config.NumberColumn(
                        "Encomendar",
                        format="%d",
                    ),
            },
        )

    st.subheader(
        "Produtos que acabam primeiro"
    )

    grafico_dados = (

        resultado[

            resultado[
                "autonomia_dias"
            ] < 999

        ][
            [
                "produto",
                "autonomia_dias",
            ]
        ]

        .nsmallest(
            20,
            "autonomia_dias",
        )

        .sort_values(
            "autonomia_dias"
        )
    )

    if not grafico_dados.empty:

        grafico = px.bar(

            grafico_dados,

            x="autonomia_dias",

            y="produto",

            orientation="h",

            labels={
                "autonomia_dias": "Dias de autonomia",
                "produto": "",
            },
        )

        grafico.update_layout(
            height=520,
            margin=dict(
                l=0,
                r=10,
                t=10,
                b=0,
            ),
        )

        st.plotly_chart(

            grafico,

            use_container_width=True,
        )


# =========================================================
# IMPORTAR INVENTÁRIO
# =========================================================

elif pagina == "📥 Importar inventário":

    st.title(
        "Importar inventário"
    )

    st.caption(
        "Carrega as listagens atuais e anteriores "
        "separadas por fornecedor."
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

                f"{fornecedor} {periodo.lower()} carregado: "
                f"{len(dados)} linhas."
            )

            st.caption(

                f"Cabeçalho identificado na linha "
                f"{cabecalho + 1}."
            )

            st.caption(

                "Colunas reconhecidas: "

                + ", ".join(

                    dados.columns.astype(
                        str
                    )
                )
            )

            st.dataframe(

                dados.head(30),

                use_container_width=True,

                hide_index=True,
            )

        except Exception as erro:

            st.error(

                f"Não consegui ler o ficheiro: "
                f"{erro}"
            )

    st.divider()

    st.subheader(
        "Estado dos ficheiros"
    )

    estado = []

    for nome_fornecedor in FORNECEDORES:

        for nome_periodo in PERIODOS:

            dados = obter_inventario(

                nome_fornecedor,

                nome_periodo,
            )

            nome_ficheiro = (

                st.session_state
                .nomes_ficheiros[
                    nome_fornecedor
                ][
                    nome_periodo
                ]
            )

            estado.append(
                {
                    "Fornecedor": nome_fornecedor,
                    "Período": nome_periodo,
                    "Ficheiro": (
                        nome_ficheiro
                        if nome_ficheiro
                        else "Não carregado"
                    ),
                    "Linhas": (
                        len(dados)
                        if dados is not None
                        else 0
                    ),
                }
            )

    st.dataframe(

        pd.DataFrame(
            estado
        ),

        use_container_width=True,

        hide_index=True,
    )

    if st.button(
        "Limpar inventários",
        type="secondary",
    ):

        st.session_state.inventarios = {

            fornecedor: {
                "Atual": None,
                "Anterior": None,
            }

            for fornecedor
            in FORNECEDORES
        }

        st.session_state.nomes_ficheiros = {

            fornecedor: {
                "Atual": None,
                "Anterior": None,
            }

            for fornecedor
            in FORNECEDORES
        }

        st.rerun()


# =========================================================
# FATURAS PENDENTES
# =========================================================

elif pagina == "🧾 Faturas pendentes":

    st.title(
        "Faturas pendentes"
    )

    st.info(
        "O PHC já retirou estas quantidades do stock. "
        "A Inviora usa as faturas para calcular o stock físico "
        "e organizar o que sai na quarta ou quinta."
    )

    dia_saida = st.radio(
        "Estas faturas saem em:",
        DIAS_SAIDA,
        horizontal=True,
    )

    ficheiros = st.file_uploader(

        "Carregar uma ou várias faturas PDF",

        type=[
            "pdf",
        ],

        accept_multiple_files=True,

        key="upload_faturas",
    )

    if ficheiros:

        if st.button(
            "Ler e adicionar faturas",
            type="primary",
        ):

            linhas_antes = len(
                st.session_state.faturas
            )

            for ficheiro in ficheiros:

                try:

                    nova_fatura = ler_fatura_pdf(

                        ficheiro,

                        dia_saida,
                    )

                    adicionar_fatura(
                        nova_fatura
                    )

                    st.success(
                        f"{ficheiro.name} adicionada."
                    )

                except Exception as erro:

                    st.error(

                        f"{ficheiro.name}: "
                        f"{erro}"
                    )

            linhas_depois = len(
                st.session_state.faturas
            )

            if linhas_depois == linhas_antes:

                st.warning(
                    "Nenhuma linha nova foi adicionada. "
                    "A fatura pode já existir."
                )

    faturas = (
        st.session_state.faturas.copy()
    )

    if faturas.empty:

        st.info(
            "Ainda não existem faturas carregadas."
        )

        st.stop()

    total_faturas = (
        faturas[
            "numero_fatura"
        ].nunique()
    )

    unidades_quarta = (

        faturas.loc[

            faturas[
                "dia_saida"
            ] == "Quarta-feira",

            "quantidade",

        ].sum()
    )

    unidades_quinta = (

        faturas.loc[

            faturas[
                "dia_saida"
            ] == "Quinta-feira",

            "quantidade",

        ].sum()
    )

    nao_identificados = int(

        (
            faturas[
                "fornecedor"
            ] == "Não identificado"
        ).sum()
    )

    coluna1, coluna2, coluna3, coluna4 = st.columns(
        4
    )

    coluna1.metric(
        "Faturas",
        total_faturas,
    )

    coluna2.metric(
        "Unidades quarta",
        formatar_numero(
            unidades_quarta,
            1,
        ),
    )

    coluna3.metric(
        "Unidades quinta",
        formatar_numero(
            unidades_quinta,
            1,
        ),
    )

    coluna4.metric(
        "Não identificados",
        nao_identificados,
    )

    st.subheader(
        "Revisão das linhas"
    )

    editada = st.data_editor(

        faturas,

        use_container_width=True,

        hide_index=True,

        disabled=[
            "numero_fatura",
            "cliente",
            "vendedor",
            "data_fatura",
            "dia_saida",
            "referencia",
            "produto",
            "quantidade",
            "ficheiro",
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

        key="editor_faturas",
    )

    if st.button(
        "Guardar correções"
    ):

        st.session_state.faturas = (

            editada.copy()
        )

        st.success(
            "Correções guardadas."
        )

    aba_quarta, aba_quinta, aba_todas = st.tabs(
        [
            "Quarta-feira",
            "Quinta-feira",
            "Todas",
        ]
    )

    configuracoes = [
        (
            aba_quarta,
            "Quarta-feira",
        ),
        (
            aba_quinta,
            "Quinta-feira",
        ),
        (
            aba_todas,
            None,
        ),
    ]

    for aba, dia in configuracoes:

        with aba:

            tabela = (

                editada

                if dia is None

                else editada[

                    editada[
                        "dia_saida"
                    ] == dia
                ]
            )

            if tabela.empty:

                st.info(
                    "Sem faturas para este dia."
                )

            else:

                resumo = (

                    tabela.groupby(

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

                    .sort_values(

                        "quantidade",

                        ascending=False,
                    )
                )

                st.subheader(
                    "Resumo para preparação"
                )

                st.dataframe(

                    resumo,

                    use_container_width=True,

                    hide_index=True,
                )

                nome_exportacao = (

                    "todas"

                    if dia is None

                    else normalizar_texto(
                        dia
                    ).replace(
                        " ",
                        "_",
                    )
                )

                st.download_button(

                    "⬇️ Exportar preparação",

                    data=converter_para_excel(

                        resumo,

                        "Preparacao",
                    ),

                    file_name=(

                        f"preparacao_"
                        f"{nome_exportacao}_"
                        f"{date.today().isoformat()}"
                        f".xlsx"
                    ),

                    mime=(

                        "application/vnd.openxmlformats-"
                        "officedocument.spreadsheetml.sheet"
                    ),

                    key=(
                        f"download_"
                        f"{nome_exportacao}"
                    ),
                )

    st.divider()

    if st.button(
        "Limpar todas as faturas",
        type="secondary",
    ):

        st.session_state.faturas = pd.DataFrame(

            columns=[
                "numero_fatura",
                "cliente",
                "vendedor",
                "data_fatura",
                "dia_saida",
                "referencia",
                "produto",
                "quantidade",
                "fornecedor",
                "ficheiro",
            ]
        )

        st.rerun()


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

        st.info(erro)

        st.stop()

    if obter_inventario(
        fornecedor,
        "Anterior",
    ) is None:

        st.warning(
            "Ainda não carregaste o período anterior. "
            "A média diária está a usar apenas as saídas atuais."
        )

    apenas_encomendar = st.toggle(
        "Mostrar apenas produtos a encomendar",
        value=True,
    )

    pesquisa = st.text_input(
        "Pesquisar produto ou referência"
    )

    tabela = resultado.copy()

    if apenas_encomendar:

        tabela = tabela[

            tabela[
                "sugestao"
            ] > 0
        ]

    if pesquisa:

        pesquisa_normalizada = normalizar_texto(
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

                pesquisa_normalizada,

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

                    pesquisa_normalizada,

                    na=False,
                )
            )

        tabela = tabela[
            mascara
        ]

    produtos_encomendar = int(

        (
            resultado[
                "sugestao"
            ] > 0
        ).sum()
    )

    quantidade_encomendar = (

        resultado[
            "sugestao"
        ].sum()
    )

    autonomias_validas = resultado.loc[

        resultado[
            "autonomia_dias"
        ] < 999,

        "autonomia_dias",
    ]

    autonomia_media = (

        autonomias_validas.mean()

        if not autonomias_validas.empty

        else 0
    )

    coluna1, coluna2, coluna3 = st.columns(
        3
    )

    coluna1.metric(
        "Produtos a encomendar",
        produtos_encomendar,
    )

    coluna2.metric(
        "Quantidade sugerida",
        formatar_numero(
            quantidade_encomendar
        ),
    )

    coluna3.metric(
        "Autonomia média",
        f"{formatar_numero(autonomia_media, 1)} dias",
    )

    colunas_encomenda = [

        coluna

        for coluna in [

            "referencia",
            "produto",
            "stock_phc",
            "media_dia",
            "autonomia_dias",
            "objetivo_dias",
            "stock_alvo",
            "sugestao",
            "estado",

        ]

        if coluna
        in tabela.columns
    ]

    st.dataframe(

        tabela[
            colunas_encomenda
        ],

        use_container_width=True,

        hide_index=True,

        column_config={

            "stock_phc":
                st.column_config.NumberColumn(
                    "Stock PHC",
                    format="%.1f",
                ),

            "media_dia":
                st.column_config.NumberColumn(
                    "Média diária",
                    format="%.2f",
                ),

            "autonomia_dias":
                st.column_config.NumberColumn(
                    "Autonomia",
                    format="%.1f dias",
                ),

            "objetivo_dias":
                st.column_config.NumberColumn(
                    "Objetivo",
                    format="%.1f dias",
                ),

            "stock_alvo":
                st.column_config.NumberColumn(
                    "Stock alvo",
                    format="%.1f",
                ),

            "sugestao":
                st.column_config.NumberColumn(
                    "Encomendar",
                    format="%d",
                ),
        },
    )

    st.download_button(

        f"⬇️ Exportar pedido {fornecedor}",

        data=converter_para_excel(

            tabela[
                colunas_encomenda
            ],

            f"Pedido {fornecedor}",
        ),

        file_name=(

            f"encomenda_"
            f"{fornecedor}_"
            f"{date.today().isoformat()}"
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

        anterior = juntar_inventarios(
            "Anterior"
        )

    else:

        atual = obter_inventario(
            fornecedor,
            "Atual",
        )

        anterior = obter_inventario(
            fornecedor,
            "Anterior",
        )

    if atual is None:

        st.info(
            "Não existem dados atuais carregados."
        )

        st.stop()

    atual = garantir_produto(
        atual
    )

    total_atual = (

        atual[
            "saidas"
        ].sum()

        if "saidas"
        in atual.columns

        else 0
    )

    total_anterior = (

        anterior[
            "saidas"
        ].sum()

        if (

            anterior is not None

            and "saidas"
            in anterior.columns
        )

        else None
    )

    variacao = (

        (

            (
                total_atual
                - total_anterior
            )

            / total_anterior
        )

        * 100

        if total_anterior not in [
            None,
            0,
        ]

        else None
    )

    coluna1, coluna2, coluna3 = st.columns(
        3
    )

    coluna1.metric(
        "Saídas atuais",
        formatar_numero(
            total_atual,
            1,
        ),
    )

    coluna2.metric(
        "Saídas anteriores",
        (
            formatar_numero(
                total_anterior,
                1,
            )
            if total_anterior is not None
            else "—"
        ),
    )

    coluna3.metric(
        "Variação",
        (
            f"{variacao:.1f}%"
            if variacao is not None
            else "—"
        ),
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

        st.subheader(
            "Produtos com mais saídas"
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

        if atual is not None:

            atual = garantir_produto(
                atual
            )

            atual[
                "fornecedor"
            ] = fornecedor

    if atual is None:

        st.info(
            "Não existem listagens atuais carregadas."
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

        pesquisa_normalizada = normalizar_texto(
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

                pesquisa_normalizada,

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

                    pesquisa_normalizada,

                    na=False,
                )
            )

        tabela = tabela[
            mascara
        ]

    st.caption(
        f"{len(tabela)} produtos encontrados"
    )

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

    st.caption(
        "Ajusta quantos dias de stock queres manter."
    )

    st.session_state.dias_listagem = st.number_input(

        "Quantos dias representa cada listagem?",

        min_value=1.0,

        max_value=31.0,

        value=float(
            st.session_state.dias_listagem
        ),

        step=1.0,

        help=(
            "Se a listagem contém uma semana, usa 7. "
            "A aplicação divide as saídas por este número "
            "para calcular a média diária."
        ),
    )

    st.divider()

    for fornecedor in FORNECEDORES:

        st.subheader(
            fornecedor
        )

        st.session_state.prazo_entrega[
            fornecedor
        ] = st.number_input(

            f"Prazo de entrega — {fornecedor} (dias)",

            min_value=0.0,

            max_value=10.0,

            value=float(

                st.session_state.prazo_entrega[
                    fornecedor
                ]
            ),

            step=0.5,

            key=(
                f"prazo_"
                f"{fornecedor}"
            ),
        )

        st.session_state.dias_objetivo[
            fornecedor
        ] = st.number_input(

            f"Objetivo de autonomia — {fornecedor} (dias)",

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

            help=(
                "Logista pode ficar em 1 dia. "
                "Tabaqueira pode ficar em 3 dias."
            ),
        )

        st.session_state.margem_dias[
            fornecedor
        ] = st.number_input(

            f"Margem adicional — {fornecedor} (dias)",

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

            help=(
                "Proteção extra contra vendas inesperadas "
                "ou atrasos. Exemplo: 0,5 equivale a meio dia."
            ),
        )

        st.session_state.multiplo[
            fornecedor
        ] = st.number_input(

            f"Múltiplo do pedido — {fornecedor}",

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

        objetivo_total = (

            st.session_state.dias_objetivo[
                fornecedor
            ]

            + st.session_state.margem_dias[
                fornecedor
            ]
        )

        st.info(

            f"A Inviora tentará deixar aproximadamente "
            f"**{formatar_numero(objetivo_total, 2)} dias** "
            f"de stock para {fornecedor}."
        )

        st.divider()

    st.subheader(
        "Como é calculado"
    )

    st.code(

        "Média diária = saídas do período ÷ dias da listagem\n"

        "Autonomia = stock PHC ÷ média diária\n"

        "Objetivo total = dias de autonomia + margem adicional\n"

        "Stock alvo = média diária × objetivo total\n"

        "Encomendar = stock alvo - stock PHC",

        language="text",
    )

    st.warning(
        "O prazo de entrega já fica guardado, "
        "mas nesta versão ainda não entra diretamente na fórmula. "
        "Primeiro vamos validar se a média diária e a autonomia "
        "batem certo com a operação real."
    )
