FROM jrottenberg/ffmpeg:6-alpine

COPY publish.sh /publish.sh
RUN chmod +x /publish.sh

ENTRYPOINT ["/publish.sh"]
