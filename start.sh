#!/usr/bin/env bash

# 1. Uruchomienie logera danych w tle
python main.py &

# 2. Uruchomienie Streamlita na porcie 8501 (przechodzi na pierwszy plan)
exec streamlit run dashboard.py --server.port=8501 --server.address=0.0.0.0 --server.headless=true
