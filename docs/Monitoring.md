# Monitoring the TickDetector services

If you're serious about running this project then you will, of course, want
to have its services monitored to be sure nothing has broken.

## Icinga2

In its incarnation as `tick.edcd.io` this service has been monitored using
[icinga2](https://icinga.com/), through manual configuration, not using its
'directory'.

There should be a sub-directory where this file is `icinga2/` which contains
various support files for this monitoring.

### Check Docker containers are running

There is a copy of the nagios/icinga plugin `check_docker_container.py` from
[BlackZork's plugin](https://exchange.icinga.com/BlackZork/check_docker_container)
.  This should be copied into an appropriate location, i.e.
`/usr/local/lib/nagios/plugins/`.  Be sure to adjust permissions as
necessary.

The icinga2 command for utilising this is defined in
`command_docker_container.conf`, which should be copied into, e.g.
`/etc/icinga2/commands.conf.d/` (anywhere under `/etc/icinga2/` will suffice,
but as this is a generic command it probably shouldn't go in a host-specific
sub-directory).

The relevant icinga2 host should have:

```
  vars.docker_containers = [
    "tickdetectorgit-eddn-1",
    "tickdetectorgit-detector-1",
    "tickdetectorgit-tick-1"
  ]
```
or other appropriate Docker container names.

The relevant icinga2 services file should have:

```
apply Service for (container_name in host.vars.docker_containers) {
  import "generic-service"
  check_command = "docker_container"

  vars.docker_container_name = container_name
}
```

### Check the services are receiving and processing data

Two checks are provided to monitor if the services are managing to pick up
new data from EDDN and process it.

#### Sqlite3 database file is being written to

`check_file_freshness.py` is a nagios/icinga plugin that will check how old
the 'modification time' of a file is.  Again, this should be placed in an
appropriate nagios/icinga `../plugins/` directory.

The definition of this is still generic enough to also be used for other
icinga2 monitoring, so `command_file_freshness.conf` can also go into
`/etc/icinga2/commands.conf.d/`.

Host configuration is, e.g.:
```
  vars.file_freshness = [
    "/home/tick/live/TickDetector.git/database/systems.db"
  ]
```

Service configuration is:
```
apply Service for (file_name in host.vars.file_freshness) {
  import "generic-service"
  check_command = "file_freshness"

  vars.file_freshness_name = file_name
  vars.file_freshness_warning = 900
  vars.file_freshness_critical = 1800
}
```
This will be 'OK' if the file exists and was updated more recently than 15
minutes ago, 'WARNING' if updated between 15 and 30 minutes ago, and
'CRITICAL' if updated 30 minutes or more ago.

Fifteen minutes was chosen because it should cope well with the weekly game
downtime on Thursdays without causing spurious alerts, but still alert
reasonably quickly to actual problems.  Thirty minutes was chosen as simply
being twice that.

#### Age of most recent 'INFLUENCE' update

`command_bgstick_sqlite_influence.conf` is a nagios/icinga plugin that
checks the `LAST_SEEN` value of the newest `INFLUENCE` row against the
current time.  Again, this should be placed in an appropriate nagios/icinga
`../plugins/` directory.


  This is specific to this project, so `command_bgstick_sqlite_influence.conf`
probably go into a relevant host sub-directory of `/etc/icinga2/`.

Host configuration is:
```
vars.bgstick_sqlite_influence = "true"
```

Service configuration is:
```
// Monitor the age of the newest 'INFLUENCE' data
apply Service "bgstick_sqlite_influence" {
  import "generic-service"
  check_command = "bgstick_sqlite_influence"

  vars.bgstick_sqlite_influence_filename = "/home/tick/live/TickDetector.git/database/systems.db"
  vars.bgstick_sqlite_influence_warning = 900
  vars.bgstick_sqlite_influence_critical = 1800

  assign where (host.vars.bgstick_sqlite_influence == "true")
}
```
NB: Yes, we had to repeat the sqlite3 database file name here, because you
can't key more than one service off the same value in icinga2.

Again this uses 15/30 minutes as the Warning/Critical thresholds.
