/*
 * Copyright © 2018 Phelbore <phelbore@gmail.com>
 * This work is free. You can redistribute it and/or modify it under the
 * terms of the Do What The Fuck You Want To Public License, Version 2,
 * as published by Sam Hocevar. See http://www.wtfpl.net/ for more details.
 */

const Database = require('better-sqlite3');
const zlib = require('zlib');
const zmq = require('zeromq');
const sock = zmq.socket('sub');
const request = require('request');
const moment = require('moment');
const path = require('path');
const db = new Database('systems.sqlitedb');

const util = require('util');

/* Handle signals for clean shutdowns
 * List of signals
 */
var shutdown_signals = {
	'SIGHUP': 1,
	'SIGINT': 2,
	'SIGTERM': 15
};

const shutdown = (signal, value) => {
	console.log("Shutting down...");

	// Perform necessary cleanup
	sock.close();
	db.close();

	console.log("Exiting.");
	process.exit(128 + value);
};

// Create a listener for each signal
Object.keys(shutdown_signals).forEach((signal) => {
	process.on(signal, () => {
		console.log(`process received "shutdown" ${signal} signal`);
		shutdown(signal, shutdown_signals[signal]);
	});
});

var msgStats = ['1', '5', '10', '15', '30', '60', 
					'120', '180', '240', '300', '360',
					'420', '480', '540', '600'];
var lock = false;
var timer = Date.now();

const thanks = ['Garud',
									'Lyrae Cursorius'];

config();
console.log('EDDN Listener started');

function config() {
	sock.setsockopt(zmq.ZMQ_RCVHWM, 50);
	eddnConnector();
	setInterval(function () {
		if ((Date.now() - timer) > 120000) {
				request('http://hosting.zaonce.net/launcher-status/status.json', function(err, res, body) {
					try {
						if(JSON.parse(body).status == 2) {
							console.log(`${moment().format()} EDDN DOWN`);
						}
					} catch(err) {
						console.log(`Error parsing ${body}: ${err}`);
					}
				});
			timer = Date.now();
		}
	});
}

function eddnConnector() {
	sock.connect('tcp://eddn.edcd.io:9500');
	sock.subscribe('');
	sock.on('close', (fd, ep) => {setTimeout(eddnConnector(), 60000)});
	sock.on('close_error', (fd, ep) => {setTimeout(eddnConnector(), 60000)});
	sock.on('disconnect', (fd, ep) => {setTimeout(eddnConnector(), 60000)});
	sock.on('message', topic=> {
		try {
			storeEntry(zlib.inflateSync(topic));
		} catch (err) {}
	});
}

function storeEntry(entry) {
	timer = Date.now();
	let parsed = null;
	try {
		parsed = JSON.parse(entry);
	} catch(err) {
		console.log(`err`);
	}

	if(parsed && parsed.header.SoftwareName == 'EDDiscovery') {
		return; // Banning EDDiscovery due to their cavalier attitude towards sending bad data.
						// https://discord.com/channels/164411426939600896/419456725075099648/827919387443986442
	}

  if(parsed && parsed.$schemaRef == 'https://eddn.edcd.io/schemas/journal/1') {
		let systemID = parsed.message.SystemAddress;
		let systemName = parsed.message.StarSystem;
		let systemX = parsed.message.StarPos[0];
		let systemY = parsed.message.StarPos[1];
		let systemZ = parsed.message.StarPos[2];
		let factions = parsed.message.Factions;
		if(systemID && systemName && factions && systemX && systemY && systemZ) {
			let mTime = moment(parsed.message.timestamp);
			let gwTime = moment(parsed.header.gatewayTimestamp);
			let dTime = moment(gwTime).diff(mTime, 'seconds');

			updateStats(dTime, parsed.header.softwareName, parsed.header.softwareVersion);
			if(dTime < 6000 && parsed.message.timestamp && parsed.header.gatewayTimestamp) {
				let sql = `INSERT INTO RAW (TIMESTAMP, GW_TIMESTAMP, SOFTWARE, VERSION, MESSAGE) VALUES(?, ?, ?, ?, ?)`;
				db.prepare(sql).run(parsed.message.timestamp, parsed.header.gatewayTimestamp, parsed.header.softwareName, parsed.header.softwareVersion, entry);
			}
		}
	}
}

function updateStats(dTime, name, version) {
	let msgCountSql = `UPDATE MSG_STATS SET COUNT = COUNT + 1 WHERE ROWID = 1`;
	let msgOldestSql = `UPDATE MSG_STATS SET OLDEST = ? WHERE ROWID = 1`;
	
	let softwareCountSql = `INSERT INTO SOFTWARE(SOFTWARE, VERSION, COUNT) VALUES(?, ?, 1) 
													ON CONFLICT(SOFTWARE, VERSION) DO UPDATE SET COUNT=COUNT+1;`;

	var oldest = db.prepare('SELECT OLDEST FROM MSG_STATS WHERE ROWID = 1').get().OLDEST;

	db.prepare(softwareCountSql).run(name, version);

	for (let i in msgStats)  {
		let delay = msgStats[i];
		if(Math.abs(dTime) <= delay*60) {
			let msgDelaySql = `UPDATE MSG_STATS SET '${delay}' = MSG_STATS.'${delay}' + 1 WHERE ROWID = 1`;
			db.prepare(msgDelaySql).run();
		}
	}

	db.prepare(msgCountSql).run();
	if(dTime>oldest) {
		db.prepare(msgOldestSql).run(dTime);
	}
}

