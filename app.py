from flask import Flask, request, jsonify
import os
import psycopg2

app = Flask(__name__)


def conectar_banco():
    return psycopg2.connect(os.environ["DATABASE_URL"])


def criar_tabela():
    conn = conectar_banco()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS medicoes (
            id SERIAL PRIMARY KEY,
            equipamento VARCHAR(100) NOT NULL,
            sequencia INTEGER NOT NULL,
            timestamp_esp32 BIGINT NOT NULL,
            pulsos INTEGER NOT NULL,
            volume NUMERIC(12,6) NOT NULL,
            recebido_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            CONSTRAINT unique_medicao
            UNIQUE (equipamento, sequencia)
        );
    """)

    conn.commit()
    cur.close()
    conn.close()


@app.route("/")
def home():
    return "API Medidor de Gas - OK"


@app.route("/api/v1/medicao", methods=["POST"])
def receber_medicao():

    dados = request.get_json()

    print("\n==============================")
    print("NOVA MEDICAO RECEBIDA")
    print("==============================")
    print(dados)

    if not dados:
        return jsonify({
            "ack": False,
            "status": "JSON_INVALIDO"
        }), 400

    equipamento = dados.get("id")
    sequencia = dados.get("seq")
    timestamp = dados.get("timestamp")
    pulsos = dados.get("pulse")
    volume = dados.get("volume")

    if None in [equipamento, sequencia, timestamp, pulsos, volume]:
        return jsonify({
            "ack": False,
            "status": "DADOS_INCOMPLETOS"
        }), 400

    conn = None

    try:

        conn = conectar_banco()
        cur = conn.cursor()

        # Verifica se a medição já existe
        cur.execute("""
            SELECT id
            FROM medicoes
            WHERE equipamento = %s
              AND sequencia = %s
        """, (equipamento, sequencia))

        existente = cur.fetchone()

        if existente:

            print("Medicao ja existe no banco.")
            print(f"ID banco: {existente[0]}")

            cur.close()
            conn.close()

            return jsonify({
                "ack": True,
                "id": equipamento,
                "seq": sequencia,
                "status": "JA_EXISTE"
            }), 200

        # Insere nova medição
        cur.execute("""
            INSERT INTO medicoes (
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

        id_banco = cur.fetchone()[0]

        conn.commit()

        print("MEDICAO GRAVADA NO BANCO")
        print(f"ID banco: {id_banco}")
        print(f"Equipamento: {equipamento}")
        print(f"Sequencia: {sequencia}")

        cur.close()
        conn.close()

        # ACK somente depois do commit
        return jsonify({
            "ack": True,
            "id": equipamento,
            "seq": sequencia,
            "status": "GRAVADO",
            "database_id": id_banco
        }), 200

    except Exception as erro:

        print("ERRO AO GRAVAR NO BANCO:")
        print(erro)

        if conn:
            conn.rollback()
            conn.close()

        return jsonify({
            "ack": False,
            "status": "ERRO_BANCO"
        }), 500


# Cria a tabela quando a aplicação inicia
try:
    criar_tabela()
    print("Tabela medicoes verificada/criada com sucesso.")
except Exception as erro:
    print("ERRO AO CRIAR TABELA:")
    print(erro)


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=10000
    )
