#!/bin/bash

if [[ -f build_drone_image.sh ]]; then
    cd ..
fi

repo="mltsp"
images="build_model extract_custom_feats featurize predict"

echo '**********************************************'
echo Downloading base images
echo '**********************************************'

for image in $images; do
    docker pull $repo/$image
done

echo '**********************************************'
echo Exporting base images
echo '**********************************************'
mkdir -p /tmp/$repo

for image in $images; do 
    out=/tmp/$repo/$image.gz
    echo Exporting $repo/$image to ${out}...

    ID=`docker run -d $repo/$image /bin/bash`
    (docker export $ID | gzip -c > $out)
done

cd dockerfiles/drone
docker build -t drone .
