# Mandate — the sovereign appliance.
#
# Built to run with nothing: no API key, no egress, no GPU. Everything
# the legally-consequential path needs is in this image.
FROM python:3.11-slim

# Tesseract WITH the language packs. Reading Portuguese with the
# English model silently strips diacritics and costs real accuracy —
# core/perception.py refuses to do it, so the packs are not optional.
RUN apt-get update && apt-get install -y --no-install-recommends \
      tesseract-ocr tesseract-ocr-por tesseract-ocr-spa \
      tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dependencies first: this layer changes rarely, so a code edit does
# not re-resolve the world.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY core/ ./core/
COPY scripts/ ./scripts/
COPY tests/ ./tests/
COPY app.py scan_tab.py ./
COPY app_data/ ./app_data/

# The appliance declares itself. resilience.py probes tier0 by the
# presence of a key; in the sovereign profile there is none, so the
# ladder starts at the local model without anyone configuring it.
ENV MANDATE_PROFILE=sovereign \
    OLLAMA_HOST=http://ollama:11434 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Health is the deterministic core, not the UI: if the engine cannot
# compute a deadline, the container is not healthy, whatever Streamlit
# thinks.
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
  CMD python -c "import sys; sys.path.insert(0,'core'); \
from datetime import date; from engine import compute_deadline; \
from pack_pt import PT; \
assert compute_deadline(PT,'cpc_processual',date(2026,3,23),10).due_date \
== date(2026,4,13)" || exit 1

EXPOSE 8501
CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0", \
     "--server.port=8501", "--server.headless=true"]
