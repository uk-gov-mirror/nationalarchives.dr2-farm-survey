module "config" {
  source  = "../../da-terraform-configurations"
  project = "dr2"
}

terraform {
  backend "s3" {
    bucket       = "dri-fs-terraform-state-store"
    key          = "farm-survey-terraform.state"
    region       = "eu-west-2"
    encrypt      = true
    use_lockfile = true
  }
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.57.1"
    }
  }
}
provider "aws" {
  region = "eu-west-2"
}
