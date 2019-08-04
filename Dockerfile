FROM python:2.7-slim
MAINTAINER Sylvain Calador <sylvain.calador@akretion.com>

ENV WORKSPACE /workspace
RUN mkdir -p $WORKSPACE
COPY . $WORKSPACE

COPY requirements.txt $WORKSPACE/requirements.txt
RUN pip install -r $WORKSPACE/requirements.txt
RUN pip install --editable $WORKSPACE

RUN useradd --shell /bin/bash -u 999 -o -c "" -m dbservice
COPY install /install
RUN apt-get update \
    && apt-get install -y --no-install-recommends gpg curl dirmngr \
    && rm -rf /var/lib/apt/lists/*

RUN /install/gosu.sh

COPY docker-cidbservice.sh /usr/local/bin/
COPY docker-celery.sh /usr/local/bin/
CMD ["bash"]
