# MMCA web app container.
#   docker build -t mmca .
#   docker run -p 8501:8501 mmca
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY mmca/ mmca/
COPY app/ app/
COPY .streamlit/ .streamlit/
COPY sample_data/ sample_data/

RUN useradd --create-home --uid 10001 mmca
USER mmca

EXPOSE 8501
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8501/_stcore/health')"

CMD ["streamlit", "run", "app/streamlit_app.py", \
     "--server.address=0.0.0.0", "--server.port=8501", "--server.headless=true"]
