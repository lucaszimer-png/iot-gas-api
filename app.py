from flask import Flask, request, jsonify
import os
import psycopg2
from psycopg2.extras import RealDictCursor

app = Flask(__name__)


# ============================================================
# CONFIGURAÇÃO
# ============================================================

DATABASE_URL = os.environ.get("DATABASE_URL")


# ============================================================
# CONEXÃO COM BANCO
# ============================================================

def conectar_banco():
    return psycopg2.connect(DATABASE_URL)


# ============================================================
# CRIAR TABELA
# ============================================================

def criar_tabela():

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

    cursor.close()
    conexao.close()

    print("Tabela medicoes verificada/criada com sucesso.")


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
# RECEBER MEDIÇÃO
# ============================================================

@app.route("/api/v1/medicao", methods=["POST"])
def receber_medicao():

    conexao = None
    cursor = None

    try:

        dados = request.get_json()

        print("")
        print("=================================")
        print("NOVA MEDICAO RECEBIDA")
        print("=================================")
        print(dados)

        # ----------------------------------------------------
        # VALIDAR DADOS
        # ----------------------------------------------------

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

        equipamento = dados["id"]
        timestamp = dados["timestamp"]
        sequencia = dados["seq"]
        pulsos = dados["pulse"]
        volume = dados["volume"]

        # ----------------------------------------------------
        # CONECTAR AO BANCO
        # ----------------------------------------------------

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

            print("Registro já existe no banco.")

            return jsonify({
                "ack": True,
                "id": equipamento,
                "seq": sequencia,
                "status": "JA_EXISTE"
            }), 200

        # ----------------------------------------------------
        # GRAVAR MEDIÇÃO
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
# CONSULTAR TODAS AS MEDIÇÕES
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

        print("ERRO AO CONSULTAR MEDIÇÕES:")
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
# CONSULTAR ÚLTIMAS 20 MEDIÇÕES
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

        print("ERRO AO CONSULTAR ÚLTIMAS MEDIÇÕES:")
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
# INICIALIZAÇÃO
# ============================================================

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
        # ÚLTIMAS 20 MEDIÇÕES
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
        # ÚLTIMO REGISTRO
        # ----------------------------------------------------

        ultimo = medicoes[0] if medicoes else None

        # ----------------------------------------------------
        # GERAR TABELA
        # ----------------------------------------------------

        linhas = ""

        for m in medicoes:

            linhas += f"""
            <tr>
                <td>{m['equipamento']}</td>
                <td>{m['sequencia']}</td>
                <td>{m['pulsos']}</td>
                <td>{float(m['volume']):.3f}</td>
                <td>{m['recebido_em']}</td>
            </tr>
            """

        # ----------------------------------------------------
        # HTML
        # ----------------------------------------------------

        html = f"""
        <!DOCTYPE html>

        <html lang="pt-BR">

        <head>

            <meta charset="UTF-8">

            <meta name="viewport"
                  content="width=device-width, initial-scale=1.0">

            <title>IoT Gas - Dashboard</title>

            <style>

                body {{
                    font-family: Arial, sans-serif;
                    margin: 0;
                    padding: 20px;
                    background: #f4f4f4;
                }}

                h1 {{
                    text-align: center;
                }}

                .container {{
                    max-width: 1100px;
                    margin: auto;
                }}

                .cards {{
                    display: grid;
                    grid-template-columns:
                        repeat(auto-fit, minmax(220px, 1fr));
                    gap: 20px;
                    margin-bottom: 30px;
                }}

                .card {{
                    background: white;
                    padding: 20px;
                    border-radius: 10px;
                    box-shadow: 0 2px 8px rgba(0,0,0,0.1);
                    text-align: center;
                }}

                .valor {{
                    font-size: 28px;
                    font-weight: bold;
                    margin-top: 10px;
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
                }}

                th {{
                    background: #222;
                    color: white;
                }}

                .online {{
                    color: green;
                    font-weight: bold;
                }}

                @media(max-width: 700px) {{

                    table {{
                        font-size: 12px;
                    }}

                    th, td {{
                        padding: 8px 4px;
                    }}

                }}

            </style>

        </head>

        <body>

        <div class="container">

            <h1>IoT Gas - Monitoramento</h1>

            <div class="cards">

                <div class="card">

                    <div>Status da API</div>

                    <div class="valor online">
                        ONLINE
                    </div>

                </div>


                <div class="card">

                    <div>Registros</div>

                    <div class="valor">
                        {resumo['registros']}
                    </div>

                </div>


                <div class="card">

                    <div>Pulsos totais</div>

                    <div class="valor">
                        {resumo['pulsos_totais']}
                    </div>

                </div>


                <div class="card">

                    <div>Volume total</div>

                    <div class="valor">
                        {float(resumo['volume_total']):.3f} m³
                    </div>

                </div>

            </div>


            <div class="card">

                <h2>Últimas medições</h2>

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

        </div>

        </body>

        </html>
        """

        return html

    except Exception as erro:

        print("ERRO NO DASHBOARD:")
        print(erro)

        return f"""
        <h1>Erro ao carregar dashboard</h1>
        <p>{erro}</p>
        """, 500

    finally:

        if cursor:
            cursor.close()

        if conexao:
            conexao.close()
