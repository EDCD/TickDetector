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

socket = io(process.argv[2])

socket.on('message', (data) => {
	console.log(`[message]: ${data}`);
})

