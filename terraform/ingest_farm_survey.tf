locals {
  account_id                      = data.aws_caller_identity.current.account_id
  tif_to_jpg_lambda_name          = "dr2-farm-survey-tif-to-jpg"
  source_jsons_bucket             = "dr2-farm-survey-jsons"
  jsons_to_validate_bucket_prefix = "jsons-to-validate"
  jsons_to_process_bucket_prefix  = "jsons-to-process"
  json_validation_lambda_name     = "dr2-farm-survey-validate-jsons"
  farm_survey_s3_queue_name       = "dr2-farm-survey-tif-to-jpg-s3-put-events"
  dest_bucket_files_prefix        = "tna-digital-files-to-process"
  dest_records_prefix             = "tna-records-to-process"
  azure_container                 = "farms"
  lambda_timeout                  = 60
  python_runtime                  = "python3.14"

  convert_to_jpg_lambda_file          = "lambda_function.py"
  validate_farm_survey_lambda_file    = "lambda_function_json_validation.py"
  validate_farm_survey_py_file        = "validate_farm_survey_jsons.py"
  preliminary_json_schema_validation  = "preliminary_json_schema_validation.json"
  json_schema_for_metadata_validation = "json_schema_for_metadata_jsons.json"
  tif_jpg_requirements_file           = "requirements-tif-to-jpg.txt"
  validation_requirements_file        = "requirements-validation.txt"
  db_file                             = "farm-survey.db"

  tif_to_jpg_lambda_name_repo = "${local.tif_to_jpg_lambda_name}-repo"
  container_login_cmd         = var.container_tool == "container" ? "${var.container_tool} registry" : var.container_tool
  container_push_and_tag_cmd  = var.container_tool == "container" ? "${var.container_tool} image" : var.container_tool

  root_account     = "arn:aws:iam::${sensitive(local.account_id)}:root"
  research_account = module.config.terraform_config["farm_survey_assume_role_arn"]
}

module "dr2_farm_survey_bucket" {
  source                   = "git::https://github.com/nationalarchives/da-terraform-modules//s3"
  bucket_name              = local.source_jsons_bucket
  bucket_versioning_status = "Disabled"

  # Will uncomment this when I have confirmation that it works

  # bucket_policy = templatefile("./templates/iam_policy/s3_cross_account_policy.json.tpl", {
  #   source_jsons_bucket_name = local.source_jsons_bucket
  #   root_account             = local.root_account
  #   research_account         = local.research_account
  # })
}

resource "aws_s3_object" "bucket_prefixes" {
  for_each = toset([local.jsons_to_validate_bucket_prefix, local.jsons_to_process_bucket_prefix])

  bucket = module.dr2_farm_survey_bucket.s3_bucket_id
  key    = "${each.value}/"
  source = "/dev/null" # Added because you can't create a prefix without a file
}

resource "aws_iam_outbound_web_identity_federation" "identity_federation_for_azure" {}


module "dr2_convert_tif_to_jpg_lambda" {
  source                         = "git::https://github.com/nationalarchives/da-terraform-modules//lambda"
  description                    = "A lambda function to retrieve .tif files, convert them to .jpg and upload them to bucket"
  function_name                  = local.tif_to_jpg_lambda_name
  handler                        = "lambda_function.lambda_handler"
  timeout_seconds                = local.lambda_timeout
  memory_size                    = 1536
  storage_size                   = 1536
  sqs_queue_mapping_batch_size   = 1
  sqs_report_batch_item_failures = true
  lambda_sqs_queue_mappings = [{
    sqs_queue_arn         = "arn:aws:sqs:eu-west-2:${local.account_id}:${local.farm_survey_s3_queue_name}"
    ignore_enabled_status = true
  }]
  policies = {
    "${local.tif_to_jpg_lambda_name}-policy" = templatefile("./templates/iam_policy/tif_to_jpg_lambda_policy.json.tpl", {
      account_id               = sensitive(local.account_id)
      lambda_name              = local.tif_to_jpg_lambda_name
      queue_name               = local.farm_survey_s3_queue_name
      source_jsons_bucket_name = local.source_jsons_bucket

      dest_account_id = var.dest_account_id
      dest_bucket     = var.dest_bucket_alias
      files_prefix    = local.dest_bucket_files_prefix
      records_prefix  = local.dest_records_prefix
    })
  }

  use_image = true
  image_url = "${module.tif_to_jpg_lambda_repo.repository_url}:latest"

  depends_on = [module.tif_to_jpg_lambda_repo]

  plaintext_env_vars = {
    AZURE_ACCOUNT_URL          = var.azure_account_url
    AZURE_CLIENT_ID            = var.azure_client_id
    AZURE_FS_CONTAINER         = local.azure_container
    AZURE_TENANT_ID            = var.azure_tenant_id
    DEST_BUCKET                = var.dest_bucket_alias
    DEST_BUCKET_FILES_PREFIX   = local.dest_bucket_files_prefix
    DEST_BUCKET_RECORDS_PREFIX = local.dest_records_prefix
  }

  tags = {
    Name = local.tif_to_jpg_lambda_name
  }
}

module "tif_to_jpg_lambda_repo" {
  source          = "git::https://github.com/nationalarchives/da-terraform-modules.git//ecr"
  repository_name = local.tif_to_jpg_lambda_name_repo
  common_tags     = {}
  repository_policy = templatefile("./templates/iam_policy/tif_to_jpg_ecr_policy.json.tpl", {
    account_id  = local.account_id
    lambda_name = local.tif_to_jpg_lambda_name
  })
  image_source_url = "https://github.com/nationalarchives/dr2-farm-survey"
}

resource "terraform_data" "docker_image" {
  # Trigger this resource's code whenever the source code files change
  triggers_replace = md5(
    jsonencode(
      {
        lambda            = filemd5("${path.module}/../${local.convert_to_jpg_lambda_file}")
        farm_survey_db    = filemd5("${path.module}/../db/${local.db_file}")
        dockerfile        = filemd5("${path.module}/../Dockerfile")
        validation_lambda = filemd5("${path.module}/../${local.validate_farm_survey_lambda_file}")
        validation_script = filemd5("${path.module}/../${local.validate_farm_survey_py_file}")
        json_schema       = filemd5("${path.module}/../${local.json_schema_for_metadata_validation}")
        requirements      = filemd5("${path.module}/../${local.tif_jpg_requirements_file}")
      }
    )
  )

  provisioner "local-exec" {
    command = <<EOF
      echo "${data.aws_ecr_authorization_token.token.password}" | ${local.container_login_cmd} login --username AWS --password-stdin ${replace(data.aws_ecr_authorization_token.token.proxy_endpoint, "https://", "")} &&
      ${var.container_tool} build ${var.container_tool == "podman" ? "--format docker " : ""} --platform linux/amd64 -t ${local.tif_to_jpg_lambda_name_repo} ../. &&
      ${local.container_push_and_tag_cmd} tag ${local.tif_to_jpg_lambda_name_repo}:latest ${module.tif_to_jpg_lambda_repo.repository_url}:latest &&
      ${local.container_push_and_tag_cmd} push ${module.tif_to_jpg_lambda_repo.repository_url}:latest
    EOF
  }
  depends_on = [module.tif_to_jpg_lambda_repo]
}

module "tif_to_jpg_queue" {
  source        = "git::https://github.com/nationalarchives/da-terraform-modules//sqs"
  delay_seconds = 90
  queue_name    = local.farm_survey_s3_queue_name
  sqs_policy = templatefile("./templates/sqs/sqs_access_policy.json.tpl", {
    account_id = local.account_id,
    queue_name = local.farm_survey_s3_queue_name
  })
  queue_cloudwatch_alarm_visible_messages_threshold = 60
  visibility_timeout                                = local.lambda_timeout * 6
  encryption_type                                   = "sse"
  create_dlq                                        = true
}

resource "aws_sqs_queue_policy" "s3_to_sqs_policy" {
  queue_url = module.tif_to_jpg_queue.sqs_queue_url

  policy = templatefile("./templates/iam_policy/trigger_sqs_from_s3_event.tpl", {
    queue_arn  = module.tif_to_jpg_queue.sqs_arn
    bucket_arn = module.dr2_farm_survey_bucket.s3_bucket_arn
  })
}

resource "aws_s3_bucket_notification" "bucket_notification" {
  bucket = module.dr2_farm_survey_bucket.s3_bucket_id

  queue {
    queue_arn     = module.tif_to_jpg_queue.sqs_arn
    events        = ["s3:ObjectCreated:*"]
    filter_prefix = "${local.jsons_to_process_bucket_prefix}/"
    filter_suffix = ".json"
  }

  depends_on = [aws_sqs_queue_policy.s3_to_sqs_policy]
}

resource "aws_lambda_event_source_mapping" "lambda_trigger" {
  event_source_arn = "arn:aws:sqs:eu-west-2:${local.account_id}:${local.farm_survey_s3_queue_name}"
  function_name    = module.dr2_convert_tif_to_jpg_lambda.lambda_arn
  batch_size       = 1
}

data "archive_file" "preliminary_json_validation_zip" {
  type        = "zip"
  output_path = "${path.module}/dist/preliminary_json_validation_payload.zip"

  source {
    content  = file("${path.module}/../${local.validate_farm_survey_lambda_file}")
    filename = local.validate_farm_survey_lambda_file
  }

  source {
    content  = file("${path.module}/../${local.validate_farm_survey_py_file}")
    filename = local.validate_farm_survey_py_file
  }

  source {
    content  = file("${path.module}/../${local.preliminary_json_schema_validation}")
    filename = local.preliminary_json_schema_validation
  }
}

resource "null_resource" "generate_python_dependencies" {
  triggers = {
    requirements_hash = filemd5("${path.module}/../${local.validation_requirements_file}")
  }

  provisioner "local-exec" {
    command = <<EOT
      rm -rf ${path.module}/dr2-farm-survey-validation_deps
      pip install --platform manylinux2014_x86_64 \
                  --target=${path.module}/dr2-farm-survey-validation_deps/python \
                  --python-version 3.14 \
                  --implementation cp \
                  --abi cp314 \
                  --only-binary=:all: \
                  --requirement ${path.module}/../${local.validation_requirements_file}
      cd ${path.module}/dr2-farm-survey-validation_deps &&
      zip -r ../dr2-farm-survey-validation_deps.zip python &&
      cd ${path.module} &&
      rm -rf ./dr2-farm-survey-validation_deps
    EOT
  }
}

resource "aws_lambda_layer_version" "python_deps" {
  filename = "${path.module}/dr2-farm-survey-validation_deps.zip"

  layer_name               = "farm_survey_validation_deps"
  compatible_runtimes      = ["python3.14"]
  compatible_architectures = ["x86_64"]
  depends_on               = [null_resource.generate_python_dependencies]
}

module "dr2_preliminary_json_validation_lambda" {
  filename = data.archive_file.preliminary_json_validation_zip.output_path

  source          = "git::https://github.com/nationalarchives/da-terraform-modules//lambda"
  description     = "A lambda function to validate the JSONs before processing"
  function_name   = local.json_validation_lambda_name
  handler         = "lambda_function_json_validation.lambda_handler"
  timeout_seconds = local.lambda_timeout
  runtime         = local.python_runtime
  memory_size     = 256
  layers          = [aws_lambda_layer_version.python_deps.arn]
  policies = {
    "${local.json_validation_lambda_name}-policy" = templatefile("./templates/iam_policy/json_preliminary_validation_lambda_policy.json.tpl", {
      source_jsons_bucket_name = local.source_jsons_bucket
      account_id               = sensitive(local.account_id)
    })
  }

  plaintext_env_vars = {
    SOURCE_JSONS_BUCKET        = local.source_jsons_bucket
    SOURCE_JSONS_BUCKET_PREFIX = local.jsons_to_validate_bucket_prefix
  }
  tags = {
    Name = local.json_validation_lambda_name
  }
}

resource "aws_lambda_permission" "allow_cross_account_invoke" {
  statement_id  = "AllowExecutionFromCrossAccount"
  action        = "lambda:InvokeFunction"
  function_name = local.json_validation_lambda_name
  principal     = local.research_account
}
