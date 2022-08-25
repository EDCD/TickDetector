/*
 * Copyright © 2018 Phelbore <phelbore@gmail.com>
 * This work is free. You can redistribute it and/or modify it under the
 * terms of the Do What The Fuck You Want To Public License, Version 2,
 * as published by Sam Hocevar. See http://www.wtfpl.net/ for more details.
 */

const Database = require('better-sqlite3');
const zlib = require('zlib');
const request = require('request');
const moment = require('moment');
const path = require('path');
const db = new Database('database/systems.db');

const util = require('util');

var lock = false;

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
	lock = true;
	clearInterval(interval_getEntries);
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

const thanks = ['Garud',
									'Lyrae Cursorius']

config();
console.log('EDDN Processor (detector) started');

function config() {
	interval_getEntries = setInterval(getEntries, 1000);
}

function getEntries() {
	if(lock) {
		return;
	}

	lock = true;
	let selectSql = `SELECT ROW, TIMESTAMP, GW_TIMESTAMP, SOFTWARE, VERSION, MESSAGE FROM RAW ORDER BY ROW ASC LIMIT 10`;
	let deleteSql = `DELETE FROM RAW WHERE ROW IN (?)`;
	let countSql = `SELECT COUNT(ROW) AS COUNT FROM RAW`;
	let results = db.prepare(selectSql).all();
	let rowIDs = '';
	for(let i in results) {
		parseEntry(JSON.parse(results[i].MESSAGE));
		rowIDs = `${rowIDs},${results[i].ROW}`;
	}
	if(rowIDs) {
		rowIDs = rowIDs.slice(1);
		deleteSql = `DELETE FROM RAW WHERE ROW IN (${rowIDs})`;
		db.exec(deleteSql);
	}
	lock = false;
}

function parseEntry(entry) {
	timer = Date.now();
  if(entry.$schemaRef == 'https://eddn.edcd.io/schemas/journal/1') {
		let systemID = entry.message.SystemAddress;
		let systemName = entry.message.StarSystem;
		let systemX = entry.message.StarPos[0];
		let systemY = entry.message.StarPos[1];
		let systemZ = entry.message.StarPos[2];
		let factions = entry.message.Factions;
		if(systemID && systemName && factions && systemX && systemY && systemZ) {
			let mTime = moment(entry.message.timestamp);
			let dTime = moment(entry.header.gatewayTimestamp).diff(mTime, 'seconds');

			addSystem(systemID, systemName, systemX, systemY, systemZ);
			if(dTime < 6000 && mTime) {
				for(let i in entry.message.Factions) {
					let faction = entry.message.Factions[i];
					if(faction.Influence>0) {
						setInfluence(systemID, faction.Name, faction.Influence, mTime.format());
					}
				}
			}
		}
	}
}

function setInfluence(systemID, faction, influence, time) {
	let getInfluenceSql = `SELECT ROWID, SYSTEM, FACTION, INFLUENCE, FIRST_SEEN, LAST_SEEN 
		FROM INFLUENCE WHERE SYSTEM = ? AND FACTION = ? AND INFLUENCE = ? 
		ORDER BY FIRST_SEEN DESC LIMIT 7`;
	
	let setInfluenceSql = `INSERT INTO INFLUENCE(SYSTEM, FACTION, INFLUENCE, FIRST_SEEN, LAST_SEEN, COUNT) 
		VALUES(?, ?, ?, ?, ?, 1)`;
	
	let updateInfluenceSql = `UPDATE INFLUENCE SET FIRST_SEEN = ?, LAST_SEEN = ?, COUNT = COUNT +1, DELTA = null WHERE ROWID = ?`;

	let influences = db.prepare(getInfluenceSql).all(systemID, faction, influence);
	if(Array.isArray(influences) && influences.length) {
		let current_first_seen = influences[0].FIRST_SEEN;
		for(let i in influences) {
			let record = influences[i];
			let first = record.FIRST_SEEN;
			let last = record.LAST_SEEN;
			let row = record.ROW;
			let diff = moment(last).diff(time, 'seconds');
			if(i == 0 && diff > 0) {
				db.prepare(updateInfluenceSql).run(first, time, row);
				updateDelta(systemID, faction);
			}
		}
	} else {
		db.prepare(setInfluenceSql).run(systemID, faction, influence, time, time);
		updateDelta(systemID, faction);
	}
}

function updateDelta(systemID, faction) {
	let influencesSql = `SELECT ROW, FACTION, INFLUENCE, FIRST_SEEN, LAST_SEEN FROM INFLUENCE WHERE
		INFLUENCE > 0 AND SYSTEM = ? AND FACTION = ? ORDER BY FIRST_SEEN DESC`;
	let updateDeltaSql = `UPDATE INFLUENCE SET DELTA = ? WHERE ROW = ?`;

	let influences = db.prepare(influencesSql).all(systemID, faction);
	if(Array.isArray(influences) && influences.length && influences.length > 1) {
		for(let j = influences.length-1; j >= 1; j--) {
			let delta = new moment(influences[j-1].FIRST_SEEN).diff(influences[j].LAST_SEEN, 'seconds');
			db.prepare(updateDeltaSql).run(delta, influences[j-1].ROW);
		}
	}
}

function addSystem(systemID, systemName, systemX, systemY, systemZ) {
	let sql = `SELECT ID FROM SYSTEMS WHERE ID=? AND NAME=?`;
	
	let result = db.prepare(sql).get(systemID, systemName);
	if(!(result && result.ID)) {
		let insertSql = `INSERT INTO SYSTEMS (ID, NAME, X, Y, Z) VALUES(?, ?, ?, ?, ?)`;
		db.prepare(insertSql).run(systemID, systemName, systemX, systemY, systemZ);
	}
}

