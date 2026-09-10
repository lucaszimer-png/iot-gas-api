from flask import Flask, request, jsonify
import os
import psycopg2
from psycopg2.extras import RealDictCursor
from html import escape

app = Flask(__name__)

# ============================================================
# CONFIGURACAO
# ============================================================

DATABASE_URL = os.environ.get("DATABASE_URL")


# ============================================================
# CONEXAO COM BANCO
# ============================================================

def conectar_banco():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL nao configurada no ambiente.")
    return psycopg2.connect(DATABASE_URL)


# ============================================================
# CRIAR TABELA
# ============================================================

def criar_tabela():
    conexao = None
    cursor = None

    try:
        conexao = conectar_banco()
        cursor = conexao.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS medicoes (
                id SERIAL PRIMARY KEY,
                equipamento TEXT NOT NULL,
                sequencia INTEGER NOT NULL,
                timestamp_esp32 BIGINT NOT NULL,
                pulsos INTEGER NOT NULL,
                volume NUMERIC NOT NULL,
                recebido_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(equipamento, sequencia)
            );
        """)

        conexao.commit()
        print("Tabela medicoes verificada/criada com sucesso.")

    except Exception as erro:
        if conexao:
            conexao.rollback()
        print("ERRO AO CRIAR/VERIFICAR TABELA:")
        print(erro)

    finally:
        if cursor:
            cursor.close()
        if conexao:
            conexao.close()


# ============================================================
# ROTA PRINCIPAL
# ============================================================

@app.route("/", methods=["GET"])
def inicio():
    return jsonify({
        "status": "online",
        "servico": "IOT Gas API"
    })


# ============================================================
# RECEBER MEDICAO
# ============================================================

@app.route("/api/v1/medicao", methods=["POST"])
def receber_medicao():

    conexao = None
    cursor = None

    try:
        dados = request.get_json(silent=True)

        if not dados:
            return jsonify({
                "ack": False,
                "erro": "JSON ausente ou invalido"
            }), 400

        print("")
        print("=================================")
        print("NOVA MEDICAO RECEBIDA")
        print("=================================")
        print(dados)

        campos = [
            "id",
            "timestamp",
            "seq",
            "pulse",
            "volume"
        ]

        for campo in campos:
            if campo not in dados:
                return jsonify({
                    "ack": False,
                    "erro": f"Campo ausente: {campo}"
                }), 400

        equipamento = str(dados["id"])
        timestamp = int(dados["timestamp"])
        sequencia = int(dados["seq"])
        pulsos = int(dados["pulse"])
        volume = float(dados["volume"])

        # Segunda camada de seguranca:
        # nao grava registros sem pulsos.
        if pulsos <= 0:
            print("Registro ignorado: pulsos = 0")

            return jsonify({
                "ack": True,
                "id": equipamento,
                "seq": sequencia,
                "status": "IGNORADO_SEM_PULSO"
            }), 200

        conexao = conectar_banco()
        cursor = conexao.cursor()

        # ----------------------------------------------------
        # VERIFICAR DUPLICIDADE
        # ----------------------------------------------------

        cursor.execute("""
            SELECT id
            FROM medicoes
            WHERE equipamento = %s
              AND sequencia = %s
        """, (
            equipamento,
            sequencia
        ))

        registro = cursor.fetchone()

        if registro:
            print("Registro ja existe no banco.")

            return jsonify({
                "ack": True,
                "id": equipamento,
                "seq": sequencia,
                "status": "JA_EXISTE"
            }), 200

        # ----------------------------------------------------
        # GRAVAR MEDICAO
        # ----------------------------------------------------

        cursor.execute("""
            INSERT INTO medicoes
            (
                equipamento,
                sequencia,
                timestamp_esp32,
                pulsos,
                volume
            )
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
        """, (
            equipamento,
            sequencia,
            timestamp,
            pulsos,
            volume
        ))

        banco_id = cursor.fetchone()[0]

        conexao.commit()

        print("")
        print("MEDICAO GRAVADA NO BANCO")
        print("ID banco:", banco_id)
        print("Equipamento:", equipamento)
        print("Sequencia:", sequencia)
        print("Pulsos:", pulsos)
        print("Volume:", volume)

        return jsonify({
            "ack": True,
            "id": equipamento,
            "seq": sequencia,
            "status": "GRAVADO",
            "database_id": banco_id
        }), 200

    except Exception as erro:

        if conexao:
            conexao.rollback()

        print("")
        print("ERRO AO GRAVAR MEDICAO:")
        print(erro)

        return jsonify({
            "ack": False,
            "status": "ERRO",
            "mensagem": str(erro)
        }), 500

    finally:

        if cursor:
            cursor.close()

        if conexao:
            conexao.close()


# ============================================================
# CONSULTAR TODAS AS MEDICOES
# ============================================================

@app.route("/api/v1/medicoes", methods=["GET"])
def consultar_medicoes():

    conexao = None
    cursor = None

    try:
        conexao = conectar_banco()

        cursor = conexao.cursor(
            cursor_factory=RealDictCursor
        )

        cursor.execute("""
            SELECT
                id,
                equipamento,
                sequencia,
                timestamp_esp32,
                pulsos,
                volume,
                recebido_em
            FROM medicoes
            ORDER BY id ASC
        """)

        medicoes = cursor.fetchall()

        return jsonify({
            "total": len(medicoes),
            "medicoes": medicoes
        }), 200

    except Exception as erro:

        print("ERRO AO CONSULTAR MEDICOES:")
        print(erro)

        return jsonify({
            "erro": str(erro)
        }), 500

    finally:

        if cursor:
            cursor.close()

        if conexao:
            conexao.close()


# ============================================================
# CONSULTAR ULTIMAS 20 MEDICOES
# ============================================================

@app.route("/api/v1/medicoes/ultimas", methods=["GET"])
def consultar_ultimas():

    conexao = None
    cursor = None

    try:
        conexao = conectar_banco()

        cursor = conexao.cursor(
            cursor_factory=RealDictCursor
        )

        cursor.execute("""
            SELECT
                id,
                equipamento,
                sequencia,
                timestamp_esp32,
                pulsos,
                volume,
                recebido_em
            FROM medicoes
            ORDER BY id DESC
            LIMIT 20
        """)

        medicoes = cursor.fetchall()

        return jsonify({
            "total": len(medicoes),
            "medicoes": medicoes
        }), 200

    except Exception as erro:

        print("ERRO AO CONSULTAR ULTIMAS MEDICOES:")
        print(erro)

        return jsonify({
            "erro": str(erro)
        }), 500

    finally:

        if cursor:
            cursor.close()

        if conexao:
            conexao.close()


# ============================================================
# DASHBOARD
# ============================================================

@app.route("/dashboard", methods=["GET"])
def dashboard():

    conexao = None
    cursor = None

    try:
        conexao = conectar_banco()

        cursor = conexao.cursor(
            cursor_factory=RealDictCursor
        )

        # ----------------------------------------------------
        # RESUMO
        # ----------------------------------------------------

        cursor.execute("""
            SELECT
                COUNT(*) AS registros,
                COALESCE(SUM(pulsos), 0) AS pulsos_totais,
                COALESCE(SUM(volume), 0) AS volume_total
            FROM medicoes
        """)

        resumo = cursor.fetchone()

        # ----------------------------------------------------
        # ULTIMAS 20 MEDICOES
        # ----------------------------------------------------

        cursor.execute("""
            SELECT
                equipamento,
                sequencia,
                pulsos,
                volume,
                timestamp_esp32,
                recebido_em
            FROM medicoes
            ORDER BY id DESC
            LIMIT 20
        """)

        medicoes = cursor.fetchall()

        # ----------------------------------------------------
        # DADOS DOS GRAFICOS
        # ----------------------------------------------------

        medicoes_grafico = list(reversed(medicoes))

        sequencias = [
            int(m["sequencia"])
            for m in medicoes_grafico
        ]

        pulsos = [
            int(m["pulsos"])
            for m in medicoes_grafico
        ]

        volumes = [
            float(m["volume"])
            for m in medicoes_grafico
        ]

        # ----------------------------------------------------
        # ULTIMA MEDICAO
        # ----------------------------------------------------

        ultimo = medicoes[0] if medicoes else None

        if ultimo:
            ultima_medicao = f"""
            <div class="ultimo-grid">

                <div>
                    <strong>Equipamento</strong>
                    <span>{escape(str(ultimo["equipamento"]))}</span>
                </div>

                <div>
                    <strong>Sequencia</strong>
                    <span>{ultimo["sequencia"]}</span>
                </div>

                <div>
                    <strong>Pulsos</strong>
                    <span>{ultimo["pulsos"]}</span>
                </div>

                <div>
                    <strong>Volume</strong>
                    <span>{float(ultimo["volume"]):.3f} m³</span>
                </div>

                <div>
                    <strong>Recebido em</strong>
                    <span>{ultimo["recebido_em"]}</span>
                </div>

            </div>
            """
        else:
            ultima_medicao = """
            <p>Nenhuma medicao registrada.</p>
            """

        # ----------------------------------------------------
        # TABELA
        # ----------------------------------------------------

        linhas = ""

        for m in medicoes:
            linhas += f"""
            <tr>
                <td>{escape(str(m["equipamento"]))}</td>
                <td>{m["sequencia"]}</td>
                <td>{m["pulsos"]}</td>
                <td>{float(m["volume"]):.3f}</td>
                <td>{m["recebido_em"]}</td>
            </tr>
            """

        if not linhas:
            linhas = """
            <tr>
                <td colspan="5">Nenhuma medicao registrada.</td>
            </tr>
            """

        # ----------------------------------------------------
        # HTML
        # Os graficos sao desenhados com SVG/JavaScript puro.
        # Nao dependem de Chart.js ou de CDN externo.
        # ----------------------------------------------------

        html = f"""
<!DOCTYPE html>
<html lang="pt-BR">

<head>

    <meta charset="UTF-8">

    <meta name="viewport"
          content="width=device-width, initial-scale=1.0">

    <meta http-equiv="refresh" content="10">

    <title>IoT Gas - Dashboard</title>

    <style>

        * {{
            box-sizing: border-box;
        }}

        body {{
            font-family: Arial, sans-serif;
            margin: 0;
            padding: 20px;
            background: #f4f4f4;
            color: #222;
        }}

        .container {{
            max-width: 1200px;
            margin: auto;
        }}

        h1 {{
            text-align: center;
            margin-bottom: 30px;
        }}

        h2 {{
            margin-top: 0;
        }}

        .cards {{
            display: grid;
            grid-template-columns:
                repeat(auto-fit, minmax(220px, 1fr));
            gap: 20px;
            margin-bottom: 25px;
        }}

        .card {{
            background: white;
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.10);
        }}

        .card-centro {{
            text-align: center;
        }}

        .card-titulo {{
            font-size: 15px;
            color: #666;
        }}

        .valor {{
            font-size: 30px;
            font-weight: bold;
            margin-top: 10px;
        }}

        .online {{
            color: green;
        }}

        .ultimo {{
            background: white;
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.10);
            margin-bottom: 25px;
        }}

        .ultimo-grid {{
            display: grid;
            grid-template-columns:
                repeat(auto-fit, minmax(180px, 1fr));
            gap: 20px;
        }}

        .ultimo-grid div {{
            display: flex;
            flex-direction: column;
            gap: 8px;
        }}

        .ultimo-grid span {{
            font-size: 18px;
        }}

        .graficos {{
            display: grid;
            grid-template-columns:
                repeat(auto-fit, minmax(400px, 1fr));
            gap: 20px;
            margin-bottom: 25px;
        }}

        .grafico {{
            background: white;
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.10);
            min-width: 0;
        }}

        .grafico-area {{
            width: 100%;
            height: 320px;
            overflow: hidden;
        }}

        .grafico-svg {{
            width: 100%;
            height: 100%;
            display: block;
        }}

        .tabela {{
            background: white;
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.10);
            overflow-x: auto;
        }}

        table {{
            width: 100%;
            border-collapse: collapse;
            background: white;
        }}

        th, td {{
            padding: 12px;
            border-bottom: 1px solid #ddd;
            text-align: center;
            white-space: nowrap;
        }}

        th {{
            background: #222;
            color: white;
        }}

        .atualizacao {{
            text-align: center;
            color: #777;
            margin-top: 20px;
            font-size: 13px;
        }}

        .sem-dados {{
            display: flex;
            align-items: center;
            justify-content: center;
            height: 100%;
            color: #777;
        }}

        @media(max-width: 700px) {{

            body {{
                padding: 10px;
            }}

            .graficos {{
                grid-template-columns: 1fr;
            }}

            .grafico-area {{
                height: 280px;
            }}

            table {{
                font-size: 11px;
            }}

            th, td {{
                padding: 7px 4px;
            }}

        }}

    </style>

</head>

<body>

<div class="container">

    <h1>IoT Gas - Monitoramento</h1>

    <!-- ================================================= -->
    <!-- INDICADORES -->
    <!-- ================================================= -->

    <div class="cards">

        <div class="card card-centro">

            <div class="card-titulo">
                Status da API
            </div>

            <div class="valor online">
                ONLINE
            </div>

        </div>

        <div class="card card-centro">

            <div class="card-titulo">
                Registros
            </div>

            <div class="valor">
                {resumo["registros"]}
            </div>

        </div>

        <div class="card card-centro">

            <div class="card-titulo">
                Pulsos totais
            </div>

            <div class="valor">
                {resumo["pulsos_totais"]}
            </div>

        </div>

        <div class="card card-centro">

            <div class="card-titulo">
                Volume total
            </div>

            <div class="valor">
                {float(resumo["volume_total"]):.3f} m³
            </div>

        </div>

    </div>


    <!-- ================================================= -->
    <!-- ULTIMA MEDICAO -->
    <!-- ================================================= -->

    <div class="ultimo">

        <h2>Ultima medicao</h2>

        {ultima_medicao}

    </div>


    <!-- ================================================= -->
    <!-- GRAFICOS -->
    <!-- ================================================= -->

    <div class="graficos">

        <div class="grafico">

            <h2>Pulsos por registro</h2>

            <div class="grafico-area" id="areaPulsos">

                <svg
                    id="graficoPulsos"
                    class="grafico-svg"
                    viewBox="0 0 800 300"
                    preserveAspectRatio="none">
                </svg>

            </div>

        </div>


        <div class="grafico">

            <h2>Volume por registro</h2>

            <div class="grafico-area" id="areaVolume">

                <svg
                    id="graficoVolume"
                    class="grafico-svg"
                    viewBox="0 0 800 300"
                    preserveAspectRatio="none">
                </svg>

            </div>

        </div>

    </div>


    <!-- ================================================= -->
    <!-- TABELA -->
    <!-- ================================================= -->

    <div class="tabela">

        <h2>Ultimas medicoes</h2>

        <table>

            <tr>
                <th>Equipamento</th>
                <th>Seq.</th>
                <th>Pulsos</th>
                <th>Volume (m³)</th>
                <th>Recebido em</th>
            </tr>

            {linhas}

        </table>

    </div>


    <div class="atualizacao">
        Pagina atualizada automaticamente a cada 10 segundos.
    </div>

</div>


<script>

    // ========================================================
    // DADOS GERADOS PELO PYTHON
    // ========================================================

    const sequencias = {sequencias};
    const pulsos = {pulsos};
    const volumes = {volumes};


    // ========================================================
    // DESENHAR GRAFICO SVG
    // ========================================================

    function desenharGrafico(id, valores, titulo) {{

        const svg = document.getElementById(id);

        svg.innerHTML = "";

        const largura = 800;
        const altura = 300;

        const margemEsquerda = 55;
        const margemDireita = 20;
        const margemTopo = 20;
        const margemBase = 40;

        const areaLargura =
            largura - margemEsquerda - margemDireita;

        const areaAltura =
            altura - margemTopo - margemBase;


        // ----------------------------------------------------
        // SEM DADOS
        // ----------------------------------------------------

        if (!valores.length) {{

            const texto = document.createElementNS(
                "http://www.w3.org/2000/svg",
                "text"
            );

            texto.setAttribute("x", largura / 2);
            texto.setAttribute("y", altura / 2);
            texto.setAttribute("text-anchor", "middle");
            texto.setAttribute("fill", "#777");
            texto.textContent = "Nenhum dado";

            svg.appendChild(texto);

            return;
        }}


        // ----------------------------------------------------
        // ESCALA
        // ----------------------------------------------------

        let maximo = Math.max(...valores);

        if (maximo <= 0) {{
            maximo = 1;
        }}

        // ----------------------------------------------------
        // EIXOS
        // ----------------------------------------------------

        const eixoX = document.createElementNS(
            "http://www.w3.org/2000/svg",
            "line"
        );

        eixoX.setAttribute("x1", margemEsquerda);
        eixoX.setAttribute("y1", margemTopo + areaAltura);
        eixoX.setAttribute("x2", largura - margemDireita);
        eixoX.setAttribute("y2", margemTopo + areaAltura);
        eixoX.setAttribute("stroke", "#999");

        svg.appendChild(eixoX);


        const eixoY = document.createElementNS(
            "http://www.w3.org/2000/svg",
            "line"
        );

        eixoY.setAttribute("x1", margemEsquerda);
        eixoY.setAttribute("y1", margemTopo);
        eixoY.setAttribute("x2", margemEsquerda);
        eixoY.setAttribute("y2", margemTopo + areaAltura);
        eixoY.setAttribute("stroke", "#999");

        svg.appendChild(eixoY);


        // ----------------------------------------------------
        // LINHAS DE GRADE
        // ----------------------------------------------------

        for (let i = 0; i <= 4; i++) {{

            const valorGrade = maximo * i / 4;

            const y =
                margemTopo +
                areaAltura -
                (valorGrade / maximo) * areaAltura;

            const linha = document.createElementNS(
                "http://www.w3.org/2000/svg",
                "line"
            );

            linha.setAttribute("x1", margemEsquerda);
            linha.setAttribute("y1", y);
            linha.setAttribute("x2", largura - margemDireita);
            linha.setAttribute("y2", y);
            linha.setAttribute("stroke", "#ddd");

            svg.appendChild(linha);


            const texto = document.createElementNS(
                "http://www.w3.org/2000/svg",
                "text"
            );

            texto.setAttribute("x", margemEsquerda - 8);
            texto.setAttribute("y", y + 4);
            texto.setAttribute("text-anchor", "end");
            texto.setAttribute("font-size", "12");
            texto.setAttribute("fill", "#666");

            texto.textContent =
                Number(valorGrade).toFixed(2);

            svg.appendChild(texto);
        }}


        // ----------------------------------------------------
        // PONTOS
        // ----------------------------------------------------

        const pontos = [];

        valores.forEach((valor, indice) => {{

            let x;

            if (valores.length === 1) {{

                x = margemEsquerda + areaLargura / 2;

            }} else {{

                x =
                    margemEsquerda +
                    (indice / (valores.length - 1)) *
                    areaLargura;
            }}

            const y =
                margemTopo +
                areaAltura -
                (valor / maximo) * areaAltura;

            pontos.push([x, y]);
        }});


        // ----------------------------------------------------
        // LINHA DO GRAFICO
        // ----------------------------------------------------

        if (pontos.length > 1) {{

            const polyline =
                document.createElementNS(
                    "http://www.w3.org/2000/svg",
                    "polyline"
                );

            polyline.setAttribute(
                "points",
                pontos.map(p => p[0] + "," + p[1]).join(" ")
            );

            polyline.setAttribute(
                "fill",
                "none"
            );

            polyline.setAttribute(
                "stroke",
                "#222"
            );

            polyline.setAttribute(
                "stroke-width",
                "3"
            );

            svg.appendChild(polyline);
        }}


        // ----------------------------------------------------
        // PONTOS DO GRAFICO
        // ----------------------------------------------------

        pontos.forEach((ponto, indice) => {{

            const circulo =
                document.createElementNS(
                    "http://www.w3.org/2000/svg",
                    "circle"
                );

            circulo.setAttribute("cx", ponto[0]);
            circulo.setAttribute("cy", ponto[1]);
            circulo.setAttribute("r", "5");
            circulo.setAttribute("fill", "#222");

            svg.appendChild(circulo);


            // Numero do valor
            const texto =
                document.createElementNS(
                    "http://www.w3.org/2000/svg",
                    "text"
                );

            texto.setAttribute("x", ponto[0]);
            texto.setAttribute("y", ponto[1] - 10);
            texto.setAttribute("text-anchor", "middle");
            texto.setAttribute("font-size", "11");
            texto.setAttribute("fill", "#333");

            texto.textContent =
                Number(valores[indice]).toFixed(3);

            svg.appendChild(texto);
        }});


        // ----------------------------------------------------
        // ROTULOS DO EIXO X
        // ----------------------------------------------------

        sequencias.forEach((seq, indice) => {{

            if (
                indice === 0 ||
                indice === sequencias.length - 1 ||
                indice % 5 === 0
            ) {{

                const ponto = pontos[indice];

                const texto =
                    document.createElementNS(
                        "http://www.w3.org/2000/svg",
                        "text"
                    );

                texto.setAttribute("x", ponto[0]);
                texto.setAttribute(
                    "y",
                    margemTopo + areaAltura + 25
                );

                texto.setAttribute(
                    "text-anchor",
                    "middle"
                );

                texto.setAttribute(
                    "font-size",
                    "12"
                );

                texto.setAttribute(
                    "fill",
                    "#666"
                );

                texto.textContent = seq;

                svg.appendChild(texto);
            }}
        }});
    }}


    // ========================================================
    // DESENHAR OS DOIS GRAFICOS
    // ========================================================

    desenharGrafico(
        "graficoPulsos",
        pulsos,
        "Pulsos"
    );

    desenharGrafico(
        "graficoVolume",
        volumes,
        "Volume"
    );

</script>

</body>
</html>
"""

        return html

    except Exception as erro:

        print("ERRO NO DASHBOARD:")
        print(erro)

        return f"""
        <!DOCTYPE html>
        <html lang="pt-BR">
        <head>
            <meta charset="UTF-8">
            <title>Erro - IoT Gas</title>
        </head>
        <body>
            <h1>Erro ao carregar dashboard</h1>
            <pre>{escape(str(erro))}</pre>
        </body>
        </html>
        """, 500

    finally:

        if cursor:
            cursor.close()

        if conexao:
            conexao.close()


# ============================================================
# INICIALIZACAO
# ============================================================

if __name__ == "__main__":

    criar_tabela()

    porta = int(os.environ.get("PORT", 5000))

    app.run(
        host="0.0.0.0",
        port=porta
    )
