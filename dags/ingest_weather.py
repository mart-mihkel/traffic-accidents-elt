import os
import datetime
import pandas as pd

from pymongo import MongoClient

from airflow.models.dag import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator

DB = "dataeng_project"
COLLECTION = "weather"
MONGO_CONNECTION_STRING = "mongodb://admin:admin@mongo:27017"

COL_MAP = {
    "Aasta": "year",
    "Kuu": "month",
    "Päev": "day",
    "Kell (UTC)": "hour",
    "Õhutemperatuur °C": "air_temperature",
    "Tunni miinimum õhutemperatuur °C": "hourly_min_air_temperature",
    "Tunni maksimum õhutemperatuur °C": "hourly_max_air_temperature",
    "10 minuti keskmine tuule kiirus m/s": "10_min_average_wind_speed",
    "Tunni maksimum tuule kiirus m/s": "hourly_maximum_wind_speed",
    "Tunni sademete summa mm": "hourly_precipitation_total",
    "Õhurõhk jaama kõrgusel hPa": "air_pressure_at_station_height",
    "Suhteline õhuniiskus %": "relative_humidity",
    "Station": "station"
}


def wrangle():
    xlsxs = filter(
        lambda x: x.endswith("xlsx"), 
        os.listdir("/tmp/historical_weather")
    )

    for f in xlsxs:
        print("Wrangling: ", f)
        df = pd.read_excel(f"/tmp/historical_weather/{f}", header=2)
        df = df.rename(columns=COL_MAP)

        stem = f.split(".")[0]
        df["station"] = stem

        if(stem == "Haademeeste"):
            df["hour"] = df["Unnamed: 3"].apply(lambda x: x.hour)
            df["year"] = df["Unnamed: 0"]
            df["month"] = df["Unnamed: 1"]
            df["day"] = df["Unnamed: 2"]
        else:
            df["hour"] = df["hour"].apply(lambda x: x.hour)

        df = df[df.columns.intersection(COL_MAP.values())]

        df.to_csv(f"/tmp/historical_weather/{stem}.csv", index=False)


def load():
    client = MongoClient(MONGO_CONNECTION_STRING, timeoutMS=40000)
    col = client[DB][COLLECTION]

    csvs = filter(
        lambda x: x.endswith("csv"),
        os.listdir("/tmp/historical_weather")
    )

    for csv in csvs:
        print("Loading: ", csv)
        items = pd.read_csv(f"/tmp/historical_weather/{csv}").to_dict(orient="records")
        col.insert_many(items)


with DAG(
    "ingest_weather", 
    start_date=datetime.datetime(2024, 1, 1),
    schedule="@yearly",
    catchup=False,
) as dag:
    extract = BashOperator(
        task_id="extract_historical_weather",
        bash_command="scripts/download_weather.bash",
    )

    wrangle_task = PythonOperator(
        task_id="preprocess_historical_weather",
        python_callable=wrangle,
    )

    load_lake = PythonOperator(
        task_id="load_historical_weather",
        python_callable=load,
    )

    cleanup = BashOperator(
        task_id="historical_weather_cleanup",
        bash_command="rm -rf /tmp/historical_weather",
    )

    _ = extract >> wrangle_task >> load_lake >> cleanup

