variable "aws_region" {
  type    = string
  default = "ca-central-1"
}

variable "db_password" {
  type      = string
  sensitive = true

  validation {
    condition     = length(var.db_password) >= 16
    error_message = "DB password must be at least 16 characters."
  }
}

variable "redis_password" {
  type      = string
  sensitive = true
  default   = ""
}

variable "jwt_secret" {
  type      = string
  sensitive = true
}

variable "db_instance_class" {
  type    = string
  default = "db.r6g.xlarge"
}

variable "redis_node_type" {
  type    = string
  default = "cache.r6g.large"
}

variable "redis_num_nodes" {
  type    = number
  default = 3
}

variable "eks_node_instance_types" {
  type    = list(string)
  default = ["m6i.xlarge"]
}

variable "eks_desired_size" {
  type    = number
  default = 3
}

variable "eks_min_size" {
  type    = number
  default = 2
}

variable "eks_max_size" {
  type    = number
  default = 10
}

variable "domain_name" {
  type    = string
  default = ""
}

variable "certificate_arn" {
  type    = string
  default = ""
}
