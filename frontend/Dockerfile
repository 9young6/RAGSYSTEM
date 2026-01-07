FROM busybox:latest

WORKDIR /site
COPY ./ /site

EXPOSE 3000
CMD ["httpd", "-f", "-p", "3000", "-h", "/site"]
