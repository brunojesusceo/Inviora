import io
import math
import re
import unicodedata
from datetime import date

import pandas as pd
import plotly.express as px
import streamlit as st


# =========================================================
# INVIORA — Smart Inventory Intelligence
# Versão 0.2.0
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
            padding-top: 1.5rem;
            padding-bottom: 2rem;
        }

        [data-testid="stSidebar"] {
            border-right: 1px solid rgba(128,128,128,0.20);
        }

        .inviora-brand {
            font-size: 2rem;
            font-weight: 800;
            letter-spacing: 0.08em;
        }

        .inviora-tagline {
            opacity: 0.70;
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


# =========================================================
# MEMÓRIA DA APLICAÇÃO
# =========================================================

VALORES_INICIAIS = {
    "atual": None,
    "anterior": None,
    "historico": None,
    "cobertura": 1.0,
    "seguranca": 15,
    "multiplo": 1,
}


for chave, valor in VALORES_INICIAIS.items():
    if chave not in st.session_state:
        st.session_state[chave] = valor


# =========================================================
# LEITURA E TRATAMENTO DOS FICHEIROS
# =========================================================

def normalizar_texto(valor):
    texto = "" if valor is None else str(valor)

    texto = unicodedata.normalize("NFKD", texto)

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
        return MAPA_COLUNAS[nome_normalizado]

    for alternativa, nome_final in sorted(
        MAPA_COLUNAS.items(),
        key=lambda item: len(item[0]),
        reverse=True,
    ):

        if len(alternativa) >= 5:

            if (
                nome_normalizado.startswith(alternativa)
                or nome_normalizado.endswith(alternativa)
            ):
                return nome_final

    return None


def pontuar_cabecalho(valores):
    colunas_encontradas = set()

    for valor in valores:
        coluna = identificar_coluna(valor)

        if coluna:
            colunas_encontradas.add(coluna)

    return len(colunas_encontradas)


def converter_numeros(serie):
    if pd.api.types.is_numeric_dtype(serie):

        return pd.to_numeric(
            serie,
            errors="coerce",
        ).fillna(0)

    texto = serie.astype(str).str.strip()

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

    tem_ambos = tem_virgula & tem_ponto

    texto.loc[tem_ambos] = (
        texto.loc[tem_ambos]
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

    apenas_virgula = tem_virgula & ~tem_ponto

    texto.loc[apenas_virgula] = (
        texto.loc[apenas_virgula]
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


def ler_ficheiro(ficheiro):
    conteudo = ficheiro.getvalue()

    extensao = ficheiro.name.lower().rsplit(
        ".",
        1,
    )[-1]

    if extensao == "csv":

        ultimo_erro = None

        for encoding in [
            "utf-8-sig",
            "utf-8",
            "latin-1",
        ]:

            try:

                dados = pd.read_csv(
                    io.BytesIO(conteudo),
                    sep=None,
                    engine="python",
                    encoding=encoding,
                )

                break

            except Exception as erro:
                ultimo_erro = erro

        else:

            raise ValueError(
                f"Não foi possível ler o CSV: {ultimo_erro}"
            )

        linha_cabecalho = 0

    else:

        amostra = pd.read_excel(
            io.BytesIO(conteudo),
            sheet_name=0,
            header=None,
            nrows=30,
            engine="openpyxl",
        )

        pontuacoes = amostra.apply(
            lambda linha: pontuar_cabecalho(
                linha.tolist()
            ),
            axis=1,
        )

        linha_cabecalho = (
            int(pontuacoes.idxmax())
            if len(pontuacoes)
            else 0
        )

        dados = pd.read_excel(
            io.BytesIO(conteudo),
            sheet_name=0,
            header=linha_cabecalho,
            engine="openpyxl",
        )

    dados = dados.dropna(
        how="all"
    ).copy()

    dados.columns = [
        str(coluna).strip()
        for coluna in dados.columns
    ]

    renomear = {}

    nomes_utilizados = set()

    for coluna in dados.columns:

        nome_final = identificar_coluna(coluna)

        if (
            nome_final
            and nome_final not in nomes_utilizados
        ):

            renomear[coluna] = nome_final

            nomes_utilizados.add(nome_final)

    dados = dados.rename(
        columns=renomear
    )

    colunas_numericas = [
        "stock_inicial",
        "entradas",
        "saidas",
        "stock_final",
        "valor_entradas",
        "valor_saidas",
    ]

    for coluna in colunas_numericas:

        if coluna in dados.columns:

            dados[coluna] = converter_numeros(
                dados[coluna]
            )

    if "data" in dados.columns:

        dados["data"] = pd.to_datetime(
            dados["data"],
            errors="coerce",
            dayfirst=True,
        )

    if "produto" in dados.columns:

        produto_normalizado = (
            dados["produto"]
            .astype(str)
            .map(normalizar_texto)
        )

        linhas_total = produto_normalizado.str.match(
            r"^(total|totais|subtotal)$",
            na=False,
        )

        dados = dados.loc[
            ~linhas_total
        ]

    return (
        dados.reset_index(drop=True),
        linha_cabecalho,
    )


def garantir_produto(dados):
    dados = dados.copy()

    if "produto" not in dados.columns:

        if "referencia" in dados.columns:

            dados["produto"] = (
                dados["referencia"]
                .astype(str)
            )

        else:

            dados["produto"] = [
                f"Produto {numero + 1}"
                for numero in range(len(dados))
            ]

    return dados


def formatar_numero(valor, casas=0):
    try:

        return (
            f"{float(valor):,.{casas}f}"
            .replace(",", "X")
            .replace(".", ",")
            .replace("X", ".")
        )

    except Exception:

        return "0"


# =========================================================
# CÁLCULO DE ENCOMENDAS
# =========================================================

def calcular_encomendas(atual, anterior):

    if atual is None or anterior is None:

        return (
            None,
            "Carrega a listagem atual e a listagem anterior.",
        )

    atual = garantir_produto(atual)

    anterior = garantir_produto(anterior)

    if (
        "referencia" in atual.columns
        and "referencia" in anterior.columns
    ):

        chave = "referencia"

    else:

        chave = "produto"

    if not {
        "saidas",
        "stock_final",
    }.issubset(atual.columns):

        return (
            None,
            "A listagem atual precisa das colunas Saídas e Stock Final.",
        )

    if "saidas" not in anterior.columns:

        return (
            None,
            "A listagem anterior precisa da coluna Saídas.",
        )

    dados_atuais = atual.groupby(
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

        stock_atual=(
            "stock_final",
            "sum",
        ),
    )

    dados_anteriores = anterior.groupby(
        chave,
        as_index=False,
    ).agg(

        produto_anterior=(
            "produto",
            "first",
        ),

        saidas_anterior=(
            "saidas",
            "sum",
        ),
    )

    resultado = dados_atuais.merge(
        dados_anteriores,
        on=chave,
        how="outer",
    )

    resultado["produto"] = (
        resultado["produto"]
        .fillna(
            resultado["produto_anterior"]
        )
    )

    resultado = resultado.drop(
        columns=["produto_anterior"],
        errors="ignore",
    )

    for coluna in [
        "saidas_atual",
        "saidas_anterior",
        "stock_atual",
    ]:

        resultado[coluna] = pd.to_numeric(
            resultado[coluna],
            errors="coerce",
        ).fillna(0)

    resultado["procura_base"] = (
        resultado["saidas_atual"] * 0.65
        + resultado["saidas_anterior"] * 0.35
    )

    resultado["stock_alvo"] = (
        resultado["procura_base"]
        * st.session_state.cobertura
        * (
            1
            + st.session_state.seguranca / 100
        )
    )

    necessidade = (
        resultado["stock_alvo"]
        - resultado["stock_atual"]
    ).clip(lower=0)

    multiplo = max(
        int(st.session_state.multiplo),
        1,
    )

    resultado["sugestao"] = necessidade.apply(
        lambda quantidade: (
            int(
                math.ceil(
                    quantidade / multiplo
                )
                * multiplo
            )
            if quantidade > 0
            else 0
        )
    )

    resultado["variacao_pct"] = resultado.apply(
        lambda linha: (

            (
                (
                    linha["saidas_atual"]
                    - linha["saidas_anterior"]
                )
                / linha["saidas_anterior"]
            )
            * 100

            if linha["saidas_anterior"] != 0

            else (
                100
                if linha["saidas_atual"] > 0
                else 0
            )
        ),
        axis=1,
    )

    resultado["motivo"] = resultado.apply(
        lambda linha: (

            "Vendas a subir e stock insuficiente"

            if (
                linha["sugestao"] > 0
                and linha["variacao_pct"] > 10
            )

            else "Stock insuficiente para a procura estimada"

            if linha["sugestao"] > 0

            else "Stock suficiente"
        ),
        axis=1,
    )

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

    return resultado, None


def converter_para_excel(dados):
    memoria = io.BytesIO()

    with pd.ExcelWriter(
        memoria,
        engine="openpyxl",
    ) as writer:

        dados.to_excel(
            writer,
            index=False,
            sheet_name="Encomenda",
        )

    memoria.seek(0)

    return memoria.getvalue()


# =========================================================
# MENU
# =========================================================

with st.sidebar:

    st.markdown(
        '<div class="inviora-brand">INVIORA</div>',
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
            "📥 Importar dados",
            "📦 Encomendas",
            "📈 Vendas",
            "📋 Produtos",
            "🧠 Assistente",
            "⚙️ Definições",
        ],
        label_visibility="collapsed",
    )

    st.divider()

    estado_atual = (
        "🟢 Atual"
        if st.session_state.atual is not None
        else "⚪ Atual"
    )

    estado_anterior = (
        "🟢 Anterior"
        if st.session_state.anterior is not None
        else "⚪ Anterior"
    )

    estado_historico = (
        "🟢 Histórico"
        if st.session_state.historico is not None
        else "⚪ Histórico"
    )

    st.caption(
        f"{estado_atual} · "
        f"{estado_anterior} · "
        f"{estado_historico}"
    )

    st.caption("Inviora v0.2.0")


# =========================================================
# DASHBOARD
# =========================================================

if pagina == "🏠 Dashboard":

    st.title("Dashboard")

    st.caption(
        "O que aconteceu, o que está a acontecer "
        "e o que precisa de atenção."
    )

    atual = st.session_state.atual

    anterior = st.session_state.anterior

    if atual is None:

        st.info(
            "Abre **Importar dados** "
            "e carrega a listagem atual."
        )

        st.stop()

    atual = garantir_produto(atual)

    total_produtos = len(atual)

    total_saidas = (
        atual["saidas"].sum()
        if "saidas" in atual.columns
        else 0
    )

    stock_total = (
        atual["stock_final"].sum()
        if "stock_final" in atual.columns
        else 0
    )

    produtos_criticos = (
        int(
            (
                atual["stock_final"] <= 0
            ).sum()
        )
        if "stock_final" in atual.columns
        else 0
    )

    variacao = None

    if (
        anterior is not None
        and "saidas" in anterior.columns
    ):

        total_anterior = anterior[
            "saidas"
        ].sum()

        if total_anterior != 0:

            percentagem = (
                (
                    total_saidas
                    - total_anterior
                )
                / total_anterior
            ) * 100

            variacao = (
                f"{percentagem:.1f}% "
                f"vs anterior"
            )

    coluna1, coluna2, coluna3, coluna4 = st.columns(
        4
    )

    coluna1.metric(
        "Produtos",
        formatar_numero(total_produtos),
    )

    coluna2.metric(
        "Saídas",
        formatar_numero(total_saidas, 1),
        variacao,
    )

    coluna3.metric(
        "Stock final",
        formatar_numero(stock_total, 1),
    )

    coluna4.metric(
        "Stock ≤ 0",
        formatar_numero(produtos_criticos),
    )

    esquerda, direita = st.columns(
        [
            1.25,
            1,
        ]
    )

    with esquerda:

        st.subheader(
            "Produtos com mais saídas"
        )

        if "saidas" in atual.columns:

            produtos_top = (
                atual.groupby(
                    "produto",
                    as_index=False,
                )["saidas"]
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
                produtos_top,
                x="saidas",
                y="produto",
                orientation="h",
                labels={
                    "saidas": "Saídas",
                    "produto": "",
                },
            )

            grafico.update_layout(
                height=430,
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

    with direita:

        st.subheader(
            "Atenção imediata"
        )

        if "stock_final" in atual.columns:

            colunas_alerta = [
                coluna
                for coluna in [
                    "referencia",
                    "produto",
                    "stock_final",
                    "saidas",
                ]
                if coluna in atual.columns
            ]

            alertas = atual.loc[
                atual["stock_final"] <= 0,
                colunas_alerta,
            ].sort_values(
                "stock_final"
            )

            if alertas.empty:

                st.success(
                    "Não existem produtos "
                    "com stock igual ou inferior a zero."
                )

            else:

                st.dataframe(
                    alertas.head(20),
                    use_container_width=True,
                    hide_index=True,
                )


# =========================================================
# IMPORTAR DADOS
# =========================================================

elif pagina == "📥 Importar dados":

    st.title("Importar dados")

    st.warning(
        "Não coloques ficheiros reais da empresa "
        "dentro do GitHub. Carrega-os apenas aqui "
        "na aplicação e com autorização."
    )

    aba_atual, aba_anterior, aba_historico = st.tabs(
        [
            "Período atual",
            "Período anterior",
            "Histórico de vendas",
        ]
    )

    configuracoes = [
        (
            aba_atual,
            "upload_atual",
            "atual",
            "Listagem atual",
        ),

        (
            aba_anterior,
            "upload_anterior",
            "anterior",
            "Listagem anterior",
        ),

        (
            aba_historico,
            "upload_historico",
            "historico",
            "Histórico de vendas",
        ),
    ]

    for (
        aba,
        chave_upload,
        chave_memoria,
        titulo,
    ) in configuracoes:

        with aba:

            ficheiro = st.file_uploader(
                f"{titulo} (.xlsx ou .csv)",
                type=[
                    "xlsx",
                    "csv",
                ],
                key=chave_upload,
            )

            if ficheiro is not None:

                try:

                    dados, cabecalho = ler_ficheiro(
                        ficheiro
                    )

                    st.session_state[
                        chave_memoria
                    ] = dados

                    st.success(
                        f"Carregado: {ficheiro.name} · "
                        f"{len(dados)} linhas · "
                        f"cabeçalho na linha {cabecalho + 1}"
                    )

                    st.caption(
                        "Colunas reconhecidas: "
                        + ", ".join(
                            dados.columns.astype(str)
                        )
                    )

                    st.dataframe(
                        dados.head(20),
                        use_container_width=True,
                        hide_index=True,
                    )

                except Exception as erro:

                    st.error(
                        f"Não consegui ler o ficheiro: {erro}"
                    )

    if st.button(
        "Limpar todos os dados desta sessão"
    ):

        st.session_state.atual = None
        st.session_state.anterior = None
        st.session_state.historico = None

        st.rerun()


# =========================================================
# ENCOMENDAS
# =========================================================

elif pagina == "📦 Encomendas":

    st.title(
        "Sugestão de encomenda"
    )

    st.warning(
        "A fórmula atual é uma simulação inicial. "
        "Valida sempre antes de encomendar."
    )

    resultado, erro = calcular_encomendas(
        st.session_state.atual,
        st.session_state.anterior,
    )

    if erro:

        st.info(erro)

        st.stop()

    mostrar_apenas = st.toggle(
        "Mostrar apenas produtos a encomendar",
        value=True,
    )

    pesquisa = st.text_input(
        "Pesquisar produto ou referência"
    )

    tabela = resultado.copy()

    if mostrar_apenas:

        tabela = tabela[
            tabela["sugestao"] > 0
        ]

    if pesquisa:

        pesquisa_normalizada = normalizar_texto(
            pesquisa
        )

        mascara = (
            tabela["produto"]
            .astype(str)
            .map(normalizar_texto)
            .str.contains(
                pesquisa_normalizada,
                na=False,
            )
        )

        if "referencia" in tabela.columns:

            mascara = mascara | (
                tabela["referencia"]
                .astype(str)
                .map(normalizar_texto)
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
            resultado["sugestao"] > 0
        ).sum()
    )

    quantidade_encomendar = resultado[
        "sugestao"
    ].sum()

    produtos_sem_stock = int(
        (
            resultado["stock_atual"] <= 0
        ).sum()
    )

    coluna1, coluna2, coluna3 = st.columns(
        3
    )

    coluna1.metric(
        "Produtos a encomendar",
        formatar_numero(
            produtos_encomendar
        ),
    )

    coluna2.metric(
        "Quantidade sugerida",
        formatar_numero(
            quantidade_encomendar
        ),
    )

    coluna3.metric(
        "Stock ≤ 0",
        formatar_numero(
            produtos_sem_stock
        ),
    )

    colunas_visiveis = [
        coluna
        for coluna in [
            "referencia",
            "produto",
            "saidas_anterior",
            "saidas_atual",
            "variacao_pct",
            "stock_atual",
            "procura_base",
            "stock_alvo",
            "sugestao",
            "motivo",
        ]
        if coluna in tabela.columns
    ]

    st.dataframe(
        tabela[colunas_visiveis],
        use_container_width=True,
        hide_index=True,
    )

    st.download_button(
        "⬇️ Exportar sugestão para Excel",

        data=converter_para_excel(
            tabela[colunas_visiveis]
        ),

        file_name=(
            f"inviora_encomenda_"
            f"{date.today().isoformat()}.xlsx"
        ),

        mime=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        ),
    )


# =========================================================
# VENDAS
# =========================================================

elif pagina == "📈 Vendas":

    st.title(
        "Análise de vendas"
    )

    historico = st.session_state.historico

    atual = st.session_state.atual

    anterior = st.session_state.anterior

    if (
        historico is not None
        and "data" in historico.columns
    ):

        historico = garantir_produto(
            historico
        )

        historico = historico.dropna(
            subset=["data"]
        ).copy()

        metricas = {}

        if "saidas" in historico.columns:

            metricas[
                "Quantidade vendida"
            ] = "saidas"

        if "valor_saidas" in historico.columns:

            metricas[
                "Valor de vendas"
            ] = "valor_saidas"

        if not metricas:

            st.warning(
                "O histórico precisa de uma coluna "
                "Saídas ou Valor Saídas."
            )

            st.stop()

        coluna1, coluna2 = st.columns(
            2
        )

        periodo = coluna1.selectbox(
            "Visualização",
            [
                "Semanal",
                "Mensal",
                "Trimestral",
                "Semestral",
                "Anual",
            ],
        )

        nome_metrica = coluna2.selectbox(
            "Métrica",
            list(metricas.keys()),
        )

        metrica = metricas[
            nome_metrica
        ]

        anos_disponiveis = sorted(
            historico["data"]
            .dt.year
            .dropna()
            .astype(int)
            .unique()
            .tolist()
        )

        anos = st.multiselect(
            "Anos a comparar",
            anos_disponiveis,

            default=(
                anos_disponiveis[-2:]
                if len(anos_disponiveis) >= 2
                else anos_disponiveis
            ),
        )

        vendas = historico[
            historico["data"]
            .dt.year
            .isin(anos)
        ].copy()

        if periodo == "Semanal":

            vendas["periodo"] = (
                vendas["data"]
                .dt.isocalendar()
                .week
                .astype(int)
            )

        elif periodo == "Mensal":

            vendas["periodo"] = (
                vendas["data"].dt.month
            )

        elif periodo == "Trimestral":

            vendas["periodo"] = (
                vendas["data"].dt.quarter
            )

        elif periodo == "Semestral":

            vendas["periodo"] = (
                (
                    vendas["data"].dt.month
                    - 1
                )
                // 6
                + 1
            )

        else:

            vendas["periodo"] = 1

        vendas["ano"] = (
            vendas["data"]
            .dt.year
            .astype(str)
        )

        vendas_agrupadas = (
            vendas.groupby(
                [
                    "ano",
                    "periodo",
                ],
                as_index=False,
            )[metrica]
            .sum()
            .sort_values(
                [
                    "ano",
                    "periodo",
                ]
            )
        )

        grafico = px.line(
            vendas_agrupadas,
            x="periodo",
            y=metrica,
            color="ano",
            markers=True,
        )

        st.plotly_chart(
            grafico,
            use_container_width=True,
        )

        st.subheader(
            "Produtos mais vendidos"
        )

        ranking = (
            vendas.groupby(
                "produto",
                as_index=False,
            )[metrica]
            .sum()
            .nlargest(
                20,
                metrica,
            )
        )

        st.dataframe(
            ranking,
            use_container_width=True,
            hide_index=True,
        )

    elif atual is not None:

        st.info(
            "O ficheiro atual não tem datas individuais. "
            "Aqui comparamos o relatório atual com o anterior."
        )

        total_atual = (
            atual["saidas"].sum()
            if "saidas" in atual.columns
            else 0
        )

        total_anterior = (
            anterior["saidas"].sum()

            if (
                anterior is not None
                and "saidas" in anterior.columns
            )

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

        coluna3.metric(
            "Variação",

            (
                f"{variacao:.1f}%"
                if variacao is not None
                else "—"
            ),
        )

    else:

        st.info(
            "Carrega dados para começar."
        )


# =========================================================
# PRODUTOS
# =========================================================

elif pagina == "📋 Produtos":

    st.title("Produtos")

    atual = st.session_state.atual

    if atual is None:

        st.info(
            "Carrega primeiro a listagem atual."
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
            tabela["produto"]
            .astype(str)
            .map(normalizar_texto)
            .str.contains(
                pesquisa_normalizada,
                na=False,
            )
        )

        if "referencia" in tabela.columns:

            mascara = mascara | (
                tabela["referencia"]
                .astype(str)
                .map(normalizar_texto)
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
# ASSISTENTE
# =========================================================

elif pagina == "🧠 Assistente":

    st.title(
        "Assistente Inviora"
    )

    st.caption(
        "Versão beta sem API externa."
    )

    atual = st.session_state.atual

    if atual is None:

        st.info(
            "Carrega primeiro a listagem atual."
        )

        st.stop()

    atual = garantir_produto(
        atual
    )

    pergunta = st.selectbox(
        "O que queres saber?",
        [
            "Resumo da operação",
            "Produto com mais saídas",
            "Produtos a encomendar",
            "Produtos em risco",
        ],
    )

    if pergunta == "Resumo da operação":

        saidas = (
            atual["saidas"].sum()
            if "saidas" in atual.columns
            else 0
        )

        stock = (
            atual["stock_final"].sum()
            if "stock_final" in atual.columns
            else 0
        )

        risco = (
            int(
                (
                    atual["stock_final"] <= 0
                ).sum()
            )

            if "stock_final" in atual.columns

            else 0
        )

        st.success(
            f"Foram analisados **{len(atual)} produtos**. "
            f"As saídas totalizam **{formatar_numero(saidas, 1)}**. "
            f"O stock final é **{formatar_numero(stock, 1)}**. "
            f"Existem **{risco} produtos em risco**."
        )

    elif pergunta == "Produto com mais saídas":

        if "saidas" not in atual.columns:

            st.warning(
                "Não encontrei a coluna Saídas."
            )

        else:

            ranking = (
                atual.groupby(
                    "produto",
                    as_index=False,
                )["saidas"]
                .sum()
                .sort_values(
                    "saidas",
                    ascending=False,
                )
            )

            primeiro = ranking.iloc[0]

            st.success(
                f"O produto com mais saídas é "
                f"**{primeiro['produto']}**, "
                f"com **{formatar_numero(primeiro['saidas'], 1)}**."
            )

    elif pergunta == "Produtos a encomendar":

        resultado, erro = calcular_encomendas(
            atual,
            st.session_state.anterior,
        )

        if erro:

            st.info(erro)

        else:

            sugestoes = resultado[
                resultado["sugestao"] > 0
            ].head(10)

            st.dataframe(
                sugestoes,
                use_container_width=True,
                hide_index=True,
            )

    else:

        if "stock_final" not in atual.columns:

            st.warning(
                "Não encontrei a coluna Stock Final."
            )

        else:

            risco = atual[
                atual["stock_final"] <= 0
            ].sort_values(
                "stock_final"
            )

            st.dataframe(
                risco,
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
        "Arredondar encomendas para múltiplos de",
        min_value=1,
        max_value=1000,
        value=int(
            st.session_state.multiplo
        ),
        step=1,
    )

    st.subheader(
        "Fórmula atual"
    )

    st.code(
        "Procura estimada = "
        "65% × saídas atuais + "
        "35% × saídas anteriores\n"

        "Stock alvo = "
        "procura estimada × cobertura × "
        "(1 + margem de segurança)\n"

        "Sugestão = "
        "máximo entre 0 e "
        "(stock alvo - stock atual)",
        language="text",
    )

    st.warning(
        "Esta fórmula é apenas um ponto de partida. "
        "Antes de ser usada no trabalho precisamos "
        "de considerar prazos de entrega, dias de encomenda, "
        "mínimos, múltiplos de caixas, feriados e promoções."
    )
  Create Inviora Streamlit application
