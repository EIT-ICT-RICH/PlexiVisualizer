__author__ = 'Frank'

import socketserver
import threading
import hashlib
import base64
import os
import json
import time
from os import listdir
from os.path import isfile, join
import argparse
import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from os.path import splitext, basename
import mimetypes
import sys

connectedclients = {}
connectedSchedulers = {}
client_schedulers = {}#key: client identity, value: list of requested schedulers
scheduler_clients = {}#key: scheduler identity, value: list of sockets that listen to this scheduler
scheduler_frames = {
	"aaaa::215:8d00:57:6466" : ["Broadcast-Frame", "Unicast-Frame"]
}#key: scheduler identity, value: list of framenames
users = {}#key: username, value: dict: password: password of user, schedulers: list of allowed schedulers

def chunks(l, n):
	#Yield successive n-sized chunks from l
	for i in range(0, len(l), n):
		yield l[i:i+n]

class Cell():
	def __init__(self, nodeid, localid, frame, status, empty=False):
		self._nodeid = nodeid.strip("[").split("]")[0].split(":")[-1]
		self._localid = localid
		self._frame = frame
		self._empty = empty
		self._status = status

	@property
	def nodeid(self):
		return self._nodeid

	@property
	def localid(self):
		return self._localid

	@property
	def frame(self):
		return self._frame

	#based on: 0:available 1:used 2: blacklisted
	@property
	def status(self):
		return self._status

	def __str__(self):
		if not self._empty:
			if self._status == 0:
				return "Not Used"
			else:
				return "Node:" + self._nodeid + "<br>frame:" + self._frame + "<br>localid:" + self._localid
		else:
			return "Emtpy cell"

class ThreadedServerHandler(socketserver.BaseRequestHandler):

	def handle(self):
		addr = self.request.getpeername()[0]
		self.data = self.request.recv(1024)
		request = str(self.data, "utf-8")
		# print("request:\n" + request)
		if "Upgrade: websocket" in request or "Upgrade: Websocket" in request:

			self.HandShake(request)
			self.client = "web"

			#get the identity
			data = self.parse_frame()
			userdata = {}
			try:
				userdata = json.loads(str(data, "utf-8"))
			except:
				print("problem with login package from " + str(addr))

			self.identity = userdata["name"]
			if self.identity not in users:
				print("Wrong login for user " + self.identity + " from " + str(addr))
				self.send(self.request, "WRONG")
				return

			if users[self.identity]["password"] != userdata["password"]:
				print("Wrong login for user " + self.identity + " from " + str(addr))
				self.send(self.request, "WRONG")
				return

			#crossreference the scheduler list with the allowed list
			schedulers = list(set(userdata["schedulers"].split(";")) & set(users[self.identity]["schedulers"]))
			#register the client
			connectedclients[self.identity] = self
			# #register the requested schedulers
			# data = str(self.parse_frame(), "utf-8")
			# print("requested schedulers: ")
			# print(userdata[2])
			client_schedulers[self.identity] = schedulers
			for shd in client_schedulers[self.identity]:
				try:
					scheduler_clients[shd].append(self)
				except:
					scheduler_clients[shd] = []
					scheduler_clients[shd].append(self)
			self.send(self.request,"OK")
			#TODO: multiple schedulers support for the frame streaming
			#send the frames for the scheduler (only the first one is supported atm
			frames = scheduler_frames[schedulers[0]]
			self.send(self.request,json.dumps(frames))
			#wait for requests
			print("New connection(webclient): " + self.identity)
			while True:
				try:
					data = self.parse_frame()
					if data == "":
						continue
					data = str(data, "utf-8")
					commands = []
					try:
						commands = json.loads(data)
					except:
						print("Client from "  + self.identity + " sended invalid json: \n" + data)
					if commands[0] == "$REQUESTHISTORY":
						packet = {}
						for scheduler in commands[1]:
							if not os.path.exists("snapshots/" + scheduler.split(":")[-1]):
								print("Client from " + self.identity + " requested history of unkown scheduler: " + scheduler)
								continue
							path = "snapshots/" + scheduler.split(":")[-1]
							files = [ f for f in listdir(path) if isfile(join(path,f)) ]
							files = [int(i.strip(".dot")) for i in files]
							packet[scheduler] = files
						#because the json parser in javascript is facking retarded we add a placeholder item to the dictionary
						packet["foo"] = []
						self.send(self.request, json.dumps(packet))
					elif commands[0] == "$REQUESTGRAPH":
						file = "snapshots/" + commands[1].split(":")[-1] + "/" + str(commands[2]) + ".dot"
						if not os.path.exists(file) or not os.path.isfile(file):
							print("Client from " + self.identity + " requested non existing graph: " + file)
							continue
						with open(file, "r") as stream:
							dotfile = stream.read()
						self.send(self.request, json.dumps([commands[1] + "at: " + datetime.datetime.fromtimestamp(int(commands[2])).strftime('%Y-%m-%d %H:%M:%S'),dotfile]))
					else:
						print("Client from " + self.identity + " issued unkown command: " + commands[0])
				except:
					print("\nClient from " + self.identity + " disconnected")
					return
		else:
			#register this scheduler
			self.client = "scheduler"
			self.frames = {}
			connectedSchedulers[request] = self
			self.identity = request
			if self.identity not in scheduler_clients:
				scheduler_clients[self.identity] = []
			self.identity = request
			print("New connection(scheduler): " + self.identity)
			self.folder = "snapshots/" + self.identity.split(":")[-1]
			if not os.path.exists(self.folder):
				os.makedirs(self.folder)
			data = str(self.request.recv(1024), "utf-8")
			jsondata = json.loads(data)
			scheduler_frames[self.identity] = []
			#create matrix with empty cells
			for framedata in jsondata:
				self.frames[framedata["id"]] = []
				scheduler_frames[self.identity].append(framedata["id"])
				#TODO: send update of these frames to clients
				#TODO: dynamic sending off ammount of cells to the client (currently hardcoded to 25)
				for y in range(0, 16):
					self.frames[framedata["id"]].append([])
					for x in range(0, framedata["cells"]):
						self.frames[framedata["id"]][y].append(Cell("","","", 0,empty=True))

			while True:
				data = str(self.request.recv(1024), "utf-8")
				if data == "":
					continue
				print("data received:")
				print(data)
				#check if data is dotfile or json
				jsondata = json.loads(data)
				if jsondata[0] == "changecell":
					cell = jsondata[1]
					#channels are on y axis slots are on x axis
					#change the cell in the correct frame, this overwrites any possible existing cells
					newcell = Cell(cell["who"], cell["id"], cell["frame"], cell["status"])
					self.frames[cell["frame"]][cell["channeloffs"]][cell["slotoffs"]] = newcell
					#package to be send to observers
					#[y, x, description, status]
					package = json.dumps([[cell["channeloffs"],cell["slotoffs"]], cell["frame"],str(newcell), newcell.status])
					print(package)
					#send it to all observers
					for client in scheduler_clients[self.identity]:
						self.send(client.request, package, t=1)
				else:
					#its a dotfile
					#for each listener, send the dot file
					print("dotfile received")
					# info = json.loads(data)
					with open(self.folder + "/" + str(int(time.time())) + ".dot", "w") as stream:
						stream.writelines(jsondata[1])
					for client in scheduler_clients[self.identity]:
						self.send(client.request, data)

	def HandShake(self, request):
		specificationGUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
		websocketkey = ""
		protocol = ""
		for line in request.split("\r\n"):
			if "Sec-WebSocket-Key:" in line:
				websocketkey = line.split(" ")[1]
			elif "Sec-WebSocket-Protocol" in line:
				protocol = line.split(":")[1].strip().split(",")[0].strip()
			elif "Origin" in line:
				self.origin = line.split(":")[0]

		# print("websocketkey: " + websocketkey + "\n")
		fullKey = hashlib.sha1(websocketkey.encode("utf-8") + specificationGUID.encode("utf-8")).digest()
		acceptKey = base64.b64encode(fullKey)
		# print("acceptKey: " + str(acceptKey, "utf-8") + "\n")
		if protocol != "":
			handshake = "HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Protocol: " + protocol + "\r\nSec-WebSocket-Accept: " + str(acceptKey, "utf-8") + "\r\n\r\n"
		else:
			handshake = "HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: " + str(acceptKey, "utf-8") + "\r\n\r\n"
		# print(handshake.strip("\n"))
		self.request.send(bytes(handshake, "utf-8"))

	#t: 0= sending of graph stuff 1=sending of matrix updates
	def send(self, socket, data, t=0):
		if t == 0:
			print("sending data: " + data)
			if len(data) < 126:
				socket.sendall(self.create_frame(data))
				return
			c = chunks(data, 125)
			socket.sendall(self.create_frame("$STARTGRAPH"))
			for co in c:
				socket.sendall(self.create_frame(co))
			socket.sendall(self.create_frame("$ENDGRAPH"))
		elif t == 1:
			print("sending data: " + data)
			if len(data) < 126:
				socket.sendall(self.create_frame("$STARTMATRIXUPDATE"))
				socket.sendall(self.create_frame(data))
				socket.sendall(self.create_frame("$ENDMATRIXUPDATE"))
				return
			c = chunks(data, 125)
			socket.sendall(self.create_frame("$STARTMATRIXUPDATE"))
			for co in c:
				socket.sendall(self.create_frame(co))
			socket.sendall(self.create_frame("$ENDMATRIXUPDATE"))


	def create_frame(self, data):
		# pack bytes for sending to client
		frame_head = bytearray(2)

		# set final fragment
		frame_head[0] = self.set_bit(frame_head[0], 7)

		# set opcode 1 = text
		frame_head[0] = self.set_bit(frame_head[0], 0)

		# payload length
		# assert len(data) < 126, "haven't implemented that yet"
		frame_head[1] = len(data)

		# add data
		frame = frame_head + data.encode('utf-8')
		# print("frame crafted for message " + data + ":")
		# print(list(hex(b) for b in frame))
		return frame

	def is_bit_set(self, int_type, offset):
		mask = 1 << offset
		return not 0 == (int_type & mask)

	def set_bit(self, int_type, offset):
		return int_type | (1 << offset)

	def bytes_to_int(self, data):
		# note big-endian is the standard network byte order
		return int.from_bytes(data, byteorder='big')

	def parse_frame(self):
		"""receive data from client"""
		s = self.request
		# read the first two bytes
		frame_head = s.recv(2)

		# very first bit indicates if this is the final fragment
		# print("final fragment: ", self.is_bit_set(frame_head[0], 7))

		# bits 4-7 are the opcode (0x01 -> text)
		# print("opcode: ", frame_head[0] & 0x0f)

		# mask bit, from client will ALWAYS be 1
		assert self.is_bit_set(frame_head[1], 7)

		# length of payload
		# 7 bits, or 7 bits + 16 bits, or 7 bits + 64 bits
		payload_length = frame_head[1] & 0x7F
		if payload_length == 126:
			raw = s.recv(2)
			payload_length = self.bytes_to_int(raw)
		elif payload_length == 127:
			raw = s.recv(8)
			payload_length = self.bytes_to_int(raw)
		# print('Payload is {} bytes'.format(payload_length))

		#masking key
		#All frames sent from the client to the server are masked by a
		#32-bit nounce value that is contained within the frame

		masking_key = s.recv(4)
		# print("mask: ", masking_key, self.bytes_to_int(masking_key))

		# finally get the payload data:
		masked_data_in = s.recv(payload_length)
		data = bytearray(payload_length)

		# The ith byte is the XOR of byte i of the data with
		# masking_key[i % 4]
		for i, b in enumerate(masked_data_in):
			data[i] = b ^ masking_key[i%4]
		return data

class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
	pass

class httpRequestHandler(BaseHTTPRequestHandler):

	def do_GET(self):
		allowedtypes = [".html", ".css", ".js"]
		# origin = self.request.getpeername()[0]
		# rootdir = "D:/PycharmProjects/Kolibri_Chat/http"
		filetype =  splitext(basename(self.path))[1].split("?")[0]
		rootdir = "http"
		if filetype not in allowedtypes and filetype != "":
			self.send_response(403)
			# Print("Client from " + origin + " asked for forbidden file " + self.path)
			return

		if self.path == "/":
			filepath = rootdir + "/index.html"
			filetype = ".html"
		else:
			filepath = rootdir + self.path.split("?")[0]

		try:
			stream = open(filepath, 'rb')
		except IOError:
			# Print("GET request to nonexisting file " + self.path + " from client " + origin)
			self.send_response(404)
			return

		self.send_response(200)
		try:
			mime = mimetypes.types_map[filetype]
		except:
			mime = 'application/octet-stream'
		self.send_header('content-type', mime)
		self.end_headers()
		self.wfile.write(stream.read())
		stream.close()
		# Print("GET request to file " + self.path + " answered to client " + origin)
		return


	def do_POST(self):
		self.send_response(403)
		# ctype, pdict = cgi.parse_header(self.headers.getheader('content-type'))
		# if ctype == 'multipart/form-data':
		# 	postvars = cgi.parse_multipart(self.rfile, pdict)
		# elif ctype == 'application/x-www-form-urlencoded':
		# 	length = int(self.headers.getheader('content-length'))
		# 	postvars = cgi.parse_qs(self.rfile.read(length), keep_blank_values=1)
		# else:
		# 	postvars = {}
		return

	def log_message(self, format, *args):
		pass
		# sys.stderr.write("%s - - [%s] %s\n" %
		# 				 (self.address_string(),
		# 				  self.log_date_time_string(),
		# 				  format%args))

def ReadDatabase():
	try:
		database = open("users.txt", "r")
		count = 0
		for line in database:
			count += 1
			parts = line.split("$")
			users[parts[0]] = {
				"password" : parts[1],
				"schedulers" : parts[2].split(";")
			}
			# users.append([line.split(" ")[0].strip("\n"), line.split(" ")[1], int(line.split(" ")[2]), int(line.split(" ")[3].strip("\n"))])
		database.close()
		print("read "+str(count)+" users from file to database")

	except:
		print("ERROR: failed reading database, server will now exit")
		time.sleep(1)
		database.close()
		sys.exit()

if __name__ == "__main__":
	parser = argparse.ArgumentParser(description="FrankFancyGraphStreamer to be used with RiSCHER scheduler")
	parser.add_argument('--ip', nargs='?', const=1, type=str, default="localhost", help="ip which the server will bind to")
	ReadDatabase()
	print("booting StreamServer and http server")
	HOST = parser.parse_args().ip
	PORT = 600
	if not os.path.exists("snapshots"):
		os.makedirs("snapshots")
	server = ThreadedTCPServer((HOST, PORT), ThreadedServerHandler)
	server_thread = threading.Thread(target=server.serve_forever)
	server_thread.daemon = True
	server_thread.start()
	print("StreamServer running at " + str(PORT) + ", waiting for connections...")
	mimetypes.init()
	server_address = (HOST, 80)
	server = HTTPServer(server_address, httpRequestHandler)
	print("http server is running at " + server_address[0] + ":" + str(server_address[1]))
	server.serve_forever()
