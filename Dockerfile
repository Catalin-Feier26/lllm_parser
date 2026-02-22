FROM perl:5.30

RUN apt-get update && apt-get install -y \
    poppler-utils \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

RUN cpanm --notest \
    Text::CSV_XS \
    Text::CSV \
    Path::Tiny \
    XML::Simple \
    Excel::ValueReader::XLSX \
    Spreadsheet::Read \
    Module::Runtime \
    DBI \
    DBD::Pg

WORKDIR /app
CMD ["/bin/bash"]