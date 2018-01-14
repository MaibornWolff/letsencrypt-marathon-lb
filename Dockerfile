FROM python:3.6

RUN mkdir /letsencrypt
WORKDIR /letsencrypt
RUN wget -q https://github.com/xenolf/lego/releases/download/v0.4.1/lego_linux_amd64.tar.xz && tar xvf lego_linux_amd64.tar.xz && mv lego_linux_amd64 lego
COPY requirements.txt /letsencrypt/
RUN pip install -r requirements.txt
COPY app/auth.py app/cert.py /letsencrypt/
CMD ["python", "cert.py", "service"]
