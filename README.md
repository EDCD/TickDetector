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

1. It provides the https://tick.edcd.io/ web page, which will display the
  latest tick known and alert if a new tick is detected.
1. It provides an API for either retrieving all known ticks, or displaying
  them in a web page.  Interested parties can either utilise this API or
  simply connect directly to the [WebSocket](#web-socket]).

#### Web Socket
As part of providing the main web page `tick.js` provides a Web Socket
which will receive a `'message'` when there is a new tick.

This socket is provided on the standard HTTP/HTTPS port, using whichever
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
