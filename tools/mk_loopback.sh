#!/bin/bash

for i in {0..10}
do
    mknod -m0660 /dev/loop$i b 7 $i
done
