FROM python:3.12 AS builder
RUN pip3 install poetry
WORKDIR /tmp
COPY . /tmp
RUN poetry build

FROM python:3.12
WORKDIR /conf
COPY --from=builder /tmp/dist/*.whl .
RUN pip install *.whl && rm -f rm *.whl
ENTRYPOINT redovisa
