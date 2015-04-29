FROM jpetazzo/dind

## install requirements
#RUN apt-get update
#RUN apt-get install -y wget curl git make \
#                       python-pip \
#                       python-numpy python-scipy python-pandas python-flask \
#                       python-numexpr python-parse python-psutil \
#                       python-requests python-simplejson python-tables \
#                       python-matplotlib python-nose python-yaml \
#                       python-sklearn \
#                       cython
                       # Add python-docker when switching to utopic / vivid

#RUN apt-get install git

# Inject MLTSP docker images
RUN mkdir -p /tmp/images
#COPY *.gz /tmp/images/
COPY build_model.gz /tmp/images/
COPY import_images.sh /tmp/images/

#RUN /usr/local/bin/wrapdocker
#RUN bash -c 'for img in /tmp/images/*; do echo Importing $image ; gzip -dc $img | docker import - mltsp/`basename $img .gz`; done'
#RUN rm /tmp/*
#
#RUN start-stop-daemon --stop --pidfile "/var/run/docker.pid"  

# See also https://intercityup.com/blog/downsizing-docker-containers.html
#          http://paislee.io/how-to-build-and-deploy-docker-images-with-drone/
