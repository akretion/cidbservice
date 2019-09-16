FROM python:3.7-slim
MAINTAINER Sylvain Calador <sylvain.calador@akretion.com>

RUN apt-get update \
    && apt-get install -y --no-install-recommends gpg curl dirmngr \
    && rm -rf /var/lib/apt/lists/*

ENV WORKSPACE /cidbservice
RUN mkdir -p $WORKSPACE
COPY . $WORKSPACE
WORKDIR $WORKSPACE

RUN pip install -r requirements.txt
RUN pip install --editable .

COPY bin/dbservice /usr/local/bin/
COPY bin/dbservice-job /usr/local/bin/
COPY bin/dev-entrypoint /usr/local/bin/
COPY config/default.conf /etc/dbservice/default.conf
RUN chmod 444 /etc/dbservice/default.conf
CMD ["bash"]
