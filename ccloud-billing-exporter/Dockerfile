FROM python:3.10.14

RUN apt-get update && apt-get -y install cron vim

WORKDIR /app

COPY crontab /etc/cron.d/crontab
COPY ccloud-billing-export.py /app/ccloud-billing-export.py

RUN chmod 0644 /etc/cron.d/crontab
RUN /usr/bin/crontab /etc/cron.d/crontab

# run crond as main process of container
CMD ["cron", "-f"]