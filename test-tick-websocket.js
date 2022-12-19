/* 
 * Simple script to test if the websocket is working, including through
 * any reverse proxy with SSL.
 *
 * Usage: <this script> <URL of web socket>
 * 
 *	node test-tick-websocket.js wss://tick.edcd.io
 *
 *
 * It bares noting that despite using the WebSocket protocol the actual
 * socket in this case has the socket.io protocol on top of that.  Thus
 * a bare WebSocket connection **will not work**.
 *
 * When it works output should be like:
 *
 * 	[message]: 2022-12-18T13:20:50+00:00
 *
 * the datetimestamp is that of the last detected tick.  If you keep it
 * running then you should get an additional message when the next tick
 * is detected.
 *
 */

/*
 *  You will need to have done:
 *
 *  	npm install socket.io-client
 */
const { io } = require("socket.io-client")

// Check we were passed a URL
if (process.argv.length != 3) {
	console.log(`Usage: ${process.argv[1]} <URL of socket.io websocket>`)
	console.log('')
	console.log('  NB: "bare" URL not including ANY path.')
	return
}
url = process.argv[2]

console.log(`Attempting to connect to: ${url}`)
socket = io(url)

socket.on('message', (data) => {
	console.log(`[message]: ${data}`);
})

