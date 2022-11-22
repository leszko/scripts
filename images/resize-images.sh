#!/bin/bash

for FILE in `ls`; do
    echo "Resizing ${FILE}..."
    if [[ "${FILE}" == *"small"* ]]; then
        convert ${FILE} -resize 600 -density 72 -quality 75 ${FILE}    
    else
        convert ${FILE} -resize 800 -density 72 -quality 75 ${FILE}
    fi
done