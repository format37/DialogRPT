FROM continuumio/miniconda3

WORKDIR /app

COPY environment.yml .
RUN conda env create -f environment.yml

SHELL ["conda", "run", "-n", "dialogrpt", "/bin/bash", "-c"]

COPY requirements.txt .
RUN python -m pip install -r requirements.txt
COPY DialogRPT/ .
RUN apt-get update; apt-get -y install redis-server
SHELL ["conda", "run", "-n", "dialogrpt", "/bin/bash", "-c"]
EXPOSE 6379
ENTRYPOINT ["conda", "run", "-n", "dialogrpt", "python", "src/server.py"]
#RUN -p 6379:6379 /bin/bash -c "source activate dialogrpt;python src/server.py"
