# news_producer.py

import requests
import json
import time
from datetime import datetime
from confluent_kafka import Producer

# ==============================
# CONFIG
# ==============================

API_KEY = "1618da35dcd04c1e8a1d18f4da3970c7"

KAFKA_CONFIG = {
    'bootstrap.servers': 'pkc-921jm.us-east-2.aws.confluent.cloud:9092',
    'security.protocol': 'SASL_SSL',
    'sasl.mechanisms': 'PLAIN',
    'sasl.username': 'JWVBQ7RG25AVCHHY',
    'sasl.password': 'cflt9aP2o4QFY2CAugnhB/J/MMhEIDYtyGdj3Gu6dcFih68+sqYqyvBvzj8ABd4g'
}

TOPIC = "news_topic"

producer = Producer(KAFKA_CONFIG)

# Cache pour éviter les doublons
sent_titles = set()

# ==============================
# DELIVERY REPORT
# ==============================

def delivery_report(err, msg):
    if err:
        print(f"Delivery failed: {err}")
    else:
        print(f"Message delivered to {msg.topic()}")

# ==============================
# FETCH NEWS
# ==============================

def fetch_news():
    url = "https://newsapi.org/v2/everything"

    params = {
        "q": '(bitcoin OR ethereum) AND (price OR trading OR market OR volatility)',
        "language": "en",
        "sortBy": "publishedAt",
        "pageSize": 10,
        "apiKey": API_KEY
    }

    response = requests.get(url, params=params)

    if response.status_code != 200:
        print("HTTP Error:", response.status_code)
        print(response.text)
        return []

    data = response.json()

    if data["status"] != "ok":
        print("API Error:", data)
        return []

    return data["articles"]

# ==============================
# SEND TO KAFKA
# ==============================

def send_to_kafka():
    articles = fetch_news()

    for article in articles:

        title = article["title"]

        # 🔥 Eviter les doublons
        if title in sent_titles:
            continue

        sent_titles.add(title)

        message = {
            "event_time": article["publishedAt"],
            "symbol": "BTCUSDT",
            "title": title,
            "source": article["source"]["name"],
            "description": article["description"],
            "ingest_time": datetime.utcnow().isoformat()
        }

        producer.produce(
            TOPIC,
            key="BTCUSDT",
            value=json.dumps(message),
            callback=delivery_report
        )

    producer.flush()

# ==============================
# MAIN LOOP (simulation temps réel)
# ==============================

if __name__ == "__main__":
    while True:
        send_to_kafka()
        time.sleep(60)  # appelle NewsAPI chaque 60 secondes