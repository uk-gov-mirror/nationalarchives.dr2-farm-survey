FROM alpine:3.24.1 AS layer-extractor
FROM public.ecr.aws/lambda/python:3.14

COPY requirements-tif-to-jpg.txt ${LAMBDA_TASK_ROOT}
RUN pip install -r requirements-tif-to-jpg.txt

USER root

RUN dnf install -y \
        libtiff-4.7.2 \
        libtiff-devel-4.7.2 \
        libjpeg-turbo-3.1.4 \
        libjpeg-turbo-devel-3.1.4 \
        ImageMagick-7.1.2-29 \
        ImageMagick-devel-7.1.2-29 && \
    dnf clean all

USER 1000

ENV RUNNING_IN_DOCKER=True

COPY db/farm-survey.db ${LAMBDA_TASK_ROOT}
COPY lambda_function.py ${LAMBDA_TASK_ROOT}
COPY validate_farm_survey_jsons.py ${LAMBDA_TASK_ROOT}
COPY json_schema_for_metadata_jsons.json ${LAMBDA_TASK_ROOT}


CMD [ "lambda_function.lambda_handler" ]