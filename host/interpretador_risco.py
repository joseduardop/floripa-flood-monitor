"""
interpretador_risco.py - fusao de dados e classificacao de risco

assina o topico flood/cemaden/raw, cruza os dados de chuva do CEMADEN com a
previsao do Open-Meteo (precipitacao 6h + umidade do solo) e calcula um indice
de risco por estacao. o resultado classificado e publicado em
flood/risco/classificado e salvo em landing/ (de onde o dashboard le).

fica em escuta permanente:
    python interpretador_risco.py
"""
import os
import json
import time
from pathlib import Path

import requests
import paho.mqtt.client as mqtt
from dotenv import load_dotenv

load_dotenv()

BASE = Path(__file__).resolve().parent

MQTT_BROKER = os.getenv("MQTT_BROKER")
MQTT_PORT = int(os.getenv("MQTT_PORT"))
TOPICO_ENTRADA = os.getenv("MQTT_TOPIC_RAW")
TOPICO_SAIDA = os.getenv("MQTT_TOPIC_RISCO")

OPENMETEO_URL = "https://api.open-meteo.com/v1/forecast"


def salvar_json(payload, origem="interpretador_risco"):
    ts = (
        payload.get("ts_processamento")
        or payload.get("ts_coleta", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    )
    pasta = BASE / "landing" / origem
    pasta.mkdir(parents=True, exist_ok=True)
    arquivo = pasta / f"{ts.replace(':', '-')}.json"
    with open(arquivo, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"[landing] salvo em {arquivo}")


def buscar_openmeteo(lat, lon):
    # retorna precipitacao prevista (prox. 6h) e umidade do solo atual
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": "precipitation,soil_moisture_0_to_1cm",
        "forecast_days": 1,
        "timezone": "America/Sao_Paulo",
    }
    r = requests.get(OPENMETEO_URL, params=params, timeout=10)
    r.raise_for_status()
    data = r.json()

    horas = data["hourly"]["time"]
    precip = data["hourly"]["precipitation"]
    soil = data["hourly"]["soil_moisture_0_to_1cm"]

    # localiza a hora atual na serie e soma as proximas 6
    agora = time.strftime("%Y-%m-%dT%H:00", time.localtime())
    try:
        idx = horas.index(agora)
    except ValueError:
        idx = 0

    precip_6h = sum(p for p in precip[idx:idx + 6] if p is not None)
    solo_atual = soil[idx] if soil[idx] is not None else 0.0

    salvar_json(data, origem="interpretador_risco/raw-open_meteo")

    return precip_6h, solo_atual


def calcular_risco(estacao, precip_6h, solo):
    # pontuacao 0-100. o componente de chuva 24h (maior peso) e ancorado na escala
    # da Defesa Civil de Florianopolis (COBRADE 1.1.1.1.2 - inundacao gradual):
    # <10mm baixo, 10-30 moderado, 30-60 alto, 60+ critico -- mesma referencia
    # usada no prototipo inicial (propostsa_projeto_final/teste/floripapluvio.py).
    # os demais componentes (72h, previsao 6h, umidade do solo) foram calibrados
    # proporcionalmente a essa escala oficial, e nao com dados historicos formais.
    score = 0

    c24 = estacao.get("chuva_24h") or 0
    if c24 >= 60: score += 40
    elif c24 >= 30: score += 25
    elif c24 >= 10: score += 10

    c72 = estacao.get("chuva_72h") or 0
    if c72 >= 120: score += 20
    elif c72 >= 60: score += 10

    if precip_6h >= 30: score += 25
    elif precip_6h >= 15: score += 15
    elif precip_6h >= 5: score += 5

    # soil_moisture_0_to_1cm (Open-Meteo, m3/m3): solo tipico observado em
    # florianopolis ~0.25-0.30 em periodo seco; saturacao tipica ~0.45+
    if solo >= 0.45: score += 15
    elif solo >= 0.30: score += 7

    if score >= 70: classe = "CRITICO"
    elif score >= 45: classe = "ALTO"
    elif score >= 20: classe = "MEDIO"
    else: classe = "BAIXO"

    return score, classe


def processar(cliente, payload_raw):
    estacoes = payload_raw.get("estacoes", [])

    # usa coordenadas da primeira estacao valida pra consultar o open-meteo
    ref = next((e for e in estacoes if e.get("lat") and e.get("lon")), None)
    if ref is None:
        print("[aviso] nenhuma estacao com coordenadas, pulando")
        return

    # modo simulacao: se o payload trouxe valores de open-meteo (do simular.py),
    # usa eles no lugar da API ao vivo. permite forcar cenarios de risco na demo.
    sim = payload_raw.get("simulacao")
    if sim:
        precip_6h = sim.get("precip_prev_6h", 0.0)
        solo = sim.get("umidade_solo", 0.0)
        print(f"[sim] open-meteo forcado: precip 6h {precip_6h}mm | solo {solo}")
    else:
        try:
            precip_6h, solo = buscar_openmeteo(ref["lat"], ref["lon"])
            print(f"[open-meteo] precip. prev. 6h: {precip_6h:.1f}mm | solo: {solo:.2f}")
        except Exception as e:
            print(f"[aviso] open-meteo falhou: {e}. usando valores zero.")
            precip_6h, solo = 0.0, 0.0

    resultados = []
    for est in estacoes:
        score, classe = calcular_risco(est, precip_6h, solo)
        resultados.append({
            "codestacao": est["codestacao"],
            "nome": est["nome"],
            "lat": est["lat"],
            "lon": est["lon"],
            "timestamp": est["timestamp"],
            "chuva_1h": est.get("chuva_1h"),
            "chuva_24h": est.get("chuva_24h"),
            "chuva_72h": est.get("chuva_72h"),
            "precip_prev_6h": round(precip_6h, 2),
            "umidade_solo": round(solo, 3),
            "score_risco": score,
            "classificacao": classe,
        })

    payload_saida = {
        "ts_processamento": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "total_estacoes": len(resultados),
        "resultados": resultados,
    }

    salvar_json(payload_raw, origem="interpretador_risco/raw")
    salvar_json(payload_saida, origem="interpretador_risco/treated")

    msg = json.dumps(payload_saida, ensure_ascii=False)
    cliente.publish(TOPICO_SAIDA, msg, qos=1)
    print(f"[mqtt] publicado em '{TOPICO_SAIDA}' com {len(resultados)} estacoes")

    for cls in ["CRITICO", "ALTO", "MEDIO", "BAIXO"]:
        n = sum(1 for r in resultados if r["classificacao"] == cls)
        if n:
            print(f"  {cls}: {n} estacoes")


def on_connect(cliente, userdata, flags, rc, properties=None):
    if rc == 0:
        print(f"[mqtt] conectado. assinando '{TOPICO_ENTRADA}'...")
        cliente.subscribe(TOPICO_ENTRADA, qos=1)
    else:
        print(f"[mqtt] falha na conexao: rc={rc}")


def on_message(cliente, userdata, msg):
    print(f"\n[mqtt] mensagem recebida em '{msg.topic}'")
    try:
        payload = json.loads(msg.payload.decode("utf-8"))
        processar(cliente, payload)
    except json.JSONDecodeError as e:
        print(f"[erro] json invalido: {e}")


def main():
    cliente = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="interpretador-risco")
    cliente.on_connect = on_connect
    cliente.on_message = on_message

    cliente.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
    print("[info] interpretador iniciado. aguardando mensagens...\n")
    cliente.loop_forever()


if __name__ == "__main__":
    main()
