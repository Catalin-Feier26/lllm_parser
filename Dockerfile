# Use official Perl base image
FROM perl:5.30

RUN apt-get update && apt-get install -y \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY . /app

RUN cpanm --notest \
    Text::CSV_XS \
    Text::CSV \
    Path::Tiny \
    Module::Runtime

RUN mkdir -p data/incoming data/archive

CMD ["/bin/bash"]
