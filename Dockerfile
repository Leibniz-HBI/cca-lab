FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY requirements.lock ./
COPY textlab ./textlab
RUN pip install --no-cache-dir -r requirements.lock && pip install --no-cache-dir --no-deps . && useradd --uid 10001 --create-home textlab && mkdir /data && chown textlab:textlab /data
ENV TEXTLAB_DATA=/data PYTHONUNBUFFERED=1
USER textlab
EXPOSE 8080
CMD ["python", "-m", "uvicorn", "textlab.api:app", "--host", "0.0.0.0", "--port", "8080"]
