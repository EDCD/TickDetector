/*
 * Copyright © 2018 Phelbore <phelbore@gmail.com>
 * This work is free. You can redistribute it and/or modify it under the
 * terms of the Do What The Fuck You Want To Public License, Version 2,
 * as published by Sam Hocevar. See http://www.wtfpl.net/ for more details.
 */

const Database = require('better-sqlite3');
const moment = require('moment');
const path = require('path');
const clustering = require('density-clustering');

const express = require('express');
const app = express();
const http = require('http').Server(app);

const cors = require('cors');
app.use(cors())

const router = express.Router();

const io = require('socket.io')(http, {
	cors: {
		origin: true,
		methods: ["GET", "POST", "OPTIONS"],
		transports: ["websocket", "polling"]
	},
	allowEIO3: true
});

const port = 9001;
const db = new Database('systems.sqlitedb');
const json2html = require('node-json2html');

const util = require('util');

var lock = false;

config();
http.listen(port, () => {
	console.log("Socket.IO server running at http://localhost:${port}/");
});

console.log('Tick Publisher started');

function config() {
//Express
	configAPI();

//Socket.io
	io.on('connection', (socket) => {
		console.log(`New connection: ${moment().format()} - ${socket.client.conn.remoteAddress}`);
		socket.send(getLastTick());
	}
	);

//Periodic
	let freshness = 14400;
	let threshold = 5;
	let delta = 7500;
	calculateTicks(freshness, threshold, delta);
	setInterval(calculateTicks, 60000, freshness, threshold, delta);
}

function configAPI() {
	// Handle OPTIONS for Cors queries
	// Ref: <http://johnzhang.io/options-request-in-express>
	app.options('/*', function(req, res, next) {
		res.header('Access-Control-Allow-Origin', '*');
		res.header('Access-Control-Allow-Methods', 'GET,POST,OPTIONS');
		res.header('Access-Control-Allow-Headers', 'Content-Type, Content-Length, X-Requested-With');
		res.send(200);
	}
	)

	app.get('/', (req, res) => res.sendFile(path.join(__dirname,'tick.html')));
	app.get('/allTicks', (req, res) => res.sendFile(path.join(__dirname,'allTicks.html')));
	app.get('/license', (req, res) => res.sendFile(path.join(__dirname,'LICENSE')));
	app.use('/api', router);

	router.get('/testTicks', (req, res) => {
		let freshness = req.query['freshness']?req.query['freshness']:7200;
		let threshold = req.query['threshold']?req.query['threshold']:5;
		let delta = req.query['delta']?req.query['delta']:1800;
		let ticks = allTicks(freshness, threshold, delta);
		if(req.query['table']) {
			let transform = {
				'tag':'tr',
					children: [{
					'tag':'td',
						'html':'${start}'
				},{
					'tag':'td',
						'html':'${detected}'
				},{
					'tag':'td',
						'html':'${size}'
			},{
					'tag':'td',
						'html':'${delay}'
			}]
		};
			let header='<tr><th>Start</th><th>Detected</th><th>Count</th><th>Delay</th></tr>';
			res.send(`<table border=1>${header}${json2html.transform(ticks, transform)}</table>`);
		} else {
			res.json(ticks);
		}
	});

	router.get('/ticks', (req, res) => {
		let start = req.query['start']?req.query['start']:'2014-12-16';
		let end = req.query['end']?req.query['end']:new Date();
		res.json(getTicks(start, end));
	});

	router.get('/tick', (req, res) => {
		res.json(getLastTick());
	});
}

function getLastTick() {
	let tickSql = `SELECT TIME FROM TICK ORDER BY TIME DESC LIMIT 1`;
	let rs = db.prepare(tickSql).get();
	if(rs && rs.TIME) {
		return rs.TIME;
	} 
}

function calculateTicks(freshness, threshold, delta) {
	if(lock) {
		return;
	}
	let runStart = new moment();

	lock = true;

	let getTimesSql = `SELECT DISTINCT SYSTEM, FIRST_SEEN, DELTA FROM INFLUENCE
		WHERE DATETIME(FIRST_SEEN) >= DATETIME(?) 
		AND INFLUENCE > 0 AND DELTA IS NOT NULL AND DELTA <= ${freshness}`;

	let start = moment().subtract(1, 'month').format('YYYY-MM-DDTHH:mm:ssZ');

	let lastTick = getLastTick();
	if(lastTick) {
		start = moment(lastTick).format('YYYY-MM-DDTHH:mm:ssZ');
	}

	let data = [];
 
	let timesRS = db.prepare(getTimesSql).all(start);
	if(Array.isArray(timesRS) && timesRS.length) {
		for(let i in timesRS) {
			data.push([moment(timesRS[i].FIRST_SEEN).format('X')]);
		}
	}

	let dbscan = new clustering.DBSCAN();
	let clusters = dbscan.run(data,delta,threshold);

	let noise = dbscan.noise;
	for(let i in clusters) {
		let sorted = clusters[i].map(x => data[x]).sort();
		let size = sorted.length;
		let start = new moment(sorted[0],'X');
		let end = new moment(sorted[size-1],'X');
		let detected = new moment(sorted[threshold-1],'X');
		if(i >= 1)  {
			console.log(`Tick - ${start.format('YYYY-MM-DD HH:mm:ss')} - ${detected.format('YYYY-MM-DD HH:mm:ss')} - ${size} items`);
			io.sockets.emit('tick', start.format('YYYY-MM-DDTHH:mm:ssZ'));
			io.sockets.send(start.format('YYYY-MM-DDTHH:mm:ssZ'));
			for(let s in io.sockets['sockets']) {
				console.log(io.sockets['sockets'][s]['conn']['remoteAddress']);
			}
		}
		saveTick(start);
	}
	let runEnd = new moment();
	setTimeout(()=>{lock = false;}, 30000);
}

function saveTick(time) {
	let tickSql = 'INSERT INTO TICK(TIME) VALUES(?)';

	db.prepare(tickSql).run(moment(time).format('YYYY-MM-DDTHH:mm:ssZ'));

}

function getTicks(start, end) {
	start = moment(start).format('YYYY-MM-DD');
	end = moment(end).format('YYYY-MM-DD');
	let tickSql = `SELECT TIME FROM TICK WHERE DATE(TIME) BETWEEN ? and ?`;
	let ticks = db.prepare(tickSql).all(start, end);
	return ticks;
}


function allTicks(freshness, threshold, delta) {
	let getTimesSql = `SELECT DISTINCT SYSTEM, FIRST_SEEN, DELTA FROM INFLUENCE
		WHERE INFLUENCE > 0 AND DELTA <= ${freshness}`;

	let data = [];
	let allTicks = [];
 
	let timesRS = db.prepare(getTimesSql).all();
	if(Array.isArray(timesRS) && timesRS.length) {
		for(let i in timesRS) {
			data.push([moment(timesRS[i].FIRST_SEEN).format('X')]);
		}
	}

	let dbscan = new clustering.DBSCAN();
	let clusters = dbscan.run(data,delta,threshold);

	let counter = 0;
	let noise = dbscan.noise;
	for(let i in clusters) {
		let sorted = clusters[i].map(x => data[x]).sort();
		let size = sorted.length;
		let start = new moment(sorted[0],'X');
		let end = new moment(sorted[size-1],'X');
		let detected = new moment(sorted[threshold-1]?sorted[threshold-1]:sorted[size-1],'X');
		let tick = {};
		tick['start'] = start.format('YYYY-MM-DD HH:mm:ss');
		tick['detected'] = detected.format('YYYY-MM-DD HH:mm:ss');
		tick['size'] = size;
		tick['delay'] = detected.diff(start,'minutes');
		allTicks.push(tick);
		counter++;
	}
	return(allTicks);
}

