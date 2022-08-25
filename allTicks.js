
const Database = require('better-sqlite3');
const moment = require('moment');
const path = require('path');
const clustering = require('density-clustering');
const db = new Database('database/systems.db');

const util = require('util');

calculateTicks();

function calculateTicks() {
	let freshness = 14400;
	let threshold = 5;
	let delta = 7500;
	
	let getTimesSql = `SELECT DISTINCT SYSTEM, FIRST_SEEN, DELTA FROM INFLUENCE
		WHERE INFLUENCE > 0 AND DELTA <= ${freshness}`;

	let data = [];
 
	let timesRS = db.prepare(getTimesSql).all();
	if(Array.isArray(timesRS) && timesRS.length) {
		for(let i in timesRS) {
			data.push([moment(timesRS[i].FIRST_SEEN).format('X')]);
		}
		console.log(`Scanning ${timesRS.length} items`);
	}

	let dbscan = new clustering.DBSCAN();
	let clusters = dbscan.run(data,delta,threshold);

	let noise = dbscan.noise;
	for(let i in clusters) {
		let sorted = clusters[i].map(x => data[x]).sort();
		let size = sorted.length;
		let start = new moment(sorted[0],'X');
		let end = new moment(sorted[size-1],'X');
		let detected = new moment(sorted[threshold-1]?sorted[threshold-1]:sorted[size-1],'X');
		if(i >= 1)  {
			console.log(`Tick - ${start.format('YYYY-MM-DD HH:mm:ss')} - ${detected.format('YYYY-MM-DD HH:mm:ss')} - ${size} items`);
		}
	}
}

