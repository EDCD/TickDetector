# Use of Docker for this project

## Configuration
There is both a `Dockerfile` for building the container images, and a 
`docker-compose.yaml` file for actually running them.

This means that you should definitely be using `docker compose` commands,
not plain `docker` ones.   You might have to install the Docker `compose`
plugin in order to have the sub-command available.

### Overriding configuration
For some things where you need custom configuration relevant to your
Docker host you will *not* need to edit either `Dockerfile` or
`docker-compose.yaml`, instead you can utilise a
`docker-composr.override.yaml` file.

For example, to tweak the network configuration you might use:

```yaml
version: '3'

networks:
  default:
    ipam:
      config:
        - subnet: 172.16.2.0/24
    driver_opts:
      # Must be no more than ppp0's MTU
      com.docker.network.driver.mtu: 1492
```
This nails the networking down to a specific subnet (rather than a
random one chosen from the Docker host's range), and ensures the MTU is
set appropriately for the upstream WAN link.

## Using on Debian bullseye

This was all developed using docker.com's own Debian APT repository,
starting with `20.10.17` versions.

If you try to use the Debian bullseye `docker.io` and `docker-compose`
packages, which are based on version 1.25.0, things will likely either
not work at all, or not as described in this document.

To set up the APT repository consult the
[upstream instructions](https://docs.docker.com/engine/install/debian/#set-up-the-repository).

## Hints

### Building the image

`docker compose build`

### Starting and stopping the containers

After a build you will want:

    docker compose up -d

To stop them:

    docker compose stop

and then to start them again, without a rebuild:

    docker compose start

Note that you can stop/start individual containers if desired.

### Checking output logs

To check latest logs from all containers:

    docker compose logs

Or if you only want a specific container:

1. `docker compose ps` - to get be sure of the container name, it's in
   the `SERVICE` column.
1. `docker compose logs <container name>`.

