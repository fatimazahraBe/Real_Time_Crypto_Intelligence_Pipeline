import json
from confluent_kafka import Producer
import websocket

# 🔹 Config Kafka (Confluent Cloud)
conf = {
    'bootstrap.servers': 'pkc-921jm.us-east-2.aws.confluent.cloud:9092',
    'security.protocol': 'SASL_SSL',
    'sasl.mechanisms': 'PLAIN',
    'sasl.username': 'JWVBQ7RG25AVCHHY',
    'sasl.password': 'cflt9aP2o4QFY2CAugnhB/J/MMhEIDYtyGdj3Gu6dcFih68+sqYqyvBvzj8ABd4g'
}

producer = Producer(conf)
topic = "trades_topic"

SYMBOLS = ["btcusdt", "ethusdt", "bnbusdt", "solusdt", "adausdt"]
stream = "/".join([f"{s}@trade" for s in SYMBOLS])
socket = f"wss://stream.binance.com:9443/stream?streams={stream}"

def on_message(ws, message):
    msg = json.loads(message)
    data = msg["data"]
    payload = {
        "symbol": data["s"],
        "price": float(data["p"]),
        "quantity": float(data["q"]),
        "timestamp": data["T"]
    }
    # Envoi vers Kafka
    producer.produce(topic, json.dumps(payload).encode("utf-8"))
    producer.flush()
    print(f"Sent to Kafka: {payload}")

def on_open(ws):
    print("Connected and streaming prices...")

def on_error(ws, error):
    print("Error:", error)

def on_close(ws, close_status_code, close_msg):
    print("Connection closed")

ws = websocket.WebSocketApp(
    socket,
    on_open=on_open,
    on_message=on_message,
    on_error=on_error,
    on_close=on_close
)

ws.run_forever()