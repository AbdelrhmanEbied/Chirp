locals {
  project     = "chirp"
  environment = "prod"

  common_tags = {
    Project     = local.project
    Environment = local.environment
    ManagedBy   = "terraform"
  }

  cluster_name = "${local.project}-${local.environment}"

  databases = [
    "chirp_auth",
    "chirp_user",
    "chirp_post",
    "chirp_graph",
    "chirp_timeline",
    "chirp_search",
    "chirp_notification",
    "chirp_messaging",
    "chirp_media",
    "chirp_moderation",
  ]

  services = {
    gateway      = { port = 8000, db = false, worker = false }
    auth         = { port = 8001, db = true, worker = false }
    user         = { port = 8002, db = true, worker = true }
    post         = { port = 8003, db = true, worker = true }
    graph        = { port = 8004, db = true, worker = false }
    timeline     = { port = 8005, db = true, worker = true }
    search       = { port = 8006, db = true, worker = true }
    notification = { port = 8007, db = true, worker = true }
    messaging    = { port = 8008, db = true, worker = false }
    media        = { port = 8009, db = true, worker = false }
    moderation   = { port = 8010, db = true, worker = false }
  }

  service_urls = {
    for name, svc in local.services :
    upper(name) => "http://${name}-svc.chirp-${local.environment}.svc.cluster.local:${svc.port}"
    if name != "gateway"
  }
}
