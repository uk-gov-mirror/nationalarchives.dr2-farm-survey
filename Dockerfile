FROM alpine:3.24.1 AS layer-extractor
FROM public.ecr.aws/lambda/python:3.14

COPY requirements-tif-to-jpg.txt ${LAMBDA_TASK_ROOT}
RUN pip install -r requirements-tif-to-jpg.txt

USER root

# RPM packages available to AL2023 https://docs.aws.amazon.com/linux/al2023/release-notes/all-packages-AL2023.12.html
RUN dnf install -y \
        libtiff-4.4.0-4.amzn2023.0.27 \
        libtiff-devel-4.4.0-4.amzn2023.0.27 \
        libjpeg-turbo-2.1.4-2.amzn2023.0.5 \
        libjpeg-turbo-devel-2.1.4-2.amzn2023.0.5 \
        ImageMagick-6.9.13.50-1.amzn2023.0.2 \
        ImageMagick-devel-6.9.13.50-1.amzn2023.0.2 && \
    dnf clean all

USER 1000

ENV RUNNING_IN_DOCKER=True

COPY db/farm-survey.db ${LAMBDA_TASK_ROOT}
COPY lambda_function.py ${LAMBDA_TASK_ROOT}
COPY validate_farm_survey_jsons.py ${LAMBDA_TASK_ROOT}
COPY json_schema_for_metadata_jsons.json ${LAMBDA_TASK_ROOT}


CMD [ "lambda_function.lambda_handler" ]