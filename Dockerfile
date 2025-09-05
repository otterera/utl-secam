FROM nvcr.io/nvidia/pytorch:23.07-py3
# FROM huggingface/transformers-pytorch-gpu:latest
# FROM mcr.microsoft.com/devcontainers/python:0-3.10
# FROM python:3.10-slim

ENV DEBIAN_FRONTEND noninteractive
ENV TZ "Asia/Tokyo"
# RUN apt-get update && \
    # apt-get upgrade -y && \
    # apt-get install -y vim && \
    # apt-get clean

# COPY requirements.txt ./
# RUN pip install --upgrade pip && \
    # pip install auto-gptq --no-build-isolation && \
    # pip install transformers autoawq

# RUN pip install -r requirements.txt
# RUN pip install -r requirements_minimum.txt
# RUN pip install transformers>=4.32.0 optimum>=1.12.0
# Use cu124 if on CUDA 12.4
# RUN pip install auto-gptq --extra-index-url https://huggingface.github.io/autogptq-index/whl/cu124/

# PS1プロンプトとvim設定を変更
RUN echo "PS1='\[\033[01;32m\]utl\[\033[00m\]:\[\033[38;5;208m\]\W\[\033[00m\]$ '" >> /root/.bashrc && \
    echo "syntax enable\nhighlight Comment ctermfg=green" >> /root/.vimrc

# エイリアスの設定
RUN echo "alias python=python3" >> /root/.bashrc && \
    echo "alias pip=pip3" >> /root/.bashrc

CMD ["/bin/bash"]
