FROM python:3.6

RUN mkdir /letsencrypt
WORKDIR /letsencrypt
RUN wget -q https://github.com/xenolf/lego/releases/download/v1.0.1/lego_v1.0.1_linux_amd64.tar.gz && tar xvf lego_v1.0.1_linux_amd64.tar.gz && rm lego_v1.0.1_linux_amd64.tar.gz
COPY requirements.txt /letsencrypt/
RUN pip install -r requirements.txt
COPY app/auth.py app/cert.py /letsencrypt/
CMD ["python", "cert.py", "service"]
