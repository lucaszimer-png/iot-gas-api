from flask import Flask, request, jsonify

app = Flask(__name__)


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

    print(f"Equipamento: {equipamento}")
    print(f"Sequencia: {sequencia}")

    return jsonify({
        "ack": True,
        "id": equipamento,
        "seq": sequencia,
        "status": "OK"
    }), 200


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=10000
    )