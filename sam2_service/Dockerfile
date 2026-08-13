ARG BASE_IMAGE=pytorch/pytorch:2.5.1-cuda12.1-cudnn9-runtime
FROM ${BASE_IMAGE}

ARG SAM2_COMMIT=2b90b9f5ceec907a1c18123530e92e794ad901a4
ENV PYTHONUNBUFFERED=1 \
    SAM2_BUILD_CUDA=0

RUN apt-get update && apt-get install -y --no-install-recommends git curl ca-certificates \
    && git clone https://github.com/facebookresearch/sam2.git /opt/sam2 \
    && git -C /opt/sam2 checkout --detach "${SAM2_COMMIT}" \
    && python -m pip install --no-cache-dir --no-build-isolation -e /opt/sam2 \
    && apt-get clean

COPY sam2_service/requirements.txt /opt/parcel-sam2/requirements.txt
RUN python -m pip install --no-cache-dir -r /opt/parcel-sam2/requirements.txt
COPY sam2_service/app.py /opt/parcel-sam2/app.py
COPY sam2_service/docker-entrypoint.sh /opt/parcel-sam2/docker-entrypoint.sh

EXPOSE 5001
ENTRYPOINT ["/opt/parcel-sam2/docker-entrypoint.sh"]
