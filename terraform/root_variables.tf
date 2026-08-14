variable "azure_account_url" {
  type        = string
  description = "URL where Azure container is held"
  sensitive   = true
}

variable "azure_client_id" {
  type      = string
  sensitive = true
}

variable "azure_tenant_id" {
  type      = string
  sensitive = true
}

variable "dest_account_id" {
  type        = string
  description = "Account ID of the destination bucket"
  sensitive   = true
}

variable "dest_bucket_alias" {
  type        = string
  description = "Alias of destination bucket"
  sensitive   = true
}

variable "container_tool" {
  type    = string
  default = "docker"
}