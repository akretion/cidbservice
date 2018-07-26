FROM python:2.7-slim
MAINTAINER Sylvain Calador <sylvain.calador@akretion.com>

ENV WORKSPACE /workspace
RUN mkdir -p $WORKSPACE
COPY . $WORKSPACE

COPY requirements.txt $WORKSPACE/requirements.txt
RUN pip install -r $WORKSPACE/requirements.txt
RUN pip install --editable $WORKSPACE

COPY docker-cidbservice.sh /usr/local/bin/
COPY docker-celery.sh /usr/local/bin/
CMD ["bash"]
