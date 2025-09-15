name = "kitsu"
title = "Kitsu"
version = "1.2.6"
client_dir = "ayon_kitsu"

services = {
    "processor": {"image": f"artifactory.lesta.io:443/vcg-docker/ayon-kitsu-processor:{version}"},
}

ayon_required_addons = {
    "core": ">=0.3.0",
}
ayon_compatible_addons = {}
