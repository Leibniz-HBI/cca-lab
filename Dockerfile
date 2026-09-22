FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY requirements.lock ./
COPY cca_lab ./cca_lab
RUN pip install --no-cache-dir -r requirements.lock && pip install --no-cache-dir --no-deps . && useradd --uid 10001 --create-home cca_lab && mkdir /data && chown cca_lab:cca_lab /data
ENV CCA_LAB_DATA=/data PYTHONUNBUFFERED=1
USER cca_lab
EXPOSE 8080
CMD ["python", "-m", "uvicorn", "cca_lab.api:app", "--host", "0.0.0.0", "--port", "8080"]
