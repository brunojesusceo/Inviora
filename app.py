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
# INVIORA
# Smart Inventory Intelligence
# Versão 0.3.0
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

        .inviora-brand {
            font-size: 2rem;
            font-weight: 800;
            letter-spacing: 0.08em;
        }

        .inviora-tagline {
            opacity: 0.72;
            margin-top: -0.4rem;
            margin-bottom: 1.4rem;
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
# MEMÓRIA
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


if "cobertura" not in st.session_state:
    st.session_state.cobertura = 1.0


if "seguranca" not in st.session_state:
    st.session_state.seguranca = 15


if "multiplo" not in st.session_state:
    st.session_state.multiplo = 1


# =========================================================
# FUNÇÕES DE TEXTO
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

        if not unicodedata.combining(letra)
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


def formatar_numero(valor, casas=0):

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

    "stock_inicial": [
        "inicial",
        "stock inicial",
        "existencia inicial",
        "saldo inicial",
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
    ],

    "valor_entradas": [
        "valor entradas",
        "valor de entradas",
    ],

    "valor_saidas": [
        "valor saidas",
        "valor vendas",
        "total vendas",
        "valor de saidas",
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
            normalizar_texto(alternativa)
        ] = nome_final


def identificar_coluna(nome):

    nome_normalizado = normalizar_texto(nome)

    if nome_normalizado in MAPA_COLUNAS:

        return MAPA_COLUNAS[
            nome_normalizado
        ]

    for alternativa, nome_final in sorted(

        MAPA_COLUNAS.items(),

        key=lambda item: len(item[0]),

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
            encontrados.add(coluna)

    return len(encontrados)


# =========================================================
# CONVERSÃO DE NÚMEROS
# =========================================================

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


# =========================================================
# LIMPEZA
# =========================================================

def limpar_linhas_tecnicas(dados):

    if dados is None:
        return dados

    dados = dados.copy()

    if "produto" in dados.columns:

        produto_normalizado = (

            dados["produto"]

            .astype(str)

            .map(
                normalizar_texto
            )
        )

        ignorar = produto_normalizado.isin(
            [
                "total",
                "totais",
                "subtotal",
                "rappel",
                "rapel",
            ]
        )

        dados = dados.loc[
            ~ignorar
        ].copy()

    if "referencia" in dados.columns:

        referencia_normalizada = (

            dados["referencia"]

            .astype(str)

            .map(
                normalizar_texto
            )
        )

        ignorar_referencia = (

            referencia_normalizada.isin(
                [
                    "ra",
                    "rappel",
                    "rapel",
                ]
            )
        )

        dados = dados.loc[
            ~ignorar_referencia
        ].copy()

    return dados


# =========================================================
# LEITURA DOS EXCEL
# =========================================================

def ler_ficheiro_tabular(ficheiro):

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

    utilizados = set()

    for coluna in dados.columns:

        nome_final = identificar_coluna(
            coluna
        )

        if (

            nome_final

            and nome_final
            not in utilizados
        ):

            renomear[
                coluna
            ] = nome_final

            utilizados.add(
                nome_final
            )

    dados = dados.rename(
        columns=renomear
    )

    for coluna in [

        "stock_inicial",
        "entradas",
        "saidas",
        "stock_final",
        "valor_entradas",
        "valor_saidas",

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

    if "data" in dados.columns:

        dados[
            "data"
        ] = pd.to_datetime(

            dados[
                "data"
            ],

            errors="coerce",

            dayfirst=True,
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

    if dados is None:
        return None

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


# =========================================================
# ACESSO AOS INVENTÁRIOS
# =========================================================

def obter_inventario(
    fornecedor,
    periodo="Atual",
):

    return st.session_state.inventarios[
        fornecedor
    ][
        periodo
    ]


def inventarios_carregados(
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
                and "referencia" in dados.columns
            ):

                lista_referencias = (
                    dados["referencia"]
                    .dropna()
                    .map(normalizar_referencia)
                    .tolist()
                )

                referencias[
                    fornecedor
                ].update(
                    lista_referencias
                )

    return referencias


def identificar_fornecedor(
    referencia,
):

    referencia = normalizar_referencia(
        referencia
    )

    referencias = referencias_por_fornecedor()

    # Os produtos da Logista são exclusivos.
    if referencia in referencias["Logista"]:

        return "Logista"

    # Os restantes produtos reconhecidos
    # pertencem à Tabaqueira.
    if referencia in referencias["Tabaqueira"]:

        return "Tabaqueira"

    return "Não identificado"


# =========================================================
# LEITURA DAS FATURAS PDF
# =========================================================

def extrair_texto_pdf(ficheiro):

    leitor = PdfReader(
        io.BytesIO(
            ficheiro.getvalue()
        )
    )

    textos = []

    for pagina in leitor.pages:

        texto = ""

        try:

            texto = pagina.extract_text(
                extraction_mode="layout"
            ) or ""

        except Exception:

            texto = pagina.extract_text() or ""

        textos.append(texto)

    return textos


def extrair_cabecalho_fatura(texto):

    numero_fatura = None

    cliente = None

    vendedor = None

    data_fatura = None

    correspondencia = re.search(

        r"FT\d+[A-Z]\d+/(\d+)",

        texto,

        flags=re.IGNORECASE,
    )

    if correspondencia:

        numero_fatura = (
            correspondencia.group(1)
        )

    datas = re.findall(

        r"\b(20\d{2}[-/.]\d{2}[-/.]\d{2})\b",

        texto,
    )

    if datas:
        data_fatura = datas[0]

    linhas = [

        linha.strip()

        for linha in texto.splitlines()

        if linha.strip()
    ]

    for indice, linha in enumerate(
        linhas
    ):

        if (

            "data cliente vend"

            in normalizar_texto(
                linha
            )
        ):

            numeros = []

            for proxima in linhas[
                indice + 1:
                indice + 7
            ]:

                numeros.extend(

                    re.findall(
                        r"\b\d+\b",
                        proxima,
                    )
                )

            if len(numeros) >= 2:

                cliente = numeros[0]

                vendedor = numeros[1]

                break

    return {

        "numero_fatura": (
            numero_fatura
            or "Sem número"
        ),

        "cliente": (
            cliente
            or "Não identificado"
        ),

        "vendedor": (
            vendedor
            or "Não identificado"
        ),

        "data_fatura": (
            data_fatura
            or ""
        ),
    }


def extrair_linhas_fatura(texto):

    artigos = []

    # Normaliza espaços, mas preserva as linhas.
    linhas = [

        re.sub(
            r"\s+",
            " ",
            linha.strip(),
        )

        for linha in texto.splitlines()

        if linha.strip()
    ]

    padrao_principal = re.compile(

        r"^(?P<referencia>\d+)\s+"

        r"(?P<produto>.+?)\s+"

        r"(?P<quantidade>\d+(?:[.,]\d+)?)\s+"

        r"M\d+\s+"

        r"Reg\b",

        flags=re.IGNORECASE,
    )

    for linha in linhas:

        resultado = padrao_principal.search(
            linha
        )

        if resultado is None:

            continue

        referencia = normalizar_referencia(

            resultado.group(
                "referencia"
            )
        )

        produto = resultado.group(
            "produto"
        ).strip()

        quantidade = float(

            resultado.group(
                "quantidade"
            ).replace(
                ",",
                ".",
            )
        )

        artigos.append(
            {
                "referencia": referencia,
                "produto": produto,
                "quantidade": quantidade,
            }
        )

    # Segundo método caso o PDF tenha partido
    # a tabela de forma diferente.
    if not artigos:

        texto_normalizado = re.sub(
            r"[ \t]+",
            " ",
            texto,
        )

        padrao_global = re.compile(

            r"(?:^|\n)\s*"

            r"(?P<referencia>\d{2,6})\s+"

            r"(?P<produto>[A-ZÀ-Ú0-9´'()+./ -]+?)\s+"

            r"(?P<quantidade>\d+(?:[.,]\d+)?)\s+"

            r"M\d+\s+Reg",

            flags=(
                re.IGNORECASE
                | re.MULTILINE
            ),
        )

        for resultado in padrao_global.finditer(
            texto_normalizado
        ):

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

    # Evita que uma linha seja reconhecida duas vezes.
    artigos_unicos = []

    chaves_utilizadas = set()

    for artigo in artigos:

        chave = (
            artigo["referencia"],
            artigo["produto"],
            artigo["quantidade"],
        )

        if chave in chaves_utilizadas:

            continue

        chaves_utilizadas.add(
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

    if not paginas:

        raise ValueError(
            "O PDF não contém texto legível."
        )

    faturas_processadas = set()

    registos = []

    mapa_fornecedores = (
        mapa_referencia_fornecedor()
    )

    for texto in paginas:

        cabecalho = (
            extrair_cabecalho_fatura(
                texto
            )
        )

        chave_fatura = cabecalho[
            "numero_fatura"
        ]

        # Evita contar ORIGINAL e DUPLICADO.
        if chave_fatura in faturas_processadas:
            continue

        faturas_processadas.add(
            chave_fatura
        )

        artigos = extrair_linhas_fatura(
            texto
        )

        for artigo in artigos:

            referencia = artigo[
                "referencia"
            ]

           
            )

            registos.append(
                {
                    **cabecalho,

                    "dia_saida": dia_saida,

                    "referencia": referencia,

                    "produto": artigo[
                        "produto"
                    ],

                    "quantidade": artigo[
                        "quantidade"
                    ],

                    "fornecedor": fornecedor,

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
    nova_fatura,
):

    existentes = (
        st.session_state.faturas.copy()
    )

    if existentes.empty:

        st.session_state.faturas = (
            nova_fatura.copy()
        )

        return len(nova_fatura), 0

    combinado = pd.concat(

        [
            existentes,
            nova_fatura,
        ],

        ignore_index=True,
    )

    antes = len(combinado)

    combinado = combinado.drop_duplicates(

        subset=[
            "numero_fatura",
            "referencia",
            "quantidade",
            "dia_saida",
        ],

        keep="first",
    )

    duplicados = (

        antes
        - len(combinado)
    )

    adicionados = (

        len(combinado)
        - len(existentes)
    )

    st.session_state.faturas = (

        combinado.reset_index(
            drop=True
        )
    )

    return adicionados, duplicados


# =========================================================
# EXPORTAR EXCEL
# =========================================================

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
# CÁLCULO DE ENCOMENDAS
# =========================================================

def calcular_encomendas(
    fornecedor,
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
    ] = pd.to_numeric(

        resultado[
            "saidas_anterior"
        ],

        errors="coerce",

    ).fillna(0)

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

    resultado[
        "variacao_pct"
    ] = resultado.apply(

        lambda linha: (

            (

                (
                    linha[
                        "saidas_atual"
                    ]

                    - linha[
                        "saidas_anterior"
                    ]
                )

                / linha[
                    "saidas_anterior"
                ]
            ) * 100

            if linha[
                "saidas_anterior"
            ] != 0

            else (

                100

                if linha[
                    "saidas_atual"
                ] > 0

                else 0
            )
        ),

        axis=1,
    )

    resultado[
        "motivo"
    ] = resultado.apply(

        lambda linha: (

            "Vendas a subir e stock insuficiente"

            if (

                linha[
                    "sugestao"
                ] > 0

                and linha[
                    "variacao_pct"
                ] > 10
            )

            else "Stock insuficiente"

            if linha[
                "sugestao"
            ] > 0

            else "Stock suficiente"
        ),

        axis=1,
    )

    resultado[
        "fornecedor"
    ] = fornecedor

    resultado = resultado.sort_values(

        [
            "sugestao",
            "saidas_atual",
        ],

        ascending=[
            False,
            False,
        ],
    )

    return (

        resultado.reset_index(
            drop=True
        ),

        None,
    )


# =========================================================
# MENU
# =========================================================

with st.sidebar:

    st.markdown(

        '<div class="inviora-brand">'
        'INVIORA'
        '</div>',

        unsafe_allow_html=True,
    )

    st.markdown(

        '<div class="inviora-tagline">'
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
        "Inviora v0.3.0"
    )


# =========================================================
# DASHBOARD
# =========================================================

if pagina == "🏠 Dashboard":

    st.title("Dashboard")

    fornecedor_filtro = st.selectbox(

        "Fornecedor",

        [
            "Todos",
            *FORNECEDORES,
        ],
    )

    if fornecedor_filtro == "Todos":

        atual = inventarios_carregados(
            "Atual"
        )

    else:

        atual = obter_inventario(

            fornecedor_filtro,

            "Atual",
        )

        if atual is not None:

            atual = garantir_produto(
                atual
            )

            atual[
                "fornecedor"
            ] = fornecedor_filtro

    if atual is None:

        st.info(
            "Carrega pelo menos uma listagem atual."
        )

        st.stop()

    faturas = (
        st.session_state.faturas.copy()
    )

    if (

        fornecedor_filtro != "Todos"

        and not faturas.empty
    ):

        faturas = faturas[

            faturas[
                "fornecedor"
            ] == fornecedor_filtro
        ]

    total_produtos = len(
        atual
    )

    total_saidas = (

        atual[
            "saidas"
        ].sum()

        if "saidas"
        in atual.columns

        else 0
    )

    stock_phc = (

        atual[
            "stock_final"
        ].sum()

        if "stock_final"
        in atual.columns

        else 0
    )

    faturado_pendente = (

        faturas[
            "quantidade"
        ].sum()

        if not faturas.empty

        else 0
    )

    stock_fisico = (

        stock_phc
        + faturado_pendente
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
        formatar_numero(
            total_produtos
        ),
    )

    coluna2.metric(
        "Saídas",
        formatar_numero(
            total_saidas,
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
            faturado_pendente,
            1,
        ),
    )

    coluna5.metric(
        "Stock físico estimado",
        formatar_numero(
            stock_fisico,
            1,
        ),
    )

    coluna1, coluna2, coluna3 = st.columns(
        3
    )

    quarta = (

        faturas.loc[

            faturas[
                "dia_saida"
            ] == "Quarta-feira",

            "quantidade",

        ].sum()

        if not faturas.empty

        else 0
    )

    quinta = (

        faturas.loc[

            faturas[
                "dia_saida"
            ] == "Quinta-feira",

            "quantidade",

        ].sum()

        if not faturas.empty

        else 0
    )

    coluna1.metric(
        "Sai quarta",
        formatar_numero(
            quarta,
            1,
        ),
    )

    coluna2.metric(
        "Sai quinta",
        formatar_numero(
            quinta,
            1,
        ),
    )

    coluna3.metric(
        "Stock ≤ 0",
        formatar_numero(
            criticos
        ),
    )

    esquerda, direita = st.columns(
        [
            1.2,
            1,
        ]
    )

    with esquerda:

        st.subheader(
            "Produtos com mais saídas"
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

    with direita:

        st.subheader(
            "Atenção imediata"
        )

        if "stock_final" in atual.columns:

            colunas = [

                coluna

                for coluna in [

                    "fornecedor",
                    "referencia",
                    "produto",
                    "stock_final",
                    "saidas",

                ]

                if coluna
                in atual.columns
            ]

            alerta = atual.loc[

                atual[
                    "stock_final"
                ] <= 0,

                colunas,

            ].sort_values(
                "stock_final"
            )

            st.dataframe(

                alerta.head(20),

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
            ][
                periodo
            ] = dados

            st.session_state.nomes_ficheiros[
                fornecedor
            ][
                periodo
            ] = ficheiro.name

            st.success(

                f"{fornecedor} {periodo.lower()} carregado. "
                f"{len(dados)} linhas."
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

                dados.head(25),

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
                    "Fornecedor": nome_fornecedor,
                    "Período": nome_periodo,
                    "Ficheiro": (
                        st.session_state.nomes_ficheiros[
                            nome_fornecedor
                        ][
                            nome_periodo
                        ]
                        or "Não carregado"
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


# =========================================================
# FATURAS PENDENTES
# =========================================================

elif pagina == "🧾 Faturas pendentes":

    st.title(
        "Faturas pendentes"
    )

    st.info(
        "O PHC já retirou estas quantidades do stock. "
        "A Inviora apenas soma as faturas para calcular "
        "o stock físico e preparar as saídas."
    )

    dia_saida = st.radio(

        "A fatura sai em:",

        DIAS_SAIDA,

        horizontal=True,
    )

    faturas_pdf = st.file_uploader(

        "Carregar faturas PDF",

        type=[
            "pdf"
        ],

        accept_multiple_files=True,
    )

    if (

        faturas_pdf

        and st.button(
            "Ler e adicionar faturas",
            type="primary",
        )
    ):

        total_adicionados = 0

        total_duplicados = 0

        for fatura_pdf in faturas_pdf:

            try:

                nova_fatura = ler_fatura_pdf(

                    fatura_pdf,

                    dia_saida,
                )

                adicionados, duplicados = (
                    adicionar_fatura(
                        nova_fatura
                    )
                )

                total_adicionados += adicionados

                total_duplicados += duplicados

            except Exception as erro:

                st.error(

                    f"{fatura_pdf.name}: "
                    f"{erro}"
                )

        if total_adicionados:

            st.success(

                f"{total_adicionados} linhas adicionadas."
            )

        if total_duplicados:

            st.warning(

                f"{total_duplicados} duplicados ignorados."
            )

    faturas = (
        st.session_state.faturas
    )

    if faturas.empty:

        st.info(
            "Ainda não existem faturas carregadas."
        )

        st.stop()

    coluna1, coluna2, coluna3 = st.columns(
        3
    )

    coluna1.metric(

        "Faturas",

        faturas[
            "numero_fatura"
        ].nunique(),
    )

    coluna2.metric(

        "Unidades quarta",

        formatar_numero(

            faturas.loc[

                faturas[
                    "dia_saida"
                ] == "Quarta-feira",

                "quantidade",

            ].sum(),

            1,
        ),
    )

    coluna3.metric(

        "Unidades quinta",

        formatar_numero(

            faturas.loc[

                faturas[
                    "dia_saida"
                ] == "Quinta-feira",

                "quantidade",

            ].sum(),

            1,
        ),
    )

    aba_quarta, aba_quinta, aba_todas = st.tabs(

        [
            "Quarta-feira",
            "Quinta-feira",
            "Todas",
        ]
    )

    configuracao_abas = [

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

    for aba, dia in configuracao_abas:

        with aba:

            tabela = (

                faturas

                if dia is None

                else faturas[

                    faturas[
                        "dia_saida"
                    ] == dia
                ]
            )

            st.dataframe(

                tabela,

                use_container_width=True,

                hide_index=True,
            )

            if not tabela.empty:

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

                nome_dia = (

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

                        f"faturas_"
                        f"{nome_dia}_"
                        f"{date.today().isoformat()}"
                        f".xlsx"
                    ),

                    mime=(

                        "application/vnd.openxmlformats-"
                        "officedocument.spreadsheetml.sheet"
                    ),

                    key=(
                        f"download_"
                        f"{nome_dia}"
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

    resultado, erro = calcular_encomendas(
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
            "A sugestão está a usar apenas o período atual."
        )

    apenas_encomendar = st.toggle(

        "Mostrar apenas produtos a encomendar",

        value=True,
    )

    tabela = resultado.copy()

    if apenas_encomendar:

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

    colunas = [

        coluna

        for coluna in [

            "referencia",
            "produto",
            "saidas_anterior",
            "saidas_atual",
            "variacao_pct",
            "stock_phc",
            "procura_base",
            "stock_alvo",
            "sugestao",
            "motivo",

        ]

        if coluna
        in tabela.columns
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

    st.title("Vendas")

    fornecedor = st.selectbox(

        "Fornecedor",

        [
            "Todos",
            *FORNECEDORES,
        ],
    )

    if fornecedor == "Todos":

        atual = inventarios_carregados(
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

    st.title("Produtos")

    fornecedor = st.selectbox(

        "Fornecedor",

        [
            "Todos",
            *FORNECEDORES,
        ],
    )

    if fornecedor == "Todos":

        atual = inventarios_carregados(
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
            "Não existem listagens carregadas."
        )

        st.stop()

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

    st.title("Definições")

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

    st.subheader(
        "Regra de encomenda"
    )

    st.code(

        "Procura estimada = "
        "65% × saídas atuais + "
        "35% × saídas anteriores\n"

        "Sem período anterior: "
        "procura estimada = saídas atuais\n"

        "Stock alvo = "
        "procura estimada × cobertura × "
        "(1 + margem de segurança)\n"

        "Sugestão = "
        "máximo entre 0 e "
        "(stock alvo - stock PHC)",

        language="text",
    )

    st.warning(
        "Esta regra ainda é experimental. "
        "Não faças encomendas reais sem validar os resultados."
    )
