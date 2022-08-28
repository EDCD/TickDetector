# EDCD Background Galaxy Simulation Tick Service

This document describes the available API endpoints of the EDCD service
that detects the Elite Dangerous "Background Galaxy Simulation" ticks.

## WebSocket
The preferred method for anyone interested in ticks is to utilise the
provided [WebSocket](https://en.wikipedia.org/wiki/WebSocket)
.  The advantage to this is that you learn the currently
latest known tick at connection time and then will receive a `'message'`
with a new tick's time as soon as it is detected.  No need for polling.

### URL
Due to how WebSockets work you simply use the URL https://tick.edcd.io/
as the endpoint to connect to.  The details of how WebSockets work cause
this to function correctly, even though going to that URL with a browser
will also work.

### Functionality 
1. Upon initial connection you will receive a plain text
  [ISO 8601](https://en.wikipedia.org/wiki/ISO_8601#Combined_date_and_time_representations)
  format timestamp citing the time of the latest known tick, e.g.
  `2022-08-27T16:14:49+00:00`.
2. Subsequently when a new tick is detected you will receive two events,
  both of which contain the same plain text ISO 8601 timestamp format
  as at startup.
    1. `'message'`
    2. `'tick'`

    Why the two events?  Because this was designed specifically for the
  web page.  The `'message'` is for both the initial display of latest tick,
  *and also* for updating that on a new tick.

    But, the `'tick'` event specifically triggers a web browser 'alert'
  pop-up when a new tick happens, which does not happen at page load.

    So, feel free to just ignore the `'tick'` events if they're not useful
  to your use case.

## API
The code also provides a more general API for retrieving data about both
the latest and historical ticks.

This is currently purposefully not documented.  Use the WebSocket.
