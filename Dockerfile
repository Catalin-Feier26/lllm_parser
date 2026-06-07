FROM perl:5.30

RUN apt-get update && apt-get install -y \
    poppler-utils \
    build-essential \
    python3 \
    python3-pip \
    python3-venv \
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
    App::Prove \
    Digest::SHA \
    File::Basename

WORKDIR /app

COPY python_inference/requirements.txt /app/python_inference/requirements.txt
RUN pip3 install --no-cache-dir -r /app/python_inference/requirements.txt

CMD ["/bin/bash"]