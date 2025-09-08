FROM nvcr.io/nvidia/pytorch:23.07-py3

ENV DEBIAN_FRONTEND noninteractive
ENV TZ "Asia/Tokyo"

RUN echo "PS1='\[\033[01;32m\]utl\[\033[00m\]:\[\033[38;5;208m\]\W\[\033[00m\]$ '" >> /root/.bashrc && \
    echo "syntax enable\nhighlight Comment ctermfg=green" >> /root/.vimrc

RUN echo "alias python=python3" >> /root/.bashrc && \
    echo "alias pip=pip3" >> /root/.bashrc

CMD ["/bin/bash"]
