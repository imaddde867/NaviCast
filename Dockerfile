FROM python:3.11-slim
WORKDIR /app
COPY requirements.lock .
RUN pip install --no-cache-dir -r requirements.lock
COPY api_server.py config.py demo_data.py mqtt_client.py prediction_service.py mid_to_country.csv ./
COPY static ./static
RUN useradd --create-home navicast && mkdir logs && chown navicast:navicast logs
USER navicast
EXPOSE 8000
CMD ["uvicorn", "api_server:app", "--host", "0.0.0.0", "--port", "8000"]
