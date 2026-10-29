FROM jsbroks/coco-annotator:python-env AS base
WORKDIR /workspace
COPY backend/ /workspace/
COPY .git /workspace/.git
RUN python set_path.py
FROM base AS production
ENV FLASK_ENV=production
ENV DEBUG=false
EXPOSE 8000
CMD ["gunicorn", "-c", "webserver/gunicorn_config.py", "--bind", "0.0.0.0:8000", "--timeout", "180", "webserver:app", "--no-sendfile"]

FROM base AS workers
CMD ["celery", "-A", "workers", "worker", "-l", "info"]

FROM base AS development
ENV FLASK_ENV=development
ENV DEBUG=true
EXPOSE 5000
CMD gunicorn -c webserver/gunicorn_config.py webserver:app --no-sendfile
