# Elite Dangerous BGS Tick Detector

Originally by [Phelbore](https://github.com/phelbore), cloned from
[Phelbore's original repo](https://github.com/phelbore/TickDetector/).

## Running this project
This is a [NodeJS](https://nodejs.org/) project, so you'll need a version
of `node` installed.  `npm` is also required.

On `tick.edcd.io` we run the latest 18.x versions by utilising the
[nodesource repositories](https://nodesource.com/blog/installing-node-js-tutorial-debian-linux/).

It will be useful to have `sqlite3` installed such that you have access
to its command-line tool.

`tick.edcd.io` runs the services in Docker containers, please see
[docs/Docker.md](docs/Docker.md) for more information.

Due to this use of Docker no attempt has been made to have `npm start` do
anything useful.  You will, instead, need to run each [component](#Components)
directly via, e.g. `node EDDN.js`.

### Components
There are three components, all necessary for this project to actually
function fully and correctly.

#### EDDN.js
This attaches to the EDDN Relay stream, checking for any `journal/1` schema
messages, and those with the applicable data get added as a new row to the
`RAW` table of the database.

'Applicable data' is, in practice, going to be picking up on `Location`,
`FSDJump` or `CarrierJump` events.  (But note that at time of writing
the `CarrierJump` event in Odyssey is actually written as a `Location` event,
which does no harm as the data they contain is of the same form.)

NB: This is where any problematic `softwarename` and/or `softwareVersion`s
thereof might be ignore.

#### detector.js
This checks periodically (once a second) for any rows in the `RAW` table
and processes the data into the `SYSTEMS` and `INFLUENCE` tables.

This includes a basic "age of the data" check, utilising the message
`timestamp` versus the `gatewaytimestamp` that was added by the EDDN Gateway.
Anything older than 6000 seconds (100 minutes) is discarded.

#### tick.js
This checks periodically (once a minute) for signs of a new tick.  This is
the guts of the overall tick detection and the algorithm used is beyond
the scope of this document at this time.

- It utilises the `density-clustering` package.

When it thinks it has found a new tick it will insert a new row into
the `TICK` table.

**This is also** responsible for serving data about ticks to interested
parties:

1. It provides a [Web Socket API](#web-socket-api) for direct connections.
1. It provides a simple web page, in turn using the Web Socket API, to display the latest tick and alert if a new tick is detected.
1. It provides an [HTTP API](#http-api) for fetching information about the latest tick and previous ticks, with simple filtering.

## API Reference

### Web Socket API
As part of providing the main web page `tick.js` provides a Web Socket
which will receive a `'message'` when there is a new tick.

This socket is provided on the standard HTTP/HTTPS port, using whichever URI
the page `tick.html` page was loaded on.  As such it is necessary for the
WebSocket to be passed through any reverse proxy you have in front of the
service.

For Apache2 you will need the `rewrite` and `proxy_wstunnel` modules
loaded (along with any dependencies, i.e. `proxy`, `proxy_http`) and then
something like:

```apache2
        <IfModule mod_proxy.c>
                SSLProxyEngine On
                SSLProxyVerify none
                ProxyPreserveHost On
                ProxyRequests Off

                <ifModule mod_rewrite.c>
                        <Location /socket.io>
                                require all granted
                        </Location>

                        RewriteEngine On
                        # LogLevel alert rewrite:trace8

                        RewriteCond %{HTTP:Upgrade} websocket [NC]
                        RewriteRule "^(/.*)$" "ws://localhost:9001$1" [P,L]

                        RewriteCond %{HTTP:Upgrade} !=websocket [NC]
                        RewriteRule "^(/.*)$" "http://localhost:9001$1" [P,L]

                        ProxyPass "/" "http://localhost:9001/"
                        ProxyPassReverse "/" "http://localhost:9001/"

                        ProxyPass "/socket.io" "ws://localhost:9001/socket.io"
                        ProxyPassReverse "/socket.io" "ws://localhost:9001/socket.io"

                </IfModule>

        </IfModule>

```
The `/socket.io` path comes from the Web Socket itself.

If you're using nginx then consult
[nginx websocket documentation](https://nginx.org/en/docs/http/websocket.html).

You *can* instead adjust `tick.html` and `tick.js` to run the WebSocket on
a separate port, but then you'll also need to adjust both `Dockerfile` and
`docker-compose.yml` to expose that extra port, along with possibly needing
to allow that extra port through any firewall you have.

### HTTP API

#### tick

Get the latest tick time as a single JSON string.

* **URL**: `/api/tick`

* **Method**: `GET`

* **URL Params**: None

* **Success Response**: `200 OK`
  **Example Content**: `"2022-10-10T17:04:17+00:00"`

* **Sample Call**:

  `curl https://<domain>/api/tick`

* **Notes**: The format of the timestamp in the response is ISO 8601 date/time, with numeric timezone suffix which is always UTC (`+00:00`).

#### ticks

Get a range of tick times between a given start and end date as a JSON formatted array of objects.

* **URL**: `/api/ticks`

* **Method**: `GET`

* **URL Params**:

  * `start`: `yyyy-mm-dd` - default value: `2014-12-16`
  * `end`: `yyyy-mm-dd` - default value: _Today's date_

* **Success Response**: `200 OK`
  **Example Content**: `[{"TIME":"2022-10-01T16:50:46+00:00"},{"TIME":"2022-10-02T17:06:26+00:00"},{"TIME":"2022-10-03T16:59:29+00:00"},{"TIME":"2022-10-04T17:01:14+00:00"}]`

* **Sample Call**:

  `curl https://<domain>/api/ticks?start=2022-10-01&end=2022-10-03`

* **Notes**:

  The response JSON is a list of objects. Each object contains a single key, `TIME` and the value is a timestamp in ISO 8601 format, with numeric timezone suffix which is always UTC (`+00:00`).


## Hosted Service

The TickDetector is also provided by the EDCD project as a hosted service for public consumption on the tick.edcd.io domain:

* https://tick.edcd.io/ - Simple web page showing latest tick, and using the web socket to alert to new ticks.
* https://tick.edcd.io/ - Web Socket for live event-based connection.
* https://tick.edcd.io/api/ - HTTP API

