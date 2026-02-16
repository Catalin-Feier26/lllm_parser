# Use official Perl base image
FROM perl:5.30

RUN apt-get update && apt-get install -y \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

# Install Perl dependencies
RUN cpanm --notest \
    Text::CSV_XS \
    Text::CSV \
    Path::Tiny \
    XML::Simple \
    Excel::ValueReader::XLSX \
    Spreadsheet::Read \
    Module::Runtime

WORKDIR /app

CMD ["/bin/bash"]
