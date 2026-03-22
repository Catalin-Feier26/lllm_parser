FROM perl:5.30

RUN apt-get update && apt-get install -y \
    poppler-utils \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN cpanm --notest \
    Text::CSV_XS \
    Text::CSV \
    Path::Tiny \
    XML::Simple \
    Excel::ValueReader::XLSX \
    Spreadsheet::Read \
    Module::Runtime \
    MongoDB \
    Test::More \
    App::Prove

WORKDIR /app
CMD ["/bin/bash"]