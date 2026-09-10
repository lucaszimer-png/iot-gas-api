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

criar_tabela()


if __name__ == "__main__":

    porta = int(os.environ.get("PORT", 5000))

    app.run(
        host="0.0.0.0",
        port=porta
    )
