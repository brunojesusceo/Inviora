import io
import math
import re
import unicodedata
from datetime import date

import pandas as pd
import plotly.express as px
import streamlit as st
from pypdf import PdfReader


st.set_page_config(
    page_title="Inviora",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded",
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
# MEMÓRIA DA APLICAÇÃO
# =========================================================

if "inventarios" not in st.session_state:

    st.session_state.inventarios = {

        fornecedor: {

            periodo: None

            for periodo in PERIODOS
        }

        for fornecedor in FORNECEDORES
    }


if "nomes_ficheiros" not in st.session_state:

    st.session_state.nomes_ficheiros = {

        fornecedor: {

            periodo: None

            for periodo in PERIODOS
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


if "cobertura" not in st.session_state:

    st.session_state.cobertura = 1.0


if "seguranca" not in st.session_state:

    st.session_state.seguranca = 15


if "multiplo" not in st.session_state:

    st.session_state.multiplo = 1


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
    ],

    "produto": [
        "designacao",
        "descricao",
        "produto",
        "nome produto",
        "designacao artigo",
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

        nomes = (

            dados["produto"]

            .astype(str)

            .map(
                normalizar_texto
            )
        )

        dados = dados.loc[

            ~nomes.isin(
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

        referencias = (

            dados["referencia"]

            .astype(str)

            .map(
                normalizar_texto
            )
        )

        dados = dados.loc[

            ~referencias.isin(
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

        dados = pd.read_csv(

            io.BytesIO(
                conteudo
            ),

            sep=None,

            engine="python",
        )

        linha_cabecalho = 0

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

            lambda linha: len(

                {
                    identificar_coluna(
                        valor
                    )

                    for valor
                    in linha.tolist()

                    if identificar_coluna(
                        valor
                    )
                }
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
# FORNECEDORES
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
# ENCOMENDAS
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

            "A listagem precisa das colunas Saídas e Stock Final.",
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
            "procura_base"
        ] = resultado[
            "saidas_atual"
        ]

    else:

        resultado[
            "procura_base"
        ] = (

            resultado[
                "saidas_atual"
            ] * 0.65

            + resultado[
                "saidas_anterior"
            ] * 0.35
        )

    resultado[
        "stock_alvo"
    ] = (

        resultado[
            "procura_base"
        ]

        * float(
            st.session_state.cobertura
        )

        * (

            1

            + float(
                st.session_state.seguranca
            ) / 100
        )
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
            st.session_state.multiplo
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

    return (

        resultado.sort_values(

            "sugestao",

            ascending=False,
        ),

        None,
    )


# =========================================================
# MENU
# =========================================================

with st.sidebar:

    st.markdown(
        "## INVIORA"
    )

    st.caption(
        "Transformar dados em decisões."
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

        atual = (

            "🟢"

            if obter_inventario(
                fornecedor,
                "Atual",
            ) is not None

            else "⚪"
        )

        anterior = (

            "🟢"

            if obter_inventario(
                fornecedor,
                "Anterior",
            ) is not None

            else "⚪"
        )

        st.caption(

            f"{atual} {fornecedor} atual · "

            f"{anterior} anterior"
        )

    numero_faturas = (

        st.session_state.faturas[
            "numero_fatura"
        ].nunique()

        if not st.session_state.faturas.empty

        else 0
    )

    st.caption(
        f"🧾 Faturas: {numero_faturas}"
    )

    st.caption(
        "Inviora v0.4.1"
    )


# =========================================================
# DASHBOARD
# =========================================================

if pagina == "🏠 Dashboard":

    st.title(
        "Dashboard"
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
            "Carrega pelo menos uma listagem atual."
        )

        st.stop()

    atual = garantir_produto(
        atual
    )

    if fornecedor != "Todos":

        atual[
            "fornecedor"
        ] = fornecedor

    faturas = (
        st.session_state.faturas.copy()
    )

    if (

        fornecedor != "Todos"

        and not faturas.empty
    ):

        faturas = faturas[

            faturas[
                "fornecedor"
            ] == fornecedor
        ]

    stock_phc = (

        atual[
            "stock_final"
        ].sum()

        if "stock_final"
        in atual.columns

        else 0
    )

    saidas = (

        atual[
            "saidas"
        ].sum()

        if "saidas"
        in atual.columns

        else 0
    )

    faturado = (

        faturas[
            "quantidade"
        ].sum()

        if not faturas.empty

        else 0
    )

    criticos = (

        int(

            (
                atual[
                    "stock_final"
                ] <= 0
            ).sum()
        )

        if "stock_final"
        in atual.columns

        else 0
    )

    coluna1, coluna2, coluna3, coluna4, coluna5 = st.columns(
        5
    )

    coluna1.metric(
        "Produtos",
        len(atual),
    )

    coluna2.metric(
        "Saídas",
        formatar_numero(
            saidas,
            1,
        ),
    )

    coluna3.metric(
        "Stock PHC",
        formatar_numero(
            stock_phc,
            1,
        ),
    )

    coluna4.metric(
        "Faturado no armazém",
        formatar_numero(
            faturado,
            1,
        ),
    )

    coluna5.metric(
        "Stock físico",
        formatar_numero(
            stock_phc + faturado,
            1,
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
                12,
                "saidas",
            )

            .sort_values(
                "saidas"
            )
        )

        grafico = px.bar(

            ranking,

            x="saidas",

            y="produto",

            orientation="h",
        )

        st.plotly_chart(

            grafico,

            use_container_width=True,
        )

    if "stock_final" in atual.columns:

        st.subheader(
            f"Produtos críticos: {criticos}"
        )

        st.dataframe(

            atual[

                atual[
                    "stock_final"
                ] <= 0

            ].head(20),

            use_container_width=True,

            hide_index=True,
        )


# =========================================================
# IMPORTAR INVENTÁRIO
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


# =========================================================
# FATURAS
# =========================================================

elif pagina == "🧾 Faturas pendentes":

    st.title(
        "Faturas pendentes"
    )

    st.info(

        "O PHC já retirou estas quantidades. "

        "A Inviora utiliza-as para calcular o stock físico "

        "e preparar as saídas."
    )

    dia_saida = st.radio(

        "A fatura sai em:",

        DIAS_SAIDA,

        horizontal=True,
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

            "Ler e adicionar faturas",

            type="primary",
        )
    ):

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

    faturas = (

        st.session_state.faturas.copy()
    )

    if faturas.empty:

        st.info(
            "Ainda não existem faturas carregadas."
        )

        st.stop()

    editada = st.data_editor(

        faturas,

        use_container_width=True,

        hide_index=True,

        column_config={

            "fornecedor":

                st.column_config.SelectboxColumn(

                    "Fornecedor",

                    options=[
                        "Logista",
                        "Tabaqueira",
                        "Não identificado",
                    ],
                )
        },
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

    resumo = (

        editada.groupby(

            [
                "dia_saida",
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

    st.subheader(
        "Resumo para preparação"
    )

    st.dataframe(

        resumo,

        use_container_width=True,

        hide_index=True,
    )

    st.download_button(

        "⬇️ Exportar preparação",

        data=converter_para_excel(

            resumo,

            "Preparacao",
        ),

        file_name=(

            f"preparacao_"

            f"{date.today().isoformat()}"

            f".xlsx"
        ),
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

        st.info(erro)

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

    coluna3.metric(

        "Stock PHC ≤ 0",

        int(

            (
                resultado[
                    "stock_phc"
                ] <= 0
            ).sum()
        ),
    )

    st.dataframe(

        tabela,

        use_container_width=True,

        hide_index=True,
    )

    st.download_button(

        f"⬇️ Exportar pedido {fornecedor}",

        data=converter_para_excel(

            tabela,

            f"Pedido {fornecedor}",
        ),

        file_name=(

            f"encomenda_"

            f"{fornecedor}_"

            f"{date.today().isoformat()}"

            f".xlsx"
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

    st.session_state.cobertura = st.number_input(

        "Semanas de cobertura",

        min_value=0.1,

        max_value=12.0,

        value=float(
            st.session_state.cobertura
        ),

        step=0.1,
    )

    st.session_state.seguranca = st.slider(

        "Margem de segurança (%)",

        min_value=0,

        max_value=100,

        value=int(
            st.session_state.seguranca
        ),

        step=5,
    )

    st.session_state.multiplo = st.number_input(

        "Arredondar pedidos para múltiplos de",

        min_value=1,

        max_value=1000,

        value=int(
            st.session_state.multiplo
        ),

        step=1,
    )

    st.warning(

        "A fórmula de encomenda ainda é experimental. "

        "Valida sempre os resultados antes de comprar."
    )
