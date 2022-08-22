const express = require('express');

const io = require('socket.io-client');
const socket = io('http://tick.edcd.io:31173');

var tick;

socket.on('tick', (data)=>console.log(`new tick at ${data}`));
socket.on('message', (data)=>{console.log(data);tick=data});

