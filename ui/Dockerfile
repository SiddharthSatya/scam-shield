FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

# The build context is ui/, so the package lands at /app/ui.
COPY . ./ui

RUN useradd --create-home --uid 10001 app
USER app

CMD ["sh", "-c", "exec streamlit run ui/app.py --server.port ${PORT:-8080} --server.address 0.0.0.0 --server.headless true --browser.gatherUsageStats false"]
